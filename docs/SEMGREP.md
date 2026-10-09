# Semgrep Guardian findings

Semgrep Guardian ran as a Claude Code hook in every build session, scanning each file as it was written. This log records every finding, with what it was and how we fixed it. Each session appends its own entries.

| Session | Rule ID | File:line | Finding | Fix |
|---|---|---|---|---|
| D (senso, writer, docs) | none | `hive/senso/client.py`, `hive/writer/brief.py` | Guardian scanned both files on write and reported no findings | n/a |

## Hardening applied in session D without a finding

- The Senso API key goes only in the `X-API-Key` header. It never appears in a URL, a log line or an exception message.
- A `402` from Senso raises `SensoCreditsExhausted`, so callers stop instead of retrying in a loop. A `401` raises an explicit auth error.
- Error messages include at most 300 characters of the response body.
- The writer wraps passages in delimiters and tells the model to treat them as data. It also checks every citation the model returns and drops any sentence that has no valid `[n]`, so an uncited claim cannot reach a brief even if the model ignores its prompt.
- `LocalKB` writes `data/kb.json` atomically through a temp file and `os.replace`.

## Screenshot

TODO: add `docs/semgrep-finding.png` showing the rule ID for the submission.
