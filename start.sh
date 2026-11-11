#!/usr/bin/env bash
# BypassX Management — start script (Linux/macOS)
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found. Copy .env.example to .env and fill in your values:"
    echo "  cp .env.example .env"
    exit 1
fi

if ! python3 -c "import discord" 2>/dev/null; then
    echo "Dependencies not installed. Installing from requirements.txt..."
    pip3 install -r requirements.txt
fi

echo "Starting BypassX Management..."
exec python3 main.py
