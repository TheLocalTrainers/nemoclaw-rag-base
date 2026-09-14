"""Show the CareClaw MongoDB setup — databases, collections, counts, indexes,
and a sample document from each. Read-only; safe to run live in a demo.

Run:  .venv/bin/python -m scripts.show_db     (or: make show-db)
"""

from __future__ import annotations

import json

from pymongo import MongoClient

from rag.config import load_config

cfg = load_config()
URI = cfg.mongodb.uri
CARECLAW_DB = cfg.careclaw.database          # operational data
RAG_DB = cfg.mongodb.database                # RAG corpus

BAR = "─" * 72


def _trim(doc: dict, limit: int = 240) -> dict:
    """Shorten long string values so a sample doc prints on a few lines."""
    out = {}
    for k, v in doc.items():
        if isinstance(v, str) and len(v) > limit:
            out[k] = v[:limit] + f"… ({len(v)} chars)"
        elif isinstance(v, list) and len(v) > 3:
            out[k] = v[:3] + [f"… (+{len(v) - 3} more)"]
        else:
            out[k] = v
    return out


def show_db(client: MongoClient, name: str, label: str) -> None:
    db = client[name]
    print(f"\n{BAR}\nDATABASE  {name}   ({label})\n{BAR}")
    colls = sorted(db.list_collection_names())
    if not colls:
        print("  (empty)")
        return
    for c in colls:
        col = db[c]
        count = col.count_documents({})
        idx = [i["name"] for i in col.list_indexes()]
        print(f"\n  ▸ {c}   —   {count} document(s)")
        print(f"      indexes: {', '.join(idx)}")
        sample = col.find_one({}, {"_id": 0})
        if sample:
            print("      sample:")
            for line in json.dumps(_trim(sample), indent=2, default=str).splitlines():
                print("        " + line)


def main() -> int:
    print(f"MongoDB @ {URI}")
    client = MongoClient(URI, serverSelectionTimeoutMS=3000)
    client.admin.command("ping")
    print("connection: OK")
    show_db(client, CARECLAW_DB, "operational: patients / cases / events / care_team / patient_reports")
    show_db(client, RAG_DB, "RAG corpus: chunks (protocol docs, text-indexed)")
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
