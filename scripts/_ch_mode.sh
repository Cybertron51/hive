envval() {
  local v="${!1:-}"
  if [ -n "$v" ]; then echo "$v"; return; fi
  [ -f .env ] || return 0
  grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e 's/^["'"'"']//' -e 's/["'"'"']$//' || true
}

PY=.venv/bin/python
CONTAINER=tokenshackathon-clickhouse
IS_CLOUD=0
case "$(envval CLICKHOUSE_URL)" in https://*) IS_CLOUD=1 ;; esac
case "$(envval CLICKHOUSE_SECURE)" in 1|true|True|TRUE) IS_CLOUD=1 ;; esac
case "${HIVE_CH_MODE:-}" in cloud) IS_CLOUD=1 ;; local) IS_CLOUD=0 ;; esac
