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

# Install pinned packages into a local .venv only when requirements.txt has active dependencies.
if grep -Eq '^[[:space:]]*[^#[:space:]]' requirements.txt 2>/dev/null; then
  if [ ! -d .venv ]; then
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -q -r requirements.txt
  python src/app.py "$@"
else
  python3 src/app.py "$@"
fi
