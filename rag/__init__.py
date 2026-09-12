"""Local Markdown → MongoDB text-index RAG scaffold for NemoClaw agents."""

from rag.config import Config, load_config
from rag.env import load_dotenv
from rag.pipeline import (
    GenerateError,
    GenerateResult,
    answer_from_context,
    format_context,
    generate_with_model,
    ingest_corpus,
    retrieve,
)
from rag.store import Hit, RagStore, open_store

__all__ = [
    "Config",
    "GenerateError",
    "GenerateResult",
    "Hit",
    "RagStore",
    "answer_from_context",
    "format_context",
    "generate_with_model",
    "ingest_corpus",
    "load_config",
    "load_dotenv",
    "open_store",
    "retrieve",
]
