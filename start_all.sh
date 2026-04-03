#!/bin/bash
# Start All Services (Backend + Frontend)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Starting All Services ==="

# Start backend
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
