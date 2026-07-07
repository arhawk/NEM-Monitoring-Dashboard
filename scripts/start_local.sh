#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

docker compose up -d --build

echo ""
echo "NEM stack is starting:"
echo "  Dashboard: http://127.0.0.1:8501"
echo "  MQTT:      127.0.0.1:1883"
echo ""
echo "To stop: docker compose down"
