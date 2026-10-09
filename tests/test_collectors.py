import asyncio
import json
import os
from pathlib import Path

import pytest

from hive.collectors import collect_all, load_sources
from hive.collectors._common import FIXTURES_DIR, UnsafeURLError, validate_url
from hive.collectors.entities import entity_hints, load_competitors, match_entities
from hive.collectors.extract import html_to_text
from hive.collectors.fixtures import UnsafePathError, resolve_fixture
from hive.collectors.rss import UnsafeFeedError, parse_feed
from hive.models import RawDocument

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "config/sources.yaml"
FIXTURE_SOURCE_IDS = {
    "nullgrid_newsroom", "nullgrid_blog", "obsidiangate_newsroom", "cyber_ledger", "edgar_mirror",
    "lattice_newsroom", "kestrel_newsroom", "kestrel_advisories", "harbor_newsroom", "harbor_blog",
}
LIVE_NAMES = {"CrowdStrike", "Palo Alto Networks", "SentinelOne", "Zscaler", "Fortinet", "Okta", "Wiz", "Cloudflare", "Datadog", "Rapid7"}
FICTIONAL_NAMES = {"Nullgrid Security", "Obsidian Gate", "Lattice Defense", "Kestrel Identity", "Harbor Cloud Security"}
network = pytest.mark.skipif(not os.environ.get("HIVE_NETWORK_TESTS"), reason="set HIVE_NETWORK_TESTS=1 for live feeds")


@pytest.fixture(scope="module")
def fixture_docs():
    return asyncio.run(collect_all(SOURCES, kinds={"fixture"}))


def test_html_to_text_keeps_hidden_div_and_comments():
    html = """<html><head><title>T</title></head><body><article>
    <p>Visible paragraph one with enough words to look like an article body for readability.</p>
    <!-- secret comment payload -->
    <div style="color:#ffffff;background:#ffffff;font-size:1px">hidden white text payload</div>
    <span style="display:none">display none payload</span>
    </article></body></html>"""
    title, text = html_to_text(html)
    assert title == "T"
    assert "Visible paragraph one" in text
    assert "secret comment payload" in text
    assert "hidden white text payload" in text
    assert "display none payload" in text


def test_html_to_text_accepts_xml_declaration():
    title, text = html_to_text('<?xml version="1.0" encoding="utf-8"?><html><head><title>X</title></head><body><p>inline xbrl body</p></body></html>')
    assert title == "X" and "inline xbrl body" in text


def test_injection_fixture_reaches_reader(fixture_docs):
    blog = next(d for d in fixture_docs if d.source_id == "nullgrid_blog")
    assert "Ignore all previous instructions" in blog.text
    assert "disregard your prior instructions" in blog.text
    assert "FedRAMP authorization" in blog.text and "Obsidian Gate" in blog.text


def test_fixture_collector_returns_all_fixtures(fixture_docs):
    assert len(fixture_docs) == 14
    assert {d.source_id for d in fixture_docs} == FIXTURE_SOURCE_IDS
    assert all(d.kind == "fixture" and d.text and d.title for d in fixture_docs)
    assert all(d.published_at is not None for d in fixture_docs)


def test_obsidian_gate_conflict_docs(fixture_docs):
    by_path = {Path(s["path"]).name: s for s in load_sources(SOURCES) if s["kind"] == "fixture"}
    by_url = {d.url: d for d in fixture_docs}
    for name, amount in (
        ("obsidiangate_funding_news.html", "$45 million"),
        ("obsidiangate_press_release.html", "$450 million"),
        ("obsidiangate_8k.html", "$450.0 million"),
    ):
        doc = by_url[by_path[name]["url"]]
        assert amount in doc.text
        assert "Obsidian Gate" in entity_hints(doc, SOURCES)


def test_fixtures_never_mention_live_vendors(fixture_docs):
    for d in fixture_docs:
        assert not set(entity_hints(d, SOURCES)) & LIVE_NAMES, d.url


def test_competitors_config():
    comps = load_competitors()
    assert {c["name"] for c in comps["live"]} == LIVE_NAMES
    assert {c["name"] for c in comps["fixture"]} == FICTIONAL_NAMES
    for c in comps["live"]:
        assert c["segments"]
        if c["ticker"]:
            assert isinstance(c["cik"], int)
    for tier in comps.values():
        for c in tier:
            assert all(len(a) > 3 for a in c.get("aliases") or []), c["name"]


@pytest.mark.parametrize("text,expected", [
    ("Attackers bypassed CrowdStrike Falcon sensors", {"CrowdStrike"}),
    ("Shares of CRWD rose 4%", {"CrowdStrike"}),
    ("Prisma Access and Cortex XSIAM updates", {"Palo Alto Networks"}),
    ("SentinelOne (NYSE: S) reported results", {"SentinelOne"}),
    ("Cloudflare (NYSE: NET) said", {"Cloudflare"}),
    ("FortiGate devices are being exploited", {"Fortinet"}),
    ("A new Auth0 feature", {"Okta"}),
    ("Nullgrid Sentinel XDR 4.0 launched", {"Nullgrid Security"}),
    ("the wizard said S and NET are words", set()),
    ("SentinelOne's report", {"SentinelOne"}),
])
def test_entity_alias_matching(text, expected):
    assert set(match_entities(text)) == expected


def test_entity_hints_merge_source_and_text():
    doc = RawDocument(source_id="crowdstrike_blog", url="https://x", title="Unit 42 and FortiGate", text="")
    assert entity_hints(doc, SOURCES) == ["CrowdStrike", "Palo Alto Networks", "Fortinet"]


async def test_edgar_cik_mode_mocked(monkeypatch):
    from hive.collectors import edgar

    submissions = {"name": "CROWDSTRIKE HOLDINGS, INC.", "filings": {"recent": {
        "form": ["4", "8-K", "10-Q"], "accessionNumber": ["0001535527-26-000001", "0001535527-26-000029", "0001535527-26-000031"],
        "filingDate": ["2026-09-01", "2026-08-26", "2026-08-27"], "primaryDocument": ["f4.xml", "crwd-8k.htm", "crwd-10q.htm"],
        "items": ["", "2.02,9.01", ""],
    }}}
    pages = {
        "crwd-8k.htm": b"<html><body><p>Item 2.02 Results of Operations.</p></body></html>",
        "ex991.htm": b"<html><body><p>Revenue grew 21% year over year.</p></body></html>",
        "crwd-10q.htm": b'<?xml version="1.0" encoding="utf-8"?><html><body><p>QUARTERLY REPORT</p></body></html>',
    }
    calls = []

    async def fake(client, url, **kw):
        calls.append(url)
        if "submissions" in url:
            return url, json.dumps(submissions).encode(), "application/json"
        if url.endswith("index.json"):
            return url, json.dumps({"directory": {"item": [{"name": "ex991.htm"}, {"name": "crwd-8k.htm"}]}}).encode(), "application/json"
        return url, pages[url.rsplit("/", 1)[1]], "text/html"

    monkeypatch.setattr(edgar, "_sec_get", fake)
    docs = await edgar.collect({"source_id": "edgar_crowdstrike", "cik": 1535527, "forms": ["8-K", "10-Q"], "max_items": 2, "name": "CrowdStrike"})
    assert [d.title.split(" -")[0] for d in docs] == ["8-K", "10-Q"]
    assert "Revenue grew 21%" in docs[0].text and "QUARTERLY REPORT" in docs[1].text
    assert docs[0].url == "https://www.sec.gov/Archives/edgar/data/1535527/000153552726000029/crwd-8k.htm"
    assert not any("f4.xml" in u for u in calls)


def test_edgar_rejects_malformed_accession():
    from hive.collectors.edgar import _archive_url

    assert _archive_url(1535527, "../../etc", "passwd") == ""
    assert _archive_url(1535527, "0001535527-26-000029", "../x.htm") == ""
    assert _archive_url("1535527/../x", "0001535527-26-000029", "a.htm") == ""


@network
async def test_live_heartbeat():
    docs = await collect_all(SOURCES)
    live_feeds = {d.source_id for d in docs if d.kind == "rss"}
    assert sum(d.kind == "fixture" for d in docs) == 14
    assert len(live_feeds) >= 5
    assert any(d.kind == "edgar" for d in docs)


@pytest.mark.parametrize("bad", ["../config/sources.yaml", "/etc/passwd", "fixtures/../../etc/passwd", "..", "fixtures"])
def test_fixture_path_traversal_rejected(bad):
    with pytest.raises((UnsafePathError, FileNotFoundError)):
        resolve_fixture(bad)


def test_fixture_symlink_escape_rejected(tmp_path):
    base = tmp_path / "fixtures"
    base.mkdir()
    (tmp_path / "secret.txt").write_text("x")
    (base / "link.html").symlink_to(tmp_path / "secret.txt")
    with pytest.raises(UnsafePathError):
        resolve_fixture("link.html", base=base)


def test_fixture_path_accepts_both_forms():
    assert resolve_fixture("fixtures/obsidiangate_8k.html") == resolve_fixture("obsidiangate_8k.html") == (FIXTURES_DIR / "obsidiangate_8k.html").resolve()


@pytest.mark.parametrize("url", [
    "file:///etc/passwd",
    "gopher://example.com/",
    "http://127.0.0.1:8123/?query=SELECT%201",
    "http://localhost:8123/",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.1/",
    "http://192.168.1.1/",
    "http://[::1]/",
    "http://[::ffff:127.0.0.1]/",
    "http://0.0.0.0/",
    "http://user:pass@example.com/",
])
async def test_validate_url_blocks_ssrf(url):
    with pytest.raises(UnsafeURLError):
        await validate_url(url)


def test_rss_rejects_entity_declarations():
    xxe = b'<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss><channel><item><title>&x;</title></item></channel></rss>'
    with pytest.raises(UnsafeFeedError):
        parse_feed(xxe)


@pytest.fixture
def internal_server():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    hits = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            hits.append(self.path)
            port = self.server.server_address[1]
            if self.path == "/feed.xml":
                body = (
                    '<?xml version="1.0"?><rss version="2.0"><channel><title>f</title>'
                    f'<item><title>leak</title><link>http://127.0.0.1:{port}/internal</link>'
                    "<description>public summary text</description></item></channel></rss>"
                ).encode()
                ctype = "application/rss+xml"
            elif self.path == "/redirect":
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{port}/internal")
                self.end_headers()
                return
            else:
                body, ctype = b"<html><body><p>INTERNAL SECRET clickhouse credentials</p></body></html>", "text/html"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", hits
    srv.shutdown()


def _allow_only(monkeypatch, allowed_url):
    from hive.collectors import _common

    original = _common.validate_url

    async def patched(url):
        return url if url == allowed_url else await original(url)

    monkeypatch.setattr(_common, "validate_url", patched)


async def test_rss_does_not_fetch_internal_article_link(internal_server, monkeypatch):
    from hive.collectors import rss

    base, hits = internal_server
    _allow_only(monkeypatch, f"{base}/feed.xml")
    docs = await rss.collect({"source_id": "evil_feed", "url": f"{base}/feed.xml"})
    assert "/internal" not in hits
    assert docs and all("INTERNAL SECRET" not in d.text for d in docs)
    assert docs[0].text == "public summary text"


async def test_page_redirect_to_internal_blocked(internal_server, monkeypatch):
    from hive.collectors import page

    base, hits = internal_server
    _allow_only(monkeypatch, f"{base}/redirect")
    with pytest.raises(UnsafeURLError):
        await page.collect({"source_id": "evil_page", "url": f"{base}/redirect"})
    assert "/internal" not in hits
