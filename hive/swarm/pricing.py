"""USD per 1M tokens for AkashML models. Unknown models fall back to an estimate by tier."""
from __future__ import annotations

from hive.config import settings

PRICES = {
    "meta-llama/Llama-3.3-70B-Instruct": {"input": 0.20, "output": 0.52},
    "Qwen/Qwen3.8-27B": {"input": 0.225, "output": 1.98},
    "openai/gpt-oss-120b": {"input": 0.037, "output": 0.187},
    "openai/gpt-oss-20b": {"input": 0.02, "output": 0.10},
}

TIER_ESTIMATE = {
    "small": {"input": 0.10, "output": 0.30},
    "large": {"input": 0.60, "output": 0.90},
}


def small_model() -> str:
    return settings.akashml_model_small or "small"


def large_model() -> str:
    return settings.akashml_model_large or "large"


def tier(model: str) -> str:
    return "large" if model == large_model() else "small"


def price(model: str) -> dict[str, float]:
    if model in PRICES:
        return PRICES[model]
    short = model.rsplit("/", 1)[-1].lower()
    return next((p for name, p in PRICES.items() if name.rsplit("/", 1)[-1].lower() == short), TIER_ESTIMATE[tier(model)])


def cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    p = price(model)
    return round((prompt_tokens * p["input"] + completion_tokens * p["output"]) / 1_000_000, 8)
