#!/usr/bin/env bash
# Unix launcher — deploy Simulacra to a sibling book folder.
# AI agents on Linux/macOS/BSD: run this (or: python3 scripts/run.py deploy …).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Error: Python 3 not found on PATH." >&2
  exit 127
fi

exec "$PY" "$ROOT/deploy_framework.py" "$@"
