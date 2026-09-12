"""Unit tests for the MongoDB RAG smoke path."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from rag.pipeline import answer_from_context, ingest_corpus, retrieve
from rag.store import open_store
from scripts.smoke_test import EXPECTED_TOKEN, SMOKE_QUESTION, SMOKE_TOKEN_QUERY, run_smoke

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus"


@unittest.skipUnless(
    os.getenv("RUN_MONGO_TESTS", "1") == "1",
    "Set RUN_MONGO_TESTS=1 (default) with MongoDB available",
)
class RagSmokeTests(unittest.TestCase):
    def test_smoke_retrieve_known_fact(self) -> None:
        with open_store(database="nemoclaw_rag_smoke", collection="chunks_unittest") as store:
            n = ingest_corpus(CORPUS, store, rebuild=True)
            self.assertGreaterEqual(n, 1)
            hits = retrieve(store, SMOKE_QUESTION, top_k=3)
            self.assertTrue(hits)
            self.assertTrue(any(EXPECTED_TOKEN in h.text for h in hits))
            token_hits = retrieve(store, SMOKE_TOKEN_QUERY, top_k=3)
            self.assertTrue(token_hits)
            answer = answer_from_context(SMOKE_QUESTION, hits)
            self.assertIn(EXPECTED_TOKEN, answer)

    def test_run_smoke_entrypoint(self) -> None:
        run_smoke(CORPUS)


if __name__ == "__main__":
    unittest.main()
