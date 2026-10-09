#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose --env-file .env -f clickhouse/docker-compose.yml up -d
for _ in $(seq 1 60); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' tokenshackathon-clickhouse 2>/dev/null)" = healthy ] && break
  sleep 2
done
scripts/apply_schema.sh
