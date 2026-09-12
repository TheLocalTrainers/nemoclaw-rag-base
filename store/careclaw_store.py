"""MongoDB-backed operational store for CareClaw.

Replaces the flat `audit_logs/pending_reviews.jsonl` and
`audit_logs/careclaw_events.jsonl` files with three collections in a dedicated
`careclaw` database (separate from the `nemoclaw_rag` corpus db on the same
Mongo instance):

    patients  — one doc per patient (demographics + protocol enrollment)
    cases     — one doc per intake case (replaces pending_reviews.jsonl)
    events    — append-only agent/PI event log (replaces careclaw_events.jsonl)

The Mongo URI/timeout are read from `rag.config` so configuration stays
centralized; the connection fails fast with a clear error when Mongo is
unreachable (mirrors rag.store.RagStore).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from rag.config import Config, load_config

STATUS_NEEDS_REVIEW = "NEEDS_PI_REVIEW"
STATUS_SIGNED = "SIGNED"
STATUS_DISMISSED = "DISMISSED"

EVENT_ENQUEUED = "CASE_ENQUEUED"
EVENT_SIGNED = "CASE_SIGNED"
EVENT_DISMISSED = "CASE_DISMISSED"

# Projection that drops Mongo's ObjectId so results are JSON-serializable.
_NO_ID = {"_id": 0}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CareClawStore:
    """Persist and query patients, intake cases, and the event log in MongoDB."""

    def __init__(
        self,
        uri: str | None = None,
        *,
        config: Config | None = None,
    ) -> None:
        self.config = config or load_config()
        mongo = self.config.mongodb
        cc = self.config.careclaw
        self.uri = (uri or mongo.uri).strip()
        self.database_name = cc.database.strip()
        try:
            self._client: MongoClient = MongoClient(
                self.uri,
                serverSelectionTimeoutMS=mongo.server_selection_timeout_ms,
            )
            # Fail fast if Mongo is unreachable (same contract as RagStore).
            self._client.admin.command("ping")
        except PyMongoError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                f"CareClaw store could not reach MongoDB at {self.uri!r}. "
                f"Start it with `make mongo-up`. Underlying error: {exc}"
            ) from exc

        db = self._client[self.database_name]
        self._patients: Collection = db[cc.patients_collection]
        self._cases: Collection = db[cc.cases_collection]
        self._events: Collection = db[cc.events_collection]
        self._care_team: Collection = db[cc.care_team_collection]
        # Patient (study-subject) ePRO submissions — vitals/symptoms/observations.
        self._patient_reports: Collection = db["patient_reports"]
        self._ensure_indexes()

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CareClawStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _ensure_indexes(self) -> None:
        self._patients.create_index([("patient_id", ASCENDING)], unique=True, name="patient_id_unique")
        self._cases.create_index([("case_id", ASCENDING)], unique=True, name="case_id_unique")
        self._cases.create_index([("status", ASCENDING), ("created_at", DESCENDING)], name="status_created")
        self._events.create_index([("ts", DESCENDING)], name="ts_desc")
        self._events.create_index([("event", ASCENDING), ("ts", DESCENDING)], name="event_ts")
        self._care_team.create_index([("user_id", ASCENDING)], unique=True, name="user_id_unique")
        self._patient_reports.create_index(
            [("patient_id", ASCENDING), ("submitted_at", DESCENDING)], name="patient_submitted"
        )
        self._patient_reports.create_index([("report_id", ASCENDING)], unique=True, name="report_id_unique")

    # ------------------------------------------------------------------ #
    # patients
    # ------------------------------------------------------------------ #
    def upsert_patient(self, patient: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a patient by `patient_id`."""
        patient_id = patient.get("patient_id")
        if not patient_id:
            raise ValueError("patient must include a 'patient_id'")
        doc = dict(patient)
        doc.setdefault("updated_at", _utc_now_iso())
        self._patients.update_one(
            {"patient_id": patient_id},
            {"$set": doc, "$setOnInsert": {"created_at": _utc_now_iso()}},
            upsert=True,
        )
        return self._patients.find_one({"patient_id": patient_id}, _NO_ID) or doc

    def get_patient(self, patient_id: str) -> dict[str, Any] | None:
        return self._patients.find_one({"patient_id": patient_id}, _NO_ID)

    def list_patients(self) -> list[dict[str, Any]]:
        """All patients, stable order by `patient_id` (for the registry table)."""
        return list(self._patients.find({}, _NO_ID).sort([("patient_id", ASCENDING)]))

    def remove_patient(self, patient_id: str) -> bool:
        """Delete a patient by `patient_id`. Returns True if a doc was removed."""
        result = self._patients.delete_one({"patient_id": patient_id})
        return result.deleted_count > 0

    def count_patients(self) -> int:
        return int(self._patients.count_documents({}))

    # ------------------------------------------------------------------ #
    # care team (the demo actors: coordinator / PI / monitor)
    # ------------------------------------------------------------------ #
    def upsert_user(self, user: dict[str, Any]) -> dict[str, Any]:
        """Insert or update a care-team member by `user_id` (e.g. the role key)."""
        user_id = user.get("user_id")
        if not user_id:
            raise ValueError("user must include a 'user_id'")
        doc = dict(user)
        doc.setdefault("updated_at", _utc_now_iso())
        self._care_team.update_one(
            {"user_id": user_id},
            {"$set": doc, "$setOnInsert": {"created_at": _utc_now_iso()}},
            upsert=True,
        )
        return self._care_team.find_one({"user_id": user_id}, _NO_ID) or doc

    def list_users(self) -> list[dict[str, Any]]:
        """Care-team members ordered by their `order` field (stable UI ordering)."""
        return list(self._care_team.find({}, _NO_ID).sort([("order", ASCENDING)]))

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        return self._care_team.find_one({"user_id": user_id}, _NO_ID)

    def count_users(self) -> int:
        return int(self._care_team.count_documents({}))

    # ------------------------------------------------------------------ #
    # cases
    # ------------------------------------------------------------------ #
    def _unique_case_id(self, case_id: str) -> str:
        """Return case_id, suffixing -2, -3, … if it already exists.

        Intake can be run repeatedly against the same fixtures (e.g. the demo
        `intake/sample`), which would otherwise collide on the deterministic
        case_id. Keeping ids unique lets the PI queue select/sign each case
        unambiguously while preserving the clean id for the first (seed) case.
        """
        if self._cases.count_documents({"case_id": case_id}, limit=1) == 0:
            return case_id
        n = 2
        while self._cases.count_documents({"case_id": f"{case_id}-{n}"}, limit=1) > 0:
            n += 1
        return f"{case_id}-{n}"

    def enqueue_case(self, case: dict[str, Any]) -> dict[str, Any]:
        """Insert an intake case with status NEEDS_PI_REVIEW and a created_at."""
        doc = dict(case)
        base_id = doc.get("case_id") or f"CASE-{_utc_now_iso()}"
        doc["case_id"] = self._unique_case_id(base_id)
        doc["status"] = doc.get("status") or STATUS_NEEDS_REVIEW
        doc["created_at"] = _utc_now_iso()
        self._cases.insert_one(doc)
        return self.get_case(doc["case_id"]) or {k: v for k, v in doc.items() if k != "_id"}

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        return self._cases.find_one({"case_id": case_id}, _NO_ID)

    def get_case_by_report_id(self, report_id: str) -> dict[str, Any] | None:
        """Find an existing case generated from a given ePRO report_id (for idempotency)."""
        return self._cases.find_one({"report_id": report_id}, _NO_ID)

    def load_pending_cases(self) -> list[dict[str, Any]]:
        """Cases awaiting PI review, newest first."""
        cursor = self._cases.find({"status": STATUS_NEEDS_REVIEW}, _NO_ID).sort(
            [("created_at", DESCENDING), ("_id", DESCENDING)]
        )
        return list(cursor)

    def list_cases(self) -> list[dict[str, Any]]:
        """All intake cases (any status), newest first — the document history."""
        cursor = self._cases.find({}, _NO_ID).sort([("created_at", DESCENDING), ("_id", DESCENDING)])
        return list(cursor)

    def set_case_status(self, case_id: str, status: str) -> dict[str, Any] | None:
        self._cases.update_one(
            {"case_id": case_id},
            {"$set": {"status": status, "updated_at": _utc_now_iso()}},
        )
        return self.get_case(case_id)

    def set_case_narrative(
        self,
        case_id: str,
        narrative: str,
        *,
        narrative_source: str | None = None,
        narrative_model: str | None = None,
    ) -> dict[str, Any] | None:
        """Persist a 3500A draft back onto the case (PI edit or async LLM upgrade).

        When `narrative_source`/`narrative_model` are given (the background LLM
        upgrade path), they are recorded too so the case reflects that its prose
        is now model-written.
        """
        fields: dict[str, Any] = {"draft_narrative": narrative, "updated_at": _utc_now_iso()}
        if narrative_source is not None:
            fields["narrative_source"] = narrative_source
        if narrative_model is not None:
            fields["narrative_model"] = narrative_model
        self._cases.update_one({"case_id": case_id}, {"$set": fields})
        return self.get_case(case_id)

    def count_cases(self, status: str | None = None) -> int:
        query = {} if status is None else {"status": status}
        return int(self._cases.count_documents(query))

    # ------------------------------------------------------------------ #
    # events
    # ------------------------------------------------------------------ #
    def append_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Append an event to the immutable log with a UTC ISO `ts`."""
        doc = dict(event)
        doc.setdefault("ts", _utc_now_iso())
        self._events.insert_one(doc)
        return {k: v for k, v in doc.items() if k != "_id"}

    def list_events(self, event: str | None = None) -> list[dict[str, Any]]:
        query = {} if event is None else {"event": event}
        return list(self._events.find(query, _NO_ID).sort([("ts", DESCENDING), ("_id", DESCENDING)]))

    def list_signed_events(self) -> list[dict[str, Any]]:
        return self.list_events(EVENT_SIGNED)

    def count_events(self, event: str | None = None) -> int:
        query = {} if event is None else {"event": event}
        return int(self._events.count_documents(query))

    # ------------------------------------------------------------------ #
    # patient reports (study-subject ePRO submissions)
    # ------------------------------------------------------------------ #
    def submit_patient_report(self, report: dict[str, Any]) -> dict[str, Any]:
        """Insert a patient ePRO submission with a generated id + UTC ISO timestamp.

        Returns the stored document (without Mongo's `_id`). The caller is
        expected to have already attached vitals/symptoms/observations and,
        optionally, a `triage` result computed by `web.patient_triage`.
        """
        doc = dict(report)
        doc.setdefault("submitted_at", _utc_now_iso())
        doc.setdefault("report_id", f"RPT-{uuid.uuid4().hex[:12].upper()}")
        self._patient_reports.insert_one(doc)
        return {k: v for k, v in doc.items() if k != "_id"}

    def set_report_triage(
        self, report_id: str, triage: dict[str, Any], summary: str | None = None
    ) -> dict[str, Any] | None:
        """Persist the deterministic triage result (and optional concern summary) on a report."""
        fields: dict[str, Any] = {"triage": triage}
        if summary is not None:
            fields["concern_summary"] = summary
        self._patient_reports.update_one({"report_id": report_id}, {"$set": fields})
        return self._patient_reports.find_one({"report_id": report_id}, _NO_ID)

    def list_patient_reports(self, patient_id: str) -> list[dict[str, Any]]:
        """A subject's report history, newest first."""
        cursor = self._patient_reports.find({"patient_id": patient_id}, _NO_ID).sort(
            [("submitted_at", DESCENDING), ("_id", DESCENDING)]
        )
        return list(cursor)

    def latest_patient_report(self, patient_id: str) -> dict[str, Any] | None:
        cursor = self._patient_reports.find({"patient_id": patient_id}, _NO_ID).sort(
            [("submitted_at", DESCENDING), ("_id", DESCENDING)]
        ).limit(1)
        docs = list(cursor)
        return docs[0] if docs else None

    def count_reports(self, patient_id: str | None = None) -> int:
        query = {} if patient_id is None else {"patient_id": patient_id}
        return int(self._patient_reports.count_documents(query))

    # ------------------------------------------------------------------ #
    # aggregate stats (mirrors the old JSONL compute_stats)
    # ------------------------------------------------------------------ #
    def compute_stats(self) -> dict[str, int]:
        pending = self.load_pending_cases()
        total_deviations = sum(len(c.get("deviations") or []) for c in pending)
        critical = sum(
            1
            for c in pending
            for d in (c.get("deviations") or [])
            if str(d.get("severity", "")).upper() == "CRITICAL"
        )
        severe_labs = sum(
            1
            for c in pending
            for lab in (c.get("lab_findings") or [])
            if lab.get("is_severe")
        )
        return {
            "pending": len(pending),
            "deviations": total_deviations,
            "critical": critical,
            "severe_labs": severe_labs,
            "signed": self.count_events(EVENT_SIGNED),
        }

    # ------------------------------------------------------------------ #
    # demo maintenance
    # ------------------------------------------------------------------ #
    def reset_demo(self) -> None:
        """Clear all CareClaw collections (patients, cases, events, care_team, patient_reports)."""
        self._patients.delete_many({})
        self._cases.delete_many({})
        self._events.delete_many({})
        self._care_team.delete_many({})
        self._patient_reports.delete_many({})


def open_store(
    *,
    uri: str | None = None,
    config: Config | None = None,
) -> CareClawStore:
    return CareClawStore(uri=uri, config=config)
