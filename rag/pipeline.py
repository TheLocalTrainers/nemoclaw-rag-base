"""Ingest / retrieve / optional LLM answer helpers.

Model and retrieval settings resolve through rag.config, so nemoclaw-rag.toml
and environment overrides are the only places to change behaviour.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from rag.chunk import chunk_markdown, iter_markdown_files, relative_corpus_path
from rag.config import Config, load_config
from rag.store import Hit, RagStore


class GenerateError(RuntimeError):
    """Raised when model generation is requested but cannot complete."""


@dataclass(frozen=True)
class GenerateResult:
    text: str
    model: str
    base_url: str


def ingest_corpus(corpus_dir: Path, store: RagStore, *, rebuild: bool = True) -> int:
    corpus_dir = Path(corpus_dir)
    files = iter_markdown_files(corpus_dir)
    if not files:
        raise FileNotFoundError(f"No indexable files found under {corpus_dir.resolve()}")

    if rebuild:
        store.clear()

    total = 0
    keep_paths: set[str] = set()
    for path in files:
        keep_paths.add(relative_corpus_path(path, corpus_dir))
        total += store.upsert_chunks(chunk_markdown(path, corpus_dir=corpus_dir))

    if not rebuild:
        store.delete_paths_except(keep_paths)
    return total


def retrieve(store: RagStore, query: str, *, top_k: int | None = None) -> list[Hit]:
    return store.search(query, top_k=top_k)


def format_context(hits: list[Hit]) -> str:
    blocks: list[str] = []
    for i, hit in enumerate(hits, start=1):
        blocks.append(f"[{i}] {hit.path}:{hit.start_line}-{hit.end_line}\n{hit.text.strip()}")
    return "\n\n".join(blocks)


def answer_from_context(query: str, hits: list[Hit]) -> str:
    """Deterministic extractive answer, used when no model is configured."""
    if not hits:
        return "No matching context found in the MongoDB RAG index."
    best = hits[0]
    return (
        f"Top match from {best.path} (lines {best.start_line}-{best.end_line}):\n"
        f"{best.text.strip()}"
    )


def generate_with_model(
    query: str,
    hits: list[Hit],
    *,
    config: Config | None = None,
) -> GenerateResult:
    """Call an OpenAI-compatible chat completion using retrieved context.

    Raises GenerateError when configuration is missing or the provider call fails,
    so callers never present an ungrounded or fake "model answer".
    """
    model_cfg = (config or load_config()).model
    api_key = model_cfg.api_key
    if not api_key:
        raise GenerateError(
            f"{model_cfg.api_key_env} is not set. "
            f"Add it to .env or export it before requesting generation."
        )
    if not hits:
        raise GenerateError("No retrieval hits available to ground the model answer.")

    payload = {
        "model": model_cfg.model,
        "temperature": model_cfg.temperature,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Answer using only the provided context. "
                    "If the answer is not present, say you do not know."
                ),
            },
            {
                "role": "user",
                "content": f"Context:\n{format_context(hits)}\n\nQuestion: {query}",
            },
        ],
    }
    req = urllib.request.Request(
        f"{model_cfg.base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=model_cfg.timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise GenerateError(f"Provider HTTP {exc.code}: {body[:400]}") from exc
    except urllib.error.URLError as exc:
        raise GenerateError(f"Provider request failed: {exc.reason}") from exc
    except TimeoutError as exc:
        raise GenerateError(
            f"Provider request timed out after {model_cfg.timeout_seconds}s"
        ) from exc

    try:
        body = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GenerateError(f"Provider returned non-JSON response: {raw[:200]!r}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GenerateError(f"Unexpected provider response shape: {body!r}") from exc

    if content is None:
        raise GenerateError("Provider returned null message content")
    text = str(content).strip()
    if not text:
        raise GenerateError("Provider returned empty message content")
    return GenerateResult(text=text, model=model_cfg.model, base_url=model_cfg.base_url)
