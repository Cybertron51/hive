#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from hive.swarm import policy

NAMES = [
    "QUARANTINE_SEVERITY", "TRUST_MIN_SEVERITY", "TRUST_PER_SEVERITY", "TRUST_PER_DISAGREE",
    "MIN_CONFIDENCE", "VERIFY_CONFIDENCE", "GROUNDING_MIN_TRUST",
]


def main() -> None:
    values = {n: getattr(policy, n) for n in NAMES}
    out = Path(__file__).resolve().parents[1] / "dashboard" / "thresholds.js"
    out.write_text("window.HIVE_POLICY = " + json.dumps(values, indent=2) + ";\n")
    print(f"{out}: {values}")


if __name__ == "__main__":
    main()
