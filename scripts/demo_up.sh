#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

RESET=0
FORCE=0
for a in "$@"; do
  case "$a" in
    --reset) RESET=1 ;;
    --force) FORCE=1 ;;
    *) echo "usage: scripts/demo_up.sh [--reset] [--force]"; exit 2 ;;
  esac
done

mkdir -p logs
PY=.venv/bin/python
HB_PATTERN='python.* -m hive\.heartbeat'
URL=http://localhost:8080/

alive() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }
dash_up() { [ "$(curl -s -m 2 -o /dev/null -w '%{http_code}' "$URL" 2>/dev/null)" = 200 ]; }
hb_pids() { pgrep -fi "$HB_PATTERN" 2>/dev/null || true; }

echo "== dashboard server"
if dash_up; then
  echo "already serving on :8080"
else
  (cd dashboard && nohup "../$PY" -m http.server 8080 --bind 127.0.0.1 >../logs/dashboard.log 2>&1 & echo $! >../logs/dashboard.pid)
  for _ in 1 2 3 4 5 6 7 8 9 10; do dash_up && break; sleep 0.5; done
  if dash_up; then echo "started (pid $(cat logs/dashboard.pid))"; else echo "FAILED to start dashboard server, see logs/dashboard.log"; exit 1; fi
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
if [ -n "$existing" ]; then
  echo "already running (pid $(echo $existing))"
else
  nohup "$PY" -m hive.heartbeat --interval 90 --brief >>logs/heartbeat.log 2>&1 &
  echo $! >logs/heartbeat.pid
  sleep 3
  if alive logs/heartbeat.pid; then echo "started (pid $(cat logs/heartbeat.pid)), logging to logs/heartbeat.log"; else echo "FAILED, last log lines:"; tail -5 logs/heartbeat.log; exit 1; fi
fi

echo
echo "Dashboard: $URL"
