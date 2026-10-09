# Hive demo script (3:00)

Setup before recording: ClickHouse up, `.env` filled, dashboard open in a browser tab, one terminal at the repo root, `data/kb.json` and the `hive` database empty.

```sh
docker compose -f clickhouse/docker-compose.yml up -d
cat clickhouse/schema.sql clickhouse/queries.sql | docker exec -i tokenshackathon-clickhouse clickhouse-client -n
rm -f data/kb.json
```

Lines marked `TODO(A)` depend on the orchestrator CLI; confirm the exact command once it lands.

## 0:00 to 0:20 Hook

> "Agents that scrape the open web read untrusted text thousands of times a day. Hive is a swarm of cheap open-weight agents doing competitive intelligence on biotech companies, and a monitoring plane that treats the swarm itself as the thing under attack."

## 0:20 to 0:50 Kick off the swarm

```sh
.venv/bin/python -m hive.orchestrator --targets config/targets.yaml --fixtures fixtures/   # TODO(A): confirm flags
```

Switch to the dashboard. Point at runs per minute by model climbing, and at the role, model, latency and cost columns.

> "Every call by every agent (scout, reader, classifier, judge) lands in ClickHouse within a second. All of it runs on AkashML open-weight models."

## 0:50 to 1:20 A clean claim

On the dashboard, open one verified claim, or run:

```sh
docker exec -it tokenshackathon-clickhouse clickhouse-client -q \
  "SELECT entity, claim_type, value, confidence, judge_verdict, senso_node_id FROM hive.claims FINAL WHERE status='verified' LIMIT 5"
```

> "The scout found a press release, the reader extracted a claim with a confidence score, the classifier labelled it, and the judge confirmed it against a second source. Only then was it written to Senso."

## 1:20 to 2:00 The catch (lead with this if short on time)

Dashboard: injection events panel, then quarantine queue.

```sh
docker exec -it tokenshackathon-clickhouse clickhouse-client -q "SELECT * FROM hive.injection_recent LIMIT 5"
docker exec -it tokenshackathon-clickhouse clickhouse-client -q "SELECT * FROM hive.source_trust_current"
```

> "This fixture page hides an instruction telling the agent to mark a competitor's trial as failed and to report a fake funding round. The heuristic detector flagged the page, the canary tripped on the reader's output, and the judge disagreed with the claim. It was quarantined, it never reached Senso, and the source lost trust."

## 2:00 to 2:20 Uncertainty

Dashboard: low-confidence and quarantine queue.

> "Low confidence and agent disagreement don't go into the brief. They're routed to a larger model or to a human."

## 2:20 to 2:45 The brief

```sh
.venv/bin/python -m hive.writer.brief "<ENTITY>" "What are the latest clinical and financing developments?" --out docs/sample_brief.md
```

> "The writer reads only from Senso's verified claims. Every sentence carries a citation, and the code drops any sentence the model returns without a valid one."

Then the trap question, which is not in the KB:

```sh
.venv/bin/python -m hive.writer.brief "<ENTITY>" "What is <ENTITY>'s stock price and market cap?"
```

Expected output: `_No verified claims in the knowledge base answer this question._`

> "The KB has nothing on the stock price, so the writer refuses instead of guessing, even though passages about the company were retrieved. It doesn't fill gaps with outside knowledge."

Then the live query on stage:

```sh
docker exec -it tokenshackathon-clickhouse clickhouse-client -q "SELECT * FROM hive.misclassification_by_model"
```

> "Misclassification rate by model over this run, straight from ClickHouse."

## 2:45 to 3:00 Semgrep close

Show `docs/SEMGREP.md` and the screenshot of the Guardian finding.

> "Semgrep Guardian scanned every edit across four Claude Code sessions while we built. This is what it caught, and here is the fix."
