#!/usr/bin/env bash
# Start Ravi AI Infrastructure
# Prefer the cross-platform CLI:  ravi start

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo ".env not found. Run:  cp .env.example .env  and configure it."
  exit 1
fi

echo "Starting Ravi AI Infrastructure..."
docker compose up -d --build
echo "Ravi is running at http://127.0.0.1:4000"
echo "Tip: pip install -e .  &&  ravi --help"
