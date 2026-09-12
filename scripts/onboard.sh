#!/usr/bin/env bash
# Helper wrapper around NemoClaw onboard.
# Requires the nemoclaw + openshell CLIs on the host.
#
# Config resolution: nemoclaw-rag.toml [agent] defaults, overridden by .env / shell env.
# Bootstrap exception: parses the TOML directly with tomllib (no pymongo needed).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

PY=python3
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
fi

read_toml_defaults() {
  "$PY" - "$ROOT/nemoclaw-rag.toml" <<'PY' 2>/dev/null || true
import sys, tomllib, pathlib
path = pathlib.Path(sys.argv[1])
agent = {}
if path.is_file():
    with path.open("rb") as fh:
        agent = tomllib.load(fh).get("agent", {})
print(f'TOML_AGENT={agent.get("harness", "hermes")}')
print(f'TOML_SANDBOX={agent.get("sandbox_name", "nemoclaw-rag-base")}')
print(f'TOML_PROVIDER={agent.get("nemoclaw_provider", "openai-api")}')
PY
}

TOML_AGENT=hermes
TOML_SANDBOX=nemoclaw-rag-base
TOML_PROVIDER=openai-api
eval "$(read_toml_defaults)"

export NEMOCLAW_AGENT="${NEMOCLAW_AGENT:-$TOML_AGENT}"
export NEMOCLAW_SANDBOX_NAME="${NEMOCLAW_SANDBOX_NAME:-$TOML_SANDBOX}"
export NEMOCLAW_PROVIDER="${NEMOCLAW_PROVIDER:-$TOML_PROVIDER}"

case "$NEMOCLAW_AGENT" in
  hermes|openclaw) ;;
  *)
    echo "NEMOCLAW_AGENT must be 'hermes' or 'openclaw', got '$NEMOCLAW_AGENT'" >&2
    exit 1
    ;;
esac

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "Warning: OPENAI_API_KEY is empty; NemoClaw onboarding will prompt for provider credentials." >&2
fi

if ! command -v nemoclaw >/dev/null 2>&1; then
  cat <<'EOF'
nemoclaw CLI not found.

Install and onboard using the official guide:
  https://docs.nvidia.com/nemoclaw/latest/

Then re-run:
  ./scripts/onboard.sh
EOF
  exit 1
fi

echo "Onboarding sandbox='$NEMOCLAW_SANDBOX_NAME' agent='$NEMOCLAW_AGENT' provider='$NEMOCLAW_PROVIDER'"

if nemoclaw onboard --help 2>/dev/null | grep -q -- '--non-interactive'; then
  nemoclaw onboard --non-interactive
else
  nemoclaw onboard
fi

echo
echo "Next:"
echo "  nemoclaw ${NEMOCLAW_SANDBOX_NAME} status"
echo "  make smoke"
