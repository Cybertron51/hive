from __future__ import annotations

from hive.models import ClaimStatus, InjectionEvent, JudgeVerdict

QUARANTINE_SEVERITY = 0.6
"""A heuristic injection event at or above this severity quarantines every claim from its document."""

TRUST_MIN_SEVERITY = 0.5
"""Only injection events at or above this severity reduce source trust."""

TRUST_PER_SEVERITY = 0.3
"""Trust penalty per counted injection event is this factor times the event severity."""

TRUST_PER_DISAGREE = 0.15
"""Trust penalty per claim the cross-document judge contradicted."""

MIN_CONFIDENCE = 0.6
"""Claims below this blended confidence are quarantined without judging."""

VERIFY_CONFIDENCE = 0.75
"""Claims need at least this confidence for the judge to verify them."""

GROUNDING_MIN_TRUST = 0.7
"""A single-source claim is verified by grounding only when its source trust is at least this."""

REASON_CORROBORATED = "corroborated: "
REASON_GROUNDED = "single-source grounded: "
REASON_UNGROUNDED = "ungrounded: "


def doc_injected(events: list[InjectionEvent], canary_tripped: bool) -> bool:
    return canary_tripped or any(e.severity >= QUARANTINE_SEVERITY for e in events)


def should_reroute(confidence: float, injected: bool) -> bool:
    return not injected and MIN_CONFIDENCE <= confidence < VERIFY_CONFIDENCE


def decide(confidence: float, injected: bool, verdict: JudgeVerdict) -> ClaimStatus:
    if injected or verdict == JudgeVerdict.DISAGREE or confidence < MIN_CONFIDENCE:
        return ClaimStatus.QUARANTINED
    if verdict == JudgeVerdict.AGREE and confidence >= VERIFY_CONFIDENCE:
        return ClaimStatus.VERIFIED
    return ClaimStatus.PENDING


def decide_grounded(confidence: float, injected: bool, verdict: JudgeVerdict, source_trust: float) -> ClaimStatus:
    if injected or verdict == JudgeVerdict.DISAGREE or confidence < MIN_CONFIDENCE:
        return ClaimStatus.QUARANTINED
    if verdict == JudgeVerdict.AGREE and confidence >= VERIFY_CONFIDENCE and source_trust >= GROUNDING_MIN_TRUST:
        return ClaimStatus.VERIFIED
    return ClaimStatus.PENDING


def injection_penalty(events: list[InjectionEvent]) -> float:
    worst: dict[tuple[str, str], float] = {}
    for e in events:
        if e.severity >= TRUST_MIN_SEVERITY:
            key = (e.doc_id, e.pattern)
            worst[key] = max(worst.get(key, 0.0), e.severity)
    return sum(TRUST_PER_SEVERITY * s for s in worst.values())


def trust_score(events: list[InjectionEvent], disagrees: int) -> float:
    return max(0.0, round(1.0 - injection_penalty(events) - TRUST_PER_DISAGREE * disagrees, 4))
