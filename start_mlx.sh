#!/bin/bash
# Start MLX VLM Server for local inference
# Model: mlx-community/gemma-4-e4b-it-8bit (Vision-Language Model)

# Install mlx-vlm if not installed
if ! python -c "import mlx_vlm" 2>/dev/null; then
    echo "Installing mlx-vlm..."
    pip install -U mlx-vlm
fi

MODEL="mlx-community/gemma-4-e4b-it-8bit"
PORT=8081

echo "Starting MLX VLM Server..."
echo "  Model: $MODEL"
echo "  Port: $PORT"
echo "  API: http://localhost:$PORT/v1"
echo ""

# Optimization: Check port availability and cooldown before starting
if lsof -i :$PORT > /dev/null 2>&1; then
    echo "[WARN] Port $PORT already in use. Killing old server..."
    lsof -t -i :$PORT | xargs kill -9 > /dev/null 2>&1 || true
    sleep 2
fi

# Set environment variable for dspy-office to use local MLX model
export DSPY_MODEL=local-mlx

# Optimization: Give LSP some breathing room before launching resource-intensive model
echo "[INFO] Waiting for system stabilization (3s)..."
sleep 3

# mlx-vlm server (OpenAI-compatible API)
echo "Launching MLX VLM Server..."
python -m mlx_vlm.server \
    --model "$MODEL" \
    --port $PORT
