"""Unit tests for ProtocolClaw protocol deviation sentinel."""

import unittest
from agents.protocol_claw import ProtocolClaw


class TestProtocolClaw(unittest.TestCase):
    def setUp(self):
        self.agent = ProtocolClaw()
        self.base_meta = {
            "patient_id": "PT-004",
            "protocol_id": "ONCO-2026-X88",
            "c1d1_date": "2026-08-20",
            "note_date": "2026-09-08", # Study Day 19 (19 days from Aug 20)
            "study_day": 19,
        }

    def test_detects_out_of_window_visit(self):
        note = "Patient presents for delayed Cycle 1 Day 14 visit today."
        deviations = self.agent.audit_record(note, self.base_meta)

        window_devs = [d for d in deviations if d["category"] == "Visit Window Non-Compliance"]
        self.assertEqual(len(window_devs), 1)
        self.assertEqual(window_devs[0]["severity"], "MAJOR")
        self.assertIn("Study Day 19", window_devs[0]["details"])

    def test_allows_in_window_visit(self):
        in_window_meta = dict(self.base_meta)
        in_window_meta["note_date"] = "2026-09-03"
        in_window_meta["study_day"] = 15
        note = "Patient presents for Cycle 1 Day 14 safety blood draw."

        deviations = self.agent.audit_record(note, in_window_meta)
        window_devs = [d for d in deviations if d["category"] == "Visit Window Non-Compliance"]
        self.assertEqual(len(window_devs), 0)

    def test_detects_prohibited_cyp3a4_inhibitor(self):
        note = "Patient started oral ketoconazole 200mg daily for nail infection."
        deviations = self.agent.audit_record(note, self.base_meta)

        drug_devs = [d for d in deviations if d["category"] == "Prohibited Concomitant Medication"]
        self.assertEqual(len(drug_devs), 1)
        self.assertEqual(drug_devs[0]["detected_drug"], "Ketoconazole")
        self.assertEqual(drug_devs[0]["severity"], "CRITICAL")
        self.assertIn("Section 5.2.1", drug_devs[0]["protocol_section"])

    def test_detects_prohibited_anticoagulant(self):
        note = "Patient was prescribed warfarin by primary cardiologist."
        deviations = self.agent.audit_record(note, self.base_meta)

        drug_devs = [d for d in deviations if d["category"] == "Prohibited Concomitant Medication"]
        self.assertEqual(len(drug_devs), 1)
        self.assertEqual(drug_devs[0]["detected_drug"], "Warfarin")


if __name__ == "__main__":
    unittest.main()
