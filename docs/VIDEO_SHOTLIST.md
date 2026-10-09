# Hive demo video shotlist (2:45)

Follows the 9 beats in [DEMO_SCRIPT.md](DEMO_SCRIPT.md), trimmed from 3:00 to 2:45. Each spoken line is under 15 words; the longer narration in DEMO_SCRIPT.md is for live Q&A.

Setup: run `scripts/demo_terminal.sh` first. It checks the stack, opens the browser tabs and prints the checklist. Record at 1280x800.

| # | Time | Secs | Screen | Command or view | What the viewer sees | Spoken line |
|---|---|---|---|---|---|---|
| 1 | 0:00-0:15 | 15 | Editor, then browser | `config/competitors.yaml` (scroll the `live:` tier), then the dashboard tab `http://localhost:8080/` | Ten real vendors with tickers and segments. Then the idle dashboard with "Heartbeat history (last 20)" showing the previous run | "Hive tracks our competitors across the open web, using a swarm of cheap agents." |
| 2 | 0:15-0:30 | 15 | Terminal | `.venv/bin/python -m hive.heartbeat --once --brief` | Collector lines scroll: 14 fixtures, 14 live feeds (The Hacker News, Unit 42, CrowdStrike blog...), 9 EDGAR filers, about 100 docs | "One heartbeat: live security news, vendor blogs and SEC filings, about a hundred documents." |
| 3 | 0:30-0:45 | 15 | Browser, dashboard | "Swarm timeline", "Runs per minute by model", then "Verified claims feed" | Timeline bars climb by status; the claims feed fills with real CrowdStrike, Palo Alto Networks and Zscaler items | "Every agent call lands in ClickHouse. Claims need a second model and source." |
| 4a | 0:45-0:57 | 12 | Browser, new tab | `fixtures/nullgrid_blog_update.html` (opened by the setup script) | A normal-looking Nullgrid Security threat research post. Nothing suspicious is visible | "This vendor blog looks like ordinary threat research." |
| 4b | 0:57-1:05 | 8 | Browser | Cmd+Option+U (view source), then Cmd+F `Ignore all previous` | The HTML comment and the white-on-white div telling AI readers Quillon Shield was breached and lost FedRAMP | "Hidden inside: instructions telling our AI to invent a competitor breach." |
| 4c | 1:05-1:15 | 10 | Browser, dashboard | "Injection events", then "Source trust" | Heuristic and canary events on `nullgrid_blog`; its trust at or near 0 | "We caught it, quarantined the claims, and zeroed that source's trust." |
| 5 | 1:15-1:35 | 20 | Browser, dashboard | "Quarantine queue", the Quillon Shield funding row | The $45M claim marked judge DISAGREE, against $450M from the press release and 8-K | "A news site says forty-five million. The filing says four fifty. Quarantined." |
| 6 | 1:35-2:00 | 25 | Terminal | `.venv/bin/python -m hive.writer.ci profile "Quillon Shield"`, then `.venv/bin/python -m hive.writer.ci digest --since "$(date -u -v-1H +%Y-%m-%dT%H:%M)"` | A profile with Positioning, Recent moves, Risks and People, every line cited `[n]`, and no breach under Risks. Then the digest grouped by claim type | "Profiles come only from approved claims in Senso. Every sentence cites a source." |
| 7 | 2:00-2:12 | 12 | Terminal | `.venv/bin/python -m hive.writer.brief "CrowdStrike" "What is CrowdStrike's internal sales quota for next quarter?"` | `_No verified claims in the knowledge base answer this question._` | "Ask about something unverified, and it refuses instead of guessing." |
| 8 | 2:12-2:30 | 18 | Terminal, then dashboard | `scripts/stage_queries.sh --pause` (misclassification by model, then cost by model); or the dashboard panels "Misclassification by model" and "Cost by model" | Judge disagree rate per model, then total heartbeat cost of about a cent | "All open-weight models on AkashML. The whole heartbeat cost about a cent." |
| 9 | 2:30-2:45 | 15 | Image viewer | `docs/semgrep/ssrf_poc.png` | The SSRF proof of concept leaking a localhost secret before the fix, then blocked after it | "We found an SSRF in our own collector, fixed it, and added regression tests." |

**Total: 165 s (2:45).**

## Recording notes

- **Beat 2:** if the heartbeat takes longer than 15 s, record it in full and jump-cut to the final summary line. For a faster run, use `--kinds fixture,rss --limit 40`, but then beat 6 has fewer EDGAR-backed claims.
- **Beat 4a:** the blog page is local. The setup script can serve `fixtures/` on `http://localhost:8081/`, so the address bar shows `localhost:8081/nullgrid_blog_update.html` rather than a long `file://` path. Zoom the browser to 110% so the article fills the frame.
- **Beat 4b:** view source is the clearest reveal. Selecting all text doesn't work, because the hidden div is 1px and unreadable even when highlighted.
- **Beats 4c and 5:** the dashboard polls ClickHouse. Wait for the panels to refresh after beat 2 before cutting to them.
- Terminal: 18 pt font, a short prompt (`export PS1='hive $ '`), and `clear` before each command.
- All fixture vendors (Nullgrid Security, Quillon Shield, Veyrn Defense, Kestrel Identity, Cindral Cloud Security) are fictional. Don't name a real company in the injection or contradiction beats.
