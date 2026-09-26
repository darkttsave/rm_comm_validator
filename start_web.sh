#!/usr/bin/env bash
set -e

# Locate repository root
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT_DIR/.venv/bin/python"

# Check if virtual environment exists
if [ ! -x "$PYTHON" ]; then
    echo "[ERROR] Virtual environment not found."
    echo ""
    echo "Initialize with:"
    echo "  python3 -m venv .venv"
    echo "  .venv/bin/python -m pip install -r requirements.txt"
    echo ""
    exit 1
fi

# Change to repository root and start web server
cd "$ROOT_DIR"
exec "$PYTHON" main.py web "$@"
