"""Entity hints: map competitor names, product aliases and tickers in a document to canonical names."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from hive.collectors._common import ROOT
from hive.models import RawDocument

COMPETITORS_PATH = ROOT / "config" / "competitors.yaml"


def load_competitors(path: str | Path = COMPETITORS_PATH) -> dict[str, list[dict]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return {tier: list(data.get(tier) or []) for tier in ("live", "fixture")}


def _patterns(company: dict) -> list[re.Pattern]:
    names = [company["name"], *(company.get("aliases") or [])]
    pats = [re.compile(rf"(?<![\w$]){re.escape(n)}(?!\w)") for n in names if n]
    if t := company.get("ticker"):
        t = re.escape(t)
        pats.append(re.compile(rf"\b(?:NASDAQ|Nasdaq|NYSE)\s*:\s*{t}\b"))
        pats.append(re.compile(rf"(?<![\w$])\${t}\b"))
    return pats


@lru_cache(maxsize=4)
def alias_index(path: str = str(COMPETITORS_PATH)) -> tuple[tuple[str, str, tuple[re.Pattern, ...]], ...]:
    comps = load_competitors(path)
    return tuple(
        (c["name"], tier, tuple(_patterns(c)))
        for tier in ("live", "fixture")
        for c in comps[tier]
    )


def match_entities(text: str, path: str | Path = COMPETITORS_PATH) -> list[str]:
    if not text:
        return []
    return [name for name, _, pats in alias_index(str(path)) if any(p.search(text) for p in pats)]


@lru_cache(maxsize=4)
def _source_hints(sources_path: str) -> dict[str, list[str]]:
    from hive.collectors import load_sources

    hints: dict[str, list[str]] = {}
    for s in load_sources(sources_path):
        ents = list(s.get("entities") or [])
        key = s.get("url") if s.get("kind") == "fixture" else s.get("source_id")
        if key:
            hints.setdefault(key, [])
            hints[key] += [e for e in ents if e not in hints[key]]
    return hints


def entity_hints(doc: RawDocument, sources_path: str | Path = ROOT / "config" / "sources.yaml") -> list[str]:
    """Canonical entity names: source-level hints from sources.yaml plus alias matches in title/text."""
    path = Path(sources_path)
    src = _source_hints(str(path if path.is_absolute() else ROOT / path))
    out = list(src.get(doc.url) or src.get(doc.source_id) or [])
    for name in match_entities(f"{doc.title}\n{doc.text}"):
        if name not in out:
            out.append(name)
    return out
