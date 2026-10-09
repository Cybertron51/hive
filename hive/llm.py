"""AkashML client. Interface is fixed; session A fills the implementation.

    result = await chat_json(model, system, user, schema_hint)
    -> LLMResult(data=dict | None, raw=str, prompt_tokens, completion_tokens, latency_ms, malformed=bool)
"""
from __future__ import annotations

import json
import time
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel

from hive.config import settings


class LLMResult(BaseModel):
    data: dict[str, Any] | None
    raw: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    malformed: bool = False


_client: AsyncOpenAI | None = None


def client() -> AsyncOpenAI:
    global _client
    if _client is None:
        if not settings.akashml_api_key:
            raise RuntimeError("AKASHML_API_KEY is not set")
        _client = AsyncOpenAI(api_key=settings.akashml_api_key, base_url=settings.akashml_base_url)
    return _client


def _extract_json(raw: str) -> dict[str, Any] | None:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:]
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def chat_json(
    model: str, system: str, user: str, schema_hint: str, temperature: float = 0.0, max_tokens: int = 1200
) -> LLMResult:
    started = time.perf_counter()
    resp = await client().chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}, "reasoning_effort": "low"},
        messages=[
            {"role": "system", "content": f"{system}\n\nRespond with one JSON object only, matching: {schema_hint}"},
            {"role": "user", "content": user},
        ],
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    raw = resp.choices[0].message.content or ""
    data = _extract_json(raw)
    usage = resp.usage
    return LLMResult(
        data=data,
        raw=raw,
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
        latency_ms=latency_ms,
        malformed=data is None,
    )
