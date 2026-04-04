#!/bin/bash
# Start DSPy Agent Server

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Starting DSPy Agent Server ==="

# Start MLX VLM Server first (if not running)
if ! pgrep -f "mlx_vlm.server" > /dev/null 2>&1; then
    echo "[INFO] Starting MLX VLM Server..."
    ./start_mlx.sh > mlx_server.log 2>&1 &
    sleep 5  # Wait for model to load
    echo "[OK] MLX VLM Server started on port 8081"
else
    echo "[INFO] MLX VLM Server already running"
fi

# Check if already running
if pgrep -f "python3.12 dspy_xiaowang.py" > /dev/null 2>&1; then
    echo "[WARN] Server already running. PID: $(pgrep -f 'python3.12 dspy_xiaowang.py')"
    exit 0
fi

# Check config exists
if [ ! -f "config.json" ]; then
    echo "[ERROR] config.json not found"
    exit 1
fi

# Start server
echo "[INFO] Starting server on port 8080..."
nohup python3.12 dspy_xiaowang.py > server.log 2>&1 &

# Wait and verify
sleep 2
if pgrep -f "python3.12 dspy_xiaowang.py" > /dev/null 2>&1; then
    PID=$(pgrep -f "python3.12 dspy_xiaowang.py")
    echo "[OK] Server started. PID: $PID"
    echo "[OK] Log file: $SCRIPT_DIR/server.log"
    echo "[OK] Health check: curl http://localhost:8080/"
else
    echo "[ERROR] Server failed to start. Check server.log"
    cat server.log
    exit 1
fi
