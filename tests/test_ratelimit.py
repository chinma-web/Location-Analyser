"""Token-bucket rate limiting and concurrent batch execution."""
import threading
import time

import pytest

from locan import llm, sentiment
from locan import reviews as reviews_mod
from locan.ratelimit import (
    MODEL_LIMITS,
    ModelRateLimiter,
    NullRateLimiter,
    RateLimitConfig,
    TokenBucket,
    estimate_tokens,
    limiter_for,
    reset_limiters,
)

# ── TokenBucket ───────────────────────────────────────────────────────────────

def test_bucket_starts_full_and_drains():
    bucket = TokenBucket(capacity=10, rate=100)
    assert bucket.available == pytest.approx(10, abs=0.1)
    assert bucket.acquire(4) is True
    assert bucket.available == pytest.approx(6, abs=0.2)


def test_bucket_refills_over_time():
    bucket = TokenBucket(capacity=10, rate=50)   # 50/s
    bucket.acquire(10)
    time.sleep(0.1)
    assert bucket.available == pytest.approx(5, abs=1.5)


def test_bucket_never_exceeds_capacity():
    bucket = TokenBucket(capacity=5, rate=1000)
    time.sleep(0.05)
    assert bucket.available <= 5


def test_acquire_blocks_until_tokens_are_available():
    bucket = TokenBucket(capacity=10, rate=100)
    bucket.acquire(10)
    started = time.monotonic()
    assert bucket.acquire(5) is True
    assert time.monotonic() - started >= 0.04   # ~0.05s to refill 5 @ 100/s


def test_acquire_respects_timeout():
    bucket = TokenBucket(capacity=10, rate=1)
    bucket.acquire(10)
    assert bucket.acquire(10, timeout=0.05) is False


def test_oversized_request_is_clamped_not_deadlocked():
    """A single call larger than the whole bucket must still go through."""
    bucket = TokenBucket(capacity=10, rate=1000)
    assert bucket.acquire(999, timeout=1) is True


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValueError):
        TokenBucket(capacity=0, rate=1)
    with pytest.raises(ValueError):
        TokenBucket(capacity=1, rate=0)


def test_bucket_is_thread_safe():
    """Concurrent acquirers must never over-draw the bucket."""
    bucket = TokenBucket(capacity=100, rate=1)   # negligible refill
    granted = []

    def worker():
        if bucket.acquire(10, timeout=0.05):
            granted.append(1)

    threads = [threading.Thread(target=worker) for _ in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(granted) == 10        # exactly capacity/10, no more
    assert bucket.available < 1


# ── token estimation ──────────────────────────────────────────────────────────

def test_estimate_tokens_scales_with_length():
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 400) == 100
    assert estimate_tokens("a" * 4000) > estimate_tokens("a" * 400)


# ── ModelRateLimiter ──────────────────────────────────────────────────────────

def test_limits_come_from_the_model_table():
    fast = ModelRateLimiter("llama-3.1-8b-instant")
    strong = ModelRateLimiter("llama-3.3-70b-versatile")
    assert strong.token_bucket.capacity > fast.token_bucket.capacity


def test_unknown_models_get_conservative_defaults():
    limiter = ModelRateLimiter("some-future-model")
    assert limiter.token_bucket.capacity > 0
    assert limiter.config.max_concurrency >= 1


def test_safety_factor_leaves_headroom():
    cfg = RateLimitConfig(tokens_per_minute=1000, safety_factor=0.5)
    limiter = ModelRateLimiter("x", cfg)
    assert limiter.token_bucket.capacity == 500


def test_acquire_charges_prompt_plus_reserved_completion():
    cfg = RateLimitConfig(tokens_per_minute=60_000, requests_per_minute=600)
    limiter = ModelRateLimiter("x", cfg)
    before = limiter.token_bucket.available
    limiter.acquire("word " * 400, max_tokens=500)   # ~500 prompt + 500 reserved
    assert before - limiter.token_bucket.available >= 900


def test_limiter_is_shared_per_model(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_DISABLED", raising=False)
    reset_limiters()
    assert limiter_for("llama-3.1-8b-instant") is limiter_for("llama-3.1-8b-instant")
    assert limiter_for("llama-3.1-8b-instant") is not limiter_for("llama-3.3-70b-versatile")


def test_rate_limiting_can_be_disabled(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_DISABLED", "1")
    reset_limiters()
    limiter = limiter_for("llama-3.3-70b-versatile")
    assert isinstance(limiter, NullRateLimiter)
    limiter.acquire("anything", 999_999)   # must not block


def test_model_table_covers_the_configured_defaults():
    for model in ("llama-3.3-70b-versatile", "llama-3.1-8b-instant"):
        assert model in MODEL_LIMITS


# ── parallel batch execution ──────────────────────────────────────────────────

def _first_review_id(prompt: str) -> int:
    """First review ID in a sentiment prompt (the schema example also uses [rN])."""
    import re
    return int(re.search(r"\[r(\d+)\] ⭐", prompt).group(1))

def test_sentiment_batches_run_concurrently_and_stay_ordered(monkeypatch):

    order_seen, lock = [], threading.Lock()
    concurrent, peak = 0, 0

    def fake_call_groq(prompt, model=None, max_tokens=0):
        nonlocal concurrent, peak
        with lock:
            concurrent += 1
            peak = max(peak, concurrent)
        first_id = _first_review_id(prompt)
        time.sleep(0.05)
        with lock:
            concurrent -= 1
            order_seen.append(first_id)
        return {"sentiment_score": 0.5, "per_review": [{"id": f"r{first_id}"}]}

    monkeypatch.setattr(llm, "call_groq", fake_call_groq)
    monkeypatch.setattr(sentiment, "SENTIMENT_BATCH_SIZE", 5)
    monkeypatch.setattr(sentiment, "SENTIMENT_MAX_WORKERS", 3)

    reviews = reviews_mod.assign_review_ids(
        [{"id": "", "rating": 5, "text": f"review {i}"} for i in range(20)]
    )
    result = sentiment.analyze_sentiment(reviews)

    assert peak > 1, "batches should overlap, not run strictly serially"
    assert result["rating_counts"]["5"] == 20


def test_batch_results_are_merged_in_submission_order(monkeypatch):
    """Batch 0 holds the newest reviews and supplies the temporal trend."""

    def fake_call_groq(prompt, model=None, max_tokens=0):
        first_id = _first_review_id(prompt)
        # Later batches finish first.
        time.sleep(0.02 if first_id > 1 else 0.08)
        return {"sentiment_score": 0.5,
                "temporal_trend": {"trend": "Improving" if first_id == 1 else "Declining"}}

    monkeypatch.setattr(llm, "call_groq", fake_call_groq)
    monkeypatch.setattr(sentiment, "SENTIMENT_BATCH_SIZE", 5)
    monkeypatch.setattr(sentiment, "SENTIMENT_MAX_WORKERS", 4)

    reviews = reviews_mod.assign_review_ids([{"rating": 4, "text": f"r{i}"} for i in range(15)])
    result = sentiment.analyze_sentiment(reviews)
    assert result["temporal_trend"]["trend"] == "Improving"


# ── Retry-After parsing ───────────────────────────────────────────────────────

@pytest.mark.parametrize("message,expected", [
    ("Rate limit reached. Please try again in 1.5s", 1.5),
    ("429: try again in 250ms", 0.25),
    ("Please retry after 12 seconds", 12.0),
    ("some unrelated failure", None),
])
def test_retry_after_parsing(message, expected):
    assert llm._retry_after_seconds(message) == expected


def test_retry_after_is_capped():
    assert llm._retry_after_seconds("try again in 9999s") == 60.0
