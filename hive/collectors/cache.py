"""Small on-disk cache for article and filing fetches, so a frequent heartbeat doesn't re-download
unchanged pages and get rate-limited. Feed indexes and EDGAR submission lists are never cached.
Disable with HIVE_NO_CACHE=1; relocate with HIVE_CACHE_DIR (default data/cache, gitignored)."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

from hive.collectors._common import ROOT

ARTICLE_TTL_S = 6 * 3600
FAILURE_TTL_S = 15 * 60


def _dir() -> Path | None:
    if os.environ.get("HIVE_NO_CACHE", "").lower() in ("1", "true", "yes"):
        return None
    return Path(os.environ.get("HIVE_CACHE_DIR") or ROOT / "data" / "cache")


def _path(url: str) -> Path | None:
    d = _dir()
    return d / f"{hashlib.sha256(url.encode()).hexdigest()}.json" if d else None


def get(url: str, ttl_s: float | None) -> dict | None:
    """Cached entry for url, or None. ttl_s=None means never expires; failures always expire after FAILURE_TTL_S."""
    p = _path(url)
    if p is None:
        return None
    try:
        entry = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if entry.get("url") != url:
        return None
    age = time.time() - float(entry.get("stored_at", 0))
    limit = FAILURE_TTL_S if entry.get("failed") else ttl_s
    return entry if limit is None or age < limit else None


def put(url: str, **fields) -> None:
    p = _path(url)
    if p is None:
        return
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"url": url, "stored_at": time.time(), **fields}), encoding="utf-8")
        tmp.replace(p)
    except OSError:
        pass
