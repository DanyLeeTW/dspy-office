#!/bin/bash
# Check status of all related servers

echo "=== System Health Check ==="
echo "Date: $(date)"
echo ""

# 1. Antigravity LSP (Port 63219)
echo "Checking Antigravity Language Server (Port 63219)..."
if lsof -i :63219 > /dev/null 2>&1; then
    PID=$(lsof -t -i :63219)
    echo "[OK] LSP is LISTENING on PID $PID"
    # Check if process is responsive (macOS compatible ps)
    ps -p $PID -o %cpu,%mem,comm | sed -n '2p'
else
    echo "[ERROR] LSP is NOT listening on port 63219!"
fi
echo ""

# 2. MLX VLM Server (Port 8081)
echo "Checking MLX VLM Server (Port 8081)..."
if curl -s http://localhost:8081/v1/models > /dev/null 2>&1; then
    echo "[OK] MLX Server is responsive"
else
    echo "[WARN] MLX Server is NOT responding or not started"
fi
echo ""

# 3. DSPy Agent Server (Port 8080)
echo "Checking DSPy Agent Server (Port 8080)..."
if curl -s http://localhost:8080/ > /dev/null 2>&1; then
    echo "[OK] DSPy Agent is running"
else
    echo "[WARN] DSPy Agent is NOT responding"
fi

echo ""
echo "=== End of Check ==="
