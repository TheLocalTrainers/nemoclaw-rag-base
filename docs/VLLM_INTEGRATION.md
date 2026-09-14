# Local vLLM Integration — CareClaw

Investigation + integration plan for wiring the on-prem vLLM (Qwen) inference
endpoint into CareClaw. The headline: **the existing `rag` LLM path already
speaks the OpenAI-compatible protocol and points at vLLM with three env vars and
zero code changes** — verified live end-to-end (see below).

_Investigated 2026-09-12 against the running server. A teammate is tuning this
server in parallel; it may be down/restarting at any time — the plan below never
hard-fails when it is._

---

## 1. Endpoint probe results (LIVE — reachable at investigation time)

Server: **vLLM 0.29.0**, OpenAI-compatible API at `http://localhost:8000`.

| Probe | Result |
|---|---|
| `GET /health` | `200` |
| `GET /v1/models` | `data[0].id = "qwen3.8-27b"` · `max_model_len = 131072` · `owned_by = vllm` |
| `POST /v1/chat/completions` | `200`, well-formed OpenAI shape (`choices[0].message.content`) |
| API key required? | **No.** `Authorization: Bearer EMPTY` (and empty/absent) all accepted. |
| Latency | ~1.8 s for a 33-token completion (warm). |

**Exact model id for the `model` field: `qwen3.8-27b`**

### Critical gotcha — it is a *reasoning* model
Completions spend tokens on hidden reasoning first (`usage.completion_tokens_details.reasoning_tokens`),
then emit the answer in `message.content`. If `max_tokens` is too small the budget
is consumed entirely by reasoning and **`content` comes back `null`** (observed with
`max_tokens: 16` — the finish_reason was `length` and content was `null`). With an
adequate budget (or none — vLLM then allows the full remaining context) `content` is
populated normally and `finish_reason` is `stop`.

Implication for CareClaw: the `rag` path (below) does **not** set `max_tokens`, so
vLLM uses its large default and `content` is populated — verified. Any new call site
that sets a small `max_tokens` must budget for reasoning tokens.

### Verified minimal call
`scripts/vllm_smoke.py` (httpx, no new deps) — **ran successfully**:

```
model: qwen3.8-27b
finish_reason: stop
content: CareClaw vLLM link OK.
usage: {'prompt_tokens': 65, 'total_tokens': 98, 'completion_tokens': 33,
        'completion_tokens_details': {'reasoning_tokens': 21}}
```

Run it yourself: `.venv/bin/python -m scripts.vllm_smoke`

---

## 2. How the existing `rag` LLM path is configured

The generation path is already provider-agnostic and OpenAI-compatible.

- **`rag/pipeline.py:73` `generate_with_model(query, hits, config)`** — builds an
  OpenAI `chat/completions` payload and POSTs to
  **`{model_cfg.base_url}/chat/completions`** (`rag/pipeline.py:112`) using
  `urllib` (stdlib — no HTTP dep at all). It reads `choices[0].message.content`
  (`rag/pipeline.py:139`) and, notably, **raises `GenerateError` if content is
  `null`/empty** (`rag/pipeline.py:143-147`) — so it never fabricates an answer.
- **`rag/config.py:82` `ModelConfig`** — the four knobs, each overridable by env:
  - `base_url`  ← `OPENAI_BASE_URL`  (default `https://api.openai.com/v1`; trailing `/` stripped, `rag/config.py:296`)
  - `model`     ← `OPENAI_MODEL`     (default `gpt-4.1-mini`)
  - `temperature` ← `OPENAI_TEMPERATURE` (default `0`)
  - `timeout_seconds` ← `OPENAI_TIMEOUT_SECONDS` (default `60`)
  - `api_key_env` = `OPENAI_API_KEY`; the secret is read via `ModelConfig.api_key` (`rag/config.py:89-91`).
- **Precedence** (`rag/config.py:6`): CLI flag > env var > `nemoclaw-rag.toml` `[model]` > dataclass default. `.env` is loaded by CLI entrypoints via `rag/env.py` (`scripts/query.py:21`).
- **CLI**: `scripts/query.py --generate` runs retrieve → generate, and on
  `GenerateError` prints `GENERATE FAIL` and exits `2` (`scripts/query.py:56-64`);
  without `--generate` it prints the deterministic extractive answer
  (`answer_from_context`, `rag/pipeline.py:62`).

**Can `generate_with_model()` point at `http://localhost:8000/v1` as-is? Yes.**
Verified end-to-end with no code edits:

```
$ OPENAI_BASE_URL=http://localhost:8000/v1 OPENAI_MODEL=qwen3.8-27b OPENAI_API_KEY=EMPTY \
    .venv/bin/python -m scripts.query "What is the project beacon code?" --generate
=== Model answer (qwen3.8-27b) ===
NEON-BEACON-42
```

Retrieval by Mongo, generation by Qwen. One caveat below.

### The one required gotcha: `OPENAI_API_KEY` must be non-empty
`generate_with_model` refuses to run if the api key is empty (`rag/pipeline.py:86-90`).
vLLM needs no key, but the pipeline's own guard does — so set a **placeholder**
`OPENAI_API_KEY=EMPTY` (any non-empty string). This is the only thing that would
otherwise block the local path.

---

## 3. HTTP client — nothing new needed

`.venv/bin/pip list`: **`httpx 0.28.1` (project dep), `requests 2.34.2`, `pymongo 4.18.1`.
`openai` is NOT installed.**

- **Option (a)** uses `rag.pipeline`, which calls the endpoint with **stdlib `urllib`** —
  literally zero HTTP deps.
- Any **new** call site (options b/c) should use **`httpx`** (already present) — an
  OpenAI-compatible call over httpx needs no new dependency. Do **not** add the
  `openai` SDK; it buys nothing here and adds weight.

---

## 4. Integration points, ranked

CareClaw story: on-prem clinical-trial safety copilot; agents are deterministic
(GAMP-5), the GB10/vLLM slot is for **narrative polish and protocol RAG Q&A**.
Every option must **fall back to the deterministic/extractive path when the
endpoint is down** — never hard-fail the demo.

### (a) RAG answer generation via `make query ... --generate` — **RECOMMENDED, effort S**
- **What**: retrieval by Mongo (`chunks`), generation by Qwen. Produces a natural-
  language, protocol-grounded, cited answer instead of the raw top chunk.
- **New deps**: none. **Code changes**: none — config only. **Already verified live.**
- **Config**: `OPENAI_BASE_URL=http://localhost:8000/v1`, `OPENAI_MODEL=qwen3.8-27b`,
  `OPENAI_API_KEY=EMPTY`. Best set in `nemoclaw-rag.toml [model]` for base_url/model
  (committed, non-secret) + `.env` for the `EMPTY` placeholder.
- **Graceful fallback**: already built in. Drop `--generate` (or let `GenerateError`
  fire) → `answer_from_context` returns the deterministic extractive top chunk. The
  CLI surfaces `GENERATE FAIL: ...` and exits `2`; the extractive path stays exit `0`.
  For a demo script, run without `--generate` as the safe default and add `--generate`
  when the server is confirmed up.
- **Why first**: smallest change, highest fit, and the retrieval half works with no
  model at all.

### (b) "Ask the protocol" panel in the web console — effort M
- **What**: new **read-only** FastAPI endpoint (e.g. `POST /api/ask`) in
  `web/server.py`: RAG-retrieve from Mongo `chunks` then vLLM-generate a cited answer.
  A protocol Q&A box in the console. (Front-end is out of scope here —
  `web/static/*` is off-limits per constraints; ship the endpoint + a curl demo, or
  let another agent add the UI.)
- **New deps**: none (reuse `rag.pipeline.retrieve` + `generate_with_model`, or an
  httpx call). Note: `web/server.py` currently imports only the `careclaw` store; this
  endpoint would additionally import `rag.store.open_store` + `rag.pipeline` — read-only
  against the RAG `chunks` collection, touching neither `careclaw.*` nor `web/static/*`.
- **Config**: identical to (a).
- **Graceful fallback**: wrap `generate_with_model` in try/except `GenerateError`;
  on failure return the extractive `answer_from_context(query, hits)` with a
  `"generated": false` flag so the UI can label it "retrieval-only (LLM offline)".
- **Port caveat**: `python -m web.server` hard-codes port **8000** (`web/server.py:219`)
  which **collides with vLLM**. Use `make web` (port 8010) or `--port 8010`. Worth
  fixing separately; out of scope here.

### (c) SafetyClaw FDA 3500A narrative POLISH — effort M, OPTIONAL by design
- **What**: an **opt-in** pass that rewrites the deterministic zero-draft narrative into
  fluent prose. Must **not** change the deterministic findings and must **keep causality
  blank** (GAMP-5 / 21 CFR Part 11 story: the signed record stays deterministic).
- **New deps**: none (httpx call). **Must not** touch `agents/*`, `store/*`, or the
  signing path per constraints — implement as a clearly-separated optional helper the
  reviewer explicitly triggers, feeding it the already-generated `draft_narrative`.
- **Config**: identical to (a). Use a system prompt that forbids adding/altering facts
  and forbids stating causality; treat output as *presentation only*.
- **Graceful fallback**: if the endpoint is down or returns null content, silently keep
  the deterministic zero-draft — the polish is cosmetic and never on the signing path.
- **Risk**: highest scrutiny (it edits regulated narrative text). Keep it visibly
  optional, non-default, and never part of the audited/signed artifact.

**Recommendation: ship (a) now (config-only, verified), then (b) as the demo's
"Ask the protocol" moment. Treat (c) as a stretch, opt-in, cosmetic-only.**

---

## 5. Copy-paste config

### `.env` (secrets/overrides — gitignored)
```dotenv
# Point the OpenAI-compatible path at the local vLLM server.
# vLLM needs no key, but rag/pipeline.py requires a NON-EMPTY value — use a placeholder.
OPENAI_API_KEY=EMPTY
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_MODEL=qwen3.8-27b
```

### `nemoclaw-rag.toml` `[model]` (committed, non-secret — the durable place for base_url/model)
```toml
[model]
base_url = "http://localhost:8000/v1"
model = "qwen3.8-27b"
temperature = 0
timeout_seconds = 60          # reasoning model; keep generous headroom
api_key_env = "OPENAI_API_KEY"
```
(Keep `OPENAI_API_KEY=EMPTY` in `.env` regardless — the TOML never holds secrets/keys.)

### One-shot verification
```bash
# minimal call (httpx, verified)
.venv/bin/python -m scripts.vllm_smoke

# end-to-end RAG (verified): Mongo retrieval + Qwen generation
OPENAI_BASE_URL=http://localhost:8000/v1 OPENAI_MODEL=qwen3.8-27b OPENAI_API_KEY=EMPTY \
  make query Q="What is the project beacon code?"   # then add --generate via scripts.query
```

---

## What was verified live vs. asserted
- **Verified live**: `/health`, `/v1/models` (model id `qwen3.8-27b`), a real
  `chat/completions` call, no-API-key acceptance, the httpx smoke script, and the full
  `scripts.query --generate` RAG path against vLLM (returned `NEON-BEACON-42`).
- **Asserted from code/contract (not executed)**: options (b) and (c) are plans, not
  built; the graceful-fallback behavior of (a) is inherited from existing code
  (`rag/pipeline.py` / `scripts/query.py`). The port-8000 collision for `python -m
  web.server` is read from source, not triggered.
```
