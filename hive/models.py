"""Shared data contracts. Every session codes against these; only session A edits this file."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid4().hex


class Role(StrEnum):
    SCOUT = "scout"
    READER = "reader"
    CLASSIFIER = "classifier"
    JUDGE = "judge"
    WRITER = "writer"
    INJECTION = "injection"


class RunStatus(StrEnum):
    OK = "ok"
    MALFORMED = "malformed"
    QUARANTINED = "quarantined"
    REROUTED = "rerouted"
    ERROR = "error"


class ClaimStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


class JudgeVerdict(StrEnum):
    AGREE = "agree"
    DISAGREE = "disagree"
    NA = "na"


class Detector(StrEnum):
    HEURISTIC = "heuristic"
    CANARY = "canary"
    JUDGE = "judge"
    CLASSIFIER = "classifier"


class RawDocument(BaseModel):
    doc_id: str = Field(default_factory=new_id)
    source_id: str
    url: str
    title: str = ""
    text: str
    published_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=now)
    kind: str = "page"


class Claim(BaseModel):
    claim_id: str = Field(default_factory=new_id)
    run_id: str
    doc_id: str
    source_id: str
    entity: str
    claim_type: str
    text: str
    value: str = ""
    confidence: float = 0.0
    status: ClaimStatus = ClaimStatus.PENDING
    judge_verdict: JudgeVerdict = JudgeVerdict.NA
    judge_reason: str = ""
    senso_node_id: str = ""
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)


class AgentRun(BaseModel):
    """One LLM call by one agent. Written to ClickHouse agent_runs."""
    run_id: str = Field(default_factory=new_id)
    ts: datetime = Field(default_factory=now)
    swarm_id: str
    role: Role
    model: str
    doc_id: str = ""
    source_id: str = ""
    latency_ms: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    confidence: float = 0.0
    label: str = ""
    status: RunStatus = RunStatus.OK
    injection_flag: bool = False
    canary_tripped: bool = False
    judge_verdict: JudgeVerdict = JudgeVerdict.NA
    error: str = ""
    output: dict[str, Any] = Field(default_factory=dict)


class InjectionEvent(BaseModel):
    event_id: str = Field(default_factory=new_id)
    ts: datetime = Field(default_factory=now)
    swarm_id: str
    run_id: str = ""
    doc_id: str
    source_id: str
    detector: Detector
    pattern: str
    snippet: str
    severity: float = 0.5


class SourceTrust(BaseModel):
    source_id: str
    trust: float = 1.0
    updated_at: datetime = Field(default_factory=now)
