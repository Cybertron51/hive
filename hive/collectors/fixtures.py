from __future__ import annotations

import asyncio
from pathlib import Path

from hive.collectors._common import ROOT, meta_published
from hive.collectors.extract import html_to_text
from hive.models import RawDocument


async def collect(source: dict) -> list[RawDocument]:
    path = Path(source["path"])
    if not path.is_absolute():
        path = ROOT / path
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
