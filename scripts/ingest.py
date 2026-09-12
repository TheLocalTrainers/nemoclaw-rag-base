"""Ingest a Markdown/text corpus into MongoDB."""

from __future__ import annotations

import argparse
from pathlib import Path

from rag.config import load_config
from rag.env import load_dotenv
from rag.pipeline import ingest_corpus
from rag.store import open_store


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    config = load_config()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path(config.corpus.dir))
    parser.add_argument("--uri", default=None, help="MongoDB URI override")
    parser.add_argument("--database", default=None, help="MongoDB database override")
    parser.add_argument("--collection", default=None, help="MongoDB collection override")
    parser.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Update in place and drop chunks for files no longer present",
    )
    args = parser.parse_args(argv)

    with open_store(
        uri=args.uri,
        database=args.database,
        collection=args.collection,
        config=config,
    ) as store:
        n = ingest_corpus(args.corpus, store, rebuild=not args.no_rebuild)
        print(
            f"Ingested {n} chunks from {args.corpus} → "
            f"{store.database_name}.{store.collection_name} ({store.count()} total)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
