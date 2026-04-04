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

# Set environment variable for dspy-office to use local MLX model
export DSPY_MODEL=local-mlx

# mlx-vlm server (OpenAI-compatible API)
python -m mlx_vlm.server \
    --model "$MODEL" \
    --port $PORT
