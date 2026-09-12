"""Minimal proof-of-connection to a local vLLM OpenAI-compatible endpoint.

Uses only httpx (already a project dependency). Run:

    .venv/bin/python -m scripts.vllm_smoke

Env overrides: OPENAI_BASE_URL (default http://localhost:8000/v1),
OPENAI_MODEL (default qwen3.8-27b), OPENAI_API_KEY (default EMPTY).
"""

from __future__ import annotations

import os

import httpx

BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:8000/v1").rstrip("/")
MODEL = os.getenv("OPENAI_MODEL", "qwen3.8-27b")
API_KEY = os.getenv("OPENAI_API_KEY", "EMPTY") or "EMPTY"

payload = {
    "model": MODEL,
    "temperature": 0,
    "max_tokens": 512,  # reasoning model: leave headroom past the thinking tokens
    "messages": [{"role": "user", "content": "Reply with exactly: CareClaw vLLM link OK."}],
}
resp = httpx.post(
    f"{BASE_URL}/chat/completions",
    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    json=payload,
    timeout=120,
)
resp.raise_for_status()
data = resp.json()
print("model:", data.get("model"))
print("finish_reason:", data["choices"][0].get("finish_reason"))
print("content:", (data["choices"][0]["message"].get("content") or "").strip())
print("usage:", data.get("usage"))
