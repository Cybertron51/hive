#!/usr/bin/env bash
set -euo pipefail
for t in agent_runs claims injection_events source_trust heartbeats seen_docs; do
  docker exec tokenshackathon-clickhouse clickhouse-client -q "TRUNCATE TABLE IF EXISTS hive.$t"
done
