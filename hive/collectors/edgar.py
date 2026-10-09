"""SEC EDGAR full-text search. SEC requires a descriptive User-Agent with contact info:
set SEC_USER_AGENT="YourOrg you@example.com"."""
from __future__ import annotations

import asyncio
import os

import httpx

from hive.collectors._common import TIMEOUT, USER_AGENT, parse_dt
from hive.collectors.extract import html_to_text
from hive.models import RawDocument

SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{adsh}/{filename}"


def _doc_url(hit: dict) -> str:
    src = hit.get("_source", {})
    adsh, _, filename = hit.get("_id", "").partition(":")
    ciks = src.get("ciks") or []
    if not (adsh and filename and ciks):
        return ""
    return ARCHIVE_URL.format(cik=int(ciks[0]), adsh=adsh.replace("-", ""), filename=filename)


async def collect(source: dict) -> list[RawDocument]:
    params = {"q": source["query"]}
    if source.get("forms"):
        params["forms"] = source["forms"]
    if source.get("startdt") and source.get("enddt"):
        params.update(dateRange="custom", startdt=source["startdt"], enddt=source["enddt"])
    max_items = int(source.get("max_items", 5))
    headers = {"User-Agent": os.environ.get("SEC_USER_AGENT", USER_AGENT), "Accept-Encoding": "gzip, deflate"}

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers=headers) as client:
        resp = await client.get(SEARCH_URL, params=params)
        resp.raise_for_status()
        hits = resp.json().get("hits", {}).get("hits", [])[:max_items]

        docs = []
        for hit in hits:
            src = hit.get("_source", {})
            url = _doc_url(hit)
            names = ", ".join(src.get("display_names") or [])
            title, text = f"{src.get('form', 'Filing')} - {names}".strip(" -"), ""
            if url:
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    _, text = html_to_text(r.text)
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.15)
            if not text:
                text = f"{title}. Filed {src.get('file_date', '')}. Period {src.get('period_ending', '')}."
            docs.append(
                RawDocument(
                    source_id=source["source_id"],
                    url=url or str(resp.url),
                    title=title,
                    text=text,
                    published_at=parse_dt(src.get("file_date")),
                    kind="edgar",
                )
            )
    return docs
