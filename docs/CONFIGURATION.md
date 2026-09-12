# Configuration — Single Source of Truth

Everything configurable in this project is declared in **one committed file**:

```
nemoclaw-rag.toml
```

Secrets are the only exception; they live in `.env` (gitignored).

## Resolution order

Highest priority wins:

| # | Layer | Where | Example |
| --- | --- | --- | --- |
| 1 | CLI flag | `scripts/*.py` argparse | `--top-k 5`, `--database mydb` |
| 2 | Environment variable | shell, or `.env` | `RAG_TOP_K=5` |
| 3 | **`nemoclaw-rag.toml`** | repo root | `[retrieval] top_k = 3` |
| 4 | Code fallback | `rag/config.py` dataclasses | `top_k: int = 3` |

`rag/config.py` is the only module that reads configuration. Every other module
(`rag/store.py`, `rag/pipeline.py`, `rag/chunk.py`, all CLIs) receives values
from it, so there are no duplicated defaults.

Inspect what is actually in effect:

```bash
make config              # human readable
python3 -m scripts.show_config --json
```

`.env` is loaded explicitly by CLI entrypoints via `rag.env.load_dotenv()`.
Library code never loads `.env` implicitly, which keeps tests deterministic.

## Registry

### `[project]` — TOML only (no env override)

| Key | Default | Meaning |
| --- | --- | --- |
| `name` | `nemoclaw-rag-base` | Project identifier |
| `smoke_token` | `NEON-BEACON-42` | Fact the smoke test must retrieve; must exist in the corpus |
| `smoke_question` | `What is the project beacon code?` | Natural-language query used by the smoke test |

### `[mongodb]`

| Key | Env override | Default | Meaning |
| --- | --- | --- | --- |
| `uri` | `MONGODB_URI` | `mongodb://127.0.0.1:27017` | Connection string |
| `database` | `MONGODB_DB` | `nemoclaw_rag` | Working database |
| `collection` | `MONGODB_COLLECTION` | `chunks` | Working collection |
| `smoke_database` | `MONGODB_SMOKE_DB` | `nemoclaw_rag_smoke` | Smoke database (isolated from real data) |
| `smoke_collection` | `MONGODB_SMOKE_COLLECTION` | `chunks` | Smoke collection |
| `server_selection_timeout_ms` | `MONGODB_TIMEOUT_MS` | `5000` | Fail fast instead of hanging |
| `port` | `MONGODB_PORT` | `27017` | Port for local startup and Compose |
| `docker_image` | `MONGODB_IMAGE` | `mongo:7` | Compose image |
| `local_version` | `MONGODB_LOCAL_VERSION` | `7.0.39` | Version downloaded when Docker is unavailable |

### `[corpus]`

| Key | Env override | Default | Meaning |
| --- | --- | --- | --- |
| `dir` | `RAG_CORPUS_DIR` | `corpus` | Directory scanned for documents |
| `extensions` | — | `[".md", ".txt"]` | Indexable file suffixes |

### `[chunking]`

| Key | Env override | Default | Meaning |
| --- | --- | --- | --- |
| `max_chars` | `RAG_CHUNK_MAX_CHARS` | `900` | Target window size |
| `overlap` | `RAG_CHUNK_OVERLAP` | `120` | Characters carried into the next window |

### `[retrieval]`

| Key | Env override | Default | Meaning |
| --- | --- | --- | --- |
| `top_k` | `RAG_TOP_K` | `3` | Chunks returned and passed to the model |
| `regex_fallback` | `RAG_REGEX_FALLBACK` | `true` | Regex scan when `$text` finds nothing |
| `min_token_length` | `RAG_MIN_TOKEN_LENGTH` | `2` | Shorter query tokens are dropped |

### `[model]`

| Key | Env override | Default | Meaning |
| --- | --- | --- | --- |
| `base_url` | `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint |
| `model` | `OPENAI_MODEL` | `gpt-4.1-mini` | Model identifier |
| `temperature` | `OPENAI_TEMPERATURE` | `0` | Sampling temperature |
| `timeout_seconds` | `OPENAI_TIMEOUT_SECONDS` | `60` | Request timeout |
| `api_key_env` | — | `OPENAI_API_KEY` | **Name** of the env var holding the secret |

The API key itself is never stored in TOML. Put it in `.env`.

### `[agent]`

| Key | Env override | Default | Meaning |
| --- | --- | --- | --- |
| `harness` | `NEMOCLAW_AGENT` | `hermes` | `hermes` or `openclaw`; validated by `scripts/onboard.sh` |
| `sandbox_name` | `NEMOCLAW_SANDBOX_NAME` | `nemoclaw-rag-base` | OpenShell sandbox name |
| `nemoclaw_provider` | `NEMOCLAW_PROVIDER` | `openai-api` | NemoClaw inference provider selection |

### Meta

| Env var | Meaning |
| --- | --- |
| `NEMOCLAW_RAG_CONFIG` | Absolute path to an alternate `nemoclaw-rag.toml` |

## Deliberate exceptions

Three places cannot import `rag/config.py`, so they read the TOML directly or
rely on `.env`. These are the only sync points in the project:

| File | Why | How it stays consistent |
| --- | --- | --- |
| `scripts/start-mongo.sh` | Runs before `pymongo` is installed | Parses `nemoclaw-rag.toml` with stdlib `tomllib`; env still wins |
| `scripts/onboard.sh` | Same bootstrap constraint | Parses `[agent]` with `tomllib`; env still wins |
| `docker-compose.yml` | YAML cannot read TOML | Uses `${MONGODB_IMAGE:-mongo:7}` / `${MONGODB_PORT:-27017}`; Compose auto-loads `.env`. **Change the port in `.env`, not only in the TOML, if you use Compose.** |

Files under `configs/` (`hermes/config.yaml.example`, `openclaw/openclaw.json.example`,
`openshell/policy-notes.md`) are **non-authoritative sketches**. Nothing reads them at
runtime; NemoClaw writes the live agent config during onboarding.

## Open decisions

Unresolved choices, with the current placeholder and what would trigger a change.

| # | Decision | Current | Change when |
| --- | --- | --- | --- |
| 1 | Retrieval strategy | MongoDB `$text` (BM25-like) + regex fallback | Paraphrased questions start missing; then add embeddings (Atlas Vector Search or a vector field + `$vectorSearch`) |
| 2 | Embeddings | None | Adopting decision 1; requires an embedding model and an `embedding` field per chunk |
| 3 | Model | `gpt-4.1-mini` via OpenAI-compatible HTTP | You have a specific small/local model; set `OPENAI_BASE_URL` + `OPENAI_MODEL` |
| 4 | Agent harness | Hermes | You prefer OpenClaw; set `NEMOCLAW_AGENT=openclaw` |
| 5 | Agent ↔ RAG bridge | **Not built** — agent cannot query the index | You want the sandboxed agent to retrieve; expose `retrieve()` as a tool/skill and allowlist MongoDB in OpenShell policy |
| 6 | MongoDB auth | None (localhost, no credentials) | Mongo is reachable off-host; add credentials to `MONGODB_URI` and TLS |
| 7 | Mongo runtime | Docker Compose, else local binary in `.tools/` | Docker group access is granted, or you move to Atlas |
| 8 | Corpus source | Static files in `corpus/` | You need live ingestion (GitHub, Slack, docs crawl) |
| 9 | Answer mode | Extractive by default, `--generate` opt-in | Generation becomes the primary path |
| 10 | Evaluation | Single smoke fact | Corpus grows; add a question/answer eval set |
| 11 | Chunking | Fixed 900/120 character windows | Retrieval quality suffers on structured docs; move to heading-aware chunking |

## Changing configuration

1. Non-secret, should apply to everyone → edit `nemoclaw-rag.toml`, commit.
2. Machine-specific or secret → put it in `.env`.
3. One-off experiment → CLI flag or inline env var, e.g. `RAG_TOP_K=10 make query Q="..."`.
4. Verify with `make config`.
