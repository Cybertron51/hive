#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/_ch_mode.sh
for t in agent_runs claims injection_events source_trust heartbeats seen_docs; do
  if [ "$IS_CLOUD" = 1 ]; then
    $PY scripts/chsql.py -q "TRUNCATE TABLE IF EXISTS hive.$t"
  else
    docker exec "$CONTAINER" clickhouse-client -q "TRUNCATE TABLE IF EXISTS hive.$t"
  fi
done
