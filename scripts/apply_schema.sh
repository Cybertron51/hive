#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/_ch_mode.sh

RO_PASSWORD=$(envval CLICKHOUSE_RO_PASSWORD)
if [ "$IS_CLOUD" = 1 ]; then
  $PY scripts/chsql.py --file clickhouse/schema.sql clickhouse/queries.sql
  $PY scripts/sync_sources.py | $PY scripts/chsql.py --file /dev/stdin
  if [ -z "$RO_PASSWORD" ]; then
    echo "NOTE: CLICKHOUSE_RO_PASSWORD not set in .env, skipping the read-only dashboard user on Cloud"
    exit 0
  fi
  USER_SQL_FULL="CREATE USER IF NOT EXISTS dashboard IDENTIFIED BY '$RO_PASSWORD' SETTINGS readonly = 1, add_http_cors_header = 1"
  ALTER_FULL="ALTER USER dashboard IDENTIFIED BY '$RO_PASSWORD' SETTINGS readonly = 1, add_http_cors_header = 1"
  USER_SQL_PLAIN="CREATE USER IF NOT EXISTS dashboard IDENTIFIED BY '$RO_PASSWORD' SETTINGS readonly = 1"
  ALTER_PLAIN="ALTER USER dashboard IDENTIFIED BY '$RO_PASSWORD' SETTINGS readonly = 1"
  if $PY scripts/chsql.py -q "$USER_SQL_FULL" -q "$ALTER_FULL" 2>/dev/null; then
    echo "dashboard user ready (readonly, CORS header enabled)"
  elif $PY scripts/chsql.py -q "$USER_SQL_PLAIN" -q "$ALTER_PLAIN"; then
    echo "NOTE: Cloud rejected add_http_cors_header for the dashboard user; run scripts/dashboard_proxy.py and set DASHBOARD_PROXY=1"
  else
    echo "FAILED to create the dashboard user on Cloud"; exit 1
  fi
  $PY scripts/chsql.py -q "REVOKE ALL ON *.* FROM dashboard" -q "GRANT SELECT ON hive.* TO dashboard"
else
  RO_PASSWORD=${RO_PASSWORD:-hive-dashboard-ro}
  cat clickhouse/schema.sql clickhouse/queries.sql | docker exec -i "$CONTAINER" clickhouse-client -n
  $PY scripts/sync_sources.py | docker exec -i "$CONTAINER" clickhouse-client -n
  docker exec -i "$CONTAINER" clickhouse-client -n <<SQL
CREATE USER IF NOT EXISTS dashboard IDENTIFIED BY '$RO_PASSWORD' SETTINGS readonly = 1, add_http_cors_header = 1;
ALTER USER dashboard IDENTIFIED BY '$RO_PASSWORD' SETTINGS readonly = 1, add_http_cors_header = 1;
REVOKE ALL ON *.* FROM dashboard;
GRANT SELECT ON hive.* TO dashboard;
SQL
fi
