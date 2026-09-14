"""Deterministic ePRO triage for CareClaw study subjects (GAMP-5 story).

A study subject (patient) submits vitals/symptoms/observations via the ePRO
eDiary. This module evaluates that submission against the study-configured
thresholds in `configs/clinical/patient_eform.json` — purely deterministically,
so the decision to raise a `PATIENT_VITAL_ALERT` is reproducible and auditable.

The local Qwen vLLM is used ONLY to *explain/summarize* a concern in
`summarize_concern` (pull Mongo data -> LLM context). It never decides the
alert, and it always falls back to deterministic text on `LLMUnavailable`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from web import llm_client

ROOT = Path(__file__).resolve().parent.parent
EFORM_PATH = ROOT / "configs/clinical/patient_eform.json"

# Ordered so we can compute the "worst" severity across all flags.
_SEVERITY_ORDER = ["NONE", "WATCH", "CONCERN", "CRITICAL"]
# WATCH is informational; CONCERN/CRITICAL publish an alert to the care team.
_ALERT_SEVERITIES = {"CONCERN", "CRITICAL"}


@lru_cache(maxsize=1)
def load_eform(path: str | None = None) -> dict[str, Any]:
    """Load the study-defined ePRO form spec + thresholds (cached)."""
    p = Path(path) if path else EFORM_PATH
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def form_spec() -> dict[str, Any]:
    """The eForm spec sent to the frontend (thresholds included for transparency)."""
    return load_eform()


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cmp(value: float, op: str, target: float) -> bool:
    if op == ">=":
        return value >= target
    if op == "<=":
        return value <= target
    if op == ">":
        return value > target
    if op == "<":
        return value < target
    if op == "==":
        return value == target
    return False


def _worst(severities: list[str]) -> str:
    worst = "NONE"
    for s in severities:
        if _SEVERITY_ORDER.index(s) > _SEVERITY_ORDER.index(worst):
            worst = s
    return worst


def _symptom_index(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Normalise the submitted symptoms[] into {key: {present, severity}}."""
    index: dict[str, dict[str, Any]] = {}
    for s in report.get("symptoms") or []:
        if not isinstance(s, dict):
            continue
        key = s.get("key")
        if not key:
            continue
        present = bool(s.get("present", True))
        index[key] = {"present": present, "severity": str(s.get("severity") or "").lower()}
    return index


def evaluate(report: dict[str, Any], *, eform: dict[str, Any] | None = None) -> dict[str, Any]:
    """Deterministically evaluate a report against the study thresholds.

    Returns {"concern": bool, "severity": "NONE|WATCH|CONCERN|CRITICAL",
             "flags": [{field, value, rule, severity, message}, ...]}.
    `concern` is True only when at least one CONCERN/CRITICAL flag fires.
    """
    spec = eform or load_eform()
    thresholds = spec.get("thresholds") or {}
    vitals = report.get("vitals") or {}
    symptoms = _symptom_index(report)
    flags: list[dict[str, Any]] = []

    # --- vitals --- (keep only the highest-severity flag per vital field, so a
    # single low SpO2 doesn't fire both the CRITICAL and the WATCH band)
    per_vital: dict[str, dict[str, Any]] = {}
    for rule in thresholds.get("vitals") or []:
        val = _num(vitals.get(rule["field"]))
        if val is None:
            continue
        if _cmp(val, rule["op"], float(rule["value"])):
            candidate = {
                "field": rule["field"],
                "value": val,
                "rule": rule["rule"],
                "severity": rule["severity"],
                "message": rule["message"],
            }
            existing = per_vital.get(rule["field"])
            if existing is None or _SEVERITY_ORDER.index(candidate["severity"]) > _SEVERITY_ORDER.index(
                existing["severity"]
            ):
                per_vital[rule["field"]] = candidate
    flags.extend(per_vital.values())

    # --- symptoms --- (keep only the highest-severity flag per symptom field)
    per_field: dict[str, dict[str, Any]] = {}
    for rule in thresholds.get("symptoms") or []:
        entry = symptoms.get(rule["field"])
        if not entry or not entry["present"]:
            continue
        when = rule.get("when", "present")
        if when != "present" and entry["severity"] != when:
            continue
        candidate = {
            "field": rule["field"],
            "value": entry["severity"] or "yes",
            "rule": rule["rule"],
            "severity": rule["severity"],
            "message": rule["message"],
        }
        existing = per_field.get(rule["field"])
        if existing is None or _SEVERITY_ORDER.index(candidate["severity"]) > _SEVERITY_ORDER.index(
            existing["severity"]
        ):
            per_field[rule["field"]] = candidate
    flags.extend(per_field.values())

    severity = _worst([f["severity"] for f in flags]) if flags else "NONE"
    concern = severity in _ALERT_SEVERITIES
    return {"concern": concern, "severity": severity, "flags": flags}


# --------------------------------------------------------------------------- #
# LLM context assembly + concern summary (pull Mongo data -> LLM context)
# --------------------------------------------------------------------------- #
_SUMMARY_SYSTEM = (
    "You are CareClaw's study-safety assistant. A clinical-trial subject on an "
    "oncology drug with a known liver-injury (hepatotoxicity) signal has submitted "
    "a home eDiary (ePRO) entry. Deterministic study rules have already flagged it "
    "as concerning. Write a brief (2-3 sentence) neutral clinical summary for the "
    "care team describing what was reported and why it may warrant attention. "
    "Rules: only use the data given; do NOT diagnose, do NOT assign causality to the "
    "study drug, do NOT recommend treatment. Refer to the subject, not 'the patient'."
)


def build_report_context(report: dict[str, Any], triage: dict[str, Any]) -> str:
    """Assemble a stored report into a compact text context for the LLM."""
    vitals = report.get("vitals") or {}
    spec = load_eform()
    unit_by_key = {v["key"]: v.get("unit", "") for v in spec.get("vitals", [])}
    vital_lines = (
        "\n".join(
            f"  - {k}: {v}{(' ' + unit_by_key.get(k, '')).rstrip()}"
            for k, v in vitals.items()
            if v not in (None, "")
        )
        or "  (none reported)"
    )
    sym = [s for s in (report.get("symptoms") or []) if isinstance(s, dict) and s.get("present", True)]
    sym_lines = (
        "\n".join(f"  - {s.get('key')}{(' [' + s['severity'] + ']') if s.get('severity') else ''}" for s in sym)
        or "  (none reported)"
    )
    flag_lines = "\n".join(f"  - [{f['severity']}] {f['rule']}: {f['message']}" for f in triage.get("flags", []))
    return (
        f"STUDY: {spec.get('protocol_id')} · {spec.get('study_drug')}\n"
        f"SUBJECT: {report.get('patient_id')}\n"
        f"SUBMITTED: {report.get('submitted_at')}\n"
        f"VITALS:\n{vital_lines}\n"
        f"SYMPTOMS REPORTED:\n{sym_lines}\n"
        f"CONCOMITANT MEDS: {report.get('meds') or '(none)'}\n"
        f"OBSERVATIONS: {report.get('observations') or '(none)'}\n"
        f"DETERMINISTIC TRIAGE: {triage.get('severity')} (concern={triage.get('concern')})\n"
        f"FLAGS:\n{flag_lines}"
    )


def _deterministic_summary(report: dict[str, Any], triage: dict[str, Any]) -> str:
    subj = report.get("patient_id", "The subject")
    parts = "; ".join(f"{f['rule']} ({f['message']})" for f in triage.get("flags", [])) or "no specific flags"
    return (
        f"{subj} submitted an eDiary entry triaged {triage.get('severity')}. "
        f"Flagged: {parts}. Deterministic study-rule assessment (LLM summary unavailable)."
    )


def summarize_concern(report: dict[str, Any], triage: dict[str, Any]) -> str:
    """Pull the report into an LLM context and ask Qwen for a brief concern summary.

    Falls back to a deterministic sentence listing the flags on `LLMUnavailable`.
    """
    context = build_report_context(report, triage)
    messages = [
        {"role": "system", "content": _SUMMARY_SYSTEM},
        {"role": "user", "content": context + "\n\nWrite the brief care-team summary now."},
    ]
    try:
        return llm_client.chat(messages, temperature=0.2, max_tokens=1024).strip()
    except llm_client.LLMUnavailable:
        return _deterministic_summary(report, triage)
