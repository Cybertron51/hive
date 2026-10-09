import asyncio, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import vuln_rss
from hive.collectors import _common, rss

hits = []
class Internal(BaseHTTPRequestHandler):
    def do_GET(self):
        hits.append(self.path)
        self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
        self.wfile.write(b"<html><body><p>INTERNAL-ONLY: db_password=hunter2, admin token abc123. This service is bound to localhost and must never be reachable from a scraped feed.</p></body></html>")
    def log_message(self, *a): pass
class Feed(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type", "application/rss+xml"); self.end_headers()
        self.wfile.write(f'<?xml version="1.0"?><rss version="2.0"><channel><title>Biotech News</title><item><title>Totally normal press release</title><link>http://127.0.0.1:{internal.server_port}/admin/secrets</link><description>Quarterly update.</description></item></channel></rss>'.encode())
    def log_message(self, *a): pass
internal = HTTPServer(("127.0.0.1", 0), Internal); feed = HTTPServer(("127.0.0.1", 0), Feed)
for s in (internal, feed): threading.Thread(target=s.serve_forever, daemon=True).start()
FEED = f"http://127.0.0.1:{feed.server_port}/feed.xml"
print("Hive SSRF PoC (CWE-918): malicious RSS item links to a localhost-only service")
print(f"feed:     {FEED}")
print(f"internal: http://127.0.0.1:{internal.server_port}/admin/secrets  (stands in for ClickHouse :8123 / 169.254.169.254)")

async def main():
    print("\n=== BEFORE: original rss.py (client.get, follow_redirects=True, no host check) ===")
    hits.clear()
    for url, text in await vuln_rss.collect({"url": FEED}):
        print(f"RawDocument url={url}\n  text: {text[:110]}")
    print(f"internal server requests: {hits}  ->  {'LEAKED into pipeline' if hits else 'not reached'}")

    print("\n=== AFTER: hive/collectors/rss.py with safe_get (feed URL allowlisted for the test only) ===")
    hits.clear()
    real = _common.validate_url
    async def allow_feed(u):
        return u if u.startswith(FEED) else await real(u)
    _common.validate_url = allow_feed
    docs = await rss.collect({"source_id": "evil_feed", "url": FEED})
    _common.validate_url = real
    for d in docs:
        print(f"RawDocument url={d.url}\n  text: {d.text[:110]}")
    print(f"internal server requests: {hits}  ->  {'LEAKED' if hits else 'BLOCKED, never requested'}")

    print("\n=== validate_url on common SSRF targets ===")
    for u in ["http://127.0.0.1:8123/?query=SELECT+*+FROM+hive.claims", "http://169.254.169.254/latest/meta-data/", "http://localhost:8123/", "http://[::ffff:127.0.0.1]/", "http://10.0.0.5/", "file:///etc/passwd"]:
        try:
            await real(u); print(f"  ALLOWED  {u}")
        except _common.UnsafeURLError as e:
            print(f"  blocked  {u}\n           {e}")
asyncio.run(main())
