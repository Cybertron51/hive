"""SEC EDGAR full-text search. SEC requires a descriptive User-Agent with contact info:
set SEC_USER_AGENT="YourOrg you@example.com"."""
from __future__ import annotations

import asyncio
import json
import os
import re

import httpx

from hive.collectors._common import USER_AGENT, ResponseTooLargeError, UnsafeURLError, decode, make_client, parse_dt, safe_get
from hive.collectors.extract import html_to_text
from hive.models import RawDocument

SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{adsh}/{filename}"
ALLOWED_HOSTS = {"efts.sec.gov", "www.sec.gov"}
MAX_ITEMS_CAP = 20
_ADSH = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_FILENAME = re.compile(r"^[A-Za-z0-9._-]+$")


def _doc_url(hit: dict) -> str:
    src = hit.get("_source", {})
    adsh, _, filename = str(hit.get("_id", "")).partition(":")
    ciks = src.get("ciks") or []
    if not (_ADSH.match(adsh) and _FILENAME.match(filename) and ciks and str(ciks[0]).isdigit()):
        return ""
    return ARCHIVE_URL.format(cik=int(ciks[0]), adsh=adsh.replace("-", ""), filename=filename)


async def collect(source: dict) -> list[RawDocument]:


    params = {"q": source["query"]}
    if source.get("forms"):
        params["forms"] = source["forms"]
    if source.get("startdt") and source.get("enddt"):
        params.update(dateRange="custom", startdt=source["startdt"], enddt=source["enddt"])
    max_items = min(int(source.get("max_items", 5)), MAX_ITEMS_CAP)

    async with make_client(**{"User-Agent": os.environ.get("SEC_USER_AGENT", USER_AGENT)}) as client:
        search_url, body, _ = await safe_get(client, SEARCH_URL, params=params, allowed_hosts=ALLOWED_HOSTS)
        hits = json.loads(body).get("hits", {}).get("hits", [])[:max_items]

        docs = []
        for hit in hits:
            src = hit.get("_source", {})
            url = _doc_url(hit)
            names = ", ".join(str(n) for n in src.get("display_names") or [])
            title, text = f"{src.get('form', 'Filing')} - {names}".strip(" -"), ""
            if url:
                try:
                    _, doc_body, ctype = await safe_get(client, url, allowed_hosts=ALLOWED_HOSTS)
                    _, text = html_to_text(decode(doc_body, ctype))
                except (httpx.HTTPError, UnsafeURLError, ResponseTooLargeError):
                    pass
                await asyncio.sleep(0.15)
            if not text:
                text = f"{title}. Filed {src.get('file_date', '')}. Period {src.get('period_ending', '')}."
            docs.append(
                RawDocument(
                    source_id=source["source_id"],
                    url=url or search_url,
                    title=title,
                    text=text,
                    published_at=parse_dt(src.get("file_date")),
                    kind="edgar",
                )
            )
    return docs
