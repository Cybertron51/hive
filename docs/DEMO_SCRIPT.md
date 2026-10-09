# Hive demo script (target 2:40)

Hive is a swarm of cheap open-weight agents that reads untrusted web pages all day, and ClickHouse watches the swarm itself so a poisoned blog post can't ship a fake breach into a brief.

## Before recording

```sh
scripts/ch_up.sh                      # only for the local fallback; skip when .env points at ClickHouse Cloud
scripts/demo_up.sh                    # dashboard on :8080 + preflight. No --reset: it would truncate the full-tick history
kill "$(cat logs/heartbeat.pid)"      # stop the background heartbeat so it can't collide with the live tick
rm -f data/seen.json                  # so the live beat collects documents instead of showing new=0
```

- The dashboard history comes from full ticks run earlier (a full tick of 96 docs took 582s with the grounding judge). Don't run a full tick on stage.
- Rehearse the bounded tick once: it takes about a minute. It runs without `--brief` to save Senso credits; beat 6 runs the profile itself. Start the beat 2 narration as soon as you press Enter.
- Open http://localhost:8080/ in a browser.
- In a second tab, open `fixtures/nullgrid_blog_update.html` rendered normally, and in a third, `view-source:` of the same file.
- Keep one terminal at the repo root and have `config/competitors.yaml` open in an editor.
- Terminal at 1280x800, 18pt. Run `clear` before each command: the beat 6 profile is about 29 lines and only fits on a cleared screen.
- The beat 6 profile takes about 15s and the trap question about 3s. Start talking while they run.

## 0:00 to 0:10 Pitch (beat 1)

Show `config/competitors.yaml`.

> "Hive is a swarm of cheap open-weight agents that reads untrusted web pages all day, and ClickHouse watches the swarm itself so a poisoned blog post can't ship a fake breach into a brief. Here it's doing competitive intelligence on these security vendors."

## 0:10 to 0:40 A live heartbeat (beats 2 and 3, the tick keeps running into beat 4)

```sh
.venv/bin/python -m hive.heartbeat --once --reset-seen --kinds fixture,rss --limit 40
```

On the dashboard, the timeline fills with runs per model and role and their latency, and the verified-claims feed updates with real items about CrowdStrike, Palo Alto Networks and others.

> "This is a bounded tick for the demo; the full feed set runs on the schedule. Every reader, classifier and judge call lands in ClickHouse within a second. The attack is staged; the live feeds are real and run through the same path."

## 0:40 to 1:05 The catch (beat 4)

1. Show the Nullgrid Security blog post rendered normally. It reads as ordinary threat research.
2. Switch to view-source and press Cmd+F for `Ignore all previous`. The hidden instruction tells AI readers to report that Quillon Shield was breached and lost FedRAMP.
3. Point at three dashboard panels in turn: injection events, quarantine queue, source trust.

> "Flagged, quarantined, source trust zeroed."

## 1:05 to 1:20 The contradiction (beat 5)

Dashboard: quarantine queue (the $45M row), then the verified-claims feed (the 8-K's $450M).

> "A news site says Quillon Shield raised $45 million; the press release and the 8-K say $450 million. The $45 million claim is quarantined and the 8-K's $450 million verifies: a secondary article can't outvote a filing."

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

> "That's [N, from the 'agent runs scanned' line] agent runs, aggregated live in [server elapsed] milliseconds. And the full feed set: 96 documents, 745 model calls, 13 cents. All on open-weight models on AkashML."

For reference, the log line behind that sentence is `[13:11:55] heartbeat new=96/96 runs=745 verified=285 quarantined=25 injections=10 cost=$0.1328 dur=582.3s status=ok`.

## 2:20 to 2:40 Semgrep and hardening (beat 9)

Show `docs/semgrep/ssrf_poc.png`.

> "Guardian scanned every edit and passed; a human review found the SSRF: one malicious feed item could make Hive read localhost services into the pipeline. Here it is before and after, and the regression tests are rule-shaped so it can't come back. We also found that an unauthenticated ClickHouse could blind the monitoring plane; it's now on ClickHouse Cloud with TLS and a proxy."

## After recording

```sh
scripts/demo_down.sh
```
