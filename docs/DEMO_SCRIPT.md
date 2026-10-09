# Hive demo script (target 2:40)

Hive is a swarm of cheap open-weight agents that reads untrusted web pages all day, and ClickHouse watches the swarm itself so a poisoned blog post can't ship a fake breach into a brief.

## Before recording

```sh
scripts/ch_up.sh
scripts/demo_up.sh --reset       # dashboard on :8080, preflight, heartbeat --interval 90 --brief in the background
rm -f data/seen.json             # so the live beat collects documents instead of showing new=0
```

- Let one background heartbeat finish so the dashboard isn't empty.
- Open http://localhost:8080/ in a browser.
- In a second tab, open `fixtures/nullgrid_blog_update.html` rendered normally, and in a third, `view-source:` of the same file.
- Keep one terminal at the repo root and have `config/competitors.yaml` open in an editor.
- Terminal at 1280x800, 18pt. Run `clear` before each command: the beat 6 profile is about 29 lines and only fits on a cleared screen.
- The beat 6 profile takes about 15s and the trap question about 3s. Start talking while they run.

## 0:00 to 0:10 Pitch (beat 1)

Show `config/competitors.yaml`.

> "Hive is a swarm of cheap open-weight agents that reads untrusted web pages all day, and ClickHouse watches the swarm itself so a poisoned blog post can't ship a fake breach into a brief. Here it's doing competitive intelligence on these security vendors."

## 0:10 to 0:40 A live heartbeat (beats 2 and 3)

```sh
.venv/bin/python -m hive.heartbeat --once --brief --reset-seen
```

On the dashboard, the timeline fills with runs per model and role and their latency, and the verified-claims feed updates with real items about CrowdStrike, Palo Alto Networks and others.

> "Every reader, classifier and judge call lands in ClickHouse within a second. The attack is staged; the live feeds are real and run through the same path."

## 0:40 to 1:05 The catch (beat 4)

1. Show the Nullgrid Security blog post rendered normally. It reads as ordinary threat research.
2. Switch to view-source and press Cmd+F for `Ignore all previous`. The hidden instruction tells AI readers to report that Quillon Shield was breached and lost FedRAMP.
3. Point at three dashboard panels in turn: injection events, quarantine queue, source trust.

> "Flagged, quarantined, source trust zeroed."

## 1:05 to 1:20 The contradiction (beat 5)

Dashboard: quarantine queue, the Quillon Shield funding row.

> "A news site says Quillon Shield raised $45 million; the press release and the 8-K say $450 million. The wrong number doesn't ship; in one run the judge was over-cautious and held the 8-K too. We'd rather miss than lie."

## 1:20 to 1:45 Profile from Senso (beat 6)

```sh
.venv/bin/python -m hive.writer.ci profile "Quillon Shield"
```

> "The writer reads only claims the judge tagged approved in Senso. Every line cites its passage, and any sentence without a valid citation is dropped. Under Risks there's no breach: the only breach claim came from the poisoned page."

## 1:45 to 2:05 The trap question (beat 7)

```sh
.venv/bin/python -m hive.writer.brief "CrowdStrike" "What is CrowdStrike's internal sales quota for next quarter?"
senso gaps list --origin api_unanswered_question --status weak --status open | head
```

Expected output: `_No verified claims in the knowledge base answer this question._`, then the question listed in Senso's gap report.

> "Ask about something that isn't verified and the writer refuses instead of guessing. The question lands in Senso's gap report as an open question for a human, along with the standing analyst questions no verified claim answers yet."

## 2:05 to 2:20 What it costs (beat 8)

```sh
scripts/stage_queries.sh --one
```

> "That's [N, from the 'agent runs scanned' line] agent runs, aggregated live in [server elapsed] milliseconds. A full heartbeat logged: `TODO(89): paste the real full-tick heartbeat line`. All on open-weight models on AkashML."

## 2:20 to 2:40 Semgrep and hardening (beat 9)

Show `docs/semgrep/ssrf_poc.png`.

> "Guardian scanned every edit and passed; a human review found the SSRF: one malicious feed item could make Hive read localhost services into the pipeline. Here it is before and after, and the regression tests are rule-shaped so it can't come back. We also found that an unauthenticated ClickHouse could blind the monitoring plane; it's now on ClickHouse Cloud with TLS and a proxy."

## After recording

```sh
scripts/demo_down.sh
```
