# Submission text for tokensand.com/cyberhack/submit

## Project name

Hive

## Tagline

A swarm of open-weight agents that scrapes the open web for competitive intelligence, and a monitoring plane that catches the swarm being attacked.

## Project description

Hive's scraper is the attack surface and its monitoring plane is the product. Any agent that reads the open web takes in untrusted text thousands of times a day. One poisoned page can tell the reader agent to report a fake funding round or mark a competitor's trial as failed, and that lie then ships into a brief someone acts on.

Hive runs a swarm of scouts, readers, classifiers and judges on cheap open-weight AkashML models to extract claims about biotech companies from RSS, SEC EDGAR and company pages. Every agent call is logged to ClickHouse with its role, model, latency, cost, confidence and injection flags. The monitoring plane watches that stream:

- Heuristic detectors and a canary in every prompt flag injected pages.
- A judge on a different model cross-checks each claim against independent sources.
- Low confidence and disagreement are quarantined or rerouted to a stronger model.
- Sources that inject lose trust.

Only judged claims reach Senso. The writer agent reads nothing else, every sentence of a brief cites a verified passage, and the code drops any sentence without a valid citation. The writer refuses questions the verified KB can't answer.

While building, we found and fixed an SSRF in our own collector: a malicious feed item could make Hive fetch localhost services into the pipeline. The before and after are proved with a PoC and regression tests.

## Tools used

- **AkashML:** the whole swarm runs on open-weight models.
  - `meta-llama/Llama-3.3-70B-Instruct` for the reader and classifier: fast (about 0.7s) with clean JSON.
  - `openai/gpt-oss-120b` as judge and reroute target: a stronger, different model family for cross-checking, and correct on our contradiction test.
  - `Qwen/Qwen3.8-27B` as writer: it cites per sentence and refuses when the verified KB has no answer.
- **ClickHouse:** the event store for `agent_runs`, `claims`, `injection_events` and `source_trust`. Views behind the live dashboard and the monitoring plane cover runs per minute by model, the confidence histogram, the quarantine queue, recent injections, misclassification rate by model, cost by model and current source trust.
- **Senso:** the verified knowledge base. Judged claims are ingested through `/org/kb/raw`, and the writer grounds only on `/org/search/context` passages, with a citation on every sentence.
- **Semgrep Guardian:** scanned every edit as a Claude Code hook. Our manual review on top of it found an SSRF (CWE-918) in the RSS collector, where untrusted feed links were fetched with redirects and no host check. We fixed it with per-hop IP validation, a body-size cap and an XXE guard, and verified the fix with a before/after PoC and regression tests (`docs/SEMGREP.md`).
- **Claude Code:** built in one day by four parallel Claude Code sessions, each owning one directory (swarm and orchestrator, ClickHouse and dashboard, collectors, Senso and writer and docs), coordinating through shared Pydantic contracts and cross-session messages.

## What the demo video shows

- The swarm kicks off on biotech targets, and agent runs climb live in ClickHouse by model and role, with latency and cost per call.
- A clean claim goes from press release to reader to classifier to judge, confirmed against a second source and written to Senso.
- The catch: a fixture page with a hidden instruction to fake a trial failure and a funding figure. The detector and canary trip, the judge disagrees, the claim is quarantined, the injection event appears and the source's trust drops.
- The low-confidence queue routes uncertain claims to a stronger model instead of into a brief.
- The writer generates a brief from Senso's verified claims, with every sentence cited, and refuses a question the KB can't answer.
- A live ClickHouse query on stage shows misclassification rate by model.
- The SSRF finding in our own collector, with the PoC before and after the fix.

## Team

- Team: Derek Peng
- Contact: derekyp9@gmail.com
