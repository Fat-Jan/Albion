#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python not found: $PYTHON_BIN" >&2
  echo "Create the venv first: python -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 127
fi

cd "$ROOT_DIR"

echo "== unittest =="
"$PYTHON_BIN" -m unittest discover -s tests -v 2>&1

echo "== compileall =="
"$PYTHON_BIN" -m compileall bot scripts tests

echo "== ok =="
