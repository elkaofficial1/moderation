#!/bin/bash
set -e

echo "=== Starting Ollama ==="
ollama serve > /tmp/ollama.log 2>&1 &
OLLAMA_PID=$!

echo "=== Waiting for Ollama ==="
until curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; do
    sleep 1
done

echo "=== Checking qwen2.5:3b ==="
if ! ollama list | grep -q '^qwen2.5:3b'; then
    echo "=== Downloading qwen2.5:3b ==="
    ollama pull qwen2.5:3b
else
    echo "=== qwen2.5:3b already exists ==="
fi

echo "=== Starting Telegram bot ==="
exec python3 bot.py
