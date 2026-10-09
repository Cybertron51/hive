from __future__ import annotations

import argparse
import asyncio
import inspect
import sys
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from hive.models import RawDocument
from hive.swarm.orchestrator import SwarmResult, run_swarm

FIXTURES = Path("fixtures")


class _TextExtractor(HTMLParser):
    _SKIP = {"script", "style", "noscript"}
    _BLOCK = {"p", "div", "li", "br", "h1", "h2", "h3", "h4", "tr", "section", "article"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._stack: list[str] = []

    def handle_starttag(self, tag, attrs):
        self._stack.append(tag)
        if tag in self._BLOCK:
            self.parts.append("\n")
        style = dict(attrs).get("style")
        if style:
            self.parts.append(f" [style={style}] ")

    def handle_endtag(self, tag):
        if tag in self._stack:
            while self._stack and self._stack.pop() != tag:
                pass

    def handle_data(self, data):
        current = self._stack[-1] if self._stack else ""
        if current == "title":
            self.title += data.strip()
        elif current not in self._SKIP:
            self.parts.append(data)

    def handle_comment(self, data):
        self.parts.append(f"<!--{data}-->")


def html_to_text(html: str) -> tuple[str, str]:
    p = _TextExtractor()
    p.feed(html)
    lines = (" ".join(line.split()) for line in "".join(p.parts).splitlines())
    return p.title, "\n".join(line for line in lines if line)


def load_fixtures(limit: int | None) -> list[RawDocument]:
    docs = []
    for path in sorted(FIXTURES.glob("*.html"))[:limit]:
        try:
            title, text = html_to_text(path.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            print(f"skip {path}: {exc}", file=sys.stderr)
            continue
        docs.append(RawDocument(source_id=path.stem.split("_")[0], url=path.resolve().as_uri(), title=title or path.stem, text=text))
    return docs


async def collect(sources: str, limit: int | None, kinds: set[str] | None = None) -> list[RawDocument]:
    try:
        from hive.collectors import collect_all
    except ImportError:
        collect_all = None
    docs: list[RawDocument] = []
    if collect_all is not None:
        try:
            try:
                out = collect_all(sources, kinds=kinds) if kinds else collect_all(sources)
            except TypeError:
                out = collect_all()
            docs = list(await out if inspect.isawaitable(out) else out)
        except Exception as exc:
            print(f"collect_all failed ({type(exc).__name__}: {exc}); falling back to fixtures", file=sys.stderr)
    if not docs:
        docs = load_fixtures(limit)
    return docs[:limit] if limit else docs


def summarize(docs: list[RawDocument], result: SwarmResult) -> str:
    out = [f"swarm {result.swarm_id}", f"docs: {len(docs)}", "", "runs (role/status):"]
    for (role, status), n in sorted(Counter((r.role.value, r.status.value) for r in result.runs).items()):
        out.append(f"  {role:<11} {status:<12} {n}")
    cost = sum(r.cost_usd for r in result.runs)
    out.append(f"  est. cost USD {cost:.6f}")
    out.append("claims (status):")
    for status, n in sorted(Counter(c.status.value for c in result.claims).items()):
        out.append(f"  {status:<12} {n}")
    out.append(f"injection events: {len(result.injection_events)}")
    for e in result.injection_events:
        out.append(f"  {e.detector.value:<9} {e.source_id:<16} {e.pattern:<24} sev={e.severity:.1f}")
    out.append("trust by source:")
    for src, t in sorted(result.trust.items(), key=lambda kv: kv[1]):
        out.append(f"  {src:<16} {t:.2f}")
    if result.sink_errors:
        out.append(f"sink errors: {len(result.sink_errors)} (first: {result.sink_errors[0]})")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hive.swarm")
    ap.add_argument("--sources", default="config/sources.yaml")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--kinds", default="", help="comma-separated collector kinds, e.g. fixture,rss")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true", help="use FakeLLM, sample docs, no Senso ingest")
    ap.add_argument("--log", action="store_true", help="write telemetry even in --dry-run")
    ap.add_argument("--brief", action="store_true", help="write cited competitor profiles and a heartbeat digest to docs/briefs/")
    args = ap.parse_args(argv)

    if args.dry_run:
        from hive.swarm import fake

        fake.install()
        docs = asyncio.run(collect(args.sources, args.limit, {"fixture"})) or fake.SAMPLE_DOCS[: args.limit]
    else:
        docs = asyncio.run(collect(args.sources, args.limit, {k for k in args.kinds.split(",") if k} or None))
    if not docs:
        print("no documents to process", file=sys.stderr)
        return 1
    async def run() -> SwarmResult:
        started = datetime.now(timezone.utc)
        result = await run_swarm(
            docs, concurrency=args.concurrency, telemetry=args.log or not args.dry_run, ingest=not args.dry_run,
        )
        print(summarize(docs, result))
        if args.brief:
            await write_briefs(result, started, log=args.log or not args.dry_run)
        return result

    asyncio.run(run())
    return 0


async def write_briefs(result: SwarmResult, since: datetime | None = None, log: bool = True) -> None:
    from hive.writer.ci import digest, save, write_profiles_for
    from hive.writer.questions import ask_all, digest_lines

    since = since or min((c.created_at for c in result.claims), default=datetime.now(timezone.utc))
    briefs = [(f"profile-{b.entity}", b) for b in await write_profiles_for(result)]
    d = await digest(since, swarm_id=result.swarm_id)
    answers, q_runs = await ask_all(swarm_id=result.swarm_id)
    d.markdown += digest_lines(answers)
    briefs.append((f"digest-{since:%Y%m%dT%H%M}", d))
    for name, b in briefs:
        path = save(b, name)
        print(f"brief {name}: {path} status={b.run.status.value} citations={len(b.citations)} dropped={b.dropped_sentences}")
    print(f"questions: {sum(a.answered for a in answers)} answered, {sum(not a.answered for a in answers)} open (filed to Senso gaps)")
    if log:
        try:
            from hive import telemetry
            for run in [b.run for _, b in briefs] + q_runs:
                telemetry.log_run(run)
            telemetry.flush()
        except Exception as exc:
            print(f"brief telemetry failed: {type(exc).__name__}: {exc}", file=sys.stderr)

if __name__ == "__main__":
    raise SystemExit(main())
