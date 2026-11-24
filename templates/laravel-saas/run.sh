#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
fi

if [ -f artisan ]; then
  if [ ! -d vendor ] && command -v composer >/dev/null 2>&1; then
    composer install --no-interaction --prefer-dist
  fi
  mkdir -p database
  touch database/database.sqlite
  php artisan key:generate --force || true
  php artisan migrate --seed --force
  php artisan serve --host=127.0.0.1 --port="${APP_PORT:-8000}"
else
  echo "Laravel app files not initialized yet in this folder."
  echo "Initialize with: composer create-project laravel/laravel . && ./run.sh"
  echo "Or add a docker-compose.yml for containerized PHP execution."
  exit 0
fi
