"""Shared test configuration."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def _no_rate_limiting(monkeypatch):
    """
    Tests must never block on real quota budgets.

    The limiter is deliberately conservative (a single 70B sentiment call
    reserves ~6k of a 12k bucket), so without this a handful of call_groq tests
    would sit through minutes of refill waiting.
    """
    monkeypatch.setenv("RATE_LIMIT_DISABLED", "1")
    import ratelimit
    ratelimit.reset_limiters()
    yield
    ratelimit.reset_limiters()
