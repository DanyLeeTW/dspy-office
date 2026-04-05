#!/bin/bash
# Start NotebookLM MCP Server (HTTP Transport)
#
# This script starts the notebooklm-mcp server with HTTP transport,
# enabling concurrent tool calls (no serialization lock).
#
# Default: http://127.0.0.1:8765/mcp

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Starting NotebookLM MCP Server ==="

# Check if already running
if pgrep -f "notebooklm-mcp.*--transport http" > /dev/null 2>&1; then
    echo "[WARN] NotebookLM MCP server already running. PID: $(pgrep -f 'notebooklm-mcp.*--transport http')"
    exit 0
fi

# Find notebooklm-mcp binary
NLM_BIN="${NLM_BIN:-$(which notebooklm-mcp 2>/dev/null || echo '')}"
if [ -z "$NLM_BIN" ]; then
    # Try uv tool location
    NLM_BIN="$HOME/.local/share/uv/tools/notebooklm-mcp-cli/bin/notebooklm-mcp"
fi

if [ ! -x "$NLM_BIN" ]; then
    echo "[ERROR] notebooklm-mcp not found. Install with: uv tool install notebooklm-mcp-cli"
    exit 1
fi

echo "[INFO] Using: $NLM_BIN"

# Start server with HTTP transport
# Port 8765 to avoid conflicts with other services
HOST="${NLM_HOST:-127.0.0.1}"
PORT="${NLM_PORT:-8765}"

echo "[INFO] Starting on $HOST:$PORT..."
nohup "$NLM_BIN" --transport http --host "$HOST" --port "$PORT" > mcp_notebooklm.log 2>&1 &

# Wait and verify
sleep 2
if pgrep -f "notebooklm-mcp.*--transport http" > /dev/null 2>&1; then
    PID=$(pgrep -f "notebooklm-mcp.*--transport http")
    echo "[OK] MCP server started. PID: $PID"
    echo "[OK] Log file: $SCRIPT_DIR/mcp_notebooklm.log"
    echo "[OK] Endpoint: http://$HOST:$PORT/mcp"
else
    echo "[ERROR] MCP server failed to start. Check mcp_notebooklm.log"
    cat mcp_notebooklm.log
    exit 1
fi
