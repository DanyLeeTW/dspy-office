#!/bin/bash
# Start All Services (MCP + Backend + Frontend)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Starting All Services ==="

# Start MCP servers first (HTTP transport for concurrent tool calls)
if [ -f "./start_mcp_notebooklm.sh" ]; then
    echo ""
    echo "=== Starting MCP Servers ==="
    ./start_mcp_notebooklm.sh || echo "[WARN] MCP server failed to start, continuing..."
fi

# Start backend
echo ""
./start_server.sh

# Start frontend
echo ""
echo "=== Starting Frontend ==="
cd frontend

if [ ! -d "node_modules" ]; then
    echo "[INFO] Installing dependencies..."
    npm install
fi

echo "[INFO] Starting frontend dev server on port 3000..."
npm run dev &

echo ""
echo "=== Services Started ==="
echo "Backend:  http://localhost:8080"
echo "Frontend: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop all services"
wait
