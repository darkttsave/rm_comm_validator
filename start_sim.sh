#!/usr/bin/env bash
# Simulation Runtime launcher
# Starts Validator Web with virtual endpoint capability enabled.

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

echo "[1/3] Checking dependencies..."

# Check socat (for Serial Virtual)
if ! command -v socat >/dev/null 2>&1; then
    echo "  ⚠ socat not found (RM Virtual Serial will be unavailable)"
    echo "    Install: sudo apt install socat"
else
    echo "  ✓ socat available"
fi

# Check if Mock EC is built (for CAN Virtual)
MOCK_EC="$SCRIPT_DIR/tools/mock_ec_node/build/mock_ec_node"
if [ ! -f "$MOCK_EC" ]; then
    echo "  ⚠ Mock EC not built (RM Virtual CAN will be unavailable)"
    echo "    Build: cd tools/mock_ec_node && ./build.sh"
else
    echo "  ✓ Mock EC built"
fi

echo ""
echo "[2/3] Virtual CAN preflight..."

# Check if vcan module is loaded
if lsmod | grep -q vcan; then
    echo "  ✓ vcan kernel module loaded"
else
    echo "  ⚠ vcan kernel module not loaded"
    echo "    Attempting to load (requires sudo)..."
    if sudo modprobe vcan 2>/dev/null; then
        echo "  ✓ vcan module loaded successfully"
    else
        echo "  ✗ Failed to load vcan module"
        echo "    RM Virtual CAN will be unavailable"
    fi
fi

# Check if vcan0 exists
if ip link show vcan0 >/dev/null 2>&1; then
    echo "  ✓ vcan0 already exists"
else
    echo "  ⚠ vcan0 does not exist"
    echo "    Creating vcan0 (requires sudo)..."
    if sudo ip link add dev vcan0 type vcan 2>/dev/null && sudo ip link set up vcan0 2>/dev/null; then
        echo "  ✓ vcan0 created and brought up"
    else
        echo "  ✗ Failed to create vcan0"
        echo "    RM Virtual CAN will be unavailable"
    fi
fi

echo ""
echo "[3/3] Starting Validator Web with Simulation enabled..."
echo "  - Virtual endpoints enabled (RM Virtual Serial / RM Virtual CAN)"
echo "  - Physical Serial/CAN devices available"
echo "  - Demo and Replay available"
echo ""
echo "Virtual endpoints will auto-start when you select them and click Start."
echo ""

# Start Web in Simulation Runtime (with --simulation flag)
python "$SCRIPT_DIR/main.py" web --host 127.0.0.1 --port 5000 --simulation

echo ""
echo "Validator stopped."
