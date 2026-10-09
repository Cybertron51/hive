from __future__ import annotations

import asyncio
import re
from calendar import timegm
from datetime import datetime, timezone

import feedparser
import httpx

from hive.collectors._common import UnsafeURLError, ResponseTooLargeError, decode, make_client, safe_get
from hive.collectors.extract import html_to_text
from hive.models import RawDocument

_ENTITY_DECL = re.compile(rb"<!ENTITY", re.IGNORECASE)
MAX_ITEMS_CAP = 50


class UnsafeFeedError(ValueError):
    pass


def _entry_dt(entry) -> datetime | None:
    st = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(timegm(st), tz=timezone.utc) if st else None


def parse_feed(body: bytes):
    if _ENTITY_DECL.search(body):
        raise UnsafeFeedError("feed declares XML entities (possible XXE / billion laughs)")
    return feedparser.parse(body, resolve_relative_uris=False, sanitize_html=True)


async def _fetch_article(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    try:
        _, body, ctype = await safe_get(client, url)
        return html_to_text(decode(body, ctype))
    except (httpx.HTTPError, UnsafeURLError, ResponseTooLargeError):
        return "", ""


async def collect(source: dict) -> list[RawDocument]:
    max_items = min(int(source.get("max_items", 10)), MAX_ITEMS_CAP)
    fetch_full = source.get("fetch_full", True)
    async with make_client() as client:
        _, body, _ = await safe_get(client, source["url"])
        feed = parse_feed(body)
        entries = feed.entries[:max_items]
        links = [e.get("link", "") for e in entries if e.get("link")]
        articles = await asyncio.gather(*(_fetch_article(client, u) for u in links)) if fetch_full else []
    full = dict(zip(links, articles))

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
