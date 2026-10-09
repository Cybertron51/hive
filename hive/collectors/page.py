from __future__ import annotations

import httpx

from hive.collectors._common import TIMEOUT, USER_AGENT, meta_published
from hive.collectors.extract import html_to_text
from hive.models import RawDocument


async def collect(source: dict) -> list[RawDocument]:
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.get(source["url"])
        resp.raise_for_status()
    title, text = html_to_text(resp.text)
    return [
        RawDocument(
            source_id=source["source_id"],
            url=str(resp.url),
            title=title,
            text=text,
            published_at=meta_published(resp.text),
            kind="page",
        )
    ]
