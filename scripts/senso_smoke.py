"""Live Senso check: me -> ingest one claim -> wait for processing -> search + context.

    .venv/bin/python scripts/senso_smoke.py
"""
from __future__ import annotations

import asyncio
import sys
import time

from hive.config import settings
from hive.models import Claim
from hive.senso.client import SensoCreditsExhausted, SensoError, SensoKB

QUERY = "What did Hive Smoke Test Bio report about its phase 2 trial?"


async def main() -> int:
    if not settings.senso_api_key:
        print("SENSO_API_KEY is not set in .env")
        return 2
    kb = SensoKB(settings.senso_api_key, settings.senso_base_url)
    try:
        me = await kb.me()
        print(f"me: org={me.get('name')} slug={me.get('slug')} free_tier={me.get('is_free_tier')}")

        claim = Claim(
            run_id="smoke",
            doc_id="smoke",
            source_id="smoke",
            entity="Hive Smoke Test Bio",
            claim_type="trial_result",
            text=f"Hive Smoke Test Bio's phase 2 trial met its primary endpoint (smoke run {int(time.time())}).",
            value="met primary endpoint",
            confidence=0.95,
        )
        node_id = await kb.ingest_claim(claim, source_url="https://example.com/hive-smoke")
        print(f"ingest: kb_node_id={node_id or '(duplicate, 409)'}")

        started = time.monotonic()
        done = await kb.wait_processed(node_id, timeout=120)
        print(f"processed: {done} after {time.monotonic() - started:.1f}s")

        res = await kb.search(QUERY)
        print(f"search: total_results={res.get('total_results')} answer={str(res.get('answer'))[:200]!r}")

        passages = await kb.context(QUERY)
        print(f"context: {len(passages)} passages")
        for p in passages[:3]:
            print(f"  score={p.score:.3f} source={p.source_url} node={p.node_id} text={p.text[:100]!r}")
        return 0 if passages else 1
    except SensoCreditsExhausted as e:
        print(f"CREDITS EXHAUSTED: {e}")
        return 3
    except SensoError as e:
        print(f"SENSO ERROR: {e}")
        return 1
    finally:
        await kb.aclose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
