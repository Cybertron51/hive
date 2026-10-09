"""SEC EDGAR collectors.
- source with `cik`: recent filings of `forms` from the submissions API (data.sec.gov), 8-K exhibits 99.x included.
- source with `query`: EDGAR full-text search (efts.sec.gov).
SEC requires a descriptive User-Agent with contact info: set SEC_USER_AGENT="YourOrg you@example.com"."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
import weakref

import httpx
from lxml import etree

from hive.collectors import cache
from hive.collectors._common import USER_AGENT, ResponseTooLargeError, UnsafeURLError, decode, make_client, parse_dt, safe_get
from hive.collectors.extract import html_to_text
from hive.models import RawDocument

SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{adsh}/{filename}"
ALLOWED_HOSTS = {"efts.sec.gov", "www.sec.gov", "data.sec.gov"}
MAX_ITEMS_CAP = 20
DOC_MAX_BYTES = 1024 * 1024
MAX_TEXT_CHARS = 30_000
SEC_MIN_INTERVAL = 0.125
_ADSH = re.compile(r"^\d{10}-\d{2}-\d{6}$")
_FILENAME = re.compile(r"^[A-Za-z0-9._-]+$")
_EX99 = re.compile(r"ex-?99|dex99", re.IGNORECASE)
log = logging.getLogger(__name__)

SEC_MAX_INFLIGHT = 4
SEC_ATTEMPTS = 3
SEC_BACKOFF_S = 1.0
SEC_MAX_RETRY_AFTER_S = 10.0
SEC_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_RETRY_STATUS = {429, 500, 502, 503, 504}


class _Limiter:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.inflight = asyncio.Semaphore(SEC_MAX_INFLIGHT)
        self.last = 0.0


_limiters: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, _Limiter]" = weakref.WeakKeyDictionary()


def _limiter() -> _Limiter:
    loop = asyncio.get_running_loop()
    lim = _limiters.get(loop)
    if lim is None:
        lim = _limiters[loop] = _Limiter()
    return lim


def _retry_delay(attempt: int, exc: Exception) -> float | None:
    """Seconds to wait before retrying, or None if exc is not retryable."""
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code not in _RETRY_STATUS:
            return None
        ra = exc.response.headers.get("retry-after", "")
        if ra.isdigit():
            return min(float(ra), SEC_MAX_RETRY_AFTER_S)
    elif not isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return None
    return SEC_BACKOFF_S * (2 ** attempt) + random.uniform(0, 0.25)


async def _sec_get(client: httpx.AsyncClient, url: str, **kw) -> tuple[str, bytes, str]:
    """SEC fair-access: requests start at most ~8/second and at most SEC_MAX_INFLIGHT run at once across
    all EDGAR sources in this event loop. Timeouts, transport errors, 429 and 5xx are retried with backoff."""
    lim = _limiter()
    for attempt in range(SEC_ATTEMPTS):
        try:
            async with lim.inflight:
                async with lim.lock:
                    wait = SEC_MIN_INTERVAL - (time.monotonic() - lim.last)
                    if wait > 0:
                        await asyncio.sleep(wait)
                    lim.last = time.monotonic()
                return await safe_get(client, url, allowed_hosts=ALLOWED_HOSTS, **kw)
        except Exception as exc:
            delay = _retry_delay(attempt, exc)
            if delay is None or attempt == SEC_ATTEMPTS - 1:
                raise
            log.info("SEC %s failed (%s: %r), retry %d in %.1fs", url, type(exc).__name__, exc, attempt + 1, delay)
            await asyncio.sleep(delay)
    raise RuntimeError("unreachable")


def _client() -> httpx.AsyncClient:
    client = make_client(**{"User-Agent": os.environ.get("SEC_USER_AGENT", USER_AGENT)})
    client.timeout = SEC_TIMEOUT
    return client


def _archive_url(cik, adsh: str, filename: str) -> str:
    if not (_ADSH.match(adsh) and _FILENAME.match(filename) and str(cik).isdigit()):
        return ""
    return ARCHIVE_URL.format(cik=int(cik), adsh=adsh.replace("-", ""), filename=filename)


async def _doc_text(client: httpx.AsyncClient, url: str) -> str:
    """Archived filings are immutable, so successful extractions are cached without expiry."""
    hit = cache.get(url, None)
    if hit is not None:
        return "" if hit.get("failed") else hit.get("text", "")
    try:
        _, body, ctype = await _sec_get(client, url, max_bytes=DOC_MAX_BYTES, truncate=True)
    except httpx.HTTPStatusError as e:
        cache.put(url, failed=True, status=e.response.status_code)
        return ""
    except (httpx.HTTPError, UnsafeURLError, ResponseTooLargeError):
        return ""
    try:
        text = html_to_text(decode(body, ctype))[1]
    except (ValueError, etree.LxmlError):
        return ""
    cache.put(url, text=text)
    return text


async def _exhibit_99_texts(client: httpx.AsyncClient, cik, adsh: str, limit: int = 2) -> list[str]:
    index_url = _archive_url(cik, adsh, "index.json")
    if not index_url:
        return []
    hit = cache.get(index_url, None)
    if hit is not None and not hit.get("failed"):
        items = hit.get("items", [])
    else:
        try:
            _, body, _ = await _sec_get(client, index_url)
            items = json.loads(body).get("directory", {}).get("item", [])
        except (httpx.HTTPError, UnsafeURLError, ResponseTooLargeError, ValueError):
            return []
        cache.put(index_url, items=[{"name": i.get("name", "")} for i in items if isinstance(i, dict)])
    names = [i.get("name", "") for i in items if _EX99.search(i.get("name", "")) and i.get("name", "").lower().endswith((".htm", ".html"))]
    texts = []
    for name in sorted(names)[:limit]:
        if (url := _archive_url(cik, adsh, name)) and (t := await _doc_text(client, url)):
            texts.append(t)
    return texts


async def _collect_by_cik(source: dict, max_items: int) -> list[RawDocument]:
    cik = int(source["cik"])
    forms = source.get("forms") or ["8-K", "10-Q"]
    forms = {forms} if isinstance(forms, str) else set(forms)
    name = source.get("name") or (source.get("entities") or [""])[0]

    async with _client() as client:
        _, body, _ = await _sec_get(client, SUBMISSIONS_URL.format(cik=cik), max_bytes=8 * 1024 * 1024)
        data = json.loads(body)
        name = name or data.get("name", "")
        recent = data.get("filings", {}).get("recent", {})
        rows = zip(
            recent.get("form", []), recent.get("accessionNumber", []), recent.get("filingDate", []),
            recent.get("primaryDocument", []), recent.get("items", []) or [""] * len(recent.get("form", [])),
        )
        picked = [r for r in rows if r[0] in forms][:max_items]

        docs = []
        for form, adsh, filed, primary, items in picked:
            url = _archive_url(cik, adsh, primary)
            if not url:
                continue
            parts = [await _doc_text(client, url)]
            if form == "8-K":
                parts += await _exhibit_99_texts(client, cik, adsh)
            text = "\n\n".join(p for p in parts if p)[:MAX_TEXT_CHARS]
            title = f"{form} - {name} ({filed})" + (f" Items {items}" if items else "")
            docs.append(
                RawDocument(
                    source_id=source["source_id"],
                    url=url,
                    title=title,
                    text=text or f"{title}. Accession {adsh}.",
                    published_at=parse_dt(filed),
                    kind="edgar",
                )
            )
    return docs


def _search_hit_url(hit: dict) -> str:
    adsh, _, filename = str(hit.get("_id", "")).partition(":")
    ciks = hit.get("_source", {}).get("ciks") or []
    return _archive_url(ciks[0], adsh, filename) if ciks else ""


async def _collect_by_query(source: dict, max_items: int) -> list[RawDocument]:
    params = {"q": source["query"]}
    if source.get("forms"):
        forms = source["forms"]
        params["forms"] = forms if isinstance(forms, str) else ",".join(forms)
    if source.get("startdt") and source.get("enddt"):
        params.update(dateRange="custom", startdt=source["startdt"], enddt=source["enddt"])

    async with _client() as client:
        search_url, body, _ = await _sec_get(client, SEARCH_URL, params=params)
        hits = json.loads(body).get("hits", {}).get("hits", [])[:max_items]
        docs = []
        for hit in hits:
            src = hit.get("_source", {})
            url = _search_hit_url(hit)
            names = ", ".join(str(n) for n in src.get("display_names") or [])
            title = f"{src.get('form', 'Filing')} - {names}".strip(" -")
            text = (await _doc_text(client, url))[:MAX_TEXT_CHARS] if url else ""
            docs.append(
                RawDocument(
                    source_id=source["source_id"],
                    url=url or search_url,
                    title=title,
                    text=text or f"{title}. Filed {src.get('file_date', '')}.",
                    published_at=parse_dt(src.get("file_date")),
                    kind="edgar",
                )
            )
    return docs


async def collect(source: dict) -> list[RawDocument]:
    max_items = min(int(source.get("max_items", 5)), MAX_ITEMS_CAP)
    if source.get("cik"):
        return await _collect_by_cik(source, max_items)
    return await _collect_by_query(source, max_items)
