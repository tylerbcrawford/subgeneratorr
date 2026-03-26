#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REQ_FILE="$ROOT_DIR/requirements-dev.txt"
STAMP_FILE="$VENV_DIR/.requirements-dev.stamp"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "error: $PYTHON_BIN not found" >&2
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

if [ ! -x "$VENV_DIR/bin/pytest" ] || [ ! -f "$STAMP_FILE" ] || [ "$REQ_FILE" -nt "$STAMP_FILE" ]; then
    "$VENV_DIR/bin/pip" install -q -r "$REQ_FILE"
    touch "$STAMP_FILE"
fi

cd "$ROOT_DIR"
exec "$VENV_DIR/bin/pytest" tests/ -v "$@"
