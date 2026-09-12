"""One-command smoke test: ingest fixture corpus into MongoDB and retrieve a known fact.

Runs against the dedicated smoke database from nemoclaw-rag.toml so it never
touches the working index.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rag.config import load_config
from rag.env import load_dotenv
from rag.pipeline import answer_from_context, ingest_corpus, retrieve
from rag.store import open_store

_CONFIG = load_config()

EXPECTED_TOKEN = _CONFIG.project.smoke_token
SMOKE_QUESTION = _CONFIG.project.smoke_question
SMOKE_TOKEN_QUERY = _CONFIG.project.smoke_token


def run_smoke(corpus: Path, *, uri: str | None = None) -> None:
    load_dotenv()
    config = load_config()
    with open_store(
        uri=uri,
        database=config.mongodb.smoke_database,
        collection=config.mongodb.smoke_collection,
        config=config,
    ) as store:
        n = ingest_corpus(corpus, store, rebuild=True)
        if n < 1:
            raise AssertionError(f"Expected at least 1 chunk, got {n}")

        hits = retrieve(store, config.project.smoke_question, top_k=3)
        if not hits:
            raise AssertionError("Retrieval returned no hits for natural-language question")

        token_hits = retrieve(store, config.project.smoke_token, top_k=3)
        if not token_hits:
            raise AssertionError(
                f"Retrieval returned no hits for token query {config.project.smoke_token!r}"
            )

        answer = answer_from_context(config.project.smoke_question, hits)
        joined = "\n".join(h.text for h in hits + token_hits)
        if config.project.smoke_token not in joined and config.project.smoke_token not in answer:
            raise AssertionError(
                f"Expected token {config.project.smoke_token!r} missing from retrieval.\n"
                f"Hits:\n{joined}\nAnswer:\n{answer}"
            )
        print("SMOKE OK")
        print(f"  config={config.source_path}")
        print(f"  mongo={store.uri}")
        print(f"  db={store.database_name}.{store.collection_name}")
        print(f"  chunks={n}")
        print(f"  top_path={hits[0].path}")
        print(f"  found={config.project.smoke_token}")


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    config = load_config()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(__file__).resolve().parents[1] / config.corpus.dir,
    )
    parser.add_argument("--uri", default=None, help="MongoDB URI override")
    args = parser.parse_args(argv)
    try:
        run_smoke(args.corpus, uri=args.uri)
    except Exception as exc:  # noqa: BLE001 - surface any smoke failure clearly
        print(f"SMOKE FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
