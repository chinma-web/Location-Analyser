"""
Thread-safe token-bucket rate limiting for the Groq API.

The whole config file is organised around Groq's quota buckets (TPM/TPD per
model), but nothing enforced them: batches were serialised with a flat
`time.sleep(1.2)` between calls, which is simultaneously too slow when the
quota is healthy and useless when several batches run concurrently.

A token bucket gives us both: parallel requests when there's headroom, and a
hard ceiling when there isn't.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass


class TokenBucket:
    """
    Classic token bucket. `capacity` tokens, refilled at `rate` tokens/second.

    Thread-safe and monotonic-clock based, so it is unaffected by system clock
    changes. `acquire()` blocks until enough tokens are available.
    """

    def __init__(self, capacity: float, rate: float, name: str = "bucket"):
        if capacity <= 0 or rate <= 0:
            raise ValueError("capacity and rate must be positive")
        self.capacity = float(capacity)
        self.rate = float(rate)
        self.name = name
        self._tokens = float(capacity)
        self._last = time.monotonic()
        self._lock = threading.Lock()
        self.total_waited = 0.0
        self.total_acquired = 0.0

    def _refill_locked(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._last = now

    @property
    def available(self) -> float:
        with self._lock:
            self._refill_locked()
            return self._tokens

    def acquire(self, tokens: float = 1.0, timeout: float | None = None) -> bool:
        """
        Block until `tokens` are available. Returns False if `timeout` expires.

        A request larger than the bucket capacity is clamped, so one oversized
        call can never deadlock the pipeline.
        """
        tokens = min(float(tokens), self.capacity)
        deadline = None if timeout is None else time.monotonic() + timeout
        started = time.monotonic()

        while True:
            with self._lock:
                self._refill_locked()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    self.total_acquired += tokens
                    self.total_waited += time.monotonic() - started
                    return True
                shortfall = tokens - self._tokens
                wait = shortfall / self.rate

            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                wait = min(wait, remaining)
            time.sleep(max(wait, 0.01))


@dataclass
class RateLimitConfig:
    """
    Per-model limits. Defaults mirror Groq's documented free-tier ceilings with
    headroom, since our token estimates are approximate.

    tokens_per_minute is the real constraint; requests_per_minute stops us from
    hammering the endpoint with many tiny calls.
    """
    tokens_per_minute: int = 6_000
    requests_per_minute: int = 30
    max_concurrency: int = 3
    safety_factor: float = 0.85     # only spend this share of the nominal quota


# Documented free-tier TPM per model, used to pick sensible defaults.
MODEL_LIMITS = {
    "llama-3.3-70b-versatile": RateLimitConfig(tokens_per_minute=14_400, requests_per_minute=30),
    "llama-3.1-8b-instant":    RateLimitConfig(tokens_per_minute=6_000,  requests_per_minute=30),
}
DEFAULT_LIMITS = RateLimitConfig()


def estimate_tokens(text: str) -> int:
    """
    Rough token count: ~4 characters per token for English prose.

    Deliberately crude — it only needs to be good enough to pace requests, and
    over-estimating is the safe direction.
    """
    return max(1, len(text) // 4)


class ModelRateLimiter:
    """Token + request buckets and a concurrency cap for a single model."""

    def __init__(self, model: str, config: RateLimitConfig | None = None):
        cfg = config or MODEL_LIMITS.get(model, DEFAULT_LIMITS)
        self.model = model
        self.config = cfg

        budget = cfg.tokens_per_minute * cfg.safety_factor
        self.token_bucket = TokenBucket(capacity=budget, rate=budget / 60.0,
                                        name=f"{model}:tokens")
        self.request_bucket = TokenBucket(capacity=cfg.requests_per_minute,
                                          rate=cfg.requests_per_minute / 60.0,
                                          name=f"{model}:requests")
        self.semaphore = threading.Semaphore(cfg.max_concurrency)

    def acquire(self, prompt: str, max_tokens: int = 0) -> None:
        """Block until this call fits inside both budgets."""
        cost = estimate_tokens(prompt) + max_tokens
        self.request_bucket.acquire(1)
        self.token_bucket.acquire(cost)

    def stats(self) -> dict:
        return {
            "model": self.model,
            "tokens_available": round(self.token_bucket.available),
            "seconds_waited": round(self.token_bucket.total_waited
                                    + self.request_bucket.total_waited, 2),
        }


class NullRateLimiter:
    """No-op limiter: used by tests and when RATE_LIMIT_DISABLED is set."""

    model = "disabled"

    def acquire(self, prompt: str, max_tokens: int = 0) -> None:
        return None

    def stats(self) -> dict:
        return {"model": "disabled", "tokens_available": None, "seconds_waited": 0.0}


_limiters: dict = {}
_limiters_lock = threading.Lock()


def rate_limiting_disabled() -> bool:
    return os.getenv("RATE_LIMIT_DISABLED", "").lower() in ("1", "true", "yes")


def limiter_for(model: str) -> ModelRateLimiter | NullRateLimiter:
    """
    Process-wide limiter per model, so concurrent batches share one budget.

    Set RATE_LIMIT_DISABLED=1 to bypass entirely — useful for paid Groq tiers
    with much higher ceilings, and for tests.
    """
    if rate_limiting_disabled():
        return NullRateLimiter()
    with _limiters_lock:
        if model not in _limiters:
            _limiters[model] = ModelRateLimiter(model)
        return _limiters[model]


def reset_limiters() -> None:
    """Test hook."""
    with _limiters_lock:
        _limiters.clear()
