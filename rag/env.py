"""Minimal .env loader so OPENAI_* / MONGODB_* from `.env` work in CLIs."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(path: Path | None = None, *, override: bool = False) -> Path | None:
    """Load KEY=VALUE pairs from a .env file into os.environ.

    - Ignores blank lines and `#` comments
    - Does not override existing environment variables unless override=True
    - Returns the path loaded, or None if no file was found
    """
    candidates: list[Path] = []
    if path is not None:
        candidates.append(Path(path))
    else:
        here = Path.cwd() / ".env"
        repo = Path(__file__).resolve().parents[1] / ".env"
        candidates.extend([here, repo])

    for candidate in candidates:
        if not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if not key:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            if override or key not in os.environ:
                os.environ[key] = value
        return candidate
    return None
