# Hive architecture

Hive is a swarm of cheap open-weight agents that reads untrusted web pages all day, and ClickHouse watches the swarm itself so a poisoned blog post can't ship a fake breach into a brief. The use case is competitive intelligence on security vendors.

![Hive dashboard](screenshots/dashboard.png)

## Data flow

1. A heartbeat runs on a timer. It collects press releases, blogs and filings, and skips documents already in `seen_docs`.
2. A reader (Llama 3.3 70B on AkashML) extracts claims. A classifier scores them. A pattern scanner and canary checks look for injected instructions.
3. A judge (gpt-oss-120b) checks each claim against up to three other documents. A claim with no second source goes to a grounding judge that checks it against its own source.
4. Policy decides each claim's status. Verified claims go to the Senso knowledge base, and each source's trust score updates.
5. Every run, claim, injection and heartbeat is logged to ClickHouse. The dashboard polls it every 2 seconds. A writer model drafts the brief.

## Policy thresholds

Constants from `hive/swarm/policy.py`; the dashboard legend is generated from them.

| Outcome | Rule |
|---|---|
| Verified | judge agrees and confidence is at least 0.75. A claim grounded only in its own source also needs source trust of at least 0.7 |
| Quarantined | judge disagrees, confidence is under 0.6, or the document has an injection event of severity 0.6 or more |
| Rerouted | confidence from 0.6 up to 0.75, so the read is redone on the larger model |
| Pending | none of the above, for example no judge verdict |
| Source trust | 1.0, minus 0.3 times severity per injection event of 0.5 or more (once per document and pattern), minus 0.15 per judge disagreement |

## ClickHouse tables and the panels that read them

| Table | Panels |
|---|---|
| `agent_runs` | swarm timeline, runs per minute, confidence histogram, cost by model |
| `claims` (latest version per claim) | verified claims feed, quarantine queue, claims by entity, misclassification by model |
| `injection_events` | injection events |
| `source_trust` | source trust |
| `heartbeats` | heartbeat header and history |
| `seen_docs` | none, only skips repeats |

## Models and cost

| Role | Model on AkashML | Price per M tokens (input/output) |
|---|---|---|
| Reader, classifier | Llama 3.3 70B Instruct | $0.20 / $0.52 |
| Judge, grounding judge, reroute | gpt-oss-120b | $0.037 / $0.187 |
| Writer | Qwen 3.8 27B | $0.225 / $1.98 |

A full heartbeat over 96 docs made 745 calls for $0.13 in 9.7 minutes. See [EVAL.md](EVAL.md) for accuracy.

## Storage and access

ClickHouse Cloud holds the data over TLS with a password. The dashboard reads through a local read-only proxy, so no credentials reach the browser. A password-protected local container on 127.0.0.1 is the fallback.

## Try it

```sh
scripts/demo_up.sh
scripts/stage_queries.sh
```
