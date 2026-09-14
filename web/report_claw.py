"""ReportClaw — event-driven LLM safety-report drafter for ePRO alerts.

When the vital-monitor publishes a ``PATIENT_VITAL_ALERT`` (a study subject's
home eDiary entry that the deterministic triage in ``web.patient_triage`` flagged
as concerning), ReportClaw runs OUT OF BAND to:

  1. Pull the triggering report + triage + the patient record from MongoDB.
  2. Turn the concerning triage flags into a case's ``deviations`` / findings and
     map the reported symptoms to MedDRA terms (SafetyClaw), so the existing PI
     detail view renders it. Labs are usually absent for an ePRO alert.
  3. Draft the FDA MedWatch 3500A / CIOMS I Section B narrative with the LLM
     (``web.narrative_llm``), falling back to the deterministic SafetyClaw
     zero-draft on any error. Causality / final action stay BLANK — the PI's call.
  4. Enqueue a NEEDS_PI_REVIEW case and append a ``REPORT_GENERATED`` event.

This is the asynchronous LLM path (contrast the deterministic, fast FastAPI
intake in ``daemon.watcher``). It is scheduled as a FastAPI BackgroundTask by the
patient-report endpoint so the subject's submit never waits on the ~100s model.

Idempotent-ish: it will not create a second case for the same ``report_id``.
"""

from __future__ import annotations

from typing import Any

from agents.safety_claw import SafetyClaw
from web import narrative_llm

# Triage severities that we treat as reportable "findings" on the case.
_FINDING_SEVERITIES = {"CONCERN", "CRITICAL"}


def _patient_meta(patient_id: str, patient: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Build the case's patient_meta from the patient record + triggering report."""
    patient = patient or {}
    return {
        "patient_id": patient_id,
        "protocol_id": patient.get("protocol_id") or "ONCO-2026-X88",
        "phase": patient.get("phase") or "Phase 1",
        "age": patient.get("age"),
        "sex": patient.get("sex"),
        "study_day": patient.get("study_day"),
        "c1d1_date": patient.get("c1d1_date"),
        # The ePRO submission date is the AE assessment date for this report.
        "note_date": (report.get("submitted_at") or "")[:10] or None,
    }


def _flags_to_deviations(triage: dict[str, Any]) -> list[dict[str, Any]]:
    """Represent each concerning triage flag as a case finding the PI view renders.

    Reuses the ``deviations`` shape (category / severity / protocol_section /
    details) so the existing static detail view renders it with no changes.
    """
    findings: list[dict[str, Any]] = []
    for f in triage.get("flags") or []:
        sev = str(f.get("severity") or "").upper()
        if sev not in _FINDING_SEVERITIES:
            continue  # WATCH/informational flags are not treated as reportable findings
        findings.append(
            {
                "category": f.get("rule") or "Subject-reported safety signal",
                # Map to the view's colour bands: CRITICAL stays critical (red),
                # CONCERN renders as a MAJOR (orange) finding.
                "severity": "CRITICAL" if sev == "CRITICAL" else "MAJOR",
                "protocol_section": "ePRO safety surveillance (Protocol §7.4)",
                "details": f.get("message") or "",
                "detected_field": f.get("field"),
                "reported_value": f.get("value"),
            }
        )
    return findings


def _observations_text(report: dict[str, Any]) -> str:
    """Assemble a free-text description of the subject-reported AE.

    Combines the subject's free-text observations with the labels of the symptoms
    they marked present, so ``SafetyClaw.extract_meddra_symptoms`` (regex over
    free text) can map them and the deterministic zero-draft has narrative body.
    """
    parts: list[str] = []
    present = [
        s for s in (report.get("symptoms") or [])
        if isinstance(s, dict) and s.get("present", True)
    ]
    if present:
        sym_bits = []
        for s in present:
            key = str(s.get("key") or "").replace("_", " ")
            sev = s.get("severity")
            sym_bits.append(f"{key}{f' ({sev})' if sev else ''}")
        parts.append("Subject reported the following symptoms: " + ", ".join(sym_bits) + ".")
    obs = (report.get("observations") or "").strip()
    if obs:
        parts.append(f"Subject observations: {obs}")
    meds = (report.get("meds") or "").strip()
    if meds:
        parts.append(f"Concomitant medications reported: {meds}")
    return " ".join(parts) or "(no free-text observations provided)"


def _vitals_line(report: dict[str, Any]) -> str:
    vitals = report.get("vitals") or {}
    bits = [f"{k}={v}" for k, v in vitals.items() if v not in (None, "")]
    return "Home vitals reported: " + (", ".join(bits) if bits else "(none)") + "."


def run_report_claw(
    patient_id: str,
    report: dict[str, Any],
    triage: dict[str, Any],
    store: Any,
) -> dict[str, Any]:
    """Draft an LLM safety report for an ePRO alert and enqueue a PI-review case.

    Returns the enqueued (or pre-existing) case dict. Idempotent per report_id.
    """
    report_id = report.get("report_id")

    # --- idempotency: never create a duplicate case for the same report ------- #
    if report_id:
        existing = store.get_case_by_report_id(report_id)
        if existing is not None:
            return existing

    patient = store.get_patient(patient_id) or {}
    patient_meta = _patient_meta(patient_id, patient, report)

    # --- findings: triage flags -> deviations; reported symptoms -> MedDRA ---- #
    deviations = _flags_to_deviations(triage)
    lab_findings: list[dict[str, Any]] = []  # ePRO alerts rarely carry labs
    safety = SafetyClaw()
    observations_text = _observations_text(report)
    symptoms_mapped = safety.extract_meddra_symptoms(observations_text)

    # --- deterministic zero-draft (fallback base for the LLM narrative) ------- #
    note_text = f"{observations_text}\n{_vitals_line(report)}"
    deterministic_narrative = safety.draft_fda_3500a_narrative(
        patient_meta,
        note_text,
        lab_findings,
        symptoms_mapped,
    )

    # --- LLM narrative (fails soft to the deterministic zero-draft) ----------- #
    draft_narrative = deterministic_narrative
    narrative_source = "deterministic"
    narrative_model = None
    try:
        llm_narrative, narrative_model = narrative_llm.generate_3500a_narrative(
            patient_meta,
            deviations,
            lab_findings,
            symptoms_mapped,
            deterministic_narrative,
        )
        if llm_narrative and llm_narrative.strip():
            draft_narrative = llm_narrative
            narrative_source = "llm"
    except narrative_llm.LLMUnavailable:
        pass  # keep deterministic zero-draft
    except Exception:  # noqa: BLE001 - never let report drafting crash the job
        pass

    severity = triage.get("severity")
    case_id = f"CASE-{patient_id}-EPRO-{report_id}" if report_id else f"CASE-{patient_id}-EPRO"
    case_payload = {
        "case_id": case_id,
        "status": "NEEDS_PI_REVIEW",
        "trigger": "PATIENT_VITAL_ALERT",
        "report_id": report_id,
        "source_files": [f"ePRO:{report_id}"],
        "source_file": f"ePRO:{report_id}",
        "patient_meta": patient_meta,
        "note_excerpt": (note_text[:500] + "…") if len(note_text) > 500 else note_text,
        "note_text": note_text,
        "lab_data": {},
        "deviations": deviations,
        "lab_findings": lab_findings,
        "symptoms_mapped": symptoms_mapped,
        "draft_narrative": draft_narrative,
        "narrative_source": narrative_source,
        "narrative_model": narrative_model,
        "triage_severity": severity,
    }

    stored_case = store.enqueue_case(case_payload)
    final_case_id = stored_case.get("case_id", case_id)
    store.append_event(
        {
            "event": "REPORT_GENERATED",
            "case_id": final_case_id,
            "patient_id": patient_id,
            "report_id": report_id,
            "narrative_source": narrative_source,
            "severity": severity,
        }
    )
    return stored_case
