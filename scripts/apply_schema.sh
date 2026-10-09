#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
DASH_PASSWORD='hive-dashboard-ro'
cat clickhouse/schema.sql clickhouse/queries.sql | docker exec -i tokenshackathon-clickhouse clickhouse-client -n
docker exec -i tokenshackathon-clickhouse clickhouse-client -n <<SQL
CREATE USER IF NOT EXISTS dashboard IDENTIFIED BY '$DASH_PASSWORD' SETTINGS readonly = 1, add_http_cors_header = 1;
ALTER USER dashboard IDENTIFIED BY '$DASH_PASSWORD' SETTINGS readonly = 1, add_http_cors_header = 1;
REVOKE ALL ON *.* FROM dashboard;
GRANT SELECT ON hive.* TO dashboard;
SQL
