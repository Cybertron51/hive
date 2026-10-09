from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from hive.models import (
    AgentRun, Claim, ClaimStatus, Detector, InjectionEvent, JudgeVerdict, RawDocument, RunStatus, SourceTrust, new_id,
)
from hive.swarm import agents, policy
from hive.swarm.injection import detect
from hive.swarm.pricing import large_model, small_model

log = logging.getLogger(__name__)

MAX_EVIDENCE = 3


@dataclass
class SwarmResult:
    swarm_id: str
    runs: list[AgentRun] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    injection_events: list[InjectionEvent] = field(default_factory=list)
    trust: dict[str, float] = field(default_factory=dict)
    brief_inputs: list[dict[str, Any]] = field(default_factory=list)
    sink_errors: list[str] = field(default_factory=list)


@dataclass
class _DocState:
    doc: RawDocument
    heuristic: list[InjectionEvent]
    reader_run: AgentRun | None = None
    claims: list[dict] = field(default_factory=list)
    classifier_conf: float | None = None
    canary: bool = False

    @property
    def injected(self) -> bool:
        return policy.doc_injected(self.heuristic, self.canary)


def _canary_event(run: AgentRun, doc: RawDocument, output: dict) -> InjectionEvent:
    quote = str(output.get("injection_quote") or "injection_suspected=true")
    return InjectionEvent(
        swarm_id=run.swarm_id, run_id=run.run_id, doc_id=doc.doc_id, source_id=doc.source_id,
        detector=Detector.CANARY, pattern=f"canary:{run.role.value}", snippet=quote[:160], severity=0.8,
    )


def _blend(claim_conf: float, classifier_conf: float | None) -> float:
    return claim_conf if classifier_conf is None else min(claim_conf, classifier_conf)


async def _process_doc(doc: RawDocument, swarm_id: str, sem: asyncio.Semaphore, result: SwarmResult) -> _DocState:
    state = _DocState(doc=doc, heuristic=detect(doc, swarm_id))
    result.injection_events.extend(state.heuristic)
    async with sem:
        reader_run, reader_out = await agents.run_reader(doc, swarm_id, small_model())
        result.runs.append(reader_run)
        state.reader_run = reader_run
        state.claims = reader_out.get("claims", [])
        if reader_run.canary_tripped:
            state.canary = True
            result.injection_events.append(_canary_event(reader_run, doc, reader_out))
        cls_run, cls_out = await agents.run_classifier(doc, state.claims, swarm_id, small_model())
        result.runs.append(cls_run)
        if cls_run.status in (RunStatus.OK, RunStatus.QUARANTINED):
            state.classifier_conf = cls_out.get("confidence")
        if cls_run.canary_tripped:
            state.canary = True
            result.injection_events.append(_canary_event(cls_run, doc, cls_out))
    if state.injected:
        for run in (reader_run, cls_run):
            if run.status == RunStatus.OK:
                run.injection_flag = True
    return state


async def _reroute(state: _DocState, swarm_id: str, sem: asyncio.Semaphore, result: SwarmResult) -> None:
    needs = [c for c in state.claims if policy.should_reroute(_blend(c["confidence"], state.classifier_conf), state.injected)]
    if not needs:
        return
    if state.reader_run and state.reader_run.status == RunStatus.OK:
        state.reader_run.status = RunStatus.REROUTED
    async with sem:
        run, out = await agents.run_reader(state.doc, swarm_id, large_model())
    result.runs.append(run)
    if run.canary_tripped:
        state.canary = True
        result.injection_events.append(_canary_event(run, state.doc, out))
    if run.status not in (RunStatus.OK, RunStatus.QUARANTINED):
        return
    fresh = {(c["entity"].lower(), c["claim_type"]): c for c in out.get("claims", [])}
    for c in needs:
        match = fresh.get((c["entity"].lower(), c["claim_type"]))
        if match:
            c.update(match)
            c["reader_run_id"] = run.run_id


def _evidence_for(state: _DocState, entity: str, states: list[_DocState]) -> list[RawDocument]:
    key = entity.lower()
    docs = [
        s.doc for s in states
        if s is not state and not s.injected and key in f"{s.doc.title}\n{s.doc.text}".lower()
    ]
    return docs[:MAX_EVIDENCE]


async def _judge_claim(
    state: _DocState, c: dict, states: list[_DocState], swarm_id: str, sem: asyncio.Semaphore, result: SwarmResult
) -> Claim:
    confidence = _blend(c["confidence"], state.classifier_conf)
    verdict, reason = JudgeVerdict.NA, ""
    if not state.injected and confidence >= policy.MIN_CONFIDENCE:
        evidence = _evidence_for(state, c["entity"], states)
        if evidence:
            payload = {k: c[k] for k in ("entity", "claim_type", "text", "value")}
            async with sem:
                run, out = await agents.run_judge(payload, evidence, swarm_id, large_model(), state.doc)
            result.runs.append(run)
            if run.status == RunStatus.OK:
                verdict, reason = JudgeVerdict(out["verdict"]), out["reason"]
        else:
            reason = "no corroborating documents"
    status = policy.decide(confidence, state.injected, verdict)
    return Claim(
        run_id=c.get("reader_run_id") or (state.reader_run.run_id if state.reader_run else new_id()),
        doc_id=state.doc.doc_id, source_id=state.doc.source_id, entity=c["entity"], claim_type=c["claim_type"],
        text=c["text"], value=c["value"], confidence=confidence, status=status,
        judge_verdict=verdict, judge_reason=reason,
    )


def _trust(states: list[_DocState], result: SwarmResult) -> dict[str, float]:
    sources = {s.doc.source_id for s in states}
    return {
        src: policy.trust_score(
            sum(1 for e in result.injection_events if e.source_id == src),
            sum(1 for c in result.claims if c.source_id == src and c.judge_verdict == JudgeVerdict.DISAGREE),
        )
        for src in sorted(sources)
    }


async def _emit(fn: Callable[..., Any], arg: Any, result: SwarmResult) -> Any:
    try:
        out = fn(arg)
        return await out if inspect.isawaitable(out) else out
    except Exception as exc:
        msg = f"{getattr(fn, '__name__', fn)}: {type(exc).__name__}: {exc}"
        result.sink_errors.append(msg[:300])
        log.warning("sink failed: %s", msg)
        return None


def _node_id(resp: Any) -> str:
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        return str(resp.get("node_id") or resp.get("id") or resp.get("content_id") or "")
    return str(getattr(resp, "node_id", "") or getattr(resp, "id", "") or "")


async def _ingest_verified(result: SwarmResult, urls: dict[str, str]) -> None:
    try:
        from hive.senso.client import get_kb
    except ImportError:
        return
    try:
        kb = get_kb()
    except Exception as exc:
        result.sink_errors.append(f"get_kb: {type(exc).__name__}: {exc}"[:300])
        return
    for claim in result.claims:
        if claim.status == ClaimStatus.VERIFIED:
            url = urls.get(claim.doc_id, "")
            ingest = lambda c, url=url: kb.ingest_claim(c, source_url=url)
            claim.senso_node_id = _node_id(await _emit(ingest, claim, result))


async def _log_telemetry(result: SwarmResult) -> None:
    try:
        from hive import telemetry
    except ImportError:
        return
    for run in result.runs:
        await _emit(telemetry.log_run, run, result)
    for event in result.injection_events:
        await _emit(telemetry.log_injection, event, result)
    for claim in result.claims:
        await _emit(telemetry.log_claim, claim, result)
    for src, score in result.trust.items():
        await _emit(telemetry.upsert_trust, SourceTrust(source_id=src, trust=score), result)
    flush = getattr(telemetry, "flush", None)
    if callable(flush):
        await _emit(lambda _: flush(), None, result)


def _brief_inputs(result: SwarmResult, docs: dict[str, RawDocument]) -> list[dict[str, Any]]:
    return [
        {
            "claim_id": c.claim_id, "entity": c.entity, "claim_type": c.claim_type, "text": c.text, "value": c.value,
            "confidence": c.confidence, "source_id": c.source_id, "url": docs[c.doc_id].url,
            "trust": result.trust.get(c.source_id, 1.0), "senso_node_id": c.senso_node_id,
        }
        for c in result.claims if c.status == ClaimStatus.VERIFIED
    ]


async def run_swarm(
    docs: list[RawDocument],
    swarm_id: str | None = None,
    concurrency: int = 8,
    telemetry: bool = True,
    ingest: bool = True,
) -> SwarmResult:
    result = SwarmResult(swarm_id=swarm_id or new_id())
    sem = asyncio.Semaphore(max(1, concurrency))
    states = list(await asyncio.gather(*(_process_doc(d, result.swarm_id, sem, result) for d in docs)))
    await asyncio.gather(*(_reroute(s, result.swarm_id, sem, result) for s in states))
    result.claims = list(await asyncio.gather(*(
        _judge_claim(s, c, states, result.swarm_id, sem, result) for s in states for c in s.claims
    )))
    result.trust = _trust(states, result)
    by_id = {d.doc_id: d for d in docs}
    if ingest:
        await _ingest_verified(result, {k: d.url for k, d in by_id.items()})
    result.brief_inputs = _brief_inputs(result, by_id)
    if telemetry:
        await _log_telemetry(result)
    return result
