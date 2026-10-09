#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

stop() {
  name=$1; pidfile=$2; pattern=$3
  pids=$(pgrep -fi "$pattern" 2>/dev/null || true)
  [ -f "$pidfile" ] && pids="$pids $(cat "$pidfile")"
  pids=$(echo $pids | tr ' ' '\n' | sort -u | while read -r p; do [ -n "$p" ] && kill -0 "$p" 2>/dev/null && echo "$p"; done)
  if [ -z "$pids" ]; then
    echo "$name: not running"
  else
    kill $pids 2>/dev/null || true
    for _ in 1 2 3 4 5 6; do
      sleep 0.5
      still=$(for p in $pids; do kill -0 "$p" 2>/dev/null && echo "$p"; done)
      [ -z "$still" ] && break
    done
    [ -n "${still:-}" ] && kill -9 $still 2>/dev/null || true
    echo "$name: stopped (pid $(echo $pids))"
  fi
  rm -f "$pidfile"
}

stop heartbeat logs/heartbeat.pid 'python.* -m hive\.heartbeat'
stop dashboard logs/dashboard.pid 'python.* -m http\.server 8080'
stop proxy logs/proxy.pid 'python.* scripts/dashboard_proxy\.py'
