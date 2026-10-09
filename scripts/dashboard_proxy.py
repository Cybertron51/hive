#!/usr/bin/env python3
from __future__ import annotations

import base64
import re
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from hive.config import settings

PORT = 8765
ALLOWED_ORIGIN = "http://localhost:8080"
MAX_BODY = 8192
READ_ONLY_SQL = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)

u = urlparse(settings.clickhouse_url)
secure = settings.clickhouse_secure or u.scheme == "https"
BASE = f"{'https' if secure else 'http'}://{u.hostname or 'localhost'}:{u.port or (8443 if secure else 8123)}/"
AUTH = "Basic " + base64.b64encode(f"{u.username or settings.clickhouse_user}:{u.password or settings.clickhouse_password}".encode()).decode()
QUERY_URL = BASE + "?readonly=1&default_format=JSON&database=" + settings.clickhouse_db


class Proxy(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self._send(204, b"")

    def do_POST(self) -> None:
        if self.path != "/query":
            return self._send(404, b'{"error":"not found"}')
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return self._send(413, b'{"error":"body size"}')
        sql = self.rfile.read(length).decode("utf-8", "replace")
        if not READ_ONLY_SQL.match(sql) or ";" in sql.rstrip().rstrip(";"):
            return self._send(400, b'{"error":"only a single SELECT is allowed"}')
        req = urllib.request.Request(QUERY_URL, data=sql.encode(), headers={"Authorization": AUTH}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                self._send(resp.status, resp.read())
        except urllib.error.HTTPError as exc:
            self._send(exc.code, exc.read()[:2000], "text/plain")
        except Exception as exc:
            self._send(502, f'{{"error":"upstream: {type(exc).__name__}"}}'.encode())

    def log_message(self, fmt: str, *args: object) -> None:
        pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Proxy)
    print(f"dashboard proxy on http://127.0.0.1:{PORT}/query -> {BASE}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
