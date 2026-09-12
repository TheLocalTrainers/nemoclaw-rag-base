"""Thin OpenAI-compatible client for the local vLLM (Qwen) endpoint.

Ready to integrate with the model served at http://localhost:8000/v1. It FAILS
SOFT: if the endpoint is disabled or unreachable (e.g. while a teammate is
tuning it in parallel), callers get an `LLMUnavailable` they can turn into a
friendly "assistant offline" message — the demo never hard-crashes.

The served model (qwen3.8-27b) is a REASONING model. Per the endpoint's
integration guide we send `chat_template_kwargs` to control thinking, keep the
sampling temperature off the near-zero floor while thinking is on (temp 0
degrades reasoning and triggers repetition loops), budget `max_tokens`
generously so reasoning tokens don't starve `content`, and use a long client
timeout (thinking turns can run minutes). Centralizing this here means every
caller (`server.py`, `patient_triage.py`, `narrative_llm.py`) is corrected
without being edited.

Config (env, overridable):
    VLLM_BASE_URL          default http://localhost:8000/v1
    VLLM_MODEL             default "" → auto-detect the first id from GET /v1/models
    VLLM_API_KEY           default "EMPTY" (vLLM ignores it but the header is required)
    VLLM_ENABLED           default "1"  ("0"/"false" turns the assistant off)
    VLLM_TIMEOUT           default "600" seconds (thinking turns can run minutes)
    VLLM_REASONING_EFFORT  default "low"  (low|medium|xhigh, or "off" to disable thinking)
"""

from __future__ import annotations

import os

import httpx

# Sampling floor while thinking is on. The guide's thinking-mode card value is
# temperature 1.0; sending temp 0 (or ~0.2) degrades reasoning and causes
# repetition loops, so we clamp any caller-supplied value up to this floor.
_THINKING_TEMP_FLOOR = 0.6
_DEFAULT_TEMPERATURE = 0.7
_DEFAULT_TOP_P = 0.9
_DEFAULT_MAX_TOKENS = 8192
_VALID_EFFORTS = ("low", "medium", "xhigh")


def _cfg(name: str, default: str) -> str:
    return os.environ.get(name, default)


def base_url() -> str:
    return _cfg("VLLM_BASE_URL", "http://localhost:8000/v1").rstrip("/")


def _api_key() -> str:
    return _cfg("VLLM_API_KEY", "EMPTY")


def _enabled() -> bool:
    return _cfg("VLLM_ENABLED", "1").lower() not in ("0", "false", "no")


def _timeout() -> float:
    try:
        return float(_cfg("VLLM_TIMEOUT", "600"))
    except ValueError:
        return 600.0


def _reasoning_effort(override: str | None) -> str:
    """Resolve effort: explicit arg > env VLLM_REASONING_EFFORT > 'low'."""
    effort = (override if override is not None else _cfg("VLLM_REASONING_EFFORT", "low"))
    return str(effort).strip().lower()


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_api_key()}", "Content-Type": "application/json"}


class LLMUnavailable(Exception):
    """Raised when the local model is disabled or unreachable."""


def _detect_model(client: httpx.Client) -> str:
    configured = _cfg("VLLM_MODEL", "").strip()
    if configured:
        return configured
    resp = client.get(f"{base_url()}/models", headers=_headers())
    resp.raise_for_status()
    data = resp.json().get("data") or []
    if not data:
        raise LLMUnavailable("vLLM /models returned no served model")
    return str(data[0]["id"])


def status() -> dict:
    """Best-effort reachability probe for the UI (never raises)."""
    if not _enabled():
        return {"available": False, "reason": "disabled", "base_url": base_url()}
    try:
        with httpx.Client(timeout=3.0) as client:
            model = _detect_model(client)
        return {"available": True, "model": model, "base_url": base_url()}
    except Exception as exc:  # noqa: BLE001 - status must never raise
        return {"available": False, "reason": str(exc)[:160], "base_url": base_url()}


def _merge_system_messages(messages: list[dict]) -> list[dict]:
    """Collapse all system messages into ONE leading system message.

    Qwen3's chat template rejects a request unless system messages are a single
    block at the very beginning ("System message must be at the beginning." →
    HTTP 400). Callers may naturally build several system messages (e.g. a base
    instruction + case context); we join them (order preserved) and move the
    single system message to the front, keeping every non-system turn in order.
    """
    systems = [str(m.get("content", "")) for m in messages if m.get("role") == "system"]
    others = [m for m in messages if m.get("role") != "system"]
    if not systems:
        return others
    return [{"role": "system", "content": "\n\n".join(s for s in systems if s)}] + others


def chat(
    messages: list[dict],
    *,
    temperature: float = _DEFAULT_TEMPERATURE,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
    reasoning_effort: str | None = None,
    top_p: float = _DEFAULT_TOP_P,
) -> str:
    """Send an OpenAI-style chat completion to the local vLLM; raise LLMUnavailable on any failure.

    The served model (qwen3.8-27b) is a REASONING model. This client applies the
    endpoint's integration guide centrally so every caller benefits:

    * Thinking control via ``chat_template_kwargs``. ``reasoning_effort`` accepts
      ``low`` | ``medium`` | ``xhigh`` (default ``low`` via VLLM_REASONING_EFFORT),
      or ``off`` to disable thinking entirely (fastest). Its default is the
      guide-recommended ``low`` for agent turns rather than the server's slow
      ``xhigh``.
    * Sampling guard: while thinking is on we clamp ``temperature`` up to a sane
      floor (~0.6) so a caller passing 0 / 0.2 / 0.3 does not send near-zero temp
      in thinking mode (which degrades reasoning and causes repetition loops).
    * Reasoning tokens count against ``max_tokens``; if the budget is too small
      the API returns content=null with finish_reason=length. We default the
      budget generously and treat null/empty content as a soft failure so the UI
      shows a friendly retry message instead of crashing.

    We only ever read ``message.content`` — never ``reasoning_content``.
    """
    if not _enabled():
        raise LLMUnavailable("assistant disabled (VLLM_ENABLED=0)")

    effort = _reasoning_effort(reasoning_effort)
    thinking_on = effort != "off"
    if thinking_on:
        # xhigh is valid but slow; anything unrecognized falls back to 'low'.
        if effort not in _VALID_EFFORTS:
            effort = "low"
        chat_template_kwargs = {"enable_thinking": True, "reasoning_effort": effort}
        # Guard sampling: don't send near-zero temp in thinking mode.
        temperature = max(temperature, _THINKING_TEMP_FLOOR)
    else:
        chat_template_kwargs = {"enable_thinking": False}

    try:
        with httpx.Client(timeout=_timeout()) as client:
            model = _detect_model(client)
            resp = client.post(
                f"{base_url()}/chat/completions",
                headers=_headers(),
                json={
                    "model": model,
                    "messages": _merge_system_messages(messages),
                    "temperature": temperature,
                    "top_p": top_p,
                    "max_tokens": max_tokens,
                    # vLLM accepts chat_template_kwargs as an OpenAI extra field.
                    "chat_template_kwargs": chat_template_kwargs,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"].get("content")
    except LLMUnavailable:
        raise
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise LLMUnavailable(str(exc)) from exc
    if not content or not content.strip():
        raise LLMUnavailable(
            "model returned empty content (finish_reason=length / reasoning budget "
            "exhausted) — raise max_tokens or lower reasoning_effort"
        )
    return content
