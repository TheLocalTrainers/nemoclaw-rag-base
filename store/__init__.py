"""CareClaw operational data store (MongoDB-backed).

The single source of truth for patient records, intake cases, and the
append-only agent/PI event log — replacing the flat `audit_logs/*.jsonl` files.
Shares the Mongo instance with the RAG corpus but uses a dedicated database.
"""

from __future__ import annotations

from store.careclaw_store import CareClawStore, open_store

__all__ = ["CareClawStore", "open_store"]
