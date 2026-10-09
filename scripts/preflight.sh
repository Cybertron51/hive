#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

CONTAINER=tokenshackathon-clickhouse
CH=http://localhost:8123
FAILS=0

pass() { printf '  PASS  %s\n' "$1"; }
fail() { printf '  FAIL  %s\n' "$1"; FAILS=$((FAILS + 1)); }
note() { printf '  NOTE  %s\n' "$1"; }

envval() {
  [ -f .env ] || return 0
  grep -E "^$1=" .env | tail -1 | cut -d= -f2- | sed -e 's/^["'"'"']//' -e 's/["'"'"']$//'
}

echo "Docker"
if docker info >/dev/null 2>&1; then pass "docker daemon running"; else fail "docker daemon not running"; fi

echo "ClickHouse"
health=$(docker inspect -f '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo missing)
if [ "$health" = healthy ]; then pass "container $CONTAINER healthy"; else fail "container $CONTAINER status: $health"; fi
if [ "$(curl -s -m 3 "$CH/ping" 2>/dev/null)" = "Ok." ]; then pass "HTTP :8123 responds"; else fail "HTTP :8123 not responding"; fi

TABLES="agent_runs claims injection_events source_trust"
VIEWS="latest_swarm runs_per_minute_by_model confidence_histogram quarantine_queue claims_by_status injection_recent injection_counts misclassification_by_model cost_by_model source_trust_current runs_timeline"
have=$(curl -s -m 5 "$CH/" --data-binary "SELECT name FROM system.tables WHERE database = 'hive'" 2>/dev/null)
if [ -z "$have" ]; then
  fail "database hive missing or empty (run scripts/apply_schema.sh)"
else
  missing=""
  for n in $TABLES $VIEWS; do echo "$have" | grep -qx "$n" || missing="$missing $n"; done
  if [ -z "$missing" ]; then pass "hive database: all tables and views present"; else fail "hive objects missing:$missing"; fi
  bad=""
  for v in $VIEWS; do
    out=$(curl -s -m 5 "$CH/" --data-binary "SELECT count() FROM hive.$v" 2>&1)
    case "$out" in *Exception*|*Code:*) bad="$bad $v" ;; esac
  done
  if [ -z "$bad" ]; then pass "all views query without error"; else fail "views erroring:$bad"; fi
fi

echo "Environment"
if [ -f .env ]; then pass ".env present"; else fail ".env missing"; fi
for k in AKASHML_API_KEY AKASHML_MODEL_SMALL AKASHML_MODEL_LARGE AKASHML_MODEL_WRITER; do
  if [ -n "$(envval $k)" ]; then pass "$k set"; else fail "$k empty or missing in .env"; fi
done

echo "AkashML"
KEY=$(envval AKASHML_API_KEY)
BASE=$(envval AKASHML_BASE_URL); BASE=${BASE:-https://api.akashml.com/v1}
MODEL=$(envval AKASHML_MODEL_SMALL)
if [ -n "$KEY" ] && [ -n "$MODEL" ]; then
  body=$(printf '{"model":"%s","messages":[{"role":"user","content":"ping"}],"max_tokens":1}' "$MODEL")
  resp=$(curl -s -m 30 -o /tmp/preflight_akash.$$ -w '%{http_code} %{time_total}' -K - "$BASE/chat/completions" \
    -H "Content-Type: application/json" -d "$body" <<<"header = \"Authorization: Bearer $KEY\"" 2>/dev/null || echo "000 0")
  code=${resp%% *}; secs=${resp##* }
  ms=$(awk -v s="$secs" 'BEGIN{printf "%d", s*1000}')
  if [ "$code" = 200 ] && grep -q '"choices"' /tmp/preflight_akash.$$ 2>/dev/null; then
    pass "chat completion on $MODEL (${ms} ms)"
  else
    fail "chat completion on $MODEL failed: HTTP $code (${ms} ms)"
  fi
  rm -f /tmp/preflight_akash.$$
else
  fail "skipped chat completion: key or small model missing"
fi

echo "Senso"
if [ -n "$(envval SENSO_API_KEY)" ]; then pass "SENSO_API_KEY set"; else note "SENSO_API_KEY unset: local KB fallback will be used"; fi

echo "Dashboard"
if [ "$(curl -s -m 3 -o /dev/null -w '%{http_code}' http://localhost:8080/ 2>/dev/null)" = 200 ]; then
  pass "dashboard reachable on :8080"
else
  fail "dashboard not reachable on :8080 (cd dashboard && python -m http.server 8080)"
fi

echo
if [ "$FAILS" -eq 0 ]; then echo "PREFLIGHT OK"; else echo "PREFLIGHT FAILED: $FAILS hard failure(s)"; fi
[ "$FAILS" -eq 0 ]
