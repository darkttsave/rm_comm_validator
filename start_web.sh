#!/usr/bin/env bash
# Normal Runtime launcher
# Starts Validator Web with physical devices only (no virtual endpoints).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== RM Communication Validator - Normal Runtime ==="
echo ""
echo "Starting Validator Web..."
echo "  - Physical Serial/CAN devices available"
echo "  - Virtual endpoints disabled"
echo "  - Demo and Replay available"
echo ""

# Check venv
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "[Error] Python virtual environment not found."
    echo "Please run: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Activate venv
source "$SCRIPT_DIR/.venv/bin/activate"

# Start Web in Normal Runtime (no --simulation flag)
python "$SCRIPT_DIR/main.py" web --host 127.0.0.1 --port 5000

echo ""
echo "Validator stopped."
