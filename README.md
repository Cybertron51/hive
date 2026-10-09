# Hive

Hive is an open-internet intelligence scraper run by a swarm of small agents on cheap open-weight models, with a security layer that watches the swarm itself. Give it a set of companies and it sends scouts, readers, classifiers and judges across public sources (RSS, SEC EDGAR, company pages). The agents extract claims, verify them against each other and write briefs. Every agent call is logged to ClickHouse, so misclassification, low confidence, agent disagreement and prompt injection hidden in scraped pages show up in real time and are quarantined before they reach a brief. Verified claims go into Senso, and the writer agent reads nothing else.

## Architecture

```
collectors (RSS, EDGAR, fixtures) ──> raw documents
        │
        ▼
swarm on AkashML: scout → reader → classifier → judge      every call ──> ClickHouse agent_runs
        │                     │                                              │
        │          injection detector (heuristics + canary) ──> injection_events
        ▼                                                                    ▼
judged claims ──> Senso (verified KB) ──> writer ──> cited brief    monitoring plane: quarantine,
                                                                    reroute, source trust penalties
```

- **Collectors** (`hive/collectors`) pull public sources and the fixture set into raw documents. One fixture carries a prompt injection and one carries a planted false number.
- **Swarm** (`hive/swarm`) runs role-typed agents concurrently with asyncio. Each agent returns structured JSON with a confidence field.
- **Monitoring plane** reads ClickHouse views to quarantine bad outputs, reroute uncertain ones and lower trust in sources that inject.
- **Verified KB** (`hive/senso`) holds judged claims only. If `SENSO_API_KEY` is unset, a local JSON store with the same interface stands in.
- **Writer** (`hive/writer`) answers only from KB passages. Every sentence must cite a passage, and the code drops any sentence without a valid citation.
- **Dashboard** (`dashboard/`) is a static page that polls ClickHouse over HTTP.

## Sponsor tools

| Tool | What it does in Hive |
|---|---|
| AkashML | Runs every swarm agent on open-weight models: small models for reader and classifier, larger ones for judge and writer |
| ClickHouse | Event store for agent runs, claims, injection events and source trust, plus the views behind the dashboard and the monitoring plane |
| Senso | Verified knowledge base. Judged claims are ingested, and the writer grounds on `/org/search/context` passages with citations |
| Semgrep Guardian | Scanned every edit across four Claude Code sessions while we built; see [docs/SEMGREP.md](docs/SEMGREP.md) |

## Run

```sh
uv venv --python 3.12 && uv pip install -e .
cp .env.example .env   # fill AKASHML_*, SENSO_API_KEY
docker compose -f clickhouse/docker-compose.yml up -d
cat clickhouse/schema.sql clickhouse/queries.sql | docker exec -i tokenshackathon-clickhouse clickhouse-client -n
```

Start the swarm:

```sh
# TODO(A): orchestrator command
```

Open the dashboard:

```sh
# TODO(A): dashboard command
```

Write a cited brief from the verified KB:

```sh
.venv/bin/python -m hive.writer.brief "<ENTITY>" "<question>" --out docs/sample_brief.md
```

See [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) for the 3-minute demo.
