# OpenShell policy notes for this base project

NemoClaw applies a versioned blueprint and network policy through OpenShell.
For this RAG base:

1. Keep egress minimal: allow only the inference provider you configure.
2. Allowlist MongoDB when the sandbox agent needs live RAG (`MONGODB_URI`, typically host gateway → `27017`).
3. Prefer running `make smoke` on the host first; that validates MongoDB ingest/retrieve without agent networking.
4. After `nemoclaw onboard`, verify with `nemoclaw <sandbox> status` and a routed inference probe.

Do not widen policy to the public internet until the smoke path is green.
