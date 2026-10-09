# Cloud agent tasks

Paste one of these into a Claude Code on the web session (https://claude.ai/code) opened on
https://github.com/Cybertron51/hive. None of them need API keys. Every task opens a pull request
and never pushes to main: the demo runs from main until 4:30 PM PT on 2026-10-09.

## Task 1: CI workflow and badge

Add `.github/workflows/ci.yml` that runs on push and pull_request: Python 3.12, `pip install uv`,
`uv venv && uv pip install -e ".[dev]"`, then `.venv/bin/python -m pytest tests/ -q`. The tests
use a fake LLM and need no secrets; one network test is skipped unless HIVE_NETWORK_TESTS=1, leave
it skipped. Add a second job that runs `.venv/bin/python scripts/eval.py --dry-run` and uploads
`docs/EVAL.md` and `docs/eval/latest.json` as a workflow artifact named `eval-dry-run`. Add the CI
status badge to the top of README.md under the first paragraph. Open a PR titled
"ci: test suite and dry-run eval on every push". Do not change any file under hive/.

## Task 2: Lint and type check, report only

Run `uvx ruff check hive/ tests/ scripts/` and `uvx mypy hive/ --ignore-missing-imports` and fix
only mechanical issues (unused imports, obvious type annotations). No behaviour changes, no
reformatting of files you did not otherwise touch. Keep every test passing. Open a PR titled
"chore: ruff and mypy cleanups" with the before and after counts in the description.

## Task 3: Architecture diagram as SVG

Read docs/ARCHITECTURE.md and README.md. Produce docs/architecture.svg, a clean left-to-right
diagram: Collectors (RSS, EDGAR, fixtures) -> Swarm on AkashML (reader, classifier, judge,
injection agent) -> Policy (quarantine, reroute, verify) -> ClickHouse Cloud (agent_runs, claims,
injection_events, source_trust, heartbeats) -> Dashboard, with Senso (approved claims only) feeding
the Writer (profiles, digest, landscape, standing questions). Embed it in README.md under
"Architecture". Open a PR titled "docs: architecture diagram".
