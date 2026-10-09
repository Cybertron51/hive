# ClickHouse telemetry for Hive

Database `hive`: `agent_runs`, `claims`, `injection_events`, `source_trust` (ReplacingMergeTree), plus views in `queries.sql`. `claims` is ReplacingMergeTree on `updated_at`, so bump `updated_at` whenever a claim's status changes.

## Start

```sh
docker compose -f clickhouse/docker-compose.yml up -d
```

## Load schema and views (idempotent, drops the old `guard` db)

```sh
scripts/apply_schema.sh
```

Clear all four tables with `scripts/reset_db.sh`. Changing a table's engine needs a manual `DROP TABLE` first, since the schema uses `IF NOT EXISTS`.

## Seed demo data

```sh
.venv/bin/python clickhouse/seed.py
```

## Query

```sh
docker exec -it tokenshackathon-clickhouse clickhouse-client -q "SELECT * FROM hive.misclassification_by_model"
```

## Dashboard

```sh
cd dashboard && python -m http.server 8080
```

Open http://localhost:8080. It polls ClickHouse HTTP on :8123 every 2s. The "latest swarm only" toggle (on by default) filters every swarm-scoped panel to the newest swarm_id; source trust is global.

## From the swarm

```python
from hive import telemetry
telemetry.log_run(run); telemetry.log_claim(claim); telemetry.log_injection(ev); telemetry.upsert_trust(t)
telemetry.flush()
```

Writes are buffered (auto-flush at 50 rows and at exit). If ClickHouse is down, batches are dropped with a warning and nothing raises.
