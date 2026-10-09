import asyncio

import pytest

from hive import heartbeat
from hive.swarm import competitors, fake

KEYS = {
    "ts", "heartbeat_id", "swarm_id", "interval_s", "docs_collected", "docs_new", "runs",
    "claims_verified", "claims_quarantined", "injections", "cost_usd", "duration_ms", "status",
}


def _tick(store, **kw):
    return asyncio.run(heartbeat.heartbeat_once(kinds={"fixture"}, seen=store, telemetry=False, ingest=False, **kw))


def test_second_tick_skips_seen_docs_and_reset_reprocesses(monkeypatch, tmp_path):
    fake.install(monkeypatch)
    store = heartbeat.SeenStore(path=tmp_path / "seen.json", use_telemetry=False)

    first = _tick(store)
    assert set(first) == KEYS
    if not first["docs_collected"]:
        pytest.skip("no fixture docs")
    assert first["docs_new"] == first["docs_collected"] and first["runs"] > 0 and first["status"] == "ok"

    second = _tick(store)
    assert second["docs_new"] == 0 and second["runs"] == 0 and second["status"] == "idle"

    third = _tick(store, reset_seen=True)
    assert third["docs_new"] == first["docs_collected"] and third["runs"] > 0


def test_run_forever_survives_tick_errors(monkeypatch, capsys):
    calls = []

    async def boom(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("collector exploded")

    monkeypatch.setattr(heartbeat, "heartbeat_once", boom)
    asyncio.run(heartbeat.run_forever(0, once=True, telemetry=False))
    assert calls and "collector exploded" in capsys.readouterr().err


def test_competitor_normalization():
    comps = competitors._entries({
        "live": [{"name": "CrowdStrike", "aliases": ["CrowdStrike Holdings", "CRWD"]}],
        "fixture": [{"name": "Sentinel Labs", "aliases": ["SentinelLabs"]}],
    })
    claims = [
        {"entity": "crwd", "text": "x"},
        {"entity": "Falcon Flex", "text": "CrowdStrike Holdings launched Falcon Flex."},
        {"entity": "Dr. Karen Liu", "text": "SentinelLabs appointed Dr. Karen Liu as CISO."},
        {"entity": "Acme", "text": "Acme raised $5M."},
    ]
    out = competitors.normalize_claims(claims, comps)
    assert [c["entity"] for c in out] == ["CrowdStrike", "CrowdStrike", "Sentinel Labs", "Acme"]
    assert [c["tracked"] for c in out] == [True, True, True, False]
    assert competitors.normalize_claims([{"entity": "Acme", "text": ""}], ())[0]["tracked"] is True
