# Hive: competitive intelligence swarm

A swarm of cheap open-weight agents turns public security-company news into verified competitor intelligence. ClickHouse watches the swarm itself for bad judgments and prompt injection, because the swarm reads untrusted text all day.

![Hive dashboard](screenshots/dashboard.png)

## Data flow

1. A heartbeat runs on a timer. It collects press releases, blogs and filings, and skips documents already in `seen_docs`.
2. A reader (Llama 3.3 70B on AkashML) extracts claims. A classifier scores them. A pattern scanner and canary checks look for injected instructions.
3. A judge (gpt-oss-120b) checks each claim against up to three other documents.
4. Policy decides each claim's status. Verified claims go to the Senso knowledge base, and each source's trust score updates.
5. Every run, claim, injection and heartbeat is logged to ClickHouse. The dashboard polls it every 2 seconds. A writer model drafts the brief.

## Policy thresholds

| Outcome | Rule |
|---|---|
| Verified | judge agrees and confidence is 0.75 or higher |
| Quarantined | judge disagrees, confidence is under 0.6, or injection severity is 0.5 or higher |
| Rerouted | confidence between 0.6 and 0.75, so the read is redone on the larger model |
| Source trust | 1.0, minus 0.3 per injection and 0.15 per judge disagreement |

## ClickHouse tables and the panels that read them

| Table | Panels |
|---|---|
| `agent_runs` | swarm timeline, runs per minute, confidence histogram, cost by model |
| `claims` (latest version per claim) | verified claims feed, quarantine queue, claims by entity, misclassification by model |
| `injection_events` | injection events |
| `source_trust` | source trust |
| `heartbeats` | heartbeat header and history |
| `seen_docs` | none, used only to skip repeated documents |

## Try it

```sh
scripts/demo_up.sh
scripts/stage_queries.sh
```
