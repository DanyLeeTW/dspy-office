#!/bin/bash
# Kill DSPy Agent Server

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Stopping DSPy Agent Server ==="

# Find and kill main server process
PID=$(pgrep -f "python3.12 dspy_xiaowang.py" 2>/dev/null || true)

if [ -n "$PID" ]; then
    echo "[INFO] Killing server PID: $PID"
    kill $PID 2>/dev/null || true
fi

# Find and kill MLX VLM server (port 8081)
MLX_PID=$(pgrep -f "mlx_vlm.server" 2>/dev/null || true)

if [ -n "$MLX_PID" ]; then
    echo "[INFO] Killing MLX VLM server PID: $MLX_PID"
    kill $MLX_PID 2>/dev/null || true
fi

sleep 1

if pgrep -f "dspy_xiaowang.py" > /dev/null 2>&1 || pgrep -f "mlx_vlm.server" > /dev/null 2>&1; then
    echo "[ERROR] Failed to kill all servers"
    exit 1
else
    echo "[OK] All servers stopped"
fi
