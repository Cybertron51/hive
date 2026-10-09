#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "chromium",
]
BASE_FLAGS = ["--headless=new", "--disable-gpu", "--hide-scrollbars", "--virtual-time-budget=6000"]


def find_chrome() -> str:
    env = os.environ.get("CHROME_BIN")
    if env:
        return env
    for c in CHROME_CANDIDATES:
        if os.path.isabs(c):
            if os.access(c, os.X_OK):
                return c
        else:
            for d in os.environ.get("PATH", "").split(os.pathsep):
                if os.access(os.path.join(d, c), os.X_OK):
                    return os.path.join(d, c)
    sys.exit("Chrome not found; set CHROME_BIN")


def page_height(chrome: str, url: str, width: int) -> int:
    proc = subprocess.run(
        [chrome, *BASE_FLAGS, f"--window-size={width},900", "--dump-dom", url],
        capture_output=True, text=True, timeout=90,
    )
    m = re.search(r'data-h="(\d+)"', proc.stdout)
    if not m:
        sys.exit(f"dashboard did not render at {url} (is it served and ClickHouse up?)")
    return int(m.group(1))


def main() -> None:
    ap = argparse.ArgumentParser(description="Full-page screenshot of the Hive dashboard")
    ap.add_argument("output", nargs="?", default="docs/screenshots/dashboard.png")
    ap.add_argument("--url", default="http://localhost:8080/")
    ap.add_argument("--width", type=int, default=1400)
    ap.add_argument("--all-swarms", action="store_true", help="turn the latest-swarm-only filter off")
    args = ap.parse_args()
    if args.all_swarms:
        args.url += ("&" if "?" in args.url else "?") + "latest=0"

    chrome = find_chrome()
    height = page_height(chrome, args.url, args.width)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [chrome, *BASE_FLAGS, f"--window-size={args.width},{height}", f"--screenshot={out.resolve()}", args.url],
        capture_output=True, timeout=90, check=True,
    )
    if not out.exists() or out.stat().st_size == 0:
        sys.exit("screenshot was not written")
    print(f"{out} ({args.width}x{height})")


if __name__ == "__main__":
    main()
