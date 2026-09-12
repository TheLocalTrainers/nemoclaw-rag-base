"""OpenClaw Always-On File Watcher Daemon for CareClaw.

Monitors `incoming_records/`. When an EHR note (.txt) and/or lab panel (.json)
arrive, runs ProtocolClaw then SafetyClaw and enqueues NEEDS_PI_REVIEW cases
for the Streamlit clinician gateway.

Paired note+lab drops for the same patient are merged into a single case so the
hackathon story shows deviations and CTCAE findings together.

Does NOT auto-sign. 21 CFR Part 11 lock happens only after PI approval in the UI.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from agents.protocol_claw import ProtocolClaw
from agents.safety_claw import SafetyClaw
from store.careclaw_store import CareClawStore
from web import narrative_llm


class OpenClawFileWatcher:
    def __init__(
        self,
        watch_dir: str | Path = "incoming_records",
        processed_dir: str | Path = "processed_records",
        audit_dir: str | Path = "audit_logs",
    ):
        self.watch_dir = Path(watch_dir)
        self.processed_dir = Path(processed_dir)
        self.audit_dir = Path(audit_dir)

        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.audit_dir.mkdir(parents=True, exist_ok=True)

        self.protocol_agent = ProtocolClaw()
        self.safety_agent = SafetyClaw()
        self._store: CareClawStore | None = None

    @property
    def store(self) -> CareClawStore:
        """Lazily open the MongoDB-backed store (single source of truth)."""
        if self._store is None:
            self._store = CareClawStore()
        return self._store

    def _read_note(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def _read_labs(self, path: Path) -> dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _archive(self, path: Path) -> Path:
        target = self.processed_dir / path.name
        shutil.move(str(path), str(target))
        return target

    def _enqueue_case(
        self,
        *,
        note_content: str,
        lab_data: dict[str, Any],
        source_files: list[str],
    ) -> dict[str, Any]:
        patient_id = lab_data.get("patient_id", "PT-004")
        # Trial phase is a per-subject field. Prefer the phase already on the
        # patient record (registry / seed); default to "Phase 1" (PT-004 is a
        # dose-finding/safety subject) otherwise.
        existing_patient = self.store.get_patient(patient_id) or {}
        phase = existing_patient.get("phase") or "Phase 1"
        # Prefer demographics carried on the uploaded lab panel, then the patient
        # record, then sensible defaults — so uploaded samples aren't all 62/Male.
        patient_meta = {
            "patient_id": patient_id,
            "protocol_id": lab_data.get("study_protocol", "ONCO-2026-X88"),
            "phase": phase,
            "c1d1_date": lab_data.get("c1d1_date") or existing_patient.get("c1d1_date") or "2026-08-20",
            "note_date": lab_data.get("draw_date", "2026-09-08"),
            "study_day": lab_data.get("study_day", 19),
            "age": lab_data.get("age") or existing_patient.get("age") or 62,
            "sex": lab_data.get("sex") or existing_patient.get("sex") or "Male",
        }

        deviations = self.protocol_agent.audit_record(note_content, patient_meta)
        print(f"    [+] ProtocolClaw identified {len(deviations)} protocol deviation(s).")

        lab_findings = (
            self.safety_agent.evaluate_lab_toxicity(lab_data) if lab_data else []
        )
        symptoms = (
            self.safety_agent.extract_meddra_symptoms(note_content) if note_content else []
        )
        deterministic_narrative = self.safety_agent.draft_fda_3500a_narrative(
            patient_meta,
            note_content or "(lab-only intake)",
            lab_findings,
            symptoms,
        )
        print("    [+] SafetyClaw generated deterministic FDA Form 3500A zero-draft.")

        # Intake stays FAST: the case is enqueued with the deterministic zero-draft
        # immediately (agent-activity animation must appear in ~2s, and Qwen takes
        # ~100s for a full 3500A). The LLM-written narrative is produced OUT OF BAND
        # — an event-driven ReportClaw upgrade triggered after enqueue, or the PI's
        # on-demand chat — so it never blocks the drop→queue path.
        #
        # Set VLLM_NARRATIVE_SYNC=1 only for offline batch/seed runs where a
        # ~100s-per-case wait is acceptable and you want the LLM prose inline.
        draft_narrative = deterministic_narrative
        narrative_source = "deterministic"
        narrative_model = None
        if os.environ.get("VLLM_NARRATIVE_SYNC", "0").lower() in ("1", "true", "yes"):
            try:
                llm_narrative, narrative_model = narrative_llm.generate_3500a_narrative(
                    patient_meta,
                    deviations,
                    lab_findings,
                    symptoms,
                    deterministic_narrative,
                )
                draft_narrative = llm_narrative
                narrative_source = "llm"
                print(
                    f"    [+] Qwen (vLLM{': ' + narrative_model if narrative_model else ''}) "
                    "generated the FDA Form 3500A narrative prose."
                )
            except narrative_llm.LLMUnavailable as exc:
                print(f"    [i] LLM narrative unavailable ({exc}); using deterministic zero-draft.")
            except Exception as exc:  # noqa: BLE001 - fail soft; never crash intake
                print(f"    [i] LLM narrative errored ({exc}); using deterministic zero-draft.")

        case_id = (
            f"CASE-{patient_meta['patient_id']}-"
            f"{patient_meta['note_date']}-"
            f"{'-'.join(Path(s).stem for s in source_files)}"
        )
        case_payload = {
            "case_id": case_id,
            "status": "NEEDS_PI_REVIEW",
            "source_files": source_files,
            "source_file": ", ".join(source_files),
            "patient_meta": patient_meta,
            "note_excerpt": (note_content[:500] + "…") if len(note_content) > 500 else note_content,
            "note_text": note_content,
            "lab_data": lab_data,
            "deviations": deviations,
            "lab_findings": lab_findings,
            "symptoms_mapped": symptoms,
            "draft_narrative": draft_narrative,
            "narrative_source": narrative_source,
            "narrative_model": narrative_model,
        }

        # MongoDB is the single source of truth: upsert the patient, insert the
        # case, then append an immutable CASE_ENQUEUED event.
        self.store.upsert_patient(self._patient_from_meta(patient_meta, lab_data))
        stored_case = self.store.enqueue_case(case_payload)
        final_case_id = stored_case.get("case_id", case_id)
        self.store.append_event(
            {
                "event": "CASE_ENQUEUED",
                "case_id": final_case_id,
                "status": "NEEDS_PI_REVIEW",
                "source_files": source_files,
                "deviation_count": len(deviations),
                "severe_lab_count": sum(1 for x in lab_findings if x.get("is_severe")),
            }
        )

        print(f"    [✓] Queued for PI review → careclaw.cases ({final_case_id})")
        return stored_case

    @staticmethod
    def _patient_from_meta(
        patient_meta: dict[str, Any], lab_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Derive a stable patient record (demographics + enrollment) for upsert."""
        return {
            "patient_id": patient_meta.get("patient_id", "PT-004"),
            "age": patient_meta.get("age"),
            "sex": patient_meta.get("sex"),
            "phase": patient_meta.get("phase", "Phase 1"),
            "protocol_id": patient_meta.get("protocol_id")
            or lab_data.get("study_protocol", "ONCO-2026-X88"),
            "study_drug": "Nexavatinib (NEX-882) 200mg PO daily",
            "c1d1_date": patient_meta.get("c1d1_date"),
            "enrollment_status": "ACTIVE",
        }

    def process_all_pending(self) -> list[dict[str, Any]]:
        """Process watch-dir files; pair note+labs into one case when both present."""
        notes = sorted(self.watch_dir.glob("*.txt"))
        labs = sorted(self.watch_dir.glob("*.json"))
        results: list[dict[str, Any]] = []

        # Prefer paired intake (hackathon Slide 4 path).
        if notes and labs:
            note_path, lab_path = notes[0], labs[0]
            print(f"[!] CareClaw Daemon: Pairing '{note_path.name}' + '{lab_path.name}'...")
            note_content = self._read_note(note_path)
            lab_data = self._read_labs(lab_path)
            case = self._enqueue_case(
                note_content=note_content,
                lab_data=lab_data,
                source_files=[note_path.name, lab_path.name],
            )
            self._archive(note_path)
            self._archive(lab_path)
            print("    [✓] Archived paired sources.\n")
            results.append(case)
            # Process any remaining unpaired files next loop.
            return results

        for note_path in notes:
            print(f"[!] CareClaw Daemon: Ingesting note '{note_path.name}'...")
            # Prefer companion labs already processed earlier in the demo.
            lab_data: dict[str, Any] = {}
            companion = self.processed_dir / "patient_004_labs.json"
            if companion.exists():
                lab_data = self._read_labs(companion)
            case = self._enqueue_case(
                note_content=self._read_note(note_path),
                lab_data=lab_data,
                source_files=[note_path.name],
            )
            self._archive(note_path)
            print(f"    [✓] Archived '{note_path.name}'.\n")
            results.append(case)

        for lab_path in labs:
            print(f"[!] CareClaw Daemon: Ingesting labs '{lab_path.name}'...")
            case = self._enqueue_case(
                note_content="",
                lab_data=self._read_labs(lab_path),
                source_files=[lab_path.name],
            )
            self._archive(lab_path)
            print(f"    [✓] Archived '{lab_path.name}'.\n")
            results.append(case)

        return results

    def start_polling(self, interval_seconds: float = 2.0) -> None:
        print("[*] OpenClaw Daemon initialized on GB10.")
        print(f"[*] Watching directory: '{self.watch_dir.resolve()}' (interval: {interval_seconds}s)")
        print(f"[*] Pending PI queue → MongoDB careclaw.cases (status NEEDS_PI_REVIEW)")
        print("[*] Press Ctrl+C to terminate.")

        try:
            while True:
                self.process_all_pending()
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\n[*] Daemon stopped by user.")


if __name__ == "__main__":
    watcher = OpenClawFileWatcher()
    watcher.start_polling()
