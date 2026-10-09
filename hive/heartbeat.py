from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hive.models import ClaimStatus, RawDocument, new_id
from hive.swarm.__main__ import collect
from hive.swarm.orchestrator import SwarmResult, run_swarm

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
SEEN_PATH = ROOT / "data" / "seen.json"
DEFAULT_SOURCES = "config/sources.yaml"


def url_hash(url: str) -> str:
    fn = _telemetry_fn("url_hash")
    if fn is not None:
        try:
            return str(fn(url))
        except Exception as exc:
            log.warning("telemetry.url_hash failed (%s: %s)", type(exc).__name__, exc)
    return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()


def _telemetry_fn(name: str):
    try:
        from hive import telemetry
    except ImportError:
        return None
    fn = getattr(telemetry, name, None)
    return fn if callable(fn) else None


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


class SeenStore:
    def __init__(self, path: Path = SEEN_PATH, use_telemetry: bool = True) -> None:
        self.path = path
        self.use_telemetry = use_telemetry

    def _load_local(self) -> set[str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return set()
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("seen store unreadable (%s); treating as empty", exc)
            return set()
        return {str(h) for h in data} if isinstance(data, list) else set()

    def _save_local(self, hashes: set[str]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(sorted(hashes)), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:
            log.warning("seen store write failed: %s", exc)

    async def seen(self, hashes: list[str]) -> set[str]:
        fn = _telemetry_fn("seen_urls") if self.use_telemetry else None
        if fn is not None:
            try:
                return set(await _maybe_await(fn(hashes))) | (self._load_local() & set(hashes))
            except Exception as exc:
                log.warning("telemetry.seen_urls failed (%s: %s); using local store", type(exc).__name__, exc)
        return self._load_local() & set(hashes)

    async def mark(self, docs: list[RawDocument]) -> None:
        if not docs:
            return
        fn = _telemetry_fn("mark_seen") if self.use_telemetry else None
        if fn is not None:
            try:
                await _maybe_await(fn(docs))
            except Exception as exc:
                log.warning("telemetry.mark_seen failed (%s: %s)", type(exc).__name__, exc)
        self._save_local(self._load_local() | {url_hash(d.url) for d in docs})

    def reset(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            log.warning("seen store reset failed: %s", exc)


def _dedupe(docs: list[RawDocument]) -> list[RawDocument]:
    out, keys = [], set()
    for d in docs:
        key = url_hash(d.url)
        if key not in keys:
            keys.add(key)
            out.append(d)
    return out


async def _brief(result: SwarmResult, log_telemetry: bool) -> None:
    try:
        from hive.writer.brief import write_briefs_for  # noqa: F401
    except ImportError:
        write_briefs_for = None
    try:
        if write_briefs_for is not None:
            from hive.swarm.__main__ import write_briefs

            await write_briefs(result, log=log_telemetry)
            return
        import hive.writer as writer

        digest = getattr(writer, "digest", None)
        if callable(digest):
            await _maybe_await(digest())
    except ImportError:
        return
    except Exception as exc:
        print(f"brief failed: {type(exc).__name__}: {exc}", file=sys.stderr)


def _log_heartbeat(record: dict) -> None:
    fn = _telemetry_fn("log_heartbeat")
    if fn is None:
        return
    try:
        fn(record)
    except Exception as exc:
        log.warning("telemetry.log_heartbeat failed (%s: %s)", type(exc).__name__, exc)


async def heartbeat_once(
    sources_path: str | Path = DEFAULT_SOURCES,
    kinds: set[str] | None = None,
    limit: int | None = None,
    *,
    interval_s: float = 0,
    reset_seen: bool = False,
    seen: SeenStore | None = None,
    telemetry: bool = True,
    ingest: bool = True,
    brief: bool = False,
    concurrency: int = 16,
) -> dict:
    start = time.monotonic()
    store = seen or SeenStore(use_telemetry=telemetry)
    if reset_seen:
        store.reset()
    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc), "heartbeat_id": new_id(), "swarm_id": "", "interval_s": int(interval_s),
        "docs_collected": 0, "docs_new": 0, "runs": 0, "claims_verified": 0, "claims_quarantined": 0,
        "injections": 0, "cost_usd": 0.0, "duration_ms": 0, "status": "ok",
    }
    try:
        docs = _dedupe(await collect(str(sources_path), limit, kinds))
        record["docs_collected"] = len(docs)
        already = set() if reset_seen else await store.seen([url_hash(d.url) for d in docs])
        new_docs = [d for d in docs if url_hash(d.url) not in already]
        record["docs_new"] = len(new_docs)
        if new_docs:
            result = await run_swarm(new_docs, concurrency=concurrency, telemetry=telemetry, ingest=ingest)
            record["swarm_id"] = result.swarm_id
            record["runs"] = len(result.runs)
            record["claims_verified"] = sum(1 for c in result.claims if c.status == ClaimStatus.VERIFIED)
            record["claims_quarantined"] = sum(1 for c in result.claims if c.status == ClaimStatus.QUARANTINED)
            record["injections"] = len(result.injection_events)
            record["cost_usd"] = round(sum(r.cost_usd for r in result.runs), 6)
            await store.mark(new_docs)
            if brief:
                await _brief(result, telemetry)
        else:
            record["status"] = "idle"
    except Exception as exc:
        record["status"] = f"error: {type(exc).__name__}: {exc}"[:200]
        log.exception("heartbeat tick failed")
    record["duration_ms"] = int((time.monotonic() - start) * 1000)
    if telemetry:
        _log_heartbeat(record)
    return record


def format_record(r: dict) -> str:
    ts = r["ts"].astimezone().strftime("%H:%M:%S") if isinstance(r["ts"], datetime) else str(r["ts"])
    return (
        f"[{ts}] heartbeat new={r['docs_new']}/{r['docs_collected']} runs={r['runs']} "
        f"verified={r['claims_verified']} quarantined={r['claims_quarantined']} injections={r['injections']} "
        f"cost=${r['cost_usd']:.4f} dur={r['duration_ms'] / 1000:.1f}s status={r['status']}"
    )


async def run_forever(
    interval_s: float,
    sources_path: str | Path = DEFAULT_SOURCES,
    kinds: set[str] | None = None,
    limit: int | None = None,
    *,
    once: bool = False,
    reset_seen: bool = False,
    brief: bool = False,
    seen: SeenStore | None = None,
    telemetry: bool = True,
    ingest: bool = True,
) -> None:
    first = True
    while True:
        try:
            record = await heartbeat_once(
                sources_path, kinds, limit, interval_s=interval_s, reset_seen=reset_seen and first,
                seen=seen, telemetry=telemetry, ingest=ingest, brief=brief,
            )
            print(format_record(record), flush=True)
        except Exception as exc:
            print(f"heartbeat tick crashed: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        first = False
        if once:
            return
        await asyncio.sleep(interval_s)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hive.heartbeat")
    ap.add_argument("--interval", type=float, default=120)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--sources", default=DEFAULT_SOURCES)
    ap.add_argument("--kinds", default="", help="comma-separated collector kinds, e.g. fixture,rss,edgar")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--reset-seen", action="store_true")
    ap.add_argument("--brief", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    kinds = {k.strip() for k in args.kinds.split(",") if k.strip()} or None
    try:
        asyncio.run(run_forever(
            args.interval, args.sources, kinds, args.limit, once=args.once, reset_seen=args.reset_seen, brief=args.brief,
        ))
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
