"""OpenClaw Always-On File Watcher Daemon for CareClaw.

Runs as an autonomous background daemon on the Dell Pro Max / NVIDIA GB10.
Monitors the local research drop folder ('incoming_records/').
When an unstructured EHR note or lab JSON drops in, it triggers ProtocolClaw
and SafetyClaw within milliseconds, logging audit trails to 'audit_logs/'.
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

    def process_file(self, file_path: Path) -> dict[str, Any]:
        """Process a single incoming file through both CareClaw agent sentinels."""
        print(f"[!] CareClaw Daemon: Ingesting '{file_path.name}'...")

        note_content = ""
        lab_data = {}

        if file_path.suffix.lower() == ".txt":
            with open(file_path, "r", encoding="utf-8") as f:
                note_content = f.read()
        elif file_path.suffix.lower() == ".json":
            with open(file_path, "r", encoding="utf-8") as f:
                lab_data = json.load(f)

        # Baseline metadata for PT-004 demonstration
        patient_meta = {
            "patient_id": lab_data.get("patient_id", "PT-004"),
            "protocol_id": lab_data.get("study_protocol", "ONCO-2026-X88"),
            "c1d1_date": "2026-08-20",
            "note_date": lab_data.get("draw_date", "2026-09-08"),
            "study_day": lab_data.get("study_day", 19),
            "age": 62,
            "sex": "Male",
        }

        # 1. Execute ProtocolClaw (Use Case 1: Deviation Sentinel)
        deviations = self.protocol_agent.audit_record(note_content, patient_meta)
        print(f"    [+] ProtocolClaw identified {len(deviations)} protocol deviation(s).")

        # 2. Execute SafetyClaw (Use Case 2: Adverse Event Scribing)
        # Check lab toxicity if lab values provided, else check mock
        if not lab_data:
            mock_chem = {"chemistry": {"ALT": {"value": 265, "unit": "U/L", "ref_high": 45}}}
            lab_findings = self.safety_agent.evaluate_lab_toxicity(mock_chem)
        else:
            lab_findings = self.safety_agent.evaluate_lab_toxicity(lab_data)

        symptoms = self.safety_agent.extract_meddra_symptoms(note_content)
        draft_narrative = self.safety_agent.draft_fda_3500a_narrative(
            patient_meta, note_content, lab_findings, symptoms
        )
        print(f"    [+] SafetyClaw generated draft FDA Form 3500A narrative.")

        # 3. Create Audit Record
        audit_record = self.safety_agent.generate_part11_audit_record(draft_narrative)

        event_payload = {
            "file_name": file_path.name,
            "patient_meta": patient_meta,
            "deviations": deviations,
            "lab_findings": lab_findings,
            "symptoms_mapped": symptoms,
            "draft_narrative": draft_narrative,
            "audit_record": audit_record,
        }

        # Log event to audit_logs
        log_file = self.audit_dir / "careclaw_events.jsonl"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_payload) + "\n")

        # Move to processed folder
        target_path = self.processed_dir / file_path.name
        shutil.move(str(file_path), str(target_path))
        print(f"    [✓] Ingestion complete. Archived to '{target_path}'.\n")

        return event_payload

    def process_all_pending(self) -> list[dict[str, Any]]:
        """Process all pending files in the watch directory (single pass)."""
        results = []
        for item in sorted(self.watch_dir.iterdir()):
            if item.is_file() and item.suffix.lower() in [".txt", ".json"]:
                results.append(self.process_file(item))
        return results

    def start_polling(self, interval_seconds: float = 2.0) -> None:
        """Continuous polling loop for always-on autonomous daemon operation."""
        print(f"[*] OpenClaw Daemon initialized on GB10.")
        print(f"[*] Watching directory: '{self.watch_dir.resolve()}' (interval: {interval_seconds}s)")
        print(f"[*] Press Ctrl+C to terminate.")

        try:
            while True:
                self.process_all_pending()
                time.sleep(interval_seconds)
        except KeyboardInterrupt:
            print("\n[*] Daemon stopped by user.")


if __name__ == "__main__":
    watcher = OpenClawFileWatcher()
    watcher.start_polling()
