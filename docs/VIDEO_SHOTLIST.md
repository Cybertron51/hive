# Hive demo video shotlist (2:40)

Follows the 9 beats and timings in [DEMO_SCRIPT.md](DEMO_SCRIPT.md). Each spoken line is under 15 words; DEMO_SCRIPT.md has the full narration.

Setup: follow "Before recording" in DEMO_SCRIPT.md (stop the background heartbeat, `rm -f data/seen.json`), then run `scripts/demo_terminal.sh`. It checks the stack, opens the browser tabs and prints the checklist. Record at 1280x800.

| # | Time | Secs | Screen | Command or view | What the viewer sees | Spoken line |
|---|---|---|---|---|---|---|
| 1 | 0:00-0:10 | 10 | Editor | `config/competitors.yaml` (scroll the `live:` tier) | Ten real security vendors with tickers and segments | "A swarm of cheap agents reads untrusted pages; ClickHouse watches the swarm." |
| 2 | 0:10-0:25 | 15 | Terminal | `.venv/bin/python -m hive.heartbeat --once --reset-seen --kinds fixture,rss --limit 40` | Collector output: the 14 fixture pages first, then live RSS items, capped at 40 docs (no EDGAR). The tick runs about a minute and keeps going through beat 4 | "A bounded tick for the demo; the full feed set runs on schedule." |
| 3 | 0:25-0:40 | 15 | Browser, dashboard | "Swarm timeline", "Runs per minute by model", then "Verified claims feed" | Timeline bars climb by model and role with latency; the claims feed fills with real CrowdStrike and Palo Alto Networks items | "Every agent call lands in ClickHouse. The attack is staged; the feeds are real." |
| 4a | 0:40-0:48 | 8 | Browser, blog tab | `fixtures/nullgrid_blog_update.html`, rendered | A normal-looking Nullgrid Security threat research post. Nothing suspicious is visible | "This vendor blog reads as ordinary threat research." |
| 4b | 0:48-0:57 | 9 | Browser, view-source tab | `view-source:` of the same page, then Cmd+F `Ignore all previous` | The HTML comment and the white-on-white div telling AI readers Quillon Shield was breached and lost FedRAMP | "Hidden inside: orders for our AI to invent a competitor breach." |
| 4c | 0:57-1:05 | 8 | Browser, dashboard | "Injection events", then "Quarantine queue", then "Source trust" | Events on `nullgrid_blog`, its claims quarantined, its trust at or near 0 | "Flagged, quarantined, source trust zeroed." |
| 5 | 1:05-1:20 | 15 | Browser, dashboard | "Quarantine queue", the Quillon Shield funding rows | The $45M claim quarantined with judge DISAGREE; the 8-K's $450M claim verified | "Forty-five or four-fifty million? The wrong number is quarantined and the 8-K verifies: a secondary article can't outvote a filing." |
| 6 | 1:20-1:45 | 25 | Terminal | `clear`, then `.venv/bin/python -m hive.writer.ci profile "Quillon Shield"` (about 15 s) | A ~29-line profile: Positioning, Recent moves, Risks, People, every line cited `[n]`, and no breach under Risks | "The writer cites only approved claims in Senso. No breach under Risks." |
| 7 | 1:45-2:05 | 20 | Terminal | `.venv/bin/python -m hive.writer.brief "CrowdStrike" "What is CrowdStrike's internal sales quota for next quarter?"`, then `senso gaps list --origin api_unanswered_question --status weak --status open \| head` | `_No verified claims in the knowledge base answer this question._`, then the question listed in Senso's gap report | "Unverified question: it refuses, and Senso logs the gap for a human." |
| 8 | 2:05-2:20 | 15 | Terminal | `scripts/stage_queries.sh --one` | Latency p50/p95 and cost by model and role, the server elapsed ms, and the "N agent runs scanned" line | "[N] agent runs, aggregated live in [elapsed] milliseconds, all on open-weight models." |
| 9 | 2:20-2:40 | 20 | Image viewer | `docs/semgrep/ssrf_poc.png` | The SSRF proof of concept leaking a localhost secret before the fix, then blocked after it | "Human review found an SSRF in our collector; fixed, with regression tests." |

**Total: 160 s (2:40).**

## Recording notes

- **Beat 2:** the bounded tick takes about a minute; start talking as soon as you press Enter and cut to the dashboard while it runs. Don't run a full tick on stage: 102 docs take 10+ minutes with the grounding judge. `collect_all` always returns the 14 fixture pages first, so the injection page and the Quillon contradiction are always inside `--limit 40`.
- **Beat 4a:** the blog page is local. `scripts/demo_terminal.sh --serve-fixtures` serves `fixtures/` on `http://localhost:8081/`, so the address bar shows `localhost:8081/nullgrid_blog_update.html` rather than a long `file://` path. Zoom the browser to 110% so the article fills the frame.
- **Beat 4b:** view source is the clearest reveal. Selecting all text doesn't work, because the hidden div is 1px and unreadable even when highlighted.
- **Beats 4c and 5:** the dashboard polls ClickHouse. Wait for the panels to refresh after the tick before cutting to them.
- **Beat 5:** after the judge fix, the final eval ruled the true 8-K $450M claim correct in 3 of 3 runs. Don't use the old "over-cautious" line.
- **Beat 8:** read N and the elapsed time off the screen; they change every run.
- Terminal: 18 pt font, a short prompt (`export PS1='hive $ '`), and `clear` before each command. The beat 6 profile only fits on a cleared screen.
- All fixture vendors (Nullgrid Security, Quillon Shield, Veyrn Defense, Kestrel Identity, Cindral Cloud Security) are fictional. Don't name a real company in the injection or contradiction beats.
