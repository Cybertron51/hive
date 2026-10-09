from __future__ import annotations

import re

from hive.models import ClaimStatus, InjectionEvent, JudgeVerdict, RawDocument

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
REASON_PRIMARY_OVERRIDE = "primary-source override: "

PRIMARY = "primary"
"""Source class for issuer-controlled or regulatory documents: filings, 8-Ks, newsrooms, press releases, IR pages."""

SECONDARY = "secondary"
"""Source class for third-party reporting: news, blogs, aggregators."""

PRIMARY_KINDS = frozenset({"edgar"})
"""Collector kinds whose documents are always primary sources."""

PRIMARY_SOURCE_ID = re.compile(r"newsroom|press|8-?k|edgar|filing|(?:^|[^a-z0-9])ir(?:$|[^a-z0-9])", re.I)
"""A source_id matching this names a company newsroom, press release, 8-K, filing or investor-relations feed."""

PRIMARY_URL = re.compile(r"sec\.gov/|/(?:newsroom|press-releases?|investors?|ir)/|8-k", re.I)
"""A document URL matching this points at a filing, newsroom, press-release or investor-relations page."""


def source_class(doc: RawDocument) -> str:
    if doc.kind in PRIMARY_KINDS or PRIMARY_SOURCE_ID.search(doc.source_id) or PRIMARY_URL.search(doc.url):
        return PRIMARY
    return SECONDARY


def primary_override(
    verdict: JudgeVerdict, reason: str, claim_class: str, contradicting_classes: list[str]
) -> tuple[JudgeVerdict, str]:
    if (
        verdict == JudgeVerdict.DISAGREE and claim_class == PRIMARY and contradicting_classes
        and all(c == SECONDARY for c in contradicting_classes)
    ):
        return JudgeVerdict.AGREE, REASON_PRIMARY_OVERRIDE + reason
    return verdict, reason


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
