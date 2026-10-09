from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import yaml

from hive.collectors import edgar, fixtures, page, rss
from hive.collectors._common import ROOT
from hive.models import RawDocument

log = logging.getLogger(__name__)

COLLECTORS = {
    "fixture": fixtures.collect,
    "page": page.collect,
    "rss": rss.collect,
    "edgar": edgar.collect,
}


def load_sources(sources_path: str | Path = "config/sources.yaml") -> list[dict]:
    path = Path(sources_path)
    if not path.is_absolute() and not path.exists():
        path = ROOT / path
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources = data.get("sources", data) if isinstance(data, dict) else data
    return [s for s in sources if s.get("enabled", True)]


async def _safe_collect(source: dict) -> list[RawDocument]:
    fn = COLLECTORS.get(source.get("kind", ""))
    if fn is None:
        log.warning("unknown source kind %r for %s", source.get("kind"), source.get("source_id"))
        return []
    try:
        return await fn(source)
    except Exception as e:
        log.warning("collector failed for %s (%s): %s", source.get("source_id"), source.get("kind"), e)
        return []


async def collect_all(sources_path: str | Path = "config/sources.yaml", kinds: set[str] | None = None) -> list[RawDocument]:
    sources = [s for s in load_sources(sources_path) if kinds is None or s.get("kind") in kinds]
    results = await asyncio.gather(*(_safe_collect(s) for s in sources))
    return [doc for docs in results for doc in docs]
