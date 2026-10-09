#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

RESET=0
FORCE=0
HEARTBEAT=1
BRIEF=0
INTERVAL=300
USAGE="usage: scripts/demo_up.sh [--reset] [--force] [--no-heartbeat] [--brief] [--interval SECONDS]
  --brief     also draft a brief each tick (costs Senso credits, off by default)
  --interval  seconds between heartbeats (default 300)"
while [ $# -gt 0 ]; do
  case "$1" in
    --reset) RESET=1 ;;
    --force) FORCE=1 ;;
    --no-heartbeat) HEARTBEAT=0 ;;
    --brief) BRIEF=1 ;;
    --interval)
      shift
      case "${1:-}" in ''|*[!0-9]*) echo "$USAGE"; exit 2 ;; *) INTERVAL=$1 ;; esac ;;
    *) echo "$USAGE"; exit 2 ;;
  esac
  shift
done
HB_ARGS=(--interval "$INTERVAL")
[ "$BRIEF" = 1 ] && HB_ARGS+=(--brief)

mkdir -p logs
source scripts/_ch_mode.sh
HB_PATTERN='^[^ ]*[Pp]ython[^ ]* -m hive\.heartbeat'
URL=http://localhost:8080/

alive() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }
dash_up() { [ "$(curl -s -m 2 -o /dev/null -w '%{http_code}' "$URL" 2>/dev/null)" = 200 ]; }
hb_pids() { pgrep -fi "$HB_PATTERN" 2>/dev/null || true; }

echo "== dashboard server"
if dash_up; then
  echo "already serving on :8080"
else
  nohup "$PY" -m http.server 8080 --bind 127.0.0.1 --directory dashboard >logs/dashboard.log 2>&1 </dev/null &
  echo $! >logs/dashboard.pid
  for _ in 1 2 3 4 5 6 7 8 9 10; do dash_up && break; sleep 0.5; done
  if dash_up; then echo "started (pid $(cat logs/dashboard.pid))"; else echo "FAILED to start dashboard server, see logs/dashboard.log"; exit 1; fi
fi

if [ "$IS_CLOUD" = 1 ]; then
  echo "== dashboard proxy (ClickHouse Cloud)"
  if [ "$(curl -s -m 2 -o /dev/null -w '%{http_code}' -X OPTIONS http://localhost:8765/query 2>/dev/null)" = 204 ]; then
    echo "already running"
  else
    nohup "$PY" scripts/dashboard_proxy.py >>logs/proxy.log 2>&1 </dev/null &
    echo $! >logs/proxy.pid
    sleep 1
    if kill -0 "$(cat logs/proxy.pid)" 2>/dev/null; then echo "started (pid $(cat logs/proxy.pid))"; else echo "FAILED, see logs/proxy.log"; exit 1; fi
  fi
  URL=http://localhost:8080/?proxy=1
fi

echo "== preflight"
if ! scripts/preflight.sh; then
  if [ "$FORCE" = 1 ]; then
    echo "preflight failed, continuing because of --force"
  else
    echo "preflight failed, aborting (use --force to continue anyway)"
    exit 1
  fi
fi

if [ "$RESET" = 1 ]; then
  echo "== reset"
  existing=$(hb_pids)
  if [ -n "$existing" ]; then
    echo "stopping running heartbeat first: $(echo $existing)"
    kill $existing 2>/dev/null || true
    sleep 1
  fi
  scripts/reset_db.sh && echo "tables truncated"
fi

echo "== heartbeat"
existing=$(hb_pids)
if [ "$HEARTBEAT" = 0 ]; then
  echo "skipped (--no-heartbeat)"
elif [ -n "$existing" ]; then
  echo "already running (pid $(echo $existing))"
else
  nohup "$PY" -m hive.heartbeat "${HB_ARGS[@]}" >>logs/heartbeat.log 2>&1 </dev/null &
  echo $! >logs/heartbeat.pid
  sleep 3
  if alive logs/heartbeat.pid; then echo "started (pid $(cat logs/heartbeat.pid)), logging to logs/heartbeat.log"; else echo "FAILED, last log lines:"; tail -5 logs/heartbeat.log; exit 1; fi
fi

echo
echo "Dashboard: $URL"
