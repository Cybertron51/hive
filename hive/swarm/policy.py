from __future__ import annotations

from hive.models import ClaimStatus, InjectionEvent, JudgeVerdict

QUARANTINE_SEVERITY = 0.5
MIN_CONFIDENCE = 0.6
VERIFY_CONFIDENCE = 0.75
TRUST_PER_INJECTION = 0.3
TRUST_PER_DISAGREE = 0.15


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


def trust_score(injection_events: int, disagrees: int) -> float:
    return max(0.0, round(1.0 - TRUST_PER_INJECTION * injection_events - TRUST_PER_DISAGREE * disagrees, 4))
