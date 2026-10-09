# Hive

Hive is a swarm of cheap open-weight agents that reads untrusted web pages all day, and ClickHouse watches the swarm itself so a poisoned blog post can't ship a fake breach into a brief.

Here the swarm does competitive intelligence on security companies. On every heartbeat it collects press releases, vendor blogs, security news and SEC filings about a tracked competitor set (CrowdStrike, Palo Alto Networks, SentinelOne, Zscaler and others). Readers and classifiers extract claims. A claim is verified only when a judge on a different model confirms it against a second source, or grounds it in the original text when the source has a clean trust history. Every agent call is logged to ClickHouse. Injection screening is cheap patterns plus a canary, and the canary catches what the regex misses. Low confidence and agent disagreement show up in real time and are quarantined before they reach a brief. Judged claims go into Senso, and the writer reads only claims tagged approved there. It produces cited competitor profiles, a "what changed since the last heartbeat" digest and a landscape table.

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full data flow and policy thresholds.

```
heartbeat ─> collectors (RSS, EDGAR, pages, fixtures) ─> raw documents
                │  safe_get: public IPs only, per-hop redirect checks, size cap
                ▼
swarm on AkashML: reader → classifier → judge        every call ──> ClickHouse
                │          injection screen: patterns + canary          │
                ▼                                                       ▼
judged claims ─> Senso shared-context (status:approved | draft)   dashboard + monitoring plane:
                ▼                                                 quarantine, reroute, source trust
writer ─> competitor profiles + heartbeat digest (every line cited)
```

- **Collectors** (`hive/collectors`) pull live security feeds, SEC EDGAR and a fictional fixture set. The fixtures stage a prompt-injected vendor blog and a $45M vs $450M funding contradiction.
- **Swarm** (`hive/swarm`) runs role-typed agents concurrently. Each returns structured JSON with a confidence field.
- **Heartbeat** (`hive/heartbeat.py`) re-runs the pipeline on a timer and skips documents it has already seen.
- **Verified KB** (`hive/senso`) writes claims into Senso's `shared-context` folder, tagged `status:approved` or `status:draft`, `owner:hive-judge`, `decided:<date>`, `entity:<name>` and `claim_type:<type>`. Retrieval keeps only approved passages.
- **Writer** (`hive/writer`) builds competitor profiles (Positioning, Recent moves, Risks, People) and a heartbeat digest grouped by claim type, using only Senso passages. Any sentence without a valid citation is dropped.
- **Dashboard** (`dashboard/`) is a static page that polls ClickHouse as a read-only user.

## Senso integration

Senso is where Hive's verified context lives and where its unanswered questions go.

- **Verified context.** Judged claims are written into the `shared-context` folder and tagged `status:approved` or `status:draft`, plus `owner:hive-judge`, `decided:<date>`, `entity:<name>` and `claim_type:<type>`. Senso search has no tag or folder filter, so each claim's text also ends with metadata lines. Retrieval keeps only passages whose own `Status:` line says approved. Untrusted fields are flattened to one line before ingest, so a scraped page can't forge that line.
- **Writer outputs.** Competitor profiles, the heartbeat digest and `docs/briefs/landscape.md` are built only from approved passages. The landscape table is copied cell by cell from claims, with no model writing it.
- **Open questions.** Every heartbeat asks five standing analyst questions per competitor: pricing, breaches, FedRAMP and certification, funding and financials, and key hires. The writer also asks any question it's given. Answered questions become cited digest lines. Unanswered ones go to Senso's gap report, filed as weak on the first sighting and open on the second, for a human to answer.
- **Caveat.** Senso files a gap only when its own retrieval returns nothing, and its API has no direct create-gap call. Its hybrid search sometimes matches another company's passages, for example Quillon Shield's FedRAMP claim for "What is Okta's FedRAMP status?". Senso then treats the question as answered even though Hive has no approved answer for that company. On our first run, 45 of 71 open questions reached the gap report. Hive's own ledger (`data/open_questions.json`, shown by `python -m hive.writer.questions`) is the complete list.

## Sponsor tools

| Tool | What it does in Hive |
|---|---|
| AkashML | Runs every agent on open-weight models: Llama 3.3 70B as reader and classifier, gpt-oss-120b as judge, Qwen3.8-27B as writer |
| ClickHouse | Event store for agent runs, claims, injection events, source trust and heartbeats, plus the views behind the dashboard, monitoring plane and stage queries |
| Senso | Verified knowledge base. Judged claims are tagged by status in `shared-context`, and the writer grounds only on approved `/org/search/context` passages |
| Semgrep Guardian | Scanned every edit across four Claude Code sessions. We also found and fixed an SSRF in our collector; see [docs/SEMGREP.md](docs/SEMGREP.md) |

## Run

```sh
uv venv --python 3.12 && uv pip install -e .
cp .env.example .env            # fill AKASHML_*, SENSO_API_KEY, CLICKHOUSE_PASSWORD
scripts/ch_up.sh                # ClickHouse on 127.0.0.1, schema applied
scripts/demo_up.sh              # dashboard on http://localhost:8080/, preflight, heartbeat every 300s (add --brief for briefs, --interval N to change)
```

One heartbeat in the foreground:

```sh
.venv/bin/python -m hive.heartbeat --once --brief
```

Profile or digest from verified claims:

```sh
.venv/bin/python -m hive.writer.ci profile "CrowdStrike"
.venv/bin/python -m hive.writer.ci digest --since 2026-10-09T18:00
.venv/bin/python -m hive.writer.ci landscape
.venv/bin/python -m hive.writer.questions          # open analyst questions, local ledger and Senso gap report
```

To stop: `scripts/demo_down.sh`. For the 3-minute demo, see [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).
