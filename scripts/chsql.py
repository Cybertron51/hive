#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from hive import telemetry


def statements(text: str) -> list[str]:
    return [s.strip() for s in re.split(r";[ \t]*(?:\n|$)", text) if s.strip()]


def main() -> int:
    ap = argparse.ArgumentParser(description="Run SQL against the ClickHouse in .env (local or Cloud)")
    ap.add_argument("-q", "--query", action="append", default=[], help="statement to run (repeatable)")
    ap.add_argument("--file", nargs="*", default=[], help="SQL files, run statement by statement")
    ap.add_argument("--format", default=None, help="output format for queries that return rows, e.g. PrettyCompact")
    ap.add_argument("--db", default="default", help="database to connect to (default: default)")
    args = ap.parse_args()

    stmts = list(args.query)
    for f in args.file:
        stmts += statements(Path(f).read_text())
    if not stmts:
        ap.error("nothing to run")

    try:
        client = telemetry.connect(args.db)
    except Exception as exc:
        print(f"connect failed: {exc}", file=sys.stderr)
        return 2
    for sql in stmts:
        try:
            returns_rows = re.match(r"\s*(SELECT|SHOW|DESCRIBE|WITH|EXISTS)\b", sql, re.I) is not None
            if returns_rows:
                out = client.raw_query(sql, fmt=args.format or "TabSeparated")
                sys.stdout.write(out.decode("utf-8", "replace"))
            else:
                client.command(sql)
        except Exception as exc:
            print(f"statement failed: {sql[:80]!r}: {exc}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
