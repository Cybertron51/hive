from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from hive.models import (
    AgentRun, Claim, ClaimStatus, Detector, InjectionEvent, JudgeVerdict, RawDocument, RunStatus, SourceTrust, new_id, now,
)
from hive.swarm import agents, policy
from hive.swarm.injection import detect
from hive.swarm.pricing import large_model, small_model

log = logging.getLogger(__name__)

MAX_EVIDENCE = 3
FLUSH_INTERVAL_S = 10.0


@dataclass
class SwarmResult:
    swarm_id: str
    runs: list[AgentRun] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    injection_events: list[InjectionEvent] = field(default_factory=list)
    trust: dict[str, float] = field(default_factory=dict)
    brief_inputs: list[dict[str, Any]] = field(default_factory=list)
    sink_errors: list[str] = field(default_factory=list)
    sink: Any = field(default=None, repr=False, compare=False)
    logged: set[str] = field(default_factory=set, repr=False, compare=False)


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


def _stream(result: SwarmResult, runs: list[AgentRun] = (), events: list[InjectionEvent] = ()) -> None:
    sink = result.sink
    if sink is None:
        return
    for fn, items, key in ((sink.log_run, runs, "run_id"), (sink.log_injection, events, "event_id")):
        for item in items:
            ident = getattr(item, key)
            if ident in result.logged:
                continue
            result.logged.add(ident)
            try:
                fn(item)
            except Exception as exc:
                msg = f"{fn.__name__}: {type(exc).__name__}: {exc}"
                result.sink_errors.append(msg[:300])
                log.warning("sink failed: %s", msg)


async def _flusher(result: SwarmResult, interval: float) -> None:
    flush = getattr(result.sink, "flush", None)
    if not callable(flush):
        return
    while True:
        await asyncio.sleep(interval)
        await _emit(lambda _: flush(), None, result)


def _canary_event(run: AgentRun, doc: RawDocument, output: dict) -> InjectionEvent:
    quote = str(output.get("injection_quote") or "injection_suspected=true")
    return InjectionEvent(
        swarm_id=run.swarm_id, run_id=run.run_id, doc_id=doc.doc_id, source_id=doc.source_id,
        detector=Detector.CANARY, pattern=f"canary:{run.role.value}", snippet=quote[:160], severity=0.8,
    )


def _blend(claim_conf: float, classifier_conf: float | None) -> float:
    return claim_conf if classifier_conf is None else min(claim_conf, classifier_conf)


async def _confirm_canary(state: _DocState, tripped: list[tuple[AgentRun, dict]], swarm_id: str, result: SwarmResult) -> None:
    if not tripped:
        return
    confirmed = policy.doc_injected(state.heuristic, False)
    if not confirmed:
        run, out = await agents.run_injection(state.doc, swarm_id, large_model())
        result.runs.append(run)
        confirmed = run.canary_tripped or run.status in (RunStatus.ERROR, RunStatus.MALFORMED)
        if run.canary_tripped:
            event = _canary_event(run, state.doc, out)
            result.injection_events.append(event)
            _stream(result, events=[event])
    if confirmed:
        state.canary = True
        events = [_canary_event(r, state.doc, out) for r, out in tripped]
        result.injection_events.extend(events)
        _stream(result, events=events)
        return
    for r, _ in tripped:
        r.status, r.injection_flag = RunStatus.OK, False


async def _process_doc(doc: RawDocument, swarm_id: str, sem: asyncio.Semaphore, result: SwarmResult) -> _DocState:
    state = _DocState(doc=doc, heuristic=detect(doc, swarm_id))
    result.injection_events.extend(state.heuristic)
    _stream(result, events=state.heuristic)
    async with sem:
        reader_run, reader_out = await agents.run_reader(doc, swarm_id, small_model())
        result.runs.append(reader_run)
        state.reader_run = reader_run
        state.claims = reader_out.get("claims", [])
        cls_run, cls_out = await agents.run_classifier(doc, state.claims, swarm_id, small_model())
        result.runs.append(cls_run)
        if cls_run.status in (RunStatus.OK, RunStatus.QUARANTINED):
            state.classifier_conf = cls_out.get("confidence")
        tripped = [(r, o) for r, o in ((reader_run, reader_out), (cls_run, cls_out)) if r.canary_tripped]
        await _confirm_canary(state, tripped, swarm_id, result)
    if state.injected:
        for run in (reader_run, cls_run):
            if run.status == RunStatus.OK:
                run.injection_flag = True
    await _reroute(state, swarm_id, sem, result)
    _stream(result, runs=[r for r in result.runs if r.doc_id == doc.doc_id])
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
    await _confirm_canary(state, [(run, out)] if run.canary_tripped else [], swarm_id, result)
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
    state: _DocState, c: dict, states: list[_DocState], swarm_id: str, sem: asyncio.Semaphore, result: SwarmResult,
    source_trust: dict[str, float],
) -> Claim:
    confidence = _blend(c["confidence"], state.classifier_conf)
    verdict, reason = JudgeVerdict.NA, ""
    status = policy.decide(confidence, state.injected, verdict)
    if not state.injected and confidence >= policy.MIN_CONFIDENCE:
        payload = {k: c[k] for k in ("entity", "claim_type", "text", "value")}
        evidence = _evidence_for(state, c["entity"], states)
        fallback = "no corroborating documents"
        if evidence:
            async with sem:
                run, out = await agents.run_judge(payload, evidence, swarm_id, large_model(), state.doc)
            result.runs.append(run)
            _stream(result, runs=[run])
            if run.status == RunStatus.OK:
                verdict, reason = JudgeVerdict(out["verdict"]), policy.REASON_CORROBORATED + out["reason"]
                picked = out.get("contradicting") or range(1, len(evidence) + 1)
                verdict, reason = policy.primary_override(
                    verdict, reason, policy.source_class(state.doc), [policy.source_class(evidence[i - 1]) for i in picked],
                )
                fallback = "evidence silent"
            else:
                fallback = f"judge {run.status.value}"
        if verdict != JudgeVerdict.NA:
            status = policy.decide(confidence, state.injected, verdict)
        else:
            verdict, reason, status = await _ground_claim(state, payload, confidence, fallback, swarm_id, sem, result, source_trust)
    return Claim(
        run_id=c.get("reader_run_id") or (state.reader_run.run_id if state.reader_run else new_id()),
        doc_id=state.doc.doc_id, source_id=state.doc.source_id, entity=c["entity"], claim_type=c["claim_type"],
        text=c["text"], value=c["value"], confidence=confidence, status=status,
        judge_verdict=verdict, judge_reason=reason, updated_at=now(),
    )


async def _ground_claim(
    state: _DocState, payload: dict, confidence: float, fallback: str, swarm_id: str, sem: asyncio.Semaphore,
    result: SwarmResult, source_trust: dict[str, float],
) -> tuple[JudgeVerdict, str, ClaimStatus]:
    async with sem:
        run, out = await agents.run_grounding(payload, state.doc, swarm_id, large_model())
    result.runs.append(run)
    _stream(result, runs=[run])
    if run.status != RunStatus.OK:
        status = policy.decide(confidence, state.injected, JudgeVerdict.NA)
        return JudgeVerdict.NA, f"{fallback}; grounding {run.status.value}: {run.error}"[:300], status
    verdict = JudgeVerdict(out["verdict"])
    status = policy.decide_grounded(confidence, state.injected, verdict, source_trust.get(state.doc.source_id, 1.0))
    if status == ClaimStatus.VERIFIED:
        prefix = policy.REASON_GROUNDED
    elif verdict == JudgeVerdict.DISAGREE:
        prefix = policy.REASON_UNGROUNDED
    else:
        prefix = f"{fallback}; grounding {verdict.value}: "
    return verdict, prefix + out["reason"], status


def _injection_trust(states: list[_DocState], result: SwarmResult) -> dict[str, float]:
    return {
        src: policy.trust_score([e for e in result.injection_events if e.source_id == src], 0)
        for src in {s.doc.source_id for s in states}
    }


def _trust(states: list[_DocState], result: SwarmResult) -> dict[str, float]:
    sources = {s.doc.source_id for s in states}
    return {
        src: policy.trust_score(
            [e for e in result.injection_events if e.source_id == src],
            sum(
                1 for c in result.claims
                if c.source_id == src and c.judge_verdict == JudgeVerdict.DISAGREE
                and c.judge_reason.startswith(policy.REASON_CORROBORATED)
            ),
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


def _load_sink() -> Any:
    try:
        from hive import telemetry
    except ImportError as exc:
        log.warning("telemetry unavailable: %s", exc)
        return None
    return telemetry


async def _log_telemetry(result: SwarmResult) -> None:
    telemetry = result.sink
    if telemetry is None:
        return
    _stream(result, runs=result.runs, events=result.injection_events)
    for claim in result.claims:
        await _emit(telemetry.log_claim, claim, result)
    for src, score in result.trust.items():
        await _emit(telemetry.upsert_trust, SourceTrust(source_id=src, trust=score), result)
    flush = getattr(telemetry, "flush", None)
    if callable(flush):
        await _emit(lambda _: flush(), None, result)


def _brief_inputs(result: SwarmResult, docs: dict[str, RawDocument], tracked: dict[str, bool]) -> list[dict[str, Any]]:
    return [
        {
            "claim_id": c.claim_id, "entity": c.entity, "claim_type": c.claim_type, "text": c.text, "value": c.value,
            "confidence": c.confidence, "source_id": c.source_id, "url": docs[c.doc_id].url,
            "trust": result.trust.get(c.source_id, 1.0), "senso_node_id": c.senso_node_id,
            "tracked": tracked.get(c.claim_id, True),
        }
        for c in result.claims if c.status == ClaimStatus.VERIFIED
    ]


async def run_swarm(
    docs: list[RawDocument],
    swarm_id: str | None = None,
    concurrency: int = 16,
    telemetry: bool = True,
    ingest: bool = True,
) -> SwarmResult:
    result = SwarmResult(swarm_id=swarm_id or new_id(), sink=_load_sink() if telemetry else None)
    flusher = asyncio.create_task(_flusher(result, FLUSH_INTERVAL_S)) if result.sink is not None else None
    try:
        return await _run(docs, result, concurrency, ingest)
    finally:
        if flusher is not None:
            flusher.cancel()
            try:
                await flusher
            except asyncio.CancelledError:
                pass


async def _run(docs: list[RawDocument], result: SwarmResult, concurrency: int, ingest: bool) -> SwarmResult:
    sem = asyncio.Semaphore(max(1, concurrency))
    states = list(await asyncio.gather(*(_process_doc(d, result.swarm_id, sem, result) for d in docs)))
    pairs = [(s, c) for s in states for c in s.claims]
    pre_trust = _injection_trust(states, result)
    result.claims = list(await asyncio.gather(
        *(_judge_claim(s, c, states, result.swarm_id, sem, result, pre_trust) for s, c in pairs)
    ))
    tracked = {claim.claim_id: bool(c.get("tracked", True)) for (_, c), claim in zip(pairs, result.claims)}
    result.trust = _trust(states, result)
    by_id = {d.doc_id: d for d in docs}
    if ingest:
        await _ingest_verified(result, {k: d.url for k, d in by_id.items()})
    result.brief_inputs = _brief_inputs(result, by_id, tracked)
    await _log_telemetry(result)
    return result
