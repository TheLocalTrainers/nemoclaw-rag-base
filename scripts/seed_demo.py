"""Seed the CareClaw demo into MongoDB (the single source of truth).

Clears the `careclaw` collections, then enqueues exactly ONE PT-004 case by
running the real ProtocolClaw / SafetyClaw agents on the committed fixtures via
the SAME daemon/store path a live intake uses — so the seeded data is identical
to a record dropped into `incoming_records/`. The patient record is upserted as
a side effect of that path.

Run:  .venv/bin/python -m scripts.seed_demo
      (or:  make seed)
"""

from __future__ import annotations

import json
from pathlib import Path

from daemon.watcher import OpenClawFileWatcher
from rag.env import load_dotenv
from store.careclaw_store import CareClawStore

ROOT = Path(__file__).resolve().parents[1]
NOTE_FIXTURE = ROOT / "corpus/fixtures/patient_004_visit_note.txt"
LABS_FIXTURE = ROOT / "corpus/fixtures/patient_004_labs.json"


def main() -> int:
    load_dotenv()

    if not NOTE_FIXTURE.exists() or not LABS_FIXTURE.exists():
        raise SystemExit(f"PT-004 fixtures not found under {ROOT / 'corpus/fixtures'}")

    # Fails fast with a clear message if Mongo is unreachable.
    store = CareClawStore()
    print(f"[*] Connected to MongoDB → {store.uri} (db: {store.database_name})")

    store.reset_demo()
    print("[*] Cleared careclaw collections (patients, cases, events).")

    note_text = NOTE_FIXTURE.read_text(encoding="utf-8")
    lab_data = json.loads(LABS_FIXTURE.read_text(encoding="utf-8"))

    watcher = OpenClawFileWatcher(
        watch_dir=ROOT / "incoming_records",
        processed_dir=ROOT / "processed_records",
        audit_dir=ROOT / "audit_logs",
    )
    print("[*] Running ProtocolClaw + SafetyClaw on PT-004 fixtures...")
    case = watcher._enqueue_case(
        note_content=note_text,
        lab_data=lab_data,
        source_files=[NOTE_FIXTURE.name, LABS_FIXTURE.name],
    )

    # Enrich the PT-004 subject record with storyboard-grounded demographics and
    # enrollment context (merged onto the thin doc the intake path upserts).
    chem = (lab_data.get("chemistry") or {})
    store.upsert_patient(
        {
            "patient_id": lab_data.get("patient_id", "PT-004"),
            "age": 62,
            "sex": "Male",
            "phase": "Phase 1",
            "diagnosis": "Refractory metastatic colorectal adenocarcinoma (mCRC)",
            "protocol_id": lab_data.get("study_protocol", "ONCO-2026-X88"),
            "study_arm": "Experimental — Nexavatinib monotherapy",
            "study_drug": "Nexavatinib (NEX-882) 200 mg PO daily",
            "site": "Site 07 — Dell Medical Oncology",
            "c1d1_date": "2026-08-20",
            "consent_date": "2026-08-14",
            "current_cycle": "Cycle 1",
            "current_study_day": lab_data.get("study_day", 19),
            "enrollment_status": "Active — on study drug",
            "baseline_labs": {
                "ALT": chem.get("ALT", {}).get("baseline_value", 28),
                "AST": chem.get("AST", {}).get("baseline_value", 24),
                "Total_Bilirubin": chem.get("Total_Bilirubin", {}).get("baseline_value", 0.8),
            },
        }
    )
    print("[*] Enriched PT-004 subject record.")

    # Seed the care team — the demo actors, so the console's role system is
    # backed by MongoDB rather than hardcoded in the frontend.
    care_team = [
        {
            "user_id": "coordinator", "name": "Sarah Kim, RN", "title": "Study Coordinator",
            "initials": "SK", "email": "s.kim@site07.example", "site": "Site 07",
            "can_sign": False, "can_manage_patients": True,
            "nav": ["intake", "inbox", "registry", "signed"], "default_view": "intake", "order": 1,
        },
        {
            "user_id": "pi", "name": "Dr. Vance, MD", "title": "Principal Investigator",
            "initials": "DV", "email": "e.vance@site07.example", "site": "Site 07",
            "can_sign": True, "can_manage_patients": False,
            "nav": ["inbox", "registry", "signed"], "default_view": "inbox", "order": 2,
        },
        {
            "user_id": "monitor", "name": "J. Alvarez", "title": "Clinical Monitor (CRA)",
            "initials": "JA", "email": "j.alvarez@sponsor.example", "site": "Sponsor CRO",
            "can_sign": False, "can_manage_patients": False,
            "nav": ["inbox", "registry", "signed"], "default_view": "inbox", "order": 3,
        },
    ]
    for member in care_team:
        store.upsert_user(member)
    print(f"[*] Seeded care team ({len(care_team)} users).")

    # Seed a small enrolled-subject roster across trial phases so the Patient
    # Registry isn't empty. PT-004 (Phase 1, active hero case) is upserted above;
    # these are additional subjects with varied phase + enrollment status.
    roster = [
        {"patient_id": "PT-001", "phase": "Phase 1", "site": "Site 07 — Dell Medical Oncology",
         "age": 58, "sex": "Female", "diagnosis": "Refractory metastatic colorectal adenocarcinoma (mCRC)",
         "enrollment_status": "On treatment"},
        {"patient_id": "PT-002", "phase": "Phase 1", "site": "Site 07 — Dell Medical Oncology",
         "age": 67, "sex": "Male", "diagnosis": "Refractory metastatic colorectal adenocarcinoma (mCRC)",
         "enrollment_status": "Screening"},
        {"patient_id": "PT-003", "phase": "Phase 1", "site": "Site 12 — Riverside Cancer Center",
         "age": 71, "sex": "Female", "diagnosis": "Refractory metastatic colorectal adenocarcinoma (mCRC)",
         "enrollment_status": "Completed"},
        {"patient_id": "PT-010", "phase": "Phase 2", "site": "Site 07 — Dell Medical Oncology",
         "age": 54, "sex": "Male", "diagnosis": "Advanced hepatocellular carcinoma",
         "enrollment_status": "On treatment"},
        {"patient_id": "PT-011", "phase": "Phase 2", "site": "Site 12 — Riverside Cancer Center",
         "age": 63, "sex": "Female", "diagnosis": "Advanced hepatocellular carcinoma",
         "enrollment_status": "Active — on study drug"},
        {"patient_id": "PT-020", "phase": "Phase 3", "site": "Site 03 — Northgate Oncology",
         "age": 60, "sex": "Male", "diagnosis": "Metastatic non-small-cell lung cancer",
         "enrollment_status": "On treatment"},
    ]
    for subj in roster:
        store.upsert_patient(subj)
    print(f"[*] Seeded patient roster ({len(roster)} additional subjects across phases).")

    # Seed a couple of prior PT-004 ePRO eDiary entries so "My Reports" isn't
    # empty. Each is triaged deterministically; a concerning one also publishes a
    # PATIENT_VITAL_ALERT — identical to the live /api/patient/report path.
    from web import patient_triage  # local import: keeps agents-only seed path light

    seed_reports = [
        {"patient_id": "PT-004", "vitals": {"temperature_c": 36.8, "heart_rate_bpm": 74,
            "systolic_bp": 118, "diastolic_bp": 76, "spo2_pct": 98, "weight_kg": 74.5},
            "symptoms": [], "meds": "None", "observations": "Feeling well today."},
        {"patient_id": "PT-004", "vitals": {"temperature_c": 38.9, "heart_rate_bpm": 104,
            "systolic_bp": 124, "diastolic_bp": 80, "spo2_pct": 97, "weight_kg": 74.0},
            "symptoms": [{"key": "jaundice", "present": True, "severity": None},
                         {"key": "fatigue", "present": True, "severity": "moderate"}],
            "meds": "Paracetamol 500 mg", "observations": "Noticed my eyes look a bit yellow."},
    ]
    alerts = 0
    for r in seed_reports:
        stored = store.submit_patient_report(r)
        triage = patient_triage.evaluate(stored)
        summary = None
        if triage["concern"]:
            summary = patient_triage.summarize_concern(stored, triage)
            store.append_event({"event": "PATIENT_VITAL_ALERT", "patient_id": stored["patient_id"],
                "report_id": stored["report_id"], "severity": triage["severity"],
                "flags": triage["flags"], "summary": summary})
            alerts += 1
        store.set_report_triage(stored["report_id"], triage, summary)
    print(f"[*] Seeded {len(seed_reports)} PT-004 ePRO reports ({alerts} alert(s) published).")

    patients = store.count_patients()
    cases = store.count_cases()
    events = store.count_events()
    print("\n[✓] Demo seeded. MongoDB now contains:")
    print(f"      patients : {patients}")
    print(f"      cases    : {cases}  (pending: {store.count_cases('NEEDS_PI_REVIEW')})")
    print(f"      events   : {events}")
    print(f"      reports  : {store.count_reports()}")
    print(f"      seed case: {case.get('case_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
