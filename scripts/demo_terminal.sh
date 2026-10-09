#!/usr/bin/env bash
# Pre-recording checklist for the Hive demo video. Read-only checks unless flags are given.
#   --open             open dashboard, injection blog and competitors.yaml
#   --serve-fixtures   serve fixtures/ on http://localhost:8081/ (loopback only) for a clean address bar
#   --resize           resize the front Terminal/iTerm window to 1280x800 (macOS)
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

OPEN=0; SERVE=0; RESIZE=0
for a in "$@"; do
  case "$a" in
    --open) OPEN=1 ;;
    --serve-fixtures) SERVE=1 ;;
    --resize) RESIZE=1 ;;
    *) echo "usage: scripts/demo_terminal.sh [--open] [--serve-fixtures] [--resize]"; exit 2 ;;
  esac
done

DASH=http://localhost:8080/
FIX_PORT=8081
BLOG_FILE="$ROOT/fixtures/nullgrid_blog_update.html"
BLOG_URL="file://$BLOG_FILE"
FAIL=0

ok()   { printf '  \033[32m[ok]\033[0m   %s\n' "$1"; }
bad()  { printf '  \033[31m[fail]\033[0m %s\n' "$1"; FAIL=1; }
todo() { printf '  \033[33m[todo]\033[0m %s\n' "$1"; }

echo "== Stack"
[ -x .venv/bin/python ] && ok "venv at .venv" || bad "missing .venv (uv venv --python 3.12 && uv pip install -e .)"
if [ "$(curl -s -m 2 -o /dev/null -w '%{http_code}' "$DASH" 2>/dev/null)" = 200 ]; then ok "dashboard serving at $DASH"; else bad "dashboard not reachable at $DASH (scripts/demo_up.sh)"; fi
if grep -qE '^CLICKHOUSE_URL=https://' .env 2>/dev/null; then
  ok "ClickHouse Cloud configured (CLICKHOUSE_URL is https)"
elif docker ps --format '{{.Names}}' 2>/dev/null | grep -qx tokenshackathon-clickhouse; then
  ok "local ClickHouse container running"
else
  bad "ClickHouse not running (scripts/ch_up.sh)"
fi
if [ -f .env ]; then
  for k in AKASHML_API_KEY SENSO_API_KEY CLICKHOUSE_PASSWORD; do
    grep -qE "^$k=.+" .env && ok ".env has $k" || bad ".env missing $k"
  done
else
  bad "no .env (cp .env.example .env)"
fi
if pgrep -fi 'python.* -m hive\.heartbeat' >/dev/null 2>&1; then todo "background heartbeat is running; stop it before recording: kill \"\$(cat logs/heartbeat.pid)\""; else ok "no background heartbeat (beat 2 runs its own bounded tick)"; fi
if [ -f data/seen.json ]; then todo "data/seen.json exists; rm -f data/seen.json so beat 2 collects documents"; else ok "no data/seen.json"; fi

echo "== Demo assets"
for f in config/competitors.yaml fixtures/nullgrid_blog_update.html fixtures/quillon_funding_news.html fixtures/quillon_press_release.html docs/semgrep/ssrf_poc.png docs/VIDEO_SHOTLIST.md; do
  [ -f "$f" ] && ok "$f" || bad "missing $f"
done

if [ "$SERVE" = 1 ]; then
  if curl -s -m 2 -o /dev/null "http://localhost:$FIX_PORT/" 2>/dev/null; then
    ok "fixtures already served on :$FIX_PORT"
  else
    mkdir -p logs
    nohup .venv/bin/python -m http.server "$FIX_PORT" --bind 127.0.0.1 --directory fixtures >logs/fixtures_http.log 2>&1 &
    echo $! > logs/fixtures_http.pid
    sleep 0.5
    ok "serving fixtures on http://localhost:$FIX_PORT/ (pid $(cat logs/fixtures_http.pid); stop: kill \$(cat logs/fixtures_http.pid))"
  fi
  BLOG_URL="http://localhost:$FIX_PORT/nullgrid_blog_update.html"
fi

if [ "$RESIZE" = 1 ]; then
  if [ "${TERM_PROGRAM:-}" = "iTerm.app" ]; then APP="iTerm2"; else APP="Terminal"; fi
  if osascript -e "tell application \"$APP\" to set bounds of front window to {0, 25, 1280, 825}" >/dev/null 2>&1; then
    ok "resized $APP window to 1280x800"
  else
    todo "could not resize $APP; set the window to 1280x800 by hand"
  fi
fi

if [ "$OPEN" = 1 ]; then
  open "$DASH" && ok "opened dashboard"
  open "$BLOG_URL" && ok "opened injection blog: $BLOG_URL"
  open -t config/competitors.yaml && ok "opened competitors.yaml in the default editor"
fi

echo "== Manual checklist"
todo "Screen recording region 1280x800; browser and terminal windows sized to match"
todo "Terminal font 18 pt (Cmd + until readable); light or dark theme to match the dashboard"
todo "Short prompt: export PS1='hive \$ '; then clear"
todo "Browser tabs, in order: $DASH | $BLOG_URL | view-source:$BLOG_URL"
todo "Browser zoom 110% on the blog tab; hide bookmarks bar; close unrelated tabs"
todo "Terminal working directory: $ROOT"
todo "Do Not Disturb on; notifications hidden"
todo "Dashboard shows history from earlier full ticks (don't run a full tick on stage)"

echo
echo "Shotlist: docs/VIDEO_SHOTLIST.md"
[ "$FAIL" = 0 ] && echo "Ready." || { echo "Fix the [fail] items above before recording."; exit 1; }
