#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
PORT="${PORT:-8080}"
echo "Serving Day {{DAY_PADDED}} static demo at http://127.0.0.1:${PORT}"
python3 -m http.server "${PORT}" --directory src --bind 127.0.0.1
