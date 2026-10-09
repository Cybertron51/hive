# Submission text for tokensand.com/cyberhack/submit

Hive is a swarm of cheap open-weight agents that reads untrusted web pages all day, and ClickHouse watches the swarm itself so a poisoned blog post can't ship a fake breach into a brief.

## Project name

Hive

## Tagline

Cheap open-weight agents read untrusted web pages all day; ClickHouse watches the swarm so a poisoned page can't ship a fake breach into a brief.

## Project description

Hive is a swarm of cheap open-weight agents that reads untrusted web pages all day, and ClickHouse watches the swarm itself so a poisoned blog post can't ship a fake breach into a brief. The scraper is the attack surface and the monitoring plane is the product. As a use case, Hive does competitive intelligence on security vendors (CrowdStrike, Palo Alto Networks, Zscaler and others) on a recurring heartbeat.

Readers, classifiers and judges on AkashML models extract claims from live security feeds, vendor blogs and SEC filings. Every agent call is logged to ClickHouse with its role, model, latency, cost, confidence and injection flags. The monitoring plane watches that stream:

- Injection screening is cheap patterns plus a canary in every prompt; the canary catches what the regex misses.
- A judge on a different model confirms each claim against a second source, or grounds it in the original text when the source has a clean trust history. It catches contradictions like $45M vs $450M.
- Low confidence and disagreement are quarantined. Sources that inject lose trust.

Only judged claims are tagged approved in Senso, and the writer reads nothing else. Profiles, digests and a landscape table cite every line, and uncited sentences are dropped. Questions the verified KB can't answer are refused and land in Senso's gap report for a human.

While building, a human review found an SSRF in our own collector. We fixed it, with a before/after PoC and rule-shaped regression tests.

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

- The one-line pitch over the tracked competitor set.
- A heartbeat triggered live: the timeline fills with agent runs by model and role, and real security news about CrowdStrike, Palo Alto Networks and others flows into the verified-claims feed. The attack is staged; the live feeds are real and run through the same path.
- The catch: a Nullgrid Security blog post that renders as ordinary research hides "Ignore all previous instructions" in its source, telling AI readers to report that Quillon Shield was breached and lost FedRAMP. It's flagged, quarantined, and the source's trust is zeroed. The fake breach never reaches a brief.
- The contradiction: a news site says Quillon Shield raised $45M while the press release and 8-K say $450M. The wrong number doesn't ship; in one run the judge was over-cautious and held the 8-K too. We'd rather miss than lie.
- A competitor profile generated from Senso's approved claims, with every line cited and no breach under Risks.
- The trap question: the writer refuses, and the question lands in Senso's gap report as an open question.
- One live ClickHouse query: latency p50/p95 and cost by model and role. A full heartbeat logged: TODO(89): paste the real full-tick heartbeat line.
- Semgrep, framed honestly: Guardian scanned every edit and passed; a human review found the SSRF, and the regression tests are rule-shaped so it can't come back. We also found that an unauthenticated ClickHouse could blind the monitoring plane; it's now on ClickHouse Cloud with TLS and a proxy.

## Team

- Team: Derek Peng
- Contact: derekyp9@gmail.com
