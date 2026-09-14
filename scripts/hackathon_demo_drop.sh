#!/usr/bin/env bash
# Drop the PT-004 hackathon fixtures into incoming_records/ for the live demo.
# Requires: python -m daemon.watcher running in another terminal.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

INCOMING="$ROOT/incoming_records"
mkdir -p "$INCOMING"

NOTE="$ROOT/corpus/fixtures/patient_004_visit_note.txt"
LABS="$ROOT/corpus/fixtures/patient_004_labs.json"

if [[ ! -f "$NOTE" || ! -f "$LABS" ]]; then
  echo "Missing fixtures under corpus/fixtures/" >&2
  exit 1
fi

# Copy (not move) so the demo can be re-run.
cp "$NOTE" "$INCOMING/"
cp "$LABS" "$INCOMING/"

echo "Dropped into $INCOMING:"
echo "  - $(basename "$NOTE")"
echo "  - $(basename "$LABS")"
echo
echo "Daemon should enqueue a NEEDS_PI_REVIEW case within ~2s."
echo "In Streamlit: mode = Review Queue → Refresh queue → Approve & Sign."
