"""Unit tests for SafetyClaw adverse event scribing agent."""

import unittest
from agents.safety_claw import SafetyClaw


class TestSafetyClaw(unittest.TestCase):
    def setUp(self):
        self.agent = SafetyClaw()
        self.patient_meta = {
            "patient_id": "PT-004",
            "protocol_id": "ONCO-2026-X88",
            "c1d1_date": "2026-08-20",
            "note_date": "2026-09-08",
            "study_day": 19,
            "age": 62,
            "sex": "Male",
        }

    def test_grade_3_alt_toxicity_grading(self):
        lab_data = {
            "chemistry": {
                "ALT": {"value": 265, "unit": "U/L", "ref_high": 45}
            }
        }
        findings = self.agent.evaluate_lab_toxicity(lab_data)

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["meddra_code"], "10001551")
        self.assertIn("Grade 3", findings[0]["ctcae_grade"])
        self.assertTrue(findings[0]["is_severe"])
        self.assertIn("MANDATORY DOSE HOLD", findings[0]["protocol_action"])

    def test_extract_meddra_symptoms(self):
        note = "Patient presents with scleral icterus, upper abdominal tenderness, and severe fatigue."
        symptoms = self.agent.extract_meddra_symptoms(note)

        pts = [s["meddra_pt"] for s in symptoms]
        self.assertIn("Ocular icterus", pts)
        self.assertIn("Abdominal pain upper", pts)
        self.assertIn("Fatigue", pts)

    def test_draft_fda_3500a_narrative_generation(self):
        lab_data = {"chemistry": {"ALT": {"value": 265, "unit": "U/L", "ref_high": 45}}}
        findings = self.agent.evaluate_lab_toxicity(lab_data)
        note = "Patient reports right-upper-quadrant abdominal soreness."

        narrative = self.agent.draft_fda_3500a_narrative(self.patient_meta, note, findings)
        self.assertIn("FDA FORM 3500A", narrative)
        self.assertIn("PT-004", narrative)
        self.assertIn("Grade 3", narrative)
        self.assertIn("Alanine aminotransferase increased", narrative)

    def test_generate_part11_audit_record(self):
        narrative = "Sample clinical narrative for verification"
        audit = self.agent.generate_part11_audit_record(narrative, clinician_id="DR-TEST")

        self.assertEqual(audit["clinician_id"], "DR-TEST")
        self.assertEqual(audit["status"], "APPROVED_AND_LOCKED")
        self.assertEqual(len(audit["sha256_signature"]), 64)


if __name__ == "__main__":
    unittest.main()
