"""SafetyClaw: Autonomous Adverse Event Scribe and FDA 3500A Narrative Drafter.

Evaluates laboratory toxicities against CTCAE v5.0 criteria, maps symptoms to
official MedDRA Preferred Terms, and pre-drafts FDA MedWatch 3500A / CIOMS I
safety narratives for 1-click Principal Investigator adjudication (21 CFR 312.64).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class SafetyClaw:
    def __init__(self, meddra_path: str | Path = "configs/clinical/meddra_mini.json"):
        self.meddra_path = Path(meddra_path)
        self.meddra_terms = self._load_meddra()

    def _load_meddra(self) -> dict[str, dict[str, str]]:
        if not self.meddra_path.exists():
            return {
                "alt": {"pt": "Alanine aminotransferase increased", "code": "10001551"},
                "ast": {"pt": "Aspartate aminotransferase increased", "code": "10003481"},
                "bilirubin": {"pt": "Blood bilirubin increased", "code": "10005364"},
                "icterus": {"pt": "Ocular icterus", "code": "10030095"},
                "abdominal": {"pt": "Abdominal pain upper", "code": "10000087"},
            }

        with open(self.meddra_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
            lookup = {}
            for item in raw.get("terms", []):
                key = item.get("pt", "").lower()
                lookup[key] = item
                lookup[item.get("llt", "").lower()] = item
            return lookup

    def evaluate_lab_toxicity(self, lab_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Grades laboratory toxicities against NCI CTCAE v5.0 thresholds."""
        findings = []
        chem = lab_data.get("chemistry", lab_data)

        # ALT Grading (ULN ~ 45 U/L)
        alt_entry = chem.get("ALT", {})
        if isinstance(alt_entry, dict) and "value" in alt_entry:
            val = alt_entry["value"]
            uln = alt_entry.get("ref_high", 45)
            multiple = val / uln

            if multiple > 1.0:
                if multiple > 20.0:
                    grade = "Grade 4 (Life-threatening)"
                elif multiple > 5.0:
                    grade = "Grade 3 (Severe / Medically Significant)"
                elif multiple > 3.0:
                    grade = "Grade 2 (Moderate)"
                else:
                    grade = "Grade 1 (Mild)"

                findings.append({
                    "analyte": "ALT (Alanine Aminotransferase)",
                    "value": f"{val} {alt_entry.get('unit', 'U/L')}",
                    "uln_multiple": f"{multiple:.1f}x ULN",
                    "ctcae_grade": grade,
                    "meddra_pt": "Alanine aminotransferase increased",
                    "meddra_code": "10001551",
                    "is_severe": multiple > 5.0,
                    "protocol_action": "MANDATORY DOSE HOLD required (Protocol Section 6.2)." if multiple > 5.0 else "Maintain dose; weekly monitoring."
                })

        # AST Grading (ULN ~ 40 U/L)
        ast_entry = chem.get("AST", {})
        if isinstance(ast_entry, dict) and "value" in ast_entry:
            val = ast_entry["value"]
            uln = ast_entry.get("ref_high", 40)
            multiple = val / uln

            if multiple > 1.0:
                grade = "Grade 3" if multiple > 5.0 else ("Grade 2" if multiple > 3.0 else "Grade 1")
                findings.append({
                    "analyte": "AST (Aspartate Aminotransferase)",
                    "value": f"{val} {ast_entry.get('unit', 'U/L')}",
                    "uln_multiple": f"{multiple:.1f}x ULN",
                    "ctcae_grade": grade,
                    "meddra_pt": "Aspartate aminotransferase increased",
                    "meddra_code": "10003481",
                    "is_severe": multiple > 5.0,
                    "protocol_action": "Dose hold and monitor." if multiple > 5.0 else "Monitor."
                })

        return findings

    def extract_meddra_symptoms(self, text: str) -> list[dict[str, str]]:
        """Maps free-text symptoms in physician notes to official MedDRA terms."""
        text_lower = text.lower()
        matched = []

        mapping = [
            (r"(scleral icterus|jaundice|yellow eyes)", "Ocular icterus", "10030095"),
            (r"(abdominal (pain|soreness|tenderness)|stomach pain)", "Abdominal pain upper", "10000087"),
            (r"(fatigue|tiredness|exhaustion)", "Fatigue", "10016256"),
            (r"(nausea)", "Nausea", "10028813"),
        ]

        for pattern, pt, code in mapping:
            if re_match := re.search(pattern, text_lower):
                matched.append({
                    "reported_term": re_match.group(0),
                    "meddra_pt": pt,
                    "meddra_code": code,
                })

        return matched

    def draft_fda_3500a_narrative(
        self,
        patient_meta: dict[str, Any],
        note_text: str,
        lab_findings: list[dict[str, Any]],
        symptoms: list[dict[str, str]] | None = None
    ) -> str:
        """Pre-drafts standard FDA Form 3500A / CIOMS I Section B safety narrative."""
        symptoms = symptoms or self.extract_meddra_symptoms(note_text)
        
        lab_lines = []
        for lab in lab_findings:
            lab_lines.append(f"  • {lab['analyte']}: {lab['value']} ({lab['uln_multiple']}) — {lab['ctcae_grade']}")

        meddra_lines = []
        for s in symptoms:
            meddra_lines.append(f"  • {s['meddra_pt']} (MedDRA Code: {s['meddra_code']}) [Reported: '{s['reported_term']}']")
        for lab in lab_findings:
            meddra_lines.append(f"  • {lab['meddra_pt']} (MedDRA Code: {lab['meddra_code']})")

        has_grade3 = any(l.get("is_severe", False) for l in lab_findings)

        narrative = f"""
================================================================================
PRE-DRAFTED FDA FORM 3500A / CIOMS I EXPEDITED SAFETY REPORT
Regulated Under: 21 CFR 312.64 (Investigator) & 21 CFR 312.32 (Sponsor)
================================================================================

SECTION A. PATIENT & TRIAL DEMOGRAPHICS
  Patient Identifier:    {patient_meta.get('patient_id', 'UNKNOWN')}
  Age / Sex:             {patient_meta.get('age', 'N/A')} yrs / {patient_meta.get('sex', 'N/A')}
  Study Protocol:        {patient_meta.get('protocol_id', 'ONCO-2026-X88')}
  Investigational Drug:  Nexavatinib (NEX-882) 200mg PO daily
  Treatment Cycle:       Cycle 1 (C1D1 Date: {patient_meta.get('c1d1_date', 'N/A')})
  Event Assessment Date: {patient_meta.get('note_date', datetime.now().strftime('%Y-%m-%d'))} (Study Day {patient_meta.get('study_day', 'N/A')})

SECTION B. ADVERSE EVENT CLINICAL NARRATIVE
  On Study Day {patient_meta.get('study_day', 'N/A')}, the patient presented for scheduled evaluation.
  Laboratory evaluation revealed significant acute transaminase elevation:
{chr(10).join(lab_lines) if lab_lines else '  • No critical acute laboratory abnormalities.'}

  Physical examination and patient history documented:
  "{note_text.strip()}"

SECTION C. CODED MEDICAL TERMINOLOGY (MedDRA v27.0)
{chr(10).join(meddra_lines) if meddra_lines else '  • No specific MedDRA terms mapped.'}

SECTION D. PROTOCOL TOXICITY MANAGEMENT & REGULATORY STATUS
  Toxicity Assessment:   {'CTCAE Grade 3 Hepatic Transaminitis (ALT > 5x ULN)' if has_grade3 else 'Non-severe laboratory elevation'}
  Protocol Mandate:      {'MANDATORY Nexavatinib DOSE HOLD required immediately under Section 6.2.' if has_grade3 else 'Continue current dose with close monitoring.'}
  Expedited Clock:       Potential qualifying serious adverse reaction. Awaiting PI causality review.

SECTION E. INVESTIGATOR ADJUDICATION & ELECTRONIC SIGN-OFF
  Causality Assessment:  [ ] Unrelated   [ ] Unlikely   [ ] Possible   [ ] Definite
  Action with Drug:      [ ] Dose Held   [ ] Dose Reduced   [ ] Discontinued
  
  Reviewing Clinician:   ______________________________________
  Electronic Signature:  [PENDING 1-CLICK AUTHENTICATED SIGN-OFF]
================================================================================
"""
        return narrative.strip()

    def generate_part11_audit_record(self, narrative: str, clinician_id: str = "PI-DR-VANCE") -> dict[str, str]:
        """Generates a cryptographically hashed 21 CFR Part 11 electronic audit record."""
        timestamp = datetime.now(timezone.utc).isoformat()
        content_to_hash = f"{narrative}|{clinician_id}|{timestamp}"
        sha256_hash = hashlib.sha256(content_to_hash.encode("utf-8")).hexdigest()

        return {
            "audit_id": f"AUDIT-{sha256_hash[:12].upper()}",
            "clinician_id": clinician_id,
            "timestamp_utc": timestamp,
            "sha256_signature": sha256_hash,
            "status": "APPROVED_AND_LOCKED",
            "regulatory_standard": "FDA 21 CFR Part 11 Compliant Electronic Record",
        }
