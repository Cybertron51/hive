from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

COMPETITORS_PATH = Path(__file__).resolve().parents[2] / "config" / "competitors.yaml"


@dataclass(frozen=True)
class Competitor:
    name: str
    aliases: tuple[str, ...]
    tier: str = ""

    @property
    def terms(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


def _entries(data: Any, tier: str = "") -> list[Competitor]:
    if isinstance(data, dict) and "competitors" in data:
        return _entries(data["competitors"], tier)
    if isinstance(data, dict) and "name" not in data:
        return [c for key, value in data.items() for c in _entries(value, str(key))]
    if isinstance(data, dict):
        aliases = data.get("aliases") or []
        aliases = [aliases] if isinstance(aliases, str) else aliases
        name = str(data["name"]).strip()
        clean = tuple(str(a).strip() for a in aliases if str(a).strip() and str(a).strip().lower() != name.lower())
        return [Competitor(name=name, aliases=clean, tier=str(data.get("tier") or tier))] if name else []
    if isinstance(data, list):
        return [c for item in data for c in _entries(item, tier)]
    if isinstance(data, str) and data.strip():
        return [Competitor(name=data.strip(), aliases=(), tier=tier)]
    return []


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> tuple[Competitor, ...]:
    try:
        import yaml

        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("competitors config unreadable (%s: %s); entity normalization disabled", type(exc).__name__, exc)
        return ()
    seen: dict[str, Competitor] = {}
    for c in _entries(data):
        seen.setdefault(c.name.lower(), c)
    return tuple(seen.values())


def load(path: Path = COMPETITORS_PATH) -> tuple[Competitor, ...]:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return ()
    return _load(str(path), mtime)


def _pattern(term: str) -> re.Pattern[str]:
    flags = 0 if term.isupper() and len(term) <= 5 else re.I
    return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])", flags)


def _first_hit(text: str, competitors: tuple[Competitor, ...]) -> Competitor | None:
    best: tuple[int, int, Competitor] | None = None
    for c in competitors:
        for term in c.terms:
            m = _pattern(term).search(text)
            if m and (best is None or (m.start(), -len(term)) < (best[0], best[1])):
                best = (m.start(), -len(term), c)
    return best[2] if best else None


def match(entity: str, text: str = "", competitors: tuple[Competitor, ...] | None = None) -> Competitor | None:
    comps = load() if competitors is None else competitors
    if not comps:
        return None
    low = entity.strip().lower()
    for c in comps:
        if low in (t.lower() for t in c.terms):
            return c
    return _first_hit(entity, comps) or (_first_hit(text, comps) if text else None)


def normalize_claims(claims: list[dict], competitors: tuple[Competitor, ...] | None = None) -> list[dict]:
    comps = load() if competitors is None else competitors
    for c in claims:
        if not comps:
            c["tracked"] = True
            continue
        hit = match(c.get("entity", ""), c.get("text", ""), comps)
        if hit:
            if hit.name != c.get("entity"):
                c.setdefault("raw_entity", c.get("entity", ""))
            c["entity"], c["tracked"] = hit.name, True
        else:
            c["tracked"] = False
    return claims


def names() -> list[str]:
    return [c.name for c in load()]


def aliases() -> dict[str, list[str]]:
    return {c.name: list(c.aliases) for c in load() if c.aliases}
