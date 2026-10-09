# What Guardian missed, and the rule that would have caught it

Semgrep Guardian scanned every file written during Hive's build and passed all of them. We then found
a server-side request forgery in the collector by hand, confirmed it with a proof of concept, fixed it,
and wrote the Semgrep rule Guardian would have needed. This document is the deliverable for that gap.

## Coverage record

| Scan set | Files | Findings |
| --- | --- | --- |
| Guardian hooks during the build, three sessions | 54 | 0 |
| Guardian re-scan of the original vulnerable collector (`docs/semgrep/vuln_rss.py`) | 1 | 0 |
| Guardian re-scan of every source file in the first commit (`934696c`) | 48 | 0 |

The re-scans were run through the Guardian hook binary with its full session lifecycle
(SessionStart, PreToolUse, PostToolUse, Stop) against the tokens-hackathon deployment. Guardian's
closing line for the first-commit scan: `48 scans this session across 48 files, 0 findings`.

## The finding Guardian missed

**CWE-918 SSRF through RSS article links.** `hive/collectors/rss.py` as first written fetched every
`<link>` from a parsed feed with an httpx client created with `follow_redirects=True`, with no scheme
or host check and no size cap. A feed is attacker-controlled input. One item can point the collector at
`http://localhost:8123/?query=...` (the event store), `http://169.254.169.254/` (cloud credentials), or
any private address. The response body becomes a `RawDocument`, goes to the reader agent, gets logged,
and can surface in a brief: an exfiltration path from internal services into the product's output.

Proof of concept: `docs/semgrep/ssrf_poc.py` starts a localhost-only server that returns
`db_password=hunter2` and a feed whose single item links to it. The original code fetched it and the
secret landed in a document record. The fixed code made zero requests to it. Evidence:
`docs/semgrep/ssrf_poc.png`, `docs/semgrep/ssrf_poc.txt`.

## Why Guardian did not see it

The bug is a taint flow, not a pattern. The dangerous call is an ordinary `client.get(url)`. What makes
it dangerous is where `url` came from: a feed entry, three statements and one comprehension earlier.
Detecting it needs a taint rule with feed entries as the source, HTTP client calls as the sink, and a
propagator through the list comprehension. Guardian's hosted rule set has SSRF rules for web framework
request parameters as sources, not for parsed feed content.

## The rule

`docs/semgrep/rules/hive-feed-ssrf.yml` contains two rules.

**`hive-untrusted-feed-link-ssrf`** (taint mode, ERROR). Sources: `feedparser.parse(...).entries`,
`$ENTRY.get("link")`, `$ENTRY.link`, `$ENTRY["link"]`. Propagator: list comprehensions, so a URL
collected into a list stays tainted. Sinks: `$CLIENT.get/post/request`, `httpx.get`, `requests.get`,
focused on the URL argument. Sanitizers: `validate_url(...)` and `safe_get(...)`, the functions the
fix introduced, so the fixed collector is clean and the original is flagged.

**`hive-httpx-follow-redirects-unvalidated`** (WARNING). Flags an httpx client constructed with
`follow_redirects=True`, because every redirect hop is a new destination that a host check on the
first URL does not cover. The fix follows redirects manually and re-validates each hop.

Run it:

```
uv tool run semgrep --config docs/semgrep/rules/hive-feed-ssrf.yml docs/semgrep/vuln_rss.py hive/collectors/
```

Expected: findings on `docs/semgrep/vuln_rss.py` (the original), none on `hive/collectors/rss.py` or
`hive/collectors/page.py` (the fix). The result of that run is recorded below.

## Rule validation

| Rule | Location | Severity |
| --- | --- | --- |
| `hive-httpx-follow-redirects-unvalidated` | `docs/semgrep/vuln_rss.py:19` | WARNING |
| `hive-httpx-follow-redirects-unvalidated` | `docs/semgrep/vuln_rss_inline.py:8` | WARNING |
| `hive-untrusted-feed-link-ssrf` | `docs/semgrep/vuln_rss_inline.py:14` | ERROR |

Run on 2026-10-09 with Semgrep OSS via `uv tool run semgrep` against the original collector, an inlined
variant of it, and the three fixed collectors: 3 findings, 0 errors. The fixed
collectors are clean.

**Limitation, stated plainly.** Semgrep OSS taint tracking is intraprocedural. The original
`vuln_rss.py` passes the feed link into a helper, `_fetch_article(client, url)`, so the taint rule
cannot follow it across the call and reports only the `follow_redirects=True` warning there. On
`vuln_rss_inline.py`, the same bug with the fetch inlined, the taint rule fires as an ERROR. Catching
the helper-function form needs interprocedural taint (Semgrep Pro), or a second rule that treats
"tainted feed link passed to any function alongside an HTTP client" as a sink, which we judged too
noisy for the fixed code that also routes links through a helper. Guardian saw neither form.

## The fix, for reference

`hive/collectors/_common.py`: `validate_url` allows only http and https, rejects credentials in the
URL, resolves the host and rejects private, loopback, link-local, multicast, reserved and non-global
addresses including IPv4-mapped IPv6. `safe_get` follows up to five redirects manually and re-validates
every hop, and caps bodies at 2 MB. `rss.py`, `page.py` and `edgar.py` fetch only through `safe_get`.
Regression tests: `test_rss_does_not_fetch_internal_article_link`,
`test_page_redirect_to_internal_blocked` in `tests/test_collectors.py`.

Remaining risk: DNS rebinding. The address is validated at resolve time, not pinned for the connection.
