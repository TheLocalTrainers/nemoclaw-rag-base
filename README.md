# nemoclaw-rag-base

Minimal base project pairing a **MongoDB RAG scaffold** with **NemoClaw / OpenShell / Hermes / OpenClaw** agent wiring, plus one smoke test.

**New here? Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — it is the handoff document.**
All configuration lives in [`nemoclaw-rag.toml`](nemoclaw-rag.toml); see [`docs/CONFIGURATION.md`](docs/CONFIGURATION.md).

## What you get

- **RAG core** (`rag/`): Markdown/text → chunk → MongoDB text index → retrieve
- **Fixture corpus** with the known token `NEON-BEACON-42`
- **Smoke test** proving ingest + retrieval without any model
- **Optional generation** through any OpenAI-compatible endpoint, which fails loudly rather than faking success
- **Agent scaffolding** for Hermes (default) and OpenClaw, plus a NemoClaw onboarding helper

## Prerequisites

- Python 3.11+ (uses stdlib `tomllib`)
- MongoDB — started for you by `make mongo-up` (Docker Compose, or a local binary fallback if Docker is unavailable)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env      # only for secrets / machine-specific overrides
```

## Quick start

```bash
make smoke
```

Starts MongoDB, ingests the fixture corpus into an isolated smoke database, and asserts that `NEON-BEACON-42` is retrievable by both a natural-language question and the raw token.

## Local query loop

```bash
make config                                          # effective configuration
make ingest                                          # corpus/ -> MongoDB
make query Q="what is the project beacon code?"      # extractive answer
make test                                            # 14 unit tests
```

With a model (needs `OPENAI_API_KEY` in `.env`):

```bash
python3 -m scripts.query --generate "what is the project beacon code?"
```

## Stack map

```text
NemoClaw CLI ── onboard / status / lifecycle
      │
      ▼
OpenShell ──── sandbox + gateway + policy + inference route
      ├── Hermes   (default harness)
      └── OpenClaw (alternate harness)

Host RAG (this repo, working today)
      corpus/ ──► MongoDB text index ──► retrieve ──► extractive | model answer
```

The agent layer is scaffolding: nothing inside a sandbox queries the index yet. See gap #1 in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Configuration

One committed file, `nemoclaw-rag.toml`, holds every non-secret setting.
Overrides resolve as **CLI flag > env var (incl. `.env`) > TOML > code default**.

```bash
make config                     # what is actually in effect
RAG_TOP_K=10 make query Q="..." # one-off override
```

Secrets go only in `.env`, which is gitignored.

## NemoClaw sandbox

```bash
# harness/sandbox default to [agent] in nemoclaw-rag.toml
make onboard
```

Details in [`docs/onboarding.md`](docs/onboarding.md).

## Layout

```text
nemoclaw-rag.toml     # single source of truth for config
rag/                  # config, env, chunk, MongoDB store, pipeline
scripts/              # ingest, query, smoke_test, show_config, start-mongo.sh, onboard.sh
corpus/               # documents to index
configs/              # non-authoritative agent sketches
tests/                # unittest suite (needs MongoDB for retrieval tests)
docs/                 # ARCHITECTURE.md, CONFIGURATION.md, onboarding.md
docker-compose.yml    # MongoDB service
```
