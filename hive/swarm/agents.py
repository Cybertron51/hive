from __future__ import annotations

from typing import Any

from hive import llm
from hive.models import AgentRun, JudgeVerdict, RawDocument, Role, RunStatus
from hive.swarm import prompts
from hive.swarm.injection import canary_check
from hive.swarm.pricing import cost_usd, small_model, large_model


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


async def _call(role: Role, model: str, user: str, swarm_id: str, doc: RawDocument | None) -> tuple[AgentRun, dict]:
    run = AgentRun(
        swarm_id=swarm_id,
        role=role,
        model=model,
        doc_id=doc.doc_id if doc else "",
        source_id=doc.source_id if doc else "",
    )
    system, schema = prompts.SYSTEM[role.value], prompts.SCHEMA[role.value]
    data: dict | None = None
    for _attempt in range(2):
        try:
            result = await llm.chat_json(model, system, user, schema)
        except Exception as exc:
            run.status = RunStatus.ERROR
            run.error = f"{type(exc).__name__}: {exc}"[:500]
            return run, {}
        run.latency_ms += result.latency_ms
        run.prompt_tokens += result.prompt_tokens
        run.completion_tokens += result.completion_tokens
        if not result.malformed and result.data is not None:
            data = result.data
            break
        run.error = f"malformed: {result.raw[:200]}"
    run.cost_usd = cost_usd(model, run.prompt_tokens, run.completion_tokens)
    if data is None:
        run.status = RunStatus.MALFORMED
        return run, {}
    run.error = ""
    run.output = data
    run.canary_tripped = canary_check(data)
    run.injection_flag = run.canary_tripped
    if run.canary_tripped:
        run.status = RunStatus.QUARANTINED
    return run, data


def _clean_claims(data: dict) -> list[dict]:
    claims = data.get("claims")
    if not isinstance(claims, list):
        return []
    out = []
    for c in claims:
        if not isinstance(c, dict) or not c.get("entity") or not c.get("text"):
            continue
        out.append({
            "entity": str(c["entity"]).strip(),
            "claim_type": str(c.get("claim_type") or "other"),
            "text": str(c["text"]),
            "value": str(c.get("value") or ""),
            "confidence": _num(c.get("confidence")),
        })
    return out


async def run_reader(doc: RawDocument, swarm_id: str, model: str | None = None) -> tuple[AgentRun, dict]:
    run, data = await _call(Role.READER, model or small_model(), prompts.reader_user(doc.title, doc.url, doc.text), swarm_id, doc)
    if run.status in (RunStatus.ERROR, RunStatus.MALFORMED):
        return run, {"claims": []}
    claims = _clean_claims(data)
    parsed = {**data, "claims": claims}
    run.confidence = sum(c["confidence"] for c in claims) / len(claims) if claims else 0.0
    run.label = claims[0]["claim_type"] if claims else ""
    return run, parsed


async def run_classifier(doc: RawDocument, claims: list[dict], swarm_id: str, model: str | None = None) -> tuple[AgentRun, dict]:
    user = prompts.classifier_user(doc.title, doc.url, doc.text, claims)
    run, data = await _call(Role.CLASSIFIER, model or small_model(), user, swarm_id, doc)
    if run.status in (RunStatus.ERROR, RunStatus.MALFORMED):
        return run, {}
    label = str(data.get("label") or "other")
    parsed = {
        **data,
        "label": label if label in prompts.LABELS else "other",
        "relevance": _num(data.get("relevance")),
        "confidence": _num(data.get("confidence")),
    }
    run.label = parsed["label"]
    run.confidence = parsed["confidence"]
    return run, parsed


async def run_judge(
    claim: dict, evidence_docs: list[RawDocument], swarm_id: str, model: str | None = None, doc: RawDocument | None = None
) -> tuple[AgentRun, dict]:
    evidence = [(d.title, d.url, d.text) for d in evidence_docs[:3]]
    run, data = await _call(Role.JUDGE, model or large_model(), prompts.judge_user(claim, evidence), swarm_id, doc)
    if run.status in (RunStatus.ERROR, RunStatus.MALFORMED):
        return run, {"verdict": JudgeVerdict.NA.value, "reason": run.error, "confidence": 0.0}
    verdict = str(data.get("verdict") or "na").lower()
    if verdict not in {v.value for v in JudgeVerdict}:
        verdict = JudgeVerdict.NA.value
    parsed = {**data, "verdict": verdict, "reason": str(data.get("reason") or ""), "confidence": _num(data.get("confidence"))}
    run.judge_verdict = JudgeVerdict(verdict)
    run.confidence = parsed["confidence"]
    run.label = verdict
    return run, parsed


def scout(sources: list[str], entity: str, trust: dict[str, float] | None = None) -> dict:
    trust = trust or {}
    ranked = sorted(sources, key=lambda s: trust.get(s, 1.0), reverse=True)
    queries = [entity] + [f"{entity} {kind.replace('_', ' ')}" for kind in prompts.LABELS if kind != "other"]
    return {"queries": queries, "prioritized_sources": [s for s in ranked if trust.get(s, 1.0) > 0.0]}


async def run_injection(doc: RawDocument, swarm_id: str, model: str | None = None) -> tuple[AgentRun, dict]:
    run, data = await _call(Role.INJECTION, model or large_model(), prompts.reader_user(doc.title, doc.url, doc.text), swarm_id, doc)
    if run.status in (RunStatus.ERROR, RunStatus.MALFORMED):
        return run, {}
    run.confidence = _num(data.get("confidence"), 0.5)
    run.label = "injection" if run.canary_tripped else "clean"
    return run, data
