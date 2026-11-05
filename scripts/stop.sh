#!/usr/bin/env bash
# Stop Ravi AI Infrastructure
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "Stopping Ravi..."
docker compose down
echo "Ravi stopped."
