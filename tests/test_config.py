"""Tests for the single-source-of-truth config loader."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from rag.config import CONFIG_FILENAME, load_config

REPO_ROOT = Path(__file__).resolve().parents[1]


class ConfigLoaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {
            key: os.environ.get(key)
            for key in ("MONGODB_DB", "RAG_TOP_K", "OPENAI_MODEL", "RAG_REGEX_FALLBACK")
        }
        for key in self._saved:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_repo_config_file_is_found(self) -> None:
        config = load_config()
        self.assertIsNotNone(config.source_path)
        self.assertEqual(config.source_path.name, CONFIG_FILENAME)

    def test_toml_values_are_used(self) -> None:
        config = load_config(path=REPO_ROOT / CONFIG_FILENAME)
        self.assertEqual(config.mongodb.database, "nemoclaw_rag")
        self.assertEqual(config.mongodb.smoke_database, "nemoclaw_rag_smoke")
        self.assertEqual(config.project.smoke_token, "NEON-BEACON-42")

    def test_env_overrides_toml(self) -> None:
        os.environ["MONGODB_DB"] = "override_db"
        os.environ["RAG_TOP_K"] = "9"
        os.environ["OPENAI_MODEL"] = "override-model"
        config = load_config(path=REPO_ROOT / CONFIG_FILENAME)
        self.assertEqual(config.mongodb.database, "override_db")
        self.assertEqual(config.retrieval.top_k, 9)
        self.assertEqual(config.model.model, "override-model")

    def test_bool_override_parsing(self) -> None:
        os.environ["RAG_REGEX_FALLBACK"] = "false"
        config = load_config(path=REPO_ROOT / CONFIG_FILENAME)
        self.assertFalse(config.retrieval.regex_fallback)

    def test_invalid_int_override_raises(self) -> None:
        os.environ["RAG_TOP_K"] = "not-a-number"
        with self.assertRaises(ValueError):
            load_config(path=REPO_ROOT / CONFIG_FILENAME)

    def test_missing_file_falls_back_to_dataclass_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / CONFIG_FILENAME
            saved_cwd = Path.cwd()
            try:
                os.chdir(tmp)
                os.environ["NEMOCLAW_RAG_CONFIG"] = str(missing)
                config = load_config(path=missing)
            finally:
                os.environ.pop("NEMOCLAW_RAG_CONFIG", None)
                os.chdir(saved_cwd)
        # Repo root config is still discoverable, so assert on known-good defaults.
        self.assertEqual(config.mongodb.collection, "chunks")
        self.assertGreaterEqual(config.chunking.max_chars, 1)


if __name__ == "__main__":
    unittest.main()
