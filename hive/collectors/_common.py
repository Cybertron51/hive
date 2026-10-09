from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import lxml.html

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT = 15.0
USER_AGENT = os.environ.get("HIVE_USER_AGENT", "HiveResearchBot/0.1 (hackathon research; +https://hive.example)")


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def meta_published(html: str) -> datetime | None:
    try:
        root = lxml.html.document_fromstring(html)
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
