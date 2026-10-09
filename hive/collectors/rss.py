from __future__ import annotations

import asyncio
from calendar import timegm
from datetime import datetime, timezone

import feedparser
import httpx

from hive.collectors._common import TIMEOUT, USER_AGENT
from hive.collectors.extract import html_to_text
from hive.models import RawDocument


def _entry_dt(entry) -> datetime | None:
    st = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(timegm(st), tz=timezone.utc) if st else None


async def _fetch_article(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return html_to_text(resp.text)
    except httpx.HTTPError:
        return "", ""


async def collect(source: dict) -> list[RawDocument]:
    max_items = int(source.get("max_items", 10))
    fetch_full = source.get("fetch_full", True)
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.get(source["url"])
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        entries = feed.entries[:max_items]
        links = [e.get("link", "") for e in entries]
        articles = (
            await asyncio.gather(*(_fetch_article(client, u) for u in links if u))
            if fetch_full
            else []
        )
    full = dict(zip([u for u in links if u], articles))

    docs = []
    for e in entries:
        link = e.get("link", "")
        _, summary = html_to_text(e.get("summary", "")) if e.get("summary") else ("", "")
        a_title, a_text = full.get(link, ("", ""))
        text = a_text if len(a_text) > len(summary) else summary
        if not text:
            continue
        docs.append(
            RawDocument(
                source_id=source["source_id"],
                url=link or source["url"],
                title=e.get("title") or a_title,
                text=text,
                published_at=_entry_dt(e),
                kind="rss",
            )
        )
    return docs
