"""CareClaw PI Review Console — FastAPI backend.

Serves a light-mode single-page clinician review gateway and a small JSON API
over MongoDB — the single source of truth the OpenClaw daemon writes to:

    careclaw.cases    ← intake cases (status NEEDS_PI_REVIEW / SIGNED / DISMISSED)
    careclaw.events   ← CASE_ENQUEUED / CASE_SIGNED / CASE_DISMISSED (append-only)
    careclaw.patients ← one doc per patient (demographics + enrollment)

No cloud egress. Signing reuses SafetyClaw's 21 CFR Part 11 audit record so the
cryptographic lock is identical to the Streamlit path.

Run:  uvicorn web.server:app --reload --port 8010
      (or:  python -m web.server)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents.safety_claw import SafetyClaw
from daemon.watcher import OpenClawFileWatcher
from store.careclaw_store import (
    EVENT_DISMISSED,
    EVENT_SIGNED,
    STATUS_DISMISSED,
    STATUS_NEEDS_REVIEW,
    STATUS_SIGNED,
    CareClawStore,
)
from web import llm_client, narrative_llm, patient_triage, report_claw

# Resolve project root so the app works regardless of the CWD it is launched from.
ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"

DEFAULT_SIGNER = "PI-DR-VANCE-MD"

app = FastAPI(title="CareClaw PI Review Console", version="1.0.0")

# One shared MongoDB-backed store for the app process (fails fast if Mongo down).
_store: CareClawStore | None = None


def get_store() -> CareClawStore:
    global _store
    if _store is None:
        _store = CareClawStore()
    return _store


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@app.get("/api/queue")
def get_queue() -> JSONResponse:
    store = get_store()
    return JSONResponse(
        {
            "pending": store.load_pending_cases(),
            "stats": store.compute_stats(),
            "signer": DEFAULT_SIGNER,
        }
    )


@app.get("/api/signed")
def get_signed() -> JSONResponse:
    # Newest first (list_signed_events already sorts by ts descending).
    return JSONResponse({"signed": get_store().list_signed_events()})


@app.get("/api/users")
def get_users() -> JSONResponse:
    """Care-team roster (the demo actors), served from MongoDB."""
    return JSONResponse({"users": get_store().list_users()})


@app.get("/api/cases")
def get_cases() -> JSONResponse:
    """All intake documents (any status) — the assistant's document history."""
    return JSONResponse({"cases": get_store().list_cases()})


# --------------------------------------------------------------------------- #
# Patient Registry — roster of enrolled subjects (add/edit/remove)
#
# Role-access is enforced in the frontend (consistent with the rest of the app —
# there is no server-side auth): the Study Coordinator can add/remove; the PI and
# Clinical Monitor see the registry read-only; the study subject has no access.
# --------------------------------------------------------------------------- #
class PatientPayload(BaseModel):
    patient_id: str
    phase: str | None = "Phase 1"
    site: str | None = None
    age: int | None = None
    sex: str | None = None
    diagnosis: str | None = None
    enrollment_status: str | None = None


@app.get("/api/patients")
def get_patients() -> JSONResponse:
    """All patients, each annotated with their latest case status (via list_cases)."""
    store = get_store()
    # Map patient_id -> latest case status (list_cases is newest-first, so the
    # first hit per patient is the most recent case).
    latest_status: dict[str, str] = {}
    for case in store.list_cases():
        pid = (case.get("patient_meta") or {}).get("patient_id")
        if pid and pid not in latest_status:
            latest_status[pid] = case.get("status")

    rows = []
    for p in store.list_patients():
        pid = p.get("patient_id")
        rows.append(
            {
                "patient_id": pid,
                "phase": p.get("phase") or "Phase 1",
                "site": p.get("site"),
                "enrollment_status": p.get("enrollment_status"),
                "age": p.get("age"),
                "sex": p.get("sex"),
                "diagnosis": p.get("diagnosis"),
                "case_status": latest_status.get(pid),
            }
        )
    return JSONResponse({"patients": rows})


@app.post("/api/patients")
def create_patient(p: PatientPayload) -> JSONResponse:
    store = get_store()
    if not p.patient_id or not p.patient_id.strip():
        raise HTTPException(status_code=400, detail="patient_id is required.")
    patient_id = p.patient_id.strip()
    if store.get_patient(patient_id) is not None:
        raise HTTPException(status_code=409, detail=f"Patient '{patient_id}' already exists.")
    doc = {
        "patient_id": patient_id,
        "phase": p.phase or "Phase 1",
        "site": p.site,
        "age": p.age,
        "sex": p.sex,
        "diagnosis": p.diagnosis,
        "enrollment_status": p.enrollment_status,
    }
    saved = store.upsert_patient(doc)
    return JSONResponse({"patient": saved})


@app.delete("/api/patients/{patient_id}")
def delete_patient(patient_id: str) -> JSONResponse:
    store = get_store()
    if not store.remove_patient(patient_id):
        raise HTTPException(status_code=404, detail=f"Patient '{patient_id}' not found.")
    return JSONResponse({"ok": True})


@app.get("/api/assistant/status")
def assistant_status() -> JSONResponse:
    """Whether the local vLLM drafting assistant is reachable right now."""
    return JSONResponse(llm_client.status())


@app.post("/api/sign/{case_id}")
def sign_case(case_id: str) -> JSONResponse:
    store = get_store()
    case = store.get_case(case_id)
    if case is None or case.get("status") != STATUS_NEEDS_REVIEW:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not in queue.")

    safety = SafetyClaw(meddra_path=ROOT / "configs/clinical/meddra_mini.json")
    narrative = case.get("draft_narrative") or ""
    audit = safety.generate_part11_audit_record(narrative, clinician_id=DEFAULT_SIGNER)

    store.set_case_status(case_id, STATUS_SIGNED)
    store.append_event(
        {
            "event": EVENT_SIGNED,
            "case_id": case.get("case_id"),
            "status": audit["status"],
            "patient_meta": case.get("patient_meta"),
            "deviations": case.get("deviations"),
            "lab_findings": case.get("lab_findings"),
            "draft_narrative": narrative,
            "audit_record": audit,
        }
    )
    return JSONResponse({"audit": audit})


# --------------------------------------------------------------------------- #
# Narrative drafting assistant — PI iterates on the 3500A with the local vLLM
# --------------------------------------------------------------------------- #
ASSISTANT_SYSTEM = (
    "You are CareClaw's regulatory drafting assistant. You help a Principal Investigator "
    "iterate on a pre-drafted FDA MedWatch 3500A / CIOMS I expedited adverse-event safety "
    "narrative for an oncology clinical trial. Follow these rules strictly:\n"
    "1. Keep every clinical fact consistent with the CASE DATA provided. Never invent labs, "
    "doses, dates, or events.\n"
    "2. NEVER assert, imply, or fill in causality (relatedness to the study drug) or the final "
    "action taken with the drug — those are the PI's determination and must remain blank/pending.\n"
    "3. Use precise, professional clinical and regulatory language suitable for an FDA filing.\n"
    "4. When the PI asks for a revision, reply with the FULL revised narrative so it can replace "
    "the current draft. When the PI asks a question, answer concisely.\n"
)


class ChatTurn(BaseModel):
    role: str
    content: str


class NarrativeChatPayload(BaseModel):
    case_id: str
    messages: list[ChatTurn] = []
    draft: str | None = None


class NarrativeSavePayload(BaseModel):
    draft: str


def _case_context(case: dict, draft: str) -> str:
    meta = case.get("patient_meta") or {}
    devs = case.get("deviations") or []
    labs = case.get("lab_findings") or []
    dev_lines = "\n".join(
        f"  - {d.get('category')} [{d.get('severity')}] {d.get('protocol_section', '')}: {d.get('details', '')}"
        for d in devs
    ) or "  (none)"
    lab_lines = "\n".join(
        f"  - {l.get('analyte')}: {l.get('value')} ({l.get('uln_multiple')}) — {l.get('ctcae_grade')}"
        for l in labs
    ) or "  (none)"
    return (
        f"CASE DATA (do not contradict):\n"
        f"Patient {meta.get('patient_id')} · {meta.get('age')}{(meta.get('sex') or '')[:1]} · "
        f"Study Day {meta.get('study_day')} · Protocol {meta.get('protocol_id')}\n"
        f"Protocol deviations:\n{dev_lines}\n"
        f"Graded labs:\n{lab_lines}\n\n"
        f"CURRENT DRAFT NARRATIVE (the document being iterated):\n{draft}"
    )


@app.post("/api/narrative/chat")
def narrative_chat(p: NarrativeChatPayload) -> JSONResponse:
    store = get_store()
    case = store.get_case(p.case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case '{p.case_id}' not found.")
    draft = p.draft if p.draft is not None else (case.get("draft_narrative") or "")

    convo = [{"role": "system", "content": ASSISTANT_SYSTEM},
             {"role": "system", "content": _case_context(case, draft)}]
    convo += [{"role": t.role, "content": t.content} for t in p.messages if t.content.strip()]
    if not any(t.role == "user" for t in p.messages):
        raise HTTPException(status_code=400, detail="No user message to respond to.")

    try:
        reply = llm_client.chat(convo, temperature=0.3, max_tokens=3072)
        return JSONResponse({"reply": reply, "available": True})
    except llm_client.LLMUnavailable as exc:
        return JSONResponse(
            {
                "reply": (
                    "The local drafting assistant (Qwen on vLLM) isn't reachable right now — "
                    "it may be restarting. Your draft is unchanged; try again in a moment."
                ),
                "available": False,
                "reason": str(exc),
            }
        )


@app.post("/api/narrative/{case_id}")
def save_narrative(case_id: str, p: NarrativeSavePayload) -> JSONResponse:
    """Persist a PI-iterated 3500A draft back onto the (still-pending) case."""
    store = get_store()
    case = store.get_case(case_id)
    if case is None or case.get("status") != STATUS_NEEDS_REVIEW:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not open for editing.")
    updated = store.set_case_narrative(case_id, p.draft)
    return JSONResponse({"ok": True, "case": updated})


# --------------------------------------------------------------------------- #
# Intake — UI-driven record drop (replaces the daemon + drop script for demos)
# --------------------------------------------------------------------------- #
class IntakePayload(BaseModel):
    note_name: str | None = None
    note_text: str | None = None
    labs_name: str | None = None
    labs_json: dict | None = None


def _new_watcher() -> OpenClawFileWatcher:
    return OpenClawFileWatcher(
        watch_dir=ROOT / "incoming_records",
        processed_dir=ROOT / "processed_records",
        audit_dir=ROOT / "audit_logs",
    )


def _build_activity(case: dict, source_files: list[str]) -> list[dict]:
    deviations = case.get("deviations") or []
    labs = case.get("lab_findings") or []
    symptoms = case.get("symptoms_mapped") or []
    severe = [l for l in labs if l.get("is_severe")]
    dev_detail = ", ".join(d.get("category", "") for d in deviations) or "no deviations"
    return [
        {
            "agent": "OpenClaw",
            "role": "Always-on sentinel",
            "text": f"Received {', '.join(source_files)}",
            "detail": "Paired note + labs into one case." if len(source_files) > 1 else "Single-file intake.",
        },
        {
            "agent": "ProtocolClaw",
            "role": "Deviation sentinel",
            "text": f"Identified {len(deviations)} protocol deviation(s)",
            "detail": dev_detail,
        },
        {
            "agent": "SafetyClaw",
            "role": "FDA 3500A scribe",
            "text": f"Graded {len(labs)} lab(s) · {len(severe)} severe · mapped {len(symptoms)} MedDRA term(s)",
            "detail": "Drafted FDA Form 3500A zero-draft (causality left blank).",
        },
        {
            "agent": "Queue",
            "role": "Handoff",
            "text": f"Queued for PI review · {case.get('case_id')}",
            "detail": "Status NEEDS_PI_REVIEW — awaiting a physician signature.",
        },
    ]


def _intake_upgrade_enabled() -> bool:
    return os.environ.get("INTAKE_LLM_UPGRADE", "1").lower() not in ("0", "false", "no")


def _run_intake_llm_upgrade_bg(case_id: str) -> None:
    """BackgroundTask: async LLM review of an uploaded intake case.

    Intake enqueues a fast DETERMINISTIC case (activity shows in ~2s). This worker
    runs AFTER the response is sent: it asks Qwen to rewrite the 3500A prose from
    the case's own findings, persists it (narrative_source→llm), and publishes a
    NARRATIVE_UPGRADED event. Fail-soft — the deterministic draft always stands if
    the model is down. Deterministic findings/grades are never touched.
    """
    store = get_store()
    try:
        case = store.get_case(case_id)
        if not case or case.get("status") != STATUS_NEEDS_REVIEW:
            return  # signed/dismissed before the upgrade ran — leave it
        llm_narrative, model = narrative_llm.generate_3500a_narrative(
            case.get("patient_meta") or {},
            case.get("deviations") or [],
            case.get("lab_findings") or [],
            case.get("symptoms_mapped") or [],
            case.get("draft_narrative") or "",
        )
        store.set_case_narrative(
            case_id, llm_narrative, narrative_source="llm", narrative_model=model
        )
        store.append_event(
            {
                "event": "NARRATIVE_UPGRADED",
                "case_id": case_id,
                "patient_id": (case.get("patient_meta") or {}).get("patient_id"),
                "narrative_source": "llm",
                "narrative_model": model,
            }
        )
        print(f"    [✓] Qwen upgraded 3500A narrative for {case_id} (async).")
    except narrative_llm.LLMUnavailable as exc:
        print(f"    [i] Intake LLM upgrade skipped for {case_id} ({exc}); deterministic draft stands.")
    except Exception as exc:  # noqa: BLE001 - fail soft; never crash the worker
        print(f"    [i] Intake LLM upgrade errored for {case_id} ({exc}); deterministic draft stands.")


@app.post("/api/intake")
def intake(p: IntakePayload, background_tasks: BackgroundTasks) -> JSONResponse:
    if not (p.note_text and p.note_text.strip()) and not p.labs_json:
        raise HTTPException(status_code=400, detail="Provide a clinical note and/or a lab panel.")
    source_files: list[str] = []
    if p.note_name:
        source_files.append(p.note_name)
    if p.labs_name:
        source_files.append(p.labs_name)
    if not source_files:
        source_files = ["ui-intake"]

    case = _new_watcher()._enqueue_case(
        note_content=p.note_text or "",
        lab_data=p.labs_json or {},
        source_files=source_files,
    )
    if _intake_upgrade_enabled():
        background_tasks.add_task(_run_intake_llm_upgrade_bg, case["case_id"])
    return JSONResponse({"case": case, "activity": _build_activity(case, source_files)})


@app.post("/api/intake/sample")
def intake_sample(background_tasks: BackgroundTasks) -> JSONResponse:
    note_path = ROOT / "corpus/fixtures/patient_004_visit_note.txt"
    labs_path = ROOT / "corpus/fixtures/patient_004_labs.json"
    if not note_path.exists() or not labs_path.exists():
        raise HTTPException(status_code=404, detail="PT-004 sample fixtures not found.")
    note_text = note_path.read_text(encoding="utf-8")
    labs_json = json.loads(labs_path.read_text(encoding="utf-8"))
    source_files = [note_path.name, labs_path.name]
    case = _new_watcher()._enqueue_case(
        note_content=note_text,
        lab_data=labs_json,
        source_files=source_files,
    )
    if _intake_upgrade_enabled():
        background_tasks.add_task(_run_intake_llm_upgrade_bg, case["case_id"])
    return JSONResponse({"case": case, "activity": _build_activity(case, source_files)})


@app.post("/api/dismiss/{case_id}")
def dismiss_case(case_id: str) -> JSONResponse:
    store = get_store()
    case = store.get_case(case_id)
    if case is None or case.get("status") != STATUS_NEEDS_REVIEW:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not in queue.")
    store.set_case_status(case_id, STATUS_DISMISSED)
    store.append_event({"event": EVENT_DISMISSED, "case_id": case_id})
    return JSONResponse({"ok": True})


# --------------------------------------------------------------------------- #
# Patient portal — study-subject ePRO submissions + background triage
# --------------------------------------------------------------------------- #
EVENT_PATIENT_ALERT = "PATIENT_VITAL_ALERT"


def _reportclaw_enabled() -> bool:
    """ReportClaw async safety-report drafting is ON by default (REPORTCLAW_ENABLED=0 disables)."""
    import os

    return os.environ.get("REPORTCLAW_ENABLED", "1").lower() not in ("0", "false", "no")


def _run_report_claw_bg(patient_id: str, report: dict, triage: dict) -> None:
    """BackgroundTask worker: the ASYNC LLM path for a PATIENT_VITAL_ALERT.

    Runs after the response has been sent, so the ~100s reasoning model never
    blocks the subject's submit. Two independent, fail-soft steps:

      1. Upgrade the concern summary on the report to the LLM version (the
         synchronous path stored a fast deterministic summary).
      2. ReportClaw: draft the FDA 3500A narrative + enqueue a PI-review case.

    Every step is wrapped so an LLM outage or Mongo hiccup only logs — it must
    never crash (the request that scheduled it has already returned).
    """
    report_id = report.get("report_id")
    # 1. Best-effort LLM concern-summary refresh (deterministic fallback already stored).
    try:
        llm_summary = patient_triage.summarize_concern(report, triage)
        if report_id and llm_summary:
            get_store().set_report_triage(report_id, triage, llm_summary)
    except Exception as exc:  # noqa: BLE001 - fail soft; deterministic summary stands
        print(f"    [i] ReportClaw concern-summary refresh failed for {report_id}: {exc}")

    # 2. LLM safety report + PI-review case.
    try:
        case = report_claw.run_report_claw(patient_id, report, triage, get_store())
        print(
            f"    [✓] ReportClaw enqueued case {case.get('case_id')} "
            f"(narrative_source={case.get('narrative_source')}) for report {report_id}"
        )
    except Exception as exc:  # noqa: BLE001 - background job must fail soft
        print(f"    [i] ReportClaw failed for report {report_id}: {exc}")


class SymptomEntry(BaseModel):
    key: str
    present: bool = True
    severity: str | None = None


class PatientReportPayload(BaseModel):
    patient_id: str
    vitals: dict = {}
    symptoms: list[SymptomEntry] = []
    meds: str | None = None
    observations: str | None = None


@app.get("/api/patient/form")
def patient_form() -> JSONResponse:
    """The study-defined ePRO eForm spec so the frontend renders it dynamically."""
    return JSONResponse(patient_triage.form_spec())


@app.post("/api/patient/report")
def submit_patient_report(
    p: PatientReportPayload, background_tasks: BackgroundTasks
) -> JSONResponse:
    """Store a subject ePRO submission, triage it, and alert on a concern.

    Flow: store report -> deterministic triage -> persist triage ON the report ->
    if concerning, publish a PATIENT_VITAL_ALERT event (with an LLM/deterministic
    concern summary) to the shared `events` collection.
    """
    store = get_store()
    report = {
        "patient_id": p.patient_id,
        "vitals": p.vitals or {},
        "symptoms": [s.model_dump() for s in p.symptoms],
        "meds": p.meds,
        "observations": p.observations,
    }
    stored = store.submit_patient_report(report)

    triage = patient_triage.evaluate(stored)
    stored["triage"] = triage

    alert_published = False
    summary = None
    if triage["concern"]:
        # Keep the request FAST: the alert event uses a deterministic summary
        # (no LLM in the request path). The richer LLM summary is refreshed in
        # the background alongside ReportClaw so the submit never waits on Qwen.
        summary = patient_triage._deterministic_summary(stored, triage)
        store.append_event(
            {
                "event": EVENT_PATIENT_ALERT,
                "patient_id": stored["patient_id"],
                "report_id": stored["report_id"],
                "severity": triage["severity"],
                "flags": triage["flags"],
                "summary": summary,
            }
        )
        alert_published = True
        stored["concern_summary"] = summary

        # Event-driven ReportClaw: the PATIENT_VITAL_ALERT triggers an ASYNC
        # LLM safety-report draft + PI-review case. Scheduled as a FastAPI
        # BackgroundTask so this request returns IMMEDIATELY — the ~100s
        # narrative generation runs after the response is sent, and the case
        # then appears in the PI inbox on its normal auto-poll. Gated by
        # REPORTCLAW_ENABLED (default on).
        if _reportclaw_enabled():
            background_tasks.add_task(
                _run_report_claw_bg, stored["patient_id"], dict(stored), triage
            )
    # Persist the triage result (and any concern summary) ON the report document.
    store.set_report_triage(stored["report_id"], triage, summary)

    return JSONResponse(
        {"report": stored, "triage": triage, "alert_event_published": alert_published}
    )


@app.get("/api/patient/reports")
def patient_reports(patient_id: str) -> JSONResponse:
    """A subject's report history (each carrying its triage result), newest first."""
    return JSONResponse({"reports": get_store().list_patient_reports(patient_id)})


@app.get("/api/patient/context")
def patient_context(patient_id: str) -> JSONResponse:
    """Assembled LLM-context text for a subject (reports + case findings).

    Demonstrates that the persisted Mongo data is pullable into an LLM context.
    """
    store = get_store()
    reports = store.list_patient_reports(patient_id)
    blocks: list[str] = []
    for r in reports:
        blocks.append(patient_triage.build_report_context(r, r.get("triage") or {}))
    cases = [c for c in store.list_cases() if (c.get("patient_meta") or {}).get("patient_id") == patient_id]
    case_lines = "\n".join(
        f"  - {c.get('case_id')} [{c.get('status')}] · "
        f"{len(c.get('deviations') or [])} deviation(s), {len(c.get('lab_findings') or [])} lab(s)"
        for c in cases
    ) or "  (no intake cases on file)"
    context = (
        f"===== CARECLAW SUBJECT CONTEXT: {patient_id} =====\n\n"
        f"CLINICAL INTAKE CASES:\n{case_lines}\n\n"
        f"ePRO eDIARY SUBMISSIONS ({len(reports)}):\n\n"
        + ("\n\n---\n\n".join(blocks) if blocks else "  (no eDiary submissions on file)")
    )
    return JSONResponse({"patient_id": patient_id, "reports": len(reports), "context": context})


# --------------------------------------------------------------------------- #
# Static frontend
# --------------------------------------------------------------------------- #
@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import os

    import uvicorn

    # Bind all interfaces by default so the console is reachable over the LAN.
    # Override with WEB_HOST=127.0.0.1 to restrict to localhost. See
    # docs/NETWORK_ACCESS.md — 0.0.0.0 exposes this app with NO authentication.
    host = os.environ.get("WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("WEB_PORT", "8010"))
    uvicorn.run("web.server:app", host=host, port=port, reload=False)
