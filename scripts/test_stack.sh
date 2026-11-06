#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose --env-file _workspace/compose.env -p open-casting exec -T app sh -c \
  'TEST_DATABASE_URL="$DATABASE_URL" TEST_REDIS_URL=redis://valkey:6379/15 RATE_LIMIT_IP=300 python -m pytest -q -o cache_dir=/tmp/pytest-cache'
