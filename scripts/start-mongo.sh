#!/usr/bin/env bash
# Start MongoDB for local RAG work.
# Prefers Docker Compose; falls back to a user-local MongoDB binary under .tools/.
#
# Bootstrap exception: this script parses nemoclaw-rag.toml directly with tomllib
# instead of importing rag.config, so it works before pymongo is installed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY=python3
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
fi

# Read defaults from the single source of truth; env vars still win.
read_toml_defaults() {
  "$PY" - "$ROOT/nemoclaw-rag.toml" <<'PY' 2>/dev/null || true
import sys, tomllib, pathlib
path = pathlib.Path(sys.argv[1])
mongo = {}
if path.is_file():
    with path.open("rb") as fh:
        mongo = tomllib.load(fh).get("mongodb", {})
print(f'TOML_PORT={mongo.get("port", 27017)}')
print(f'TOML_IMAGE={mongo.get("docker_image", "mongo:7")}')
print(f'TOML_VERSION={mongo.get("local_version", "7.0.39")}')
PY
}

TOML_PORT=27017
TOML_IMAGE="mongo:7"
TOML_VERSION="7.0.39"
eval "$(read_toml_defaults)"

PORT="${MONGODB_PORT:-$TOML_PORT}"
MONGO_VER="${MONGODB_LOCAL_VERSION:-$TOML_VERSION}"
export MONGODB_IMAGE="${MONGODB_IMAGE:-$TOML_IMAGE}"
export MONGODB_PORT="$PORT"
export MONGODB_URI="${MONGODB_URI:-mongodb://127.0.0.1:${PORT}}"

mongo_ping() {
  MONGODB_URI="$MONGODB_URI" "$PY" -c 'import os; from pymongo import MongoClient; MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=1500).admin.command("ping")'
}

if mongo_ping >/dev/null 2>&1; then
  echo "MongoDB already reachable at ${MONGODB_URI}"
  exit 0
fi

if docker info >/dev/null 2>&1; then
  echo "Starting MongoDB via Docker Compose (${MONGODB_IMAGE}, port ${PORT})..."
  docker compose up -d mongo
  for _ in $(seq 1 30); do
    if mongo_ping >/dev/null 2>&1; then
      echo "MongoDB ready (docker) at ${MONGODB_URI}"
      exit 0
    fi
    sleep 1
  done
  echo "Docker MongoDB did not become ready" >&2
  exit 1
fi

ARCH="$(uname -m)"
case "$ARCH" in
  aarch64|arm64) MONGO_ARCH=aarch64 ;;
  x86_64|amd64) MONGO_ARCH=x86_64 ;;
  *) echo "Unsupported arch: $ARCH" >&2; exit 1 ;;
esac

MONGO_DIR="$ROOT/.tools/mongodb"
MONGO_TGZ_URL="https://fastdl.mongodb.org/linux/mongodb-linux-${MONGO_ARCH}-ubuntu2204-${MONGO_VER}.tgz"

if [[ ! -x "$MONGO_DIR/bin/mongod" ]]; then
  echo "Docker unavailable; downloading MongoDB ${MONGO_VER} (${MONGO_ARCH}) into .tools/ ..."
  mkdir -p "$ROOT/.tools"
  curl -fsSL -o /tmp/mongodb-local.tgz "$MONGO_TGZ_URL"
  rm -rf "$MONGO_DIR" "$ROOT/.tools/mongodb-extract"
  mkdir -p "$ROOT/.tools/mongodb-extract"
  tar -xzf /tmp/mongodb-local.tgz -C "$ROOT/.tools/mongodb-extract"
  EXTRACTED="$(find "$ROOT/.tools/mongodb-extract" -maxdepth 1 -type d -name 'mongodb-linux-*' | head -1)"
  mv "$EXTRACTED" "$MONGO_DIR"
  rm -rf "$ROOT/.tools/mongodb-extract"
fi

mkdir -p "$ROOT/.rag/mongo-data"
echo "Starting local mongod on port ${PORT}..."
"$MONGO_DIR/bin/mongod" \
  --dbpath "$ROOT/.rag/mongo-data" \
  --port "$PORT" \
  --bind_ip 127.0.0.1 \
  --fork \
  --logpath "$ROOT/.rag/mongod.log"

for _ in $(seq 1 30); do
  if mongo_ping >/dev/null 2>&1; then
    echo "MongoDB ready (local binary) at ${MONGODB_URI}"
    exit 0
  fi
  sleep 1
done

echo "Local mongod did not become ready; see .rag/mongod.log" >&2
exit 1
