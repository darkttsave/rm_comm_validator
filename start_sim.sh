#!/usr/bin/env bash
# Simulation Runtime launcher
# Enables virtual endpoint capability without eager setup.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== RM Communication Validator - Simulation Runtime ==="
echo ""

# Check venv
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "[Error] Python virtual environment not found."
    echo "Please run: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Activate venv
source "$SCRIPT_DIR/.venv/bin/activate"

echo "Starting Validator Web with Simulation capability enabled..."
echo ""
echo "Virtual endpoints:"
echo "  - RM Virtual Serial: Ready (requires socat)"
echo "  - RM Virtual CAN: Setup required if vcan0 not available"
echo ""
echo "Use ./start_can_sim.sh to set up vcan0 if needed."
echo ""

# Start Web in Simulation Runtime (with --simulation flag)
# No eager Mock startup, no eager vcan0 setup
python "$SCRIPT_DIR/main.py" web --host 127.0.0.1 --port 5000 --simulation

echo ""
echo "Validator stopped."
