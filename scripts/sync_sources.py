#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import yaml

CONFIG = Path(__file__).resolve().parents[1] / "config" / "sources.yaml"


def lit(v: object) -> str:
    return "'" + str(v).replace("\\", "\\\\").replace("'", "\\'") + "'"


def main() -> None:
    doc = yaml.safe_load(CONFIG.read_text())
    sources = doc["sources"] if isinstance(doc, dict) else doc
    rows = [f"({lit(s['source_id'])}, {lit(s.get('kind', ''))}, {lit(s.get('tier', ''))})" for s in sources if s.get("source_id")]
    print("INSERT INTO hive.source_kinds (source_id, kind, tier) VALUES " + ", ".join(rows))


if __name__ == "__main__":
    main()
