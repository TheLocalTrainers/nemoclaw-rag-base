# Architecture Handoff — nemoclaw-rag-base

Handoff document for another agent or engineer picking up this project.
Everything below was verified by running it, not inferred.

- **Repo root:** `/home/dell/nemoclaw-rag-base`
- **Last verified:** 14/14 unit tests pass, smoke test passes against a live MongoDB
- **Config source of truth:** `nemoclaw-rag.toml` (see `docs/CONFIGURATION.md`)

## 1. What this project is

A minimal base for running a **sandboxed AI agent with retrieval**. Two layers:

1. **Host RAG layer (built, working).** Markdown → chunks → MongoDB text index → retrieve → extractive answer, with optional generation through any OpenAI-compatible model.
2. **Agent runtime layer (scaffolded, not live).** Helper scripts and non-authoritative config sketches for onboarding Hermes or OpenClaw into an NVIDIA OpenShell sandbox via the NemoClaw CLI.

MongoDB is a hard requirement (hackathon constraint) and is the only datastore.

## 2. Stack roles

| Component | Role | Status |
| --- | --- | --- |
| **MongoDB** | Chunk store + text-index retrieval | **Live and used** |
| **Python RAG core** (`rag/`) | Chunk, store, retrieve, generate | **Live and used** |
| **NemoClaw** | Onboarding / lifecycle CLI for the agent sandbox | Helper script only; CLI not installed here |
| **OpenShell** | Sandbox, gateway, network policy, inference routing | Documented; not provisioned |
| **Hermes** | Default agent harness | Config sketch only |
| **OpenClaw** | Alternate agent harness | Config sketch only |

## 3. Data flow

```text
corpus/**/*.md
      │  iter_markdown_files()  — resolves symlinks, refuses escapes outside corpus/
      ▼
rag/chunk.py            900-char windows, 120-char overlap, corpus-relative paths
      │
      ▼
rag/store.py            MongoDB: one doc per chunk
      │                   { path, chunk_id, text, search_text, start_line, end_line }
      │                 indexes: unique (path, chunk_id) + text index on (text, search_text)
      ▼
query ──► RagStore.search()
            1. $text search with quoted tokens, sorted by textScore
            2. regex fallback if $text returns nothing
      │
      ▼
rag/pipeline.py
      ├── answer_from_context()   deterministic, no model  ← default
      └── generate_with_model()   OpenAI-compatible /chat/completions ← --generate
```

`search_text` is a punctuation-stripped copy of `text`. That is what makes
hyphenated tokens such as `NEON-BEACON-42` retrievable, since MongoDB's text
index would otherwise split them awkwardly.

## 4. File map

| Path | Purpose |
| --- | --- |
| `nemoclaw-rag.toml` | **Single source of truth for all configuration** |
| `rag/config.py` | Only config reader: TOML + env overrides, typed dataclasses |
| `rag/env.py` | Minimal stdlib `.env` loader (no third-party dotenv) |
| `rag/chunk.py` | File discovery + chunking; path-escape protection |
| `rag/store.py` | MongoDB store, index management, search |
| `rag/pipeline.py` | Ingest orchestration, retrieve, extractive answer, model call |
| `scripts/ingest.py` | CLI: corpus → MongoDB |
| `scripts/query.py` | CLI: question → context → extractive or model answer |
| `scripts/smoke_test.py` | CLI: end-to-end check against an isolated smoke database |
| `scripts/show_config.py` | CLI: print effective config (start here when debugging) |
| `scripts/start-mongo.sh` | Start Mongo: Docker Compose, else local binary in `.tools/` |
| `scripts/onboard.sh` | NemoClaw onboarding wrapper; validates harness choice |
| `corpus/fixtures/neon-beacon.md` | Fixture holding the smoke fact |
| `tests/test_config.py` | Config precedence and validation |
| `tests/test_generate.py` | Model path: success, missing key, null content, CLI exit code |
| `tests/test_smoke_rag.py` | Retrieval of the known fact |
| `configs/**` | Non-authoritative agent sketches; nothing reads them at runtime |
| `docs/CONFIGURATION.md` | Config registry + open decisions |
| `docs/onboarding.md` | Sandbox onboarding steps |

## 5. Commands

```bash
# one-time
python3 -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env          # only needed for secrets/overrides

make config     # show effective configuration
make smoke      # start Mongo, ingest fixtures, assert NEON-BEACON-42 retrieved
make ingest     # corpus/ -> nemoclaw_rag.chunks
make query Q="what is the project beacon code?"
make test       # 14 unit tests
make mongo-up / mongo-down / mongo-logs
make onboard    # NemoClaw onboarding (requires nemoclaw CLI)
```

Model-backed answer (needs a key in `.env`):

```bash
python3 -m scripts.query --generate "what is the project beacon code?"
```

## 6. Verified state

```text
$ make test      → Ran 14 tests ... OK
$ make smoke     → SMOKE OK, chunks=1, found=NEON-BEACON-42
$ make config    → config file: /home/dell/nemoclaw-rag-base/nemoclaw-rag.toml
```

Environment facts on this machine:

- MongoDB **7.0.39** running from `.tools/mongodb` on `127.0.0.1:27017`, data in `.rag/mongo-data`
- Docker is installed but the `dell` user is **not** in the `docker` group, so `scripts/start-mongo.sh` used the local-binary fallback
- `pymongo` 4.18.1 in `.venv`; runtime otherwise stdlib only
- Corpus currently contains **one** file, producing **one** chunk
- Git: branch `master`, **no commits yet** — everything is untracked

## 7. Behaviour contracts worth preserving

- `--generate` **fails loudly** (exit `2`, `GENERATE FAIL: ...`) on a missing key, HTTP error, non-JSON body, or null/empty content. It never prints an extractive chunk labelled as a model answer.
- The smoke test writes only to `nemoclaw_rag_smoke`, never the working database.
- Ingest defaults to a full rebuild. `--no-rebuild` updates in place **and** deletes chunks for files that no longer exist.
- Symlinks pointing outside `corpus/` are skipped, not indexed.
- Stored chunk paths are corpus-relative, so the index is portable across machines.

## 8. Known gaps

Ordered by what would block real use.

1. **The agent cannot query the index.** No Hermes skill or OpenClaw tool calls `retrieve()`. This is the single biggest gap between "RAG scaffold" and "agentic RAG".
2. **Keyword retrieval only.** MongoDB `$text` will miss paraphrases and relational questions. No embeddings or vector search.
3. **No live provider test.** The model path is verified with mocks and failure injection; nothing has called a real endpoint.
4. **NemoClaw/OpenShell unverified here.** Neither CLI is installed, so `scripts/onboard.sh` has never completed on this machine.
5. **Unauthenticated MongoDB** bound to localhost. Fine locally, unsafe if exposed.
6. **Single-fact evaluation.** One smoke token is a regression guard, not a quality measure.
7. **Fixed-size chunking** ignores headings and document structure.
8. **Nothing is committed to git.**

## 9. Suggested next steps

1. `git add -A && git commit` to create a baseline.
2. Expose retrieval to the agent: a small JSON-in/JSON-out `retrieve` entrypoint, registered as a Hermes skill or OpenClaw tool, with MongoDB allowlisted in OpenShell policy.
3. Run one real `--generate` call against your chosen small model and record the result.
4. Grow the corpus, then decide open decision #1 (stay on `$text` or add vectors) based on observed misses.
5. Add an eval set once there is more than one question worth answering.

## 10. Pointers

- Config registry and open decisions: `docs/CONFIGURATION.md`
- Sandbox onboarding: `docs/onboarding.md`
- Policy notes: `configs/openshell/policy-notes.md`
