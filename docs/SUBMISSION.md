# Submission text for tokensand.com/cyberhack/submit

## Project name

Hive

## Tagline

Competitive intelligence on security companies from a swarm of open-weight agents, with a monitoring plane that catches the swarm being attacked.

## Project description

Hive's scraper is the attack surface and its monitoring plane is the product. Hive tracks security vendors (CrowdStrike, Palo Alto Networks, SentinelOne, Zscaler and others) on a recurring heartbeat. Any agent that reads the open web takes in untrusted text thousands of times a day. One poisoned vendor blog can tell the reader agent to report that a competitor was breached or lost its FedRAMP authorization, and that lie then ships into a brief someone acts on.

On every heartbeat, readers, classifiers and judges on cheap open-weight AkashML models extract claims from live security feeds, vendor blogs and SEC filings. Every agent call is logged to ClickHouse with its role, model, latency, cost, confidence and injection flags. The monitoring plane watches that stream:

- Pattern detectors and a canary in every prompt flag injected pages.
- A judge on a different model cross-checks each claim against independent sources and catches contradictions like $45M vs $450M.
- Low confidence and disagreement are quarantined or rerouted.
- Sources that inject lose trust.

Only judged claims are tagged approved in Senso. The writer reads nothing else and produces cited competitor profiles and a "what changed since the last heartbeat" digest. The code drops any sentence without a valid citation, and the writer refuses questions the verified KB can't answer.

While building, we found and fixed an SSRF in our own collector, proved with a before/after PoC and regression tests.

## Tools used

- **AkashML:** the whole swarm runs on open-weight models.
  - `meta-llama/Llama-3.3-70B-Instruct` for the reader and classifier: fast (about 0.7s) with clean JSON.
  - `openai/gpt-oss-120b` as judge and reroute target: a stronger, different model family for cross-checking, and correct on our contradiction test.
  - `Qwen/Qwen3.8-27B` as writer: it cites per sentence and refuses when the verified KB has no answer.
- **ClickHouse:** the event store for `agent_runs`, `claims`, `injection_events`, `source_trust` and heartbeats. Views behind the live dashboard and the monitoring plane cover runs per minute by model, the confidence histogram, the quarantine queue, recent injections, misclassification rate by model, cost by model and current source trust.
- **Senso:** the verified knowledge base. Judged claims go into the `shared-context` folder, tagged `status:approved` or `status:draft`, `owner:hive-judge`, `decided:<date>`, `entity:` and `claim_type:`. The writer grounds only on approved `/org/search/context` passages, with a citation on every line.
- **Semgrep Guardian:** scanned every edit as a Claude Code hook. Our manual review on top of it found an SSRF (CWE-918) in the RSS collector, where untrusted feed links were fetched with redirects and no host check. We fixed it with per-hop IP validation, a body-size cap and an XXE guard, and verified the fix with a before/after PoC and regression tests (`docs/SEMGREP.md`).
- **Claude Code:** built in one day by four parallel Claude Code sessions, each owning one directory (swarm and orchestrator, ClickHouse and dashboard, collectors, Senso and writer and docs), coordinating through shared Pydantic contracts and cross-session messages.

## What the demo video shows

- The tracked competitor set and the dashboard idle after the last heartbeat.
- A heartbeat triggered live: the timeline fills with agent runs by model and role, and real security news about CrowdStrike, Palo Alto Networks and others flows into the verified-claims feed.
- The catch: a planted Nullgrid Security blog post hides instructions to report that Quillon Shield was breached and lost FedRAMP. The detector and canary trip, the claims are quarantined, the source's trust drops to zero, and the fake breach never reaches a brief.
- The contradiction: a news site says Quillon Shield raised $45M while the press release and 8-K say $450M. The judge quarantines the wrong number.
- A competitor profile and the heartbeat digest generated from Senso's approved claims, with every line cited.
- The trap question: the writer refuses to answer what the verified KB doesn't contain.
- Cost by model: the whole heartbeat ran on open-weight models for about a cent. A live ClickHouse query shows misclassification rate by model.
- The SSRF finding in our own collector, with the PoC before and after the fix.

## Team

- Team: Derek Peng
- Contact: derekyp9@gmail.com
