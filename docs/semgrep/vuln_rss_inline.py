# INTENTIONALLY VULNERABLE: the same SSRF as vuln_rss.py with the fetch inlined into collect().
# Used to validate docs/semgrep/rules/hive-feed-ssrf.yml, whose taint tracking is intraprocedural.
import feedparser
import httpx


async def collect(source):
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(source["url"])
        feed = feedparser.parse(resp.content)
        out = []
        for entry in feed.entries[:10]:
            link = entry.get("link", "")
            page = await client.get(link)
            out.append((link, page.text))
    return out
