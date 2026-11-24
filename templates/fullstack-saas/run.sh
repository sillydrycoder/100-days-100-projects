#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export DEMO_MODE="${DEMO_MODE:-true}"
export API_PORT="${API_PORT:-8000}"

echo "Starting Day {{DAY_PADDED}} Full-Stack SaaS demo on http://localhost:${API_PORT} (DEMO_MODE=${DEMO_MODE})"
python3 backend/main.py
