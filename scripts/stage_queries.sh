#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.."

PAUSE=0
[ "${1:-}" = "--pause" ] && PAUSE=1

PW=$(grep -E '^CLICKHOUSE_PASSWORD=' .env 2>/dev/null | tail -1 | cut -d= -f2- | sed -e 's/^["'"'"']//' -e 's/["'"'"']$//')
EXEC=(docker exec -i)
if [ -n "$PW" ]; then
  export CLICKHOUSE_PASSWORD="$PW"
  EXEC+=(-e CLICKHOUSE_USER=default -e CLICKHOUSE_PASSWORD)
fi
EXEC+=(tokenshackathon-clickhouse clickhouse-client --format PrettyCompact)

run() {
  printf '\n\033[1m%s\033[0m\n' "$1"
  out=$("${EXEC[@]}" -q "$2" 2>&1) || { echo "query failed: $out"; return; }
  if [ -n "$out" ]; then echo "$out"; else echo "(no rows)"; fi
  if [ "$PAUSE" = 1 ]; then read -r -p "(enter for next) " _ </dev/tty || true; fi
}

read -r -d '' Q1 <<'SQL'
SELECT model, judged, disagreed, disagree_rate
FROM hive.misclassification_by_model
WHERE swarm_id = (
    SELECT swarm_id FROM hive.agent_runs
    WHERE swarm_id IN (SELECT swarm_id FROM hive.misclassification_by_model)
    GROUP BY swarm_id ORDER BY max(ts) DESC LIMIT 1
)
SQL

read -r -d '' Q2 <<'SQL'
SELECT formatDateTime(ts, '%H:%i:%S') AS time, source_id, detector, pattern,
       substring(replaceRegexpAll(snippet, '[\\r\\n\\t]+', ' '), 1, 80) AS snippet
FROM hive.injection_recent
ORDER BY ts DESC
LIMIT 10
SQL

read -r -d '' Q3 <<'SQL'
SELECT model, role, count() AS runs,
       round(quantile(0.5)(latency_ms)) AS p50_ms,
       round(quantile(0.95)(latency_ms)) AS p95_ms,
       round(sum(cost_usd), 5) AS cost_usd
FROM hive.agent_runs
GROUP BY model, role
ORDER BY model, role
SQL

read -r -d '' Q4 <<'SQL'
SELECT entity,
       countIf(status = 'verified') AS verified,
       count() AS total,
       ifNotFinite(round(avgIf(confidence, status = 'verified'), 2), 0) AS avg_conf_verified,
       round(avg(confidence), 2) AS avg_conf_all
FROM hive.claims FINAL
GROUP BY entity
ORDER BY verified DESC, total DESC
LIMIT 15
SQL

run "1. Which model does the judge disagree with most? (latest swarm with judged claims)" "$Q1"
run "2. Prompt injection caught in the wild: source, detector, pattern and the hostile text" "$Q2"
run "3. What the swarm costs: latency p50/p95 and spend per model and role" "$Q3"
run "4. The CI payoff: verified claims per competitor with average confidence" "$Q4"
