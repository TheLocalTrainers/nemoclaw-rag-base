"""Markdown chunking for local RAG. Defaults come from rag.config."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rag.config import load_config


@dataclass(frozen=True)
class Chunk:
    path: str
    chunk_id: int
    text: str
    start_line: int
    end_line: int


def iter_markdown_files(corpus_dir: Path) -> list[Path]:
    extensions = set(load_config().corpus.extensions)
    root = corpus_dir.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Corpus directory not found: {root}")

    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in extensions or not path.is_file():
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            # Refuse symlink / path escape outside the corpus root.
            continue
        files.append(resolved)
    return files


def relative_corpus_path(path: Path, corpus_dir: Path) -> str:
    return path.resolve().relative_to(corpus_dir.resolve()).as_posix()


def chunk_markdown(
    path: Path,
    *,
    corpus_dir: Path | None = None,
    max_chars: int | None = None,
    overlap: int | None = None,
) -> list[Chunk]:
    """Split a Markdown/text file into overlapping character windows."""
    chunking = load_config().chunking
    max_chars = chunking.max_chars if max_chars is None else max_chars
    overlap = chunking.overlap if overlap is None else overlap

    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if not lines:
        return []

    stored_path = (
        relative_corpus_path(path, corpus_dir) if corpus_dir is not None else path.as_posix()
    )

    chunks: list[Chunk] = []
    buf: list[str] = []
    start_line = 1
    chunk_id = 0

    def flush(end_line: int) -> None:
        nonlocal chunk_id, buf, start_line
        text = "\n".join(buf).strip()
        if not text:
            buf = []
            start_line = end_line + 1
            return
        chunks.append(
            Chunk(
                path=stored_path,
                chunk_id=chunk_id,
                text=text,
                start_line=start_line,
                end_line=end_line,
            )
        )
        chunk_id += 1
        if overlap > 0 and text:
            overlap_text = text[-overlap:]
            buf = [overlap_text]
            start_line = max(1, end_line - overlap_text.count("\n"))
        else:
            buf = []
            start_line = end_line + 1

    for idx, line in enumerate(lines, start=1):
        candidate = "\n".join(buf + [line]) if buf else line
        if len(candidate) > max_chars and buf:
            flush(idx - 1)
            buf.append(line)
        else:
            buf.append(line)
            if not line.strip() and len("\n".join(buf)) >= max_chars // 2:
                flush(idx)

    if buf:
        flush(len(lines))
    return chunks
