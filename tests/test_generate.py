"""Unit tests for model generation readiness (no live provider required)."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from rag.env import load_dotenv
from rag.pipeline import GenerateError, generate_with_model
from rag.store import Hit
from scripts import query as query_cli


def _hit() -> Hit:
    return Hit(
        path="fixtures/neon-beacon.md",
        chunk_id=0,
        text="The beacon code is NEON-BEACON-42.",
        start_line=1,
        end_line=2,
        score=1.0,
    )


class EnvLoaderTests(unittest.TestCase):
    def test_load_dotenv_sets_missing_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("OPENAI_API_KEY=from-file\nOPENAI_MODEL=tiny\n", encoding="utf-8")
            os.environ.pop("OPENAI_API_KEY", None)
            os.environ.pop("OPENAI_MODEL", None)
            loaded = load_dotenv(env_path)
            self.assertEqual(loaded, env_path)
            self.assertEqual(os.environ["OPENAI_API_KEY"], "from-file")
            self.assertEqual(os.environ["OPENAI_MODEL"], "tiny")


class GenerateTests(unittest.TestCase):
    def test_missing_api_key_raises(self) -> None:
        os.environ.pop("OPENAI_API_KEY", None)
        with self.assertRaises(GenerateError):
            generate_with_model("beacon?", [_hit()])

    def test_empty_hits_raises(self) -> None:
        os.environ["OPENAI_API_KEY"] = "sk-test"
        with self.assertRaises(GenerateError):
            generate_with_model("beacon?", [])

    def test_successful_generate(self) -> None:
        os.environ["OPENAI_API_KEY"] = "sk-test"
        os.environ["OPENAI_BASE_URL"] = "https://example.test/v1"
        os.environ["OPENAI_MODEL"] = "tiny-model"
        payload = {
            "choices": [{"message": {"content": "The code is NEON-BEACON-42."}}],
        }
        fake_resp = mock.MagicMock()
        fake_resp.read.return_value = json.dumps(payload).encode("utf-8")
        fake_resp.__enter__.return_value = fake_resp
        fake_resp.__exit__.return_value = False
        with mock.patch("urllib.request.urlopen", return_value=fake_resp):
            result = generate_with_model("beacon?", [_hit()])
        self.assertIn("NEON-BEACON-42", result.text)
        self.assertEqual(result.model, "tiny-model")

    def test_null_content_raises(self) -> None:
        os.environ["OPENAI_API_KEY"] = "sk-test"
        payload = {"choices": [{"message": {"content": None}}]}
        fake_resp = mock.MagicMock()
        fake_resp.read.return_value = json.dumps(payload).encode("utf-8")
        fake_resp.__enter__.return_value = fake_resp
        fake_resp.__exit__.return_value = False
        with mock.patch("urllib.request.urlopen", return_value=fake_resp):
            with self.assertRaises(GenerateError):
                generate_with_model("beacon?", [_hit()])


class QueryGenerateCliTests(unittest.TestCase):
    def test_generate_without_key_exits_nonzero(self) -> None:
        os.environ.pop("OPENAI_API_KEY", None)
        hits = [_hit()]
        with mock.patch("scripts.query.open_store") as open_store:
            store = mock.MagicMock()
            open_store.return_value.__enter__.return_value = store
            open_store.return_value.__exit__.return_value = False
            with mock.patch("scripts.query.retrieve", return_value=hits):
                with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                    code = query_cli.main(["beacon?", "--generate"])
        self.assertEqual(code, 2)
        self.assertIn("GENERATE FAIL", err.getvalue())


if __name__ == "__main__":
    unittest.main()
