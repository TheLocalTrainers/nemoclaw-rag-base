"""ProtocolClaw: Autonomous Protocol Deviation and Compliance Sentinel.

Monitors incoming patient clinical records against clinical trial protocol rules:
1. Calculates exact study days and audits visit windows against allowable thresholds.
2. Identifies brand/generic names of prohibited concomitant medications.
3. Flags Important Protocol Deviations (IPDs) with exact protocol citations.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # Fallback handled gracefully if yaml is absent


class ProtocolClaw:
    def __init__(self, rules_path: str | Path = "configs/clinical/protocol_rules.yaml"):
        self.rules_path = Path(rules_path)
        self.rules = self._load_rules()

    def _load_rules(self) -> dict[str, Any]:
        if not self.rules_path.exists():
            return self._default_fallback_rules()

        if yaml is not None:
            with open(self.rules_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}

        # Minimal fallback if PyYAML is not yet installed
        return self._default_fallback_rules()

    def _default_fallback_rules(self) -> dict[str, Any]:
        return {
            "protocol_id": "ONCO-2026-X88",
            "visit_windows": {
                "cycle_1_day_14": {"target_day": 14, "window_days": 2, "description": "C1D14 (Days 12-16)"},
                "cycle_1_day_28": {"target_day": 28, "window_days": 2, "description": "C1D28 (Days 26-30)"},
            },
            "prohibited_concomitant_medications": [
                {
                    "category": "Potent CYP3A4 Inhibitors",
                    "protocol_section": "Section 5.2.1",
                    "severity": "CRITICAL",
                    "drugs": ["ketoconazole", "itraconazole", "posaconazole", "clarithromycin", "ritonavir"],
                    "rationale": "Increases Nexavatinib exposure >3.5x, causing severe transaminitis.",
                    "action": "Immediate PI notification. Withhold study drug and discontinue inhibitor."
                },
                {
                    "category": "Therapeutic Anticoagulants",
                    "protocol_section": "Section 5.2.3",
                    "severity": "HIGH",
                    "drugs": ["warfarin", "apixaban", "rivaroxaban"],
                    "rationale": "Elevated additive major bleeding risk.",
                    "action": "Switch to prophylactic low-molecular-weight heparin if indicated."
                }
            ]
        }

    def audit_record(self, note_text: str, patient_meta: dict[str, Any]) -> list[dict[str, Any]]:
        """Audit a clinical progress note and metadata for protocol deviations."""
        deviations: list[dict[str, Any]] = []

        # 1. Study Day Calculation & Visit Window Verification
        actual_study_day = patient_meta.get("study_day")
        if actual_study_day is None:
            c1d1_str = patient_meta.get("c1d1_date")
            note_date_str = patient_meta.get("note_date")
            if c1d1_str and note_date_str:
                c1d1_date = datetime.strptime(c1d1_str, "%Y-%m-%d")
                note_date = datetime.strptime(note_date_str, "%Y-%m-%d")
                actual_study_day = (note_date - c1d1_date).days + 1

        if actual_study_day is not None:
            # Check for Cycle 1 Day 14 mentions
            if re.search(r"(C1D14|Cycle\s*1\s*Day\s*14|Day\s*14)", note_text, re.IGNORECASE):
                c1d14_cfg = self.rules.get("visit_windows", {}).get("cycle_1_day_14", {})
                target_day = c1d14_cfg.get("target_day", 14)
                window_days = c1d14_cfg.get("window_days", 2)
                min_day = target_day - window_days
                max_day = target_day + window_days

                if not (min_day <= actual_study_day <= max_day):
                    days_off = actual_study_day - max_day if actual_study_day > max_day else actual_study_day - min_day
                    deviations.append({
                        "type": "IMPORTANT_PROTOCOL_DEVIATION",
                        "category": "Visit Window Non-Compliance",
                        "severity": "MAJOR",
                        "protocol_section": "Section 8.1 (Schedule of Assessments)",
                        "details": (
                            f"Cycle 1 Day 14 safety visit performed on Study Day {actual_study_day}. "
                            f"Protocol allowable window is Day {target_day} ± {window_days} days (Days {min_day} to {max_day}). "
                            f"Assessment completed {abs(days_off)} day(s) outside permissible window."
                        ),
                        "action_required": "Log deviation in EDC within 5 days; verify evaluability of PK/safety endpoints.",
                    })

        # 2. Prohibited Concomitant Medication Detection
        note_lower = note_text.lower()
        for group in self.rules.get("prohibited_concomitant_medications", []):
            category = group.get("category", "Prohibited Drug")
            section = group.get("protocol_section", "Section 5.2")
            severity = group.get("severity", "HIGH")
            rationale = group.get("rationale", "")
            action = group.get("action", "")

            for drug in group.get("drugs", []):
                # Match word boundary for drug name
                if re.search(rf"\b{re.escape(drug)}\b", note_lower):
                    deviations.append({
                        "type": "IMPORTANT_PROTOCOL_DEVIATION",
                        "category": "Prohibited Concomitant Medication",
                        "severity": severity,
                        "detected_drug": drug.title(),
                        "drug_class": category,
                        "protocol_section": section,
                        "details": f"Patient documented taking prohibited agent '{drug.title()}' ({category}).",
                        "clinical_impact": rationale,
                        "action_required": action,
                    })

        return deviations
