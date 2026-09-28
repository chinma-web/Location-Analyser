"""Tokenisation, similarity, geocode caching, and URL-expansion safety."""
import pytest

from locan import geo
from locan import reviews as reviews_mod

# ── similarity primitives ─────────────────────────────────────────────────────

def test_jaccard_bounds():
    a, b = reviews_mod._tokenise("alpha bravo charlie"), reviews_mod._tokenise("alpha bravo charlie")
    assert reviews_mod._jaccard(a, b) == 1.0
    assert reviews_mod._jaccard(a, reviews_mod._tokenise("delta echo")) == 0.0
    assert reviews_mod._jaccard(frozenset(), a) == 0.0


def test_length_prefilter_matches_exact_jaccard():
    """The cheap size-ratio filter must never change the answer."""
    import random
    random.seed(11)
    vocab = [f"w{i}" for i in range(40)]
    for _ in range(300):
        a = frozenset(random.sample(vocab, random.randint(1, 20)))
        b = frozenset(random.sample(vocab, random.randint(1, 20)))
        for threshold in (0.55, 0.70):
            assert reviews_mod._similar(a, b, threshold) == (reviews_mod._jaccard(a, b) > threshold)


def test_similar_handles_empty_token_sets():
    assert reviews_mod._similar(frozenset(), reviews_mod._tokenise("hello"), 0.7) is False


# ── geocode caching ───────────────────────────────────────────────────────────

def test_photon_requests_are_cached(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(req.full_url)

        class _Resp:
            def read(self_inner): return b'{"features": []}'
            def __enter__(self_inner): return self_inner
            def __exit__(self_inner, *a): return False
        return _Resp()

    geo.clear_geocode_cache()
    monkeypatch.setattr(geo.urllib.request, "urlopen", fake_urlopen)

    geo._photon_request({"q": "Pune", "limit": 1})
    geo._photon_request({"q": "Pune", "limit": 1})
    geo._photon_request({"limit": 1, "q": "Pune"})    # same query, different key order
    assert len(calls) == 1, "identical geocode lookups should hit the network once"

    geo._photon_request({"q": "Mumbai", "limit": 1})
    assert len(calls) == 2


def test_cache_returns_independent_objects(monkeypatch):
    def fake_urlopen(req, timeout=None):
        class _Resp:
            def read(self_inner): return b'{"features": [{"a": 1}]}'
            def __enter__(self_inner): return self_inner
            def __exit__(self_inner, *a): return False
        return _Resp()

    geo.clear_geocode_cache()
    monkeypatch.setattr(geo.urllib.request, "urlopen", fake_urlopen)

    first = geo._photon_request({"q": "Delhi"})
    first["features"].append({"mutated": True})
    second = geo._photon_request({"q": "Delhi"})
    assert second["features"] == [{"a": 1}], "callers must not be able to poison the cache"


# ── URL expansion safety ──────────────────────────────────────────────────────

@pytest.mark.parametrize("url,allowed", [
    ("https://maps.app.goo.gl/abc123", True),
    ("https://www.google.com/maps/place/X", True),
    ("https://goo.gl/maps/xyz", True),
    ("https://evil.example.com/steal", False),
    ("http://169.254.169.254/latest/meta-data/", False),
    ("https://notgoogle.com/maps", False),
    ("https://google.com.evil.net/maps", False),
])
def test_host_allowlist(url, allowed):
    assert geo._host_allowed(url) is allowed


def test_expand_refuses_untrusted_hosts(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not make a request to a non-allowlisted host")

    monkeypatch.setattr(geo.urllib.request, "urlopen", boom)
    url = "http://169.254.169.254/latest/meta-data/"
    assert geo.expand_maps_url(url) == url


def test_expand_uses_head_not_get(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["method"] = req.get_method()

        class _Resp:
            url = "https://www.google.com/maps/place/Resolved"
            def __enter__(self_inner): return self_inner
            def __exit__(self_inner, *a): return False
        return _Resp()

    monkeypatch.setattr(geo.urllib.request, "urlopen", fake_urlopen)
    out = geo.expand_maps_url("https://maps.app.goo.gl/abc123")
    assert seen["method"] == "HEAD"
    assert out.endswith("Resolved")


def test_expand_rejects_a_redirect_that_leaves_the_allowlist(monkeypatch):
    def fake_urlopen(req, timeout=None):
        class _Resp:
            url = "https://evil.example.com/landing"
            def __enter__(self_inner): return self_inner
            def __exit__(self_inner, *a): return False
        return _Resp()

    monkeypatch.setattr(geo.urllib.request, "urlopen", fake_urlopen)
    original = "https://maps.app.goo.gl/abc123"
    assert geo.expand_maps_url(original) == original
