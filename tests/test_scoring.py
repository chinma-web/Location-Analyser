"""
Tests for the deterministic scoring engine.

This is the one part of the pipeline that decides the verdict, so it gets the
tightest coverage: component maths, the missing-data policy, weight
renormalisation, penalties, thresholds, and monotonicity.
"""
import pytest

from scoring import (
    DEFAULT_CONFIG,
    ScoringConfig,
    aspect_component,
    consistency_component,
    data_sufficiency,
    rating_component,
    recency_component,
    risk_penalty,
    score_location,
    sentiment_component,
    trust_component,
    verdict_for,
)

PASS_VERIF = {"verification_status": "PASS", "accuracy": 0.9, "coverage": 1.0, "corrections": []}


def reviews(n, rating=5):
    return [{"id": f"r{i+1}", "rating": rating, "text": "x"} for i in range(n)]


# ── sentiment ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [(-1.0, 0.0), (0.0, 5.0), (1.0, 10.0), (0.5, 7.5)])
def test_sentiment_maps_to_0_10(raw, expected):
    assert sentiment_component({"sentiment_score": raw}) == expected


def test_sentiment_is_none_when_absent_and_clamps_out_of_range():
    assert sentiment_component({}) is None
    assert sentiment_component({"sentiment_score": "high"}) is None
    assert sentiment_component({"sentiment_score": 4.0}) == 10.0


# ── aspects ───────────────────────────────────────────────────────────────────

def test_aspect_component_is_weighted_by_configured_importance():
    sent = {"aspect_scores": {
        "food_quality": {"score": 10},   # weight 1.5
        "accessibility": {"score": 0},   # weight 0.5
    }}
    assert aspect_component(sent) == pytest.approx(7.5)


def test_unscored_aspects_are_excluded_not_defaulted():
    """The old engine fell back to 5.0/10, dragging sparse places to 'average'."""
    assert aspect_component({"aspect_scores": {}}) is None
    assert aspect_component({"aspect_scores": {"service": {"score": None}}}) is None
    assert aspect_component({"aspect_scores": {"service": {"score": 9}}}) == 9.0


# ── rating ────────────────────────────────────────────────────────────────────

def test_rating_prefers_google_score_then_sample_mean():
    assert rating_component({"google_score": 4.5}, []) == 9.0
    assert rating_component({}, reviews(4, rating=3)) == 6.0
    assert rating_component({}, []) is None


# ── trust ─────────────────────────────────────────────────────────────────────

def test_trust_returns_none_when_guardrail_said_nothing():
    assert trust_component({}, PASS_VERIF) is None


def test_missing_trust_is_neutral_not_optimistic():
    # Only fake-probability known: trust falls back to 0.5, not the old 0.7.
    comp = trust_component({"fake_review_probability": 0.0}, PASS_VERIF)
    assert comp == pytest.approx(5.0 * (0.5 + 0.9 * 0.5), abs=0.05)


def test_unverified_run_is_discounted_never_boosted():
    guard = {"trust_score": 0.9, "fake_review_probability": 0.0}
    verified   = trust_component(guard, PASS_VERIF)
    unverified = trust_component(guard, {"verification_status": "UNAVAILABLE", "accuracy": None})
    assert unverified < 9.0
    assert unverified == pytest.approx(9.0 * DEFAULT_CONFIG.unverified_trust_multiplier, abs=0.05)
    assert verified > unverified


def test_fake_probability_pulls_trust_down():
    clean   = trust_component({"trust_score": 0.9, "fake_review_probability": 0.0}, PASS_VERIF)
    suspect = trust_component({"trust_score": 0.9, "fake_review_probability": 0.8}, PASS_VERIF)
    assert suspect < clean


# ── consistency ───────────────────────────────────────────────────────────────

def test_consistency_rewards_agreement_and_needs_a_minimum_sample():
    agree    = {"per_review": [{"score": 0.8}] * 5}
    disagree = {"per_review": [{"score": s} for s in (-1, 1, -1, 1, 0)]}
    assert consistency_component(agree) == 10.0
    assert consistency_component(disagree) < 5.0
    assert consistency_component({"per_review": [{"score": 0.5}, {"score": 0.5}]}) is None


# ── recency ───────────────────────────────────────────────────────────────────

def test_recency_requires_a_real_trend_score():
    """Regression: recency used to fall back to the overall sentiment score,
    which double-counted the same signal inside the composite."""
    assert recency_component({"sentiment_score": 0.9}) is None
    assert recency_component({"temporal_trend": {"trend": "Stable"}}) is None


def test_recency_trend_direction_adjusts_the_score():
    stable = recency_component({"temporal_trend": {"recent_score": 0.0, "trend": "Stable"}})
    up     = recency_component({"temporal_trend": {"recent_score": 0.0, "trend": "Improving"}})
    down   = recency_component({"temporal_trend": {"recent_score": 0.0, "trend": "Declining"}})
    assert down < stable < up


# ── penalties ─────────────────────────────────────────────────────────────────

def test_penalty_scales_with_severity_and_is_capped():
    guard = {"genuine_concerns": [{"severity": "Major"}] * 10}
    assert risk_penalty(guard, {}) == DEFAULT_CONFIG.max_risk_penalty
    assert risk_penalty({"genuine_concerns": [{"severity": "Minor"}]}, {}) == 0.2


def test_only_evidenced_corrections_are_penalised():
    with_ev    = {"corrections": [{"evidence_review_ids": ["r1"]}]}
    without_ev = {"corrections": [{"evidence_review_ids": []}]}
    assert risk_penalty({}, with_ev) == DEFAULT_CONFIG.evidenced_correction_penalty
    assert risk_penalty({}, without_ev) == 0.0


# ── verdict thresholds ────────────────────────────────────────────────────────

@pytest.mark.parametrize("score,label", [
    (10.0, "HIGHLY RECOMMENDED"), (8.0, "HIGHLY RECOMMENDED"),
    (7.99, "RECOMMENDED"), (6.5, "RECOMMENDED"),
    (6.49, "VISIT WITH CAUTION"), (4.5, "VISIT WITH CAUTION"),
    (4.49, "NOT RECOMMENDED"), (0.0, "NOT RECOMMENDED"),
])
def test_verdict_thresholds(score, label):
    assert verdict_for(score) == label


# ── composite ─────────────────────────────────────────────────────────────────

def test_weights_are_renormalised_over_available_components():
    """Sentiment-only input must score exactly the sentiment component."""
    out = score_location(reviews(10), {}, {"sentiment_score": 0.6},
                         {"trust_score": None}, {"verification_status": "UNAVAILABLE"})
    bd = out["score_breakdown"]
    assert bd["components_used"] == ["rating", "sentiment"]
    assert "aspect" in bd["components_missing"]
    assert sum(bd["effective_weights"].values()) == pytest.approx(1.0)


def test_single_component_scores_exactly_that_component():
    out = score_location([], {}, {"sentiment_score": 0.6}, {}, {"verification_status": "UNAVAILABLE"})
    assert out["score_breakdown"]["components_used"] == ["sentiment"]
    assert out["score"] == pytest.approx(8.0)


def test_no_data_at_all_does_not_crash():
    out = score_location([], {}, {}, {}, {})
    assert out["score"] == 0.0
    assert out["verdict"] == "NOT RECOMMENDED"
    assert out["score_breakdown"]["components_used"] == []


def test_composite_is_monotonic_in_sentiment():
    def score(s):
        return score_location(reviews(20), {"google_score": 4.0}, {"sentiment_score": s},
                              {"trust_score": 0.8, "fake_review_probability": 0.1},
                              PASS_VERIF)["score"]
    assert score(-0.9) < score(0.0) < score(0.9)


def test_engine_is_deterministic():
    args = (reviews(12), {"google_score": 4.2}, {"sentiment_score": 0.4},
            {"trust_score": 0.7, "fake_review_probability": 0.1}, PASS_VERIF)
    assert score_location(*args) == score_location(*args)


def test_penalty_is_applied_to_the_composite():
    base = score_location(reviews(20), {"google_score": 4.0}, {"sentiment_score": 0.5},
                          {"trust_score": 0.8, "fake_review_probability": 0.1}, PASS_VERIF)
    hit = score_location(reviews(20), {"google_score": 4.0}, {"sentiment_score": 0.5},
                         {"trust_score": 0.8, "fake_review_probability": 0.1,
                          "genuine_concerns": [{"severity": "Major"}]}, PASS_VERIF)
    assert hit["score"] == pytest.approx(base["score"] - 1.5, abs=0.02)


def test_score_is_clamped_to_0_10():
    out = score_location(reviews(3, rating=1), {"google_score": 0.1},
                         {"sentiment_score": -1.0},
                         {"trust_score": 0.0, "fake_review_probability": 1.0,
                          "genuine_concerns": [{"severity": "Major"}] * 5}, PASS_VERIF)
    assert 0.0 <= out["score"] <= 10.0


# ── configurability ───────────────────────────────────────────────────────────

def test_config_is_honoured():
    strict = ScoringConfig(verdict_thresholds=((9.5, "HIGHLY RECOMMENDED"),), lowest_verdict="NOPE")
    out = score_location([], {}, {"sentiment_score": 0.6}, {}, {}, cfg=strict)
    assert out["verdict"] == "NOPE"


def test_config_is_immutable():
    from dataclasses import FrozenInstanceError

    with pytest.raises(FrozenInstanceError):
        DEFAULT_CONFIG.max_risk_penalty = 99


# ── data sufficiency ──────────────────────────────────────────────────────────

def test_data_sufficiency_grows_with_sample_size():
    small = data_sufficiency(5,  {}, {}, PASS_VERIF)
    big   = data_sufficiency(50, {}, {}, PASS_VERIF)
    assert big > small


def test_tiny_samples_are_heavily_discounted():
    assert data_sufficiency(2, {}, {}, PASS_VERIF) < data_sufficiency(5, {}, {}, PASS_VERIF)


def test_unaudited_analysis_has_lower_sufficiency_than_audited():
    audited   = data_sufficiency(30, {}, {}, PASS_VERIF)
    unaudited = data_sufficiency(30, {}, {}, {"verification_status": "UNAVAILABLE", "coverage": 0.0})
    assert unaudited < audited


def test_partial_audit_coverage_earns_partial_credit():
    full = data_sufficiency(30, {}, {}, {"verification_status": "PASS", "coverage": 1.0})
    part = data_sufficiency(30, {}, {}, {"verification_status": "PASS", "coverage": 0.2})
    assert part < full


def test_sufficiency_stays_within_bounds():
    for n in (0, 1, 10, 1000):
        val = data_sufficiency(n, {"consistency": 10}, {"trust_score": 1.0}, PASS_VERIF)
        assert 0.0 <= val <= 1.0
