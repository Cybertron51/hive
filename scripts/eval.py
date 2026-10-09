#!/usr/bin/env python3
"""Measure Hive's extraction, classification, injection detection and judging.

  .venv/bin/python scripts/eval.py --dry-run               # FakeLLM, free; writes docs/eval/dry_run.json + docs/eval/EVAL_dry_run.md
  .venv/bin/python scripts/eval.py --live [--repeat 3]     # real models over fixtures; writes docs/eval/latest.json + docs/EVAL.md
  .venv/bin/python scripts/eval.py --sources [--live]      # live feeds: injection events by source (heuristic; --live adds the canary)

Never writes to ClickHouse or Senso (telemetry=False, ingest=False). A --live run exits 1 if a planted claim
or a claim from an injected doc reaches VERIFIED.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hive.collectors import collect_all, load_sources  # noqa: E402
from hive.config import settings  # noqa: E402
from hive.eval import report, score  # noqa: E402
from hive.swarm.injection import detect  # noqa: E402
from hive.swarm.orchestrator import run_swarm  # noqa: E402

OUT_DIR = ROOT / "docs" / "eval"
EVAL_MD = ROOT / "docs" / "EVAL.md"
SOURCES = ROOT / "config" / "sources.yaml"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _archive(data: dict, mode: str) -> None:
    stamp = data["generated_at"].replace(":", "").replace("-", "")
    _write_json(OUT_DIR / "runs" / f"{stamp}_{mode}.json", data)


def _require_live() -> None:
    if not settings.akashml_api_key:
        sys.exit("--live needs AKASHML_API_KEY in .env (use --dry-run for a free structural check)")


async def eval_fixtures(mode: str, repeat: int, concurrency: int) -> dict:
    gt = score.load_ground_truth()
    docs = await collect_all(SOURCES, kinds={"fixture"})
    url_to_file = {s["url"]: Path(s["path"]).name for s in load_sources(SOURCES) if s["kind"] == "fixture"}
    fixture_of = {d.doc_id: url_to_file[d.url] for d in docs if d.url in url_to_file}
    missing = set(gt["docs"]) - set(fixture_of.values())
    if missing:
        print(f"warning: ground truth docs not collected: {sorted(missing)}", file=sys.stderr)

    runs, models = [], set()
    for i in range(repeat):
        t0 = time.perf_counter()
        result = await run_swarm(docs, concurrency=concurrency, telemetry=False, ingest=False)
        wall = time.perf_counter() - t0
        models |= {r.model for r in result.runs}
        scored = score.score_fixtures(docs, fixture_of, result, gt, wall)
        runs.append(scored)
        h = scored["headline"]
        print(f"run {i + 1}/{repeat}: recall {h['extraction_recall']}, precision {h['extraction_precision']}, "
              f"injection TPR {h['injection_tpr']} FPR {h['injection_fpr']}, planted leaks {h['planted_leaks']}, "
              f"judge {h['judge_contradiction_accuracy']}, ${h['cost_usd_total']:.4f}, {wall:.1f}s")
    return {"mode": mode, "generated_at": _now(), "models": sorted(models), "docs": len(docs), "runs": runs}


async def eval_sources(live: bool, concurrency: int) -> dict:
    docs = await collect_all(SOURCES, kinds={"rss", "edgar"})
    if live:
        result = await run_swarm(docs, concurrency=concurrency, telemetry=False, ingest=False)
        events = result.injection_events
        cost = round(sum(r.cost_usd for r in result.runs), 6)
    else:
        events = [e for d in docs for e in detect(d)]
        cost = 0.0
    data = score.score_sources(docs, events, swarm_ran=live)
    data["headline"]["cost_usd"] = cost
    return {"mode": "sources-live" if live else "sources-heuristic", "generated_at": _now(), "result": data}


def _print_fixture_summary(fx: dict) -> None:
    first = fx["runs"][0]
    print()
    for key, label, fmt, _ in report.HEADLINE:
        print(f"  {label:<55} {fmt(first['headline'][key]) if first['headline'][key] is not None else 'n/a'}")
    print(f"\n  failures ({len(first['failures'])}):")
    for f in first["failures"]:
        print(f"   - {f}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="use the deterministic FakeLLM (free)")
    mode.add_argument("--live", action="store_true", help="use the real AkashML models")
    ap.add_argument("--sources", action="store_true", help="scan live feeds for injection false positives instead of the fixtures")
    ap.add_argument("--repeat", type=int, default=1, help="fixture runs to average (live models vary run to run)")
    ap.add_argument("--concurrency", type=int, default=8)
    args = ap.parse_args(argv)

    if args.sources:
        if args.dry_run:
            ap.error("--sources takes --live or nothing (heuristic only); --dry-run has no meaning there")
        if args.live:
            _require_live()
        src = asyncio.run(eval_sources(args.live, args.concurrency))
        _write_json(OUT_DIR / "sources_latest.json", src)
        _archive(src, src["mode"])
        EVAL_MD.write_text(report.render(_read_json(OUT_DIR / "latest.json"), src), encoding="utf-8")
        h = src["result"]["headline"]
        print(f"{h['flagged_docs']}/{h['docs']} live docs flagged ({h['detectors']}), {h['events']} events, ${h['cost_usd']:.4f}")
        for r in src["result"]["by_source"]:
            if r["flagged"]:
                print(f"  {r['source_id']:<26} {r['flagged']}/{r['docs']} flagged  {r['patterns']}")
        print(f"wrote {EVAL_MD.relative_to(ROOT)} and docs/eval/sources_latest.json")
        return 0

    if not (args.dry_run or args.live):
        ap.error("choose --dry-run or --live (or --sources)")
    if args.dry_run:
        from hive.swarm import fake

        fake.install()
        fx = asyncio.run(eval_fixtures("dry-run", args.repeat, args.concurrency))
        _write_json(OUT_DIR / "dry_run.json", fx)
        (OUT_DIR / "EVAL_dry_run.md").write_text(report.render(fx, None), encoding="utf-8")
        written = "docs/eval/dry_run.json and docs/eval/EVAL_dry_run.md"
    else:
        _require_live()
        fx = asyncio.run(eval_fixtures("live", args.repeat, args.concurrency))
        _write_json(OUT_DIR / "latest.json", fx)
        _archive(fx, "live")
        EVAL_MD.write_text(report.render(fx, _read_json(OUT_DIR / "sources_latest.json")), encoding="utf-8")
        written = "docs/EVAL.md and docs/eval/latest.json"

    _print_fixture_summary(fx)
    print(f"\nwrote {written}")
    leaked = args.live and any(r["headline"]["planted_leaks"] or r["headline"]["verified_from_injected_docs"] for r in fx["runs"])
    if leaked:
        print("FAIL: a planted claim or a claim from an injected doc reached VERIFIED", file=sys.stderr)
    return 1 if leaked else 0


if __name__ == "__main__":
    raise SystemExit(main())
