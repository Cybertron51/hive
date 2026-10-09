from __future__ import annotations

from hive.collectors._common import decode, make_client, meta_published, safe_get
from hive.collectors.extract import html_to_text
from hive.models import RawDocument


async def collect(source: dict) -> list[RawDocument]:
    async with make_client() as client:
        final_url, body, ctype = await safe_get(client, source["url"])
    html = decode(body, ctype)
    title, text = html_to_text(html)
    return [
        RawDocument(
            source_id=source["source_id"],
            url=final_url,
            title=title,
            text=text,
            published_at=meta_published(html),
            kind="page",
        )
    ]
