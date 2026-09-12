# Onboarding this base with NemoClaw / OpenShell

## Host prerequisites

- Linux host with Docker (or a compatible container runtime)
- MongoDB — provided by `make mongo-up` (Compose, or local binary fallback)
- [NemoClaw](https://github.com/NVIDIA/NemoClaw) CLI
- [OpenShell](https://github.com/NVIDIA/OpenShell) CLI / gateway
- An OpenAI-compatible API key for a small model

## Recommended order

**1. Validate the RAG layer first (no sandbox required).**

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
make smoke
```

**2. Set secrets.** Non-secret config already lives in `nemoclaw-rag.toml`.

```bash
cp .env.example .env
# set OPENAI_API_KEY; override MONGODB_* / NEMOCLAW_* only if needed
make config          # confirm what is in effect
```

**3. Choose the harness.** Default is Hermes, from `[agent].harness` in `nemoclaw-rag.toml`.

```bash
make onboard                              # uses the TOML default
NEMOCLAW_AGENT=openclaw make onboard      # one-off override
```

`scripts/onboard.sh` rejects any value other than `hermes` or `openclaw`, and warns
if `OPENAI_API_KEY` is empty.

**4. Confirm sandbox health.**

```bash
nemoclaw nemoclaw-rag-base status
```

Replace the name if you changed `[agent].sandbox_name`.

**5. Connect the agent to retrieval.** This is not built yet. To do it you need to:

- expose `rag.pipeline.retrieve()` as a Hermes skill or OpenClaw tool
- allowlist MongoDB egress in OpenShell policy (see `configs/openshell/policy-notes.md`)
- decide whether the sandbox reaches the host MongoDB or runs its own instance

## Roles in this stack

| Layer | Role in this project |
| --- | --- |
| OpenShell | Sandbox, gateway, inference proxy, network policy |
| NemoClaw | Onboarding, blueprint, lifecycle CLI |
| Hermes | Default agent harness |
| OpenClaw | Alternate agent harness |
| MongoDB | Chunk store + text-index retrieval |
| `rag/` | Chunking, storage, retrieval, optional generation |

## Notes

- Files under `configs/` are illustrative. NemoClaw writes the real agent config during onboarding.
- Keep egress minimal until the smoke path is green; see `configs/openshell/policy-notes.md`.
