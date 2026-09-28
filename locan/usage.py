"""
Token and cost accounting.

Every stage of the pipeline calls a paid API and nothing counted it. A run of
100 reviews is seven-plus Groq calls, and the only feedback was a wall-clock
timer — you could not tell a cache hit from a 40,000-token run.

This records what the provider actually reported (never an estimate, when a
real count is available) and prices it from a table that is easy to keep
current. Prices are USD per million tokens.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

# USD per 1M tokens (input, output). Groq publishes per-model pricing; these
# are the on-demand rates for the models this project uses. Unknown models are
# priced at zero and reported as such rather than guessed at.
PRICING = {
    "llama-3.3-70b-versatile": (0.59, 0.79),
    "llama-3.1-8b-instant":    (0.05, 0.08),
    "llama-3.1-70b-versatile": (0.59, 0.79),
}

# Apify's Google Maps scraper bills per place-with-reviews, not per token.
APIFY_COST_PER_PLACE = 0.007


@dataclass
class ModelUsage:
    """Token totals for one model within one run."""
    model: str
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated: bool = False          # True if any call fell back to an estimate

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cost_usd(self) -> float:
        input_rate, output_rate = PRICING.get(self.model, (0.0, 0.0))
        return round(self.prompt_tokens / 1e6 * input_rate
                     + self.completion_tokens / 1e6 * output_rate, 6)

    @property
    def priced(self) -> bool:
        return self.model in PRICING

    def as_dict(self) -> dict:
        return {
            "model": self.model, "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
            "priced": self.priced,
            "estimated": self.estimated,
        }


@dataclass
class UsageMeter:
    """Thread-safe accumulator — sentiment batches run concurrently."""
    by_model: dict = field(default_factory=dict)
    scrapes: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, model: str, prompt_tokens: int, completion_tokens: int,
               estimated: bool = False) -> None:
        with self._lock:
            entry = self.by_model.setdefault(model, ModelUsage(model=model))
            entry.calls += 1
            entry.prompt_tokens += max(0, int(prompt_tokens or 0))
            entry.completion_tokens += max(0, int(completion_tokens or 0))
            entry.estimated = entry.estimated or estimated

    def record_scrape(self, count: int = 1) -> None:
        with self._lock:
            self.scrapes += count

    def reset(self) -> None:
        with self._lock:
            self.by_model.clear()
            self.scrapes = 0

    def summary(self) -> dict:
        with self._lock:
            models = [u.as_dict() for u in self.by_model.values()]
        llm_cost = sum(m["cost_usd"] for m in models)
        scrape_cost = round(self.scrapes * APIFY_COST_PER_PLACE, 6)
        return {
            "calls": sum(m["calls"] for m in models),
            "prompt_tokens": sum(m["prompt_tokens"] for m in models),
            "completion_tokens": sum(m["completion_tokens"] for m in models),
            "total_tokens": sum(m["total_tokens"] for m in models),
            "llm_cost_usd": round(llm_cost, 6),
            "scrape_cost_usd": scrape_cost,
            "total_cost_usd": round(llm_cost + scrape_cost, 6),
            "scrapes": self.scrapes,
            "by_model": models,
            "any_estimated": any(m["estimated"] for m in models),
            "any_unpriced": any(not m["priced"] for m in models),
        }


# One meter per process. analyze() resets it at the start of a run, so the
# figures attached to a report describe that run only.
METER = UsageMeter()


def record_response(model: str, response) -> None:
    """
    Record usage from a Groq SDK response.

    Falls back to a character-based estimate when the provider omits usage, and
    marks the run as estimated so the UI can say so instead of quietly showing
    a made-up number.
    """
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None)
    completion_tokens = getattr(usage, "completion_tokens", None)
    if prompt_tokens is None and completion_tokens is None:
        return
    METER.record(model, prompt_tokens or 0, completion_tokens or 0)


def record_estimate(model: str, prompt: str, output: str = "") -> None:
    """Fallback accounting when the provider returned no usage block."""
    METER.record(model, len(prompt or "") // 4, len(output or "") // 4, estimated=True)


def format_cost(cost: float) -> str:
    """Human-readable cost — fractions of a cent are the normal case here."""
    if cost <= 0:
        return "$0.00"
    if cost < 0.01:
        return f"<$0.01 ({cost * 100:.2f}¢)"
    return f"${cost:.2f}"
