#!/bin/bash
# Kill DSPy Agent Server

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Stopping DSPy Agent Server ==="

# Find and kill server process
PID=$(pgrep -f "python3.12 dspy_xiaowang.py" 2>/dev/null || true)

if [ -z "$PID" ]; then
    echo "[INFO] Server is not running"
    exit 0
fi

echo "[INFO] Killing server PID: $PID"
kill $PID 2>/dev/null || true

# Wait for process to die
sleep 1

if pgrep -f "python3.12 dspy_xiaowang.py" > /dev/null 2>&1; then
    echo "[WARN] Process still running, force killing..."
    pkill -9 -f "python3.12 dspy_xiaowang.py" 2>/dev/null || true
    sleep 1
fi

if pgrep -f "python3.12 dspy_xiaowang.py" > /dev/null 2>&1; then
    echo "[ERROR] Failed to kill server"
    exit 1
else
    echo "[OK] Server stopped"
fi
