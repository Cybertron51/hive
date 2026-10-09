from __future__ import annotations

import asyncio
import ipaddress
import os
import socket
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
import lxml.html

ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = ROOT / "fixtures"
TIMEOUT = httpx.Timeout(15.0, connect=5.0)
MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
ALLOWED_SCHEMES = {"http", "https"}
USER_AGENT = os.environ.get("HIVE_USER_AGENT", "HiveResearchBot/0.1 (hackathon research; +https://hive.example)")

HTML_PARSER = lxml.html.HTMLParser(no_network=True, huge_tree=False, remove_comments=False)


class UnsafeURLError(ValueError):
    pass


class ResponseTooLargeError(ValueError):
    pass


def _ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or not ip.is_global
    )


async def validate_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise UnsafeURLError(f"scheme not allowed: {parts.scheme!r}")
    host = parts.hostname
    if not host:
        raise UnsafeURLError("missing host")
    if parts.username or parts.password:
        raise UnsafeURLError("credentials in URL not allowed")
    try:
        port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
    except ValueError as e:
        raise UnsafeURLError(f"bad port: {e}") from e
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise UnsafeURLError(f"cannot resolve {host!r}: {e}") from e
    if not infos:
        raise UnsafeURLError(f"no addresses for {host!r}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%", 1)[0])
        if _ip_blocked(ip):
            raise UnsafeURLError(f"{host!r} resolves to non-public address {ip}")
    return url


def make_client(**headers: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=TIMEOUT,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT, **headers},
        limits=httpx.Limits(max_connections=10),
    )


async def safe_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict | None = None,
    allowed_hosts: set[str] | None = None,
    max_bytes: int = MAX_BYTES,
    truncate: bool = False,
) -> tuple[str, bytes, str]:
    """GET with scheme/IP validation on every redirect hop and a body size cap.
    With truncate=True an oversized body is cut at max_bytes instead of raising.
    Returns (final_url, body, content_type)."""
    for _ in range(MAX_REDIRECTS + 1):
        await validate_url(url)
        if allowed_hosts is not None and (urlsplit(url).hostname or "").lower() not in allowed_hosts:
            raise UnsafeURLError(f"host not allowed: {urlsplit(url).hostname!r}")
        async with client.stream("GET", url, params=params) as resp:
            if resp.is_redirect:
                location = resp.headers.get("location", "")
                if not location:
                    raise httpx.HTTPStatusError("redirect without location", request=resp.request, response=resp)
                url, params = urljoin(str(resp.url), location), None
                continue
            resp.raise_for_status()
            declared = resp.headers.get("content-length", "")
            if not truncate and declared.isdigit() and int(declared) > max_bytes:
                raise ResponseTooLargeError(f"content-length {declared} exceeds {max_bytes}")
            buf = bytearray()
            async for chunk in resp.aiter_bytes():
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    if truncate:
                        del buf[max_bytes:]
                        break
                    raise ResponseTooLargeError(f"body exceeds {max_bytes} bytes")
            return str(resp.url), bytes(buf), resp.headers.get("content-type", "")
    raise UnsafeURLError(f"too many redirects (> {MAX_REDIRECTS})")


def decode(body: bytes, content_type: str) -> str:
    charset = "utf-8"
    for part in content_type.split(";"):
        k, _, v = part.strip().partition("=")
        if k.lower() == "charset" and v:
            charset = v.strip('"\' ')
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def meta_published(html: str) -> datetime | None:
    try:
        root = lxml.html.document_fromstring(html, parser=HTML_PARSER)
    except Exception:
        return None
    for xp in (
        '//meta[@name="article:published_time"]/@content',
        '//meta[@property="article:published_time"]/@content',
        "//time/@datetime",
    ):
        vals = root.xpath(xp)
        if vals and (dt := parse_dt(vals[0])):
            return dt
    return None
