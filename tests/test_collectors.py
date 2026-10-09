import asyncio
from pathlib import Path

import pytest
import yaml

from hive.collectors import collect_all, load_sources
from hive.collectors._common import FIXTURES_DIR, UnsafeURLError, validate_url
from hive.collectors.extract import html_to_text
from hive.collectors.fixtures import UnsafePathError, resolve_fixture
from hive.collectors.rss import UnsafeFeedError, parse_feed

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SOURCE_IDS = {
    "helixon_newsroom", "helixon_blog", "vantra_newsroom", "biotech_ledger",
    "edgar_mirror", "orrin_newsroom", "calyx_newsroom", "strand_blog",
}


@pytest.fixture(scope="module")
def fixture_docs():
    return asyncio.run(collect_all(ROOT / "config/sources.yaml", kinds={"fixture"}))


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


def test_injection_fixture_reaches_reader(fixture_docs):
    blog = next(d for d in fixture_docs if d.url.endswith("/blog/q3-update"))
    assert "Ignore all previous instructions" in blog.text
    assert "disregard your prior instructions" in blog.text
    assert "$900" in blog.text


def test_fixture_collector_returns_all_fixtures(fixture_docs):
    assert len(fixture_docs) == 14
    assert {d.source_id for d in fixture_docs} == FIXTURE_SOURCE_IDS
    assert all(d.kind == "fixture" and d.text and d.title for d in fixture_docs)
    assert all(d.published_at is not None for d in fixture_docs)


def test_vantra_conflict_docs_have_vantra_entity_hints(fixture_docs):
    by_path = {Path(s["path"]).name: s for s in load_sources(ROOT / "config/sources.yaml") if s["kind"] == "fixture"}
    by_url = {d.url: d for d in fixture_docs}
    for name, amount in (("vantra_funding_news.html", "$45 million"), ("vantra_press_release.html", "$450 million")):
        src = by_path[name]
        assert any("Vantra" in e for e in src["entities"])
        assert amount in by_url[src["url"]].text


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
    assert resolve_fixture("fixtures/vantra_8k.html") == resolve_fixture("vantra_8k.html") == (FIXTURES_DIR / "vantra_8k.html").resolve()


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
