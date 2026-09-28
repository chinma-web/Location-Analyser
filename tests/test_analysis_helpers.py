"""
Tests for the pure analysis helpers in location.py.

These run with no API keys and no network: review cleaning, the heuristic
fake-review pre-pass, batch merging, and the JSON-repair logic.
"""
import json

import pytest

import location as L


def rv(text, rating=5, author="Ann", date="2025-01-01"):
    return {"author": author, "rating": rating, "text": text, "date": date, "likes": 0}


# ── _clean_reviews ────────────────────────────────────────────────────────────

def test_clean_reviews_drops_near_duplicates_but_keeps_distinct_ones():
    reviews = [
        rv("The food here was absolutely delicious and the staff were lovely"),
        rv("The food here was absolutely delicious and the staff were lovely"),
        rv("Parking is a nightmare, avoid on weekends"),
    ]
    cleaned = L._clean_reviews(reviews)
    assert len(cleaned) == 2
    assert cleaned[0]["text"].startswith("The food")
    assert cleaned[1]["text"].startswith("Parking")


def test_clean_reviews_keeps_reviews_that_merely_share_common_words():
    reviews = [
        rv("great coffee and a nice quiet atmosphere for working"),
        rv("terrible service, waited forty minutes for a cold sandwich"),
    ]
    assert len(L._clean_reviews(reviews)) == 2


def test_clean_reviews_preserves_order_and_handles_empty():
    assert L._clean_reviews([]) == []
    reviews = [rv("alpha bravo charlie"), rv("delta echo foxtrot"), rv("golf hotel india")]
    assert [r["text"] for r in L._clean_reviews(reviews)] == [r["text"] for r in reviews]


# ── _heuristic_checks ─────────────────────────────────────────────────────────

def test_heuristics_on_empty_input():
    out = L._heuristic_checks([])
    assert out["flags"] == ["No reviews to analyze"]


def test_heuristics_flag_suspicious_five_star_ratio():
    reviews = [rv(f"amazing place number {i}", rating=5) for i in range(20)]
    flags = " ".join(L._heuristic_checks(reviews)["flags"])
    assert "5-star ratio" in flags
    assert "same star rating" in flags


def test_heuristics_flag_review_bombing():
    reviews = [rv(f"terrible experience {i}", rating=1) for i in range(10)]
    flags = " ".join(L._heuristic_checks(reviews)["flags"])
    assert "1-star ratio" in flags


def test_heuristics_flag_low_author_diversity():
    reviews = [rv(f"nice spot number {i}", rating=r, author="SamePerson")
               for i, r in enumerate([5, 4, 3, 5, 4, 3, 5, 4, 2, 1])]
    flags = " ".join(L._heuristic_checks(reviews)["flags"])
    assert "author diversity" in flags


def test_heuristics_flag_small_samples():
    flags = " ".join(L._heuristic_checks([rv("ok", rating=4)] * 2)["flags"])
    assert "Too few reviews" in flags


def test_heuristics_do_not_flag_a_healthy_mix():
    texts = [
        "Lovely evening, the pasta was perfectly cooked and service was warm",
        "Decent but overpriced for what you get, would not rush back",
        "Staff were rude when we asked about the bill, disappointing",
        "Great cocktails though the music was far too loud for conversation",
        "Solid brunch spot, the eggs benedict is worth ordering",
        "Waited 40 minutes for a table despite having a booking",
        "Beautiful interior, friendly team, will definitely return soon",
        "Average food, nothing memorable but nothing offensive either",
        "Best tiramisu in the city, genuinely excellent dessert menu",
        "Too cramped and noisy, we left before dessert arrived",
    ]
    # Vary the dates too: identical dates legitimately trip the review-bombing check.
    reviews = [rv(t, rating=r, author=f"user{i}", date=f"2025-0{i % 9 + 1}-1{i % 9}")
               for i, (t, r) in enumerate(zip(texts, [5, 3, 2, 4, 4, 2, 5, 3, 5, 2]))]
    assert L._heuristic_checks(reviews)["flags"] == []


def test_heuristic_stats_are_accurate():
    reviews = [rv("good food", rating=5, author="a"), rv("bad food", rating=1, author="b")]
    stats = L._heuristic_checks(reviews)["stats"]
    assert stats["total_reviews"] == 2
    assert stats["avg_rating"] == 3.0
    assert stats["unique_authors"] == 2
    assert stats["five_star_pct"] == 0.5


# ── _merge_sentiment_batches ──────────────────────────────────────────────────

def test_merge_single_batch_is_a_passthrough():
    batch = {"sentiment_score": 0.5, "positive_keywords": ["tasty"]}
    assert L._merge_sentiment_batches([batch]) == batch


def test_merge_empty_input():
    assert L._merge_sentiment_batches([]) == {}


def test_merge_concatenates_per_review_and_dedupes_keywords():
    merged = L._merge_sentiment_batches([
        {"per_review": [{"id": "r1"}], "positive_keywords": ["tasty", "cheap"], "sentiment_score": 0.5},
        {"per_review": [{"id": "r2"}], "positive_keywords": ["tasty", "quick"], "sentiment_score": 0.5},
    ])
    assert [p["id"] for p in merged["per_review"]] == ["r1", "r2"]
    assert merged["positive_keywords"] == ["tasty", "cheap", "quick"]


def test_merge_accumulates_theme_frequency_and_evidence():
    merged = L._merge_sentiment_batches([
        {"themes": [{"name": "parking", "frequency": 2, "evidence_review_ids": ["r1"]}]},
        {"themes": [{"name": "parking", "frequency": 3, "evidence_review_ids": ["r1", "r9"]}]},
    ])
    theme = merged["themes"][0]
    assert theme["frequency"] == 5
    assert theme["evidence_review_ids"] == ["r1", "r9"]


def test_merge_sums_emotion_distribution():
    merged = L._merge_sentiment_batches([
        {"emotion_distribution": {"Happy": 2, "Angry": 1}},
        {"emotion_distribution": {"Happy": 3}},
    ])
    assert merged["emotion_distribution"]["Happy"] == 5
    assert merged["emotion_distribution"]["Angry"] == 1


def test_merge_averages_aspect_scores_and_sums_mentions():
    merged = L._merge_sentiment_batches([
        {"aspect_scores": {"service": {"score": 6.0, "reviews_mentioning": 2,
                                       "evidence_review_ids": ["r1"]}}},
        {"aspect_scores": {"service": {"score": 8.0, "reviews_mentioning": 3,
                                       "evidence_review_ids": ["r1", "r7"]}}},
    ])
    service = merged["aspect_scores"]["service"]
    assert service["score"] == 7.0
    assert service["reviews_mentioning"] == 5
    assert service["evidence_review_ids"] == ["r1", "r7"]


def test_merge_leaves_unmentioned_aspects_as_none():
    merged = L._merge_sentiment_batches([{"aspect_scores": {}}, {"aspect_scores": {}}])
    assert merged["aspect_scores"]["food_quality"]["score"] is None


@pytest.mark.parametrize("scores,label", [
    ([0.8, 0.9], "Positive"),
    ([-0.8, -0.6], "Negative"),
    ([0.05, -0.05], "Neutral"),
    ([0.3, 0.05], "Mixed"),
])
def test_merged_label_follows_merged_score(scores, label):
    merged = L._merge_sentiment_batches([{"sentiment_score": s} for s in scores])
    assert merged["overall_sentiment"] == label


def test_polarised_batches_are_mixed_not_neutral():
    """+0.9 and -0.6 average to +0.15, which used to be labelled 'Neutral'."""
    merged = L._merge_sentiment_batches(
        [{"sentiment_score": 0.9}, {"sentiment_score": -0.6}]
    )
    assert merged["overall_sentiment"] == "Mixed"
    assert merged["batch_score_spread"] == 1.5


# ── JSON repair in call_groq ──────────────────────────────────────────────────

class _FakeGroq:
    """Minimal stand-in for the Groq client returning a canned completion."""

    def __init__(self, content):
        payload = self
        self._content = content

        class _Message:
            def __init__(self, c): self.content = c

        class _Choice:
            def __init__(self, c): self.message = _Message(c)

        class _Completions:
            def create(self_inner, **kwargs):
                class _Res:
                    choices = [_Choice(payload._content)]
                return _Res()

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


@pytest.mark.parametrize("raw,expected", [
    ('{"a": 1}', {"a": 1}),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('Sure! Here you go:\n{"a": 1}\nHope that helps', {"a": 1}),
    ('<think>weighing it up</think>{"a": 1}', {"a": 1}),
])
def test_call_groq_recovers_json_from_messy_output(monkeypatch, raw, expected):
    monkeypatch.setattr(L, "get_groq", lambda: _FakeGroq(raw))
    assert L.call_groq("prompt") == expected


def test_call_groq_repairs_a_truncated_object(monkeypatch):
    monkeypatch.setattr(L, "get_groq", lambda: _FakeGroq('{"items": ["a", "b"'))
    assert L.call_groq("prompt") == {"items": ["a", "b"]}


def test_call_groq_returns_empty_dict_on_unrecoverable_output(monkeypatch):
    monkeypatch.setattr(L, "get_groq", lambda: _FakeGroq("no json at all here"))
    monkeypatch.setattr(L.time, "sleep", lambda *_: None)
    assert L.call_groq("prompt") == {}
