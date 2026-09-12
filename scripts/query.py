"""Query the MongoDB RAG index and print top hits / optional model answer."""

from __future__ import annotations

import argparse
import sys

from rag.config import load_config
from rag.env import load_dotenv
from rag.pipeline import (
    GenerateError,
    answer_from_context,
    format_context,
    generate_with_model,
    retrieve,
)
from rag.store import open_store


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    config = load_config()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--uri", default=None, help="MongoDB URI override")
    parser.add_argument("--database", default=None, help="MongoDB database override")
    parser.add_argument("--collection", default=None, help="MongoDB collection override")
    parser.add_argument("--top-k", type=int, default=config.retrieval.top_k)
    parser.add_argument(
        "--generate",
        action="store_true",
        help=(
            f"Call the configured OpenAI-compatible model "
            f"(requires {config.model.api_key_env}); fails loud on error"
        ),
    )
    args = parser.parse_args(argv)

    with open_store(
        uri=args.uri,
        database=args.database,
        collection=args.collection,
        config=config,
    ) as store:
        hits = retrieve(store, args.query, top_k=args.top_k)

    if not hits:
        print("No hits.", file=sys.stderr)
        return 1

    print("=== Context ===")
    print(format_context(hits))
    print()

    if args.generate:
        try:
            result = generate_with_model(args.query, hits, config=config)
        except GenerateError as exc:
            print(f"GENERATE FAIL: {exc}", file=sys.stderr)
            return 2
        print(f"=== Model answer ({result.model}) ===")
        print(result.text)
        return 0

    print("=== Extractive answer ===")
    print(answer_from_context(args.query, hits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
