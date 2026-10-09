# INTENTIONALLY VULNERABLE: demo copy for docs/semgrep/ssrf_poc.py. Not imported by Hive.
# Verbatim copy of the fetch logic in hive/collectors/rss.py as first written (before the fix).
import asyncio
import feedparser
import httpx
from hive.collectors.extract import html_to_text
TIMEOUT = 15.0
USER_AGENT = "HiveResearchBot/0.1 (hackathon research; +https://hive.example)"

async def _fetch_article(client, url):
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return html_to_text(resp.text)
    except httpx.HTTPError:
        return "", ""

async def collect(source):
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.get(source["url"])
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        links = [e.get("link", "") for e in feed.entries[:10]]
        articles = await asyncio.gather(*(_fetch_article(client, u) for u in links if u))
    return [(u, t) for u, (_, t) in zip(links, articles) if t]
