from __future__ import annotations

import asyncio
from pathlib import Path

from hive.collectors._common import FIXTURES_DIR, MAX_BYTES, meta_published
from hive.collectors.extract import html_to_text
from hive.models import RawDocument


class UnsafePathError(ValueError):
    pass


def resolve_fixture(path_str: str, base: Path = FIXTURES_DIR) -> Path:
    base = base.resolve()
    raw = Path(path_str)
    if raw.is_absolute():
        raise UnsafePathError(f"absolute fixture path not allowed: {path_str!r}")
    if raw.parts and raw.parts[0] == base.name:
        raw = Path(*raw.parts[1:])
    path = (base / raw).resolve()
    if not path.is_relative_to(base) or path == base:
        raise UnsafePathError(f"fixture path escapes {base}: {path_str!r}")
    if not path.is_file():
        raise FileNotFoundError(path_str)
    if path.stat().st_size > MAX_BYTES:
        raise UnsafePathError(f"fixture too large: {path_str!r}")
    return path


async def collect(source: dict) -> list[RawDocument]:
    path = resolve_fixture(source["path"])
    html = await asyncio.to_thread(path.read_text, encoding="utf-8")
    title, text = html_to_text(html)
    return [
        RawDocument(
            source_id=source["source_id"],
            url=source.get("url") or path.as_uri(),
            title=title,
            text=text,
            published_at=meta_published(html),
            kind="fixture",
        )
    ]
