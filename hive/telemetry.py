from __future__ import annotations

import atexit
import json
import logging
import threading
import time
from typing import Any
from urllib.parse import urlparse

import clickhouse_connect

from hive.config import settings
from hive.models import AgentRun, Claim, InjectionEvent, SourceTrust

log = logging.getLogger("hive.telemetry")

FLUSH_AT = 50
MAX_BUFFER = 5000
RETRY_AFTER_S = 5.0

COLUMNS: dict[str, list[str]] = {
    "agent_runs": [
        "run_id", "ts", "swarm_id", "role", "model", "doc_id", "source_id",
        "latency_ms", "prompt_tokens", "completion_tokens", "cost_usd",
        "confidence", "label", "status", "injection_flag", "canary_tripped",
        "judge_verdict", "error", "output",
    ],
    "claims": [
        "claim_id", "run_id", "doc_id", "source_id", "entity", "claim_type",
        "text", "value", "confidence", "status", "judge_verdict",
        "judge_reason", "senso_node_id", "created_at",
    ],
    "injection_events": [
        "event_id", "ts", "swarm_id", "run_id", "doc_id", "source_id",
        "detector", "pattern", "snippet", "severity",
    ],
    "source_trust": ["source_id", "trust", "updated_at"],
}

_lock = threading.Lock()
_buffers: dict[str, list[list[Any]]] = {t: [] for t in COLUMNS}
_client: Any = None
_down_until = 0.0


def _get_client() -> Any:
    global _client, _down_until
    if _client is not None:
        return _client
    if time.monotonic() < _down_until:
        return None
    try:
        u = urlparse(settings.clickhouse_url)
        _client = clickhouse_connect.get_client(
            host=u.hostname or "localhost",
            port=u.port or (8443 if u.scheme == "https" else 8123),
            secure=u.scheme == "https",
            username=u.username or "default",
            password=u.password or "",
            database=settings.clickhouse_db,
            connect_timeout=2,
            send_receive_timeout=10,
        )
    except Exception as exc:
        log.warning("clickhouse unavailable: %s", exc)
        _down_until = time.monotonic() + RETRY_AFTER_S
        return None
    return _client


def _mark_down(exc: Exception) -> None:
    global _client, _down_until
    log.warning("clickhouse error, dropping batch: %s", exc)
    _client = None
    _down_until = time.monotonic() + RETRY_AFTER_S


def _enqueue(table: str, row: list[Any]) -> None:
    with _lock:
        buf = _buffers[table]
        buf.append(row)
        if len(buf) > MAX_BUFFER:
            del buf[: len(buf) - MAX_BUFFER]
        full = len(buf) >= FLUSH_AT
    if full:
        flush()


def log_run(run: AgentRun) -> None:
    try:
        _enqueue("agent_runs", [
            run.run_id, run.ts, run.swarm_id, str(run.role), run.model,
            run.doc_id, run.source_id, run.latency_ms, run.prompt_tokens,
            run.completion_tokens, run.cost_usd, run.confidence, run.label,
            str(run.status), int(run.injection_flag), int(run.canary_tripped),
            str(run.judge_verdict), run.error, json.dumps(run.output, default=str),
        ])
    except Exception as exc:
        log.warning("log_run dropped: %s", exc)


def log_claim(claim: Claim) -> None:
    try:
        _enqueue("claims", [
            claim.claim_id, claim.run_id, claim.doc_id, claim.source_id,
            claim.entity, claim.claim_type, claim.text, claim.value,
            claim.confidence, str(claim.status), str(claim.judge_verdict),
            claim.judge_reason, claim.senso_node_id, claim.created_at,
        ])
    except Exception as exc:
        log.warning("log_claim dropped: %s", exc)


def log_injection(ev: InjectionEvent) -> None:
    try:
        _enqueue("injection_events", [
            ev.event_id, ev.ts, ev.swarm_id, ev.run_id, ev.doc_id,
            ev.source_id, str(ev.detector), ev.pattern, ev.snippet, ev.severity,
        ])
    except Exception as exc:
        log.warning("log_injection dropped: %s", exc)


def upsert_trust(t: SourceTrust) -> None:
    try:
        _enqueue("source_trust", [t.source_id, t.trust, t.updated_at])
    except Exception as exc:
        log.warning("upsert_trust dropped: %s", exc)


def flush() -> None:
    with _lock:
        pending = {t: rows for t, rows in _buffers.items() if rows}
        for t in pending:
            _buffers[t] = []
    if not pending:
        return
    client = _get_client()
    if client is None:
        log.warning("clickhouse down, dropped %d rows", sum(map(len, pending.values())))
        return
    for table, rows in pending.items():
        try:
            client.insert(table, rows, column_names=COLUMNS[table])
        except Exception as exc:
            _mark_down(exc)
            return


def query(sql: str) -> list[dict[str, Any]]:
    client = _get_client()
    if client is None:
        return []
    try:
        return list(client.query(sql).named_results())
    except Exception as exc:
        _mark_down(exc)
        return []


atexit.register(flush)
