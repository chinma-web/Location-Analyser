"""
Regression tests for the verification-integrity fixes.

These guard the single most important property of this project: the app must
never claim an independent audit happened when it did not.
"""
from locan import config as config_mod
from locan import corrections, guardrail, pipeline, verify


def test_unavailable_is_not_reported_as_pass():
    v = verify._unavailable_verification("Groq verifier call failed: 401 unauthorized")
    assert v["verification_status"] == "UNAVAILABLE"
    assert v["status"] == "UNAVAILABLE"
    assert v["accuracy"] is None, "a run that never happened must not report an accuracy"
    assert v["hallucination_detected"] is None, "unknown is not False"
    assert v["coverage"] == 0.0
    for field in verify.VERIFIED_FIELDS:
        assert v[field]["status"] == "UNCHECKED"
        assert v[field]["observations"] == [], "no observation may be fabricated"


def test_normalise_marks_absent_fields_unchecked():
    # Verifier answered, but only about sentiment.
    raw = {
        "verification_status": "PASS",
        "accuracy": 0.8,
        "sentiment": {"status": "PASS", "observations": ["12 of 20 reviews are 5-star."]},
    }
    v = verify._normalise_verification(raw)
    assert v["fields_checked"] == ["sentiment"]
    assert set(v["fields_unchecked"]) == {"aspects", "keywords", "guardrail", "evidence"}
    assert v["coverage"] == 0.2
    for field in v["fields_unchecked"]:
        assert v[field]["status"] == "UNCHECKED"
        assert v[field]["observations"] == []


def test_normalise_rejects_unknown_status_and_bogus_accuracy():
    v = verify._normalise_verification({"verification_status": "LOOKS_FINE", "accuracy": "high"})
    assert v["verification_status"] == "UNKNOWN"
    assert v["accuracy"] is None


def test_normalise_drops_blank_observations():
    v = verify._normalise_verification({
        "verification_status": "PASS",
        "keywords": {"status": "PASS", "observations": ["", "   ", None, "real one"]},
    })
    assert v["keywords"]["observations"] == ["real one"]


def test_unverified_run_is_discounted_not_rewarded():
    """Identical inputs: an unverified run must not outscore a verified one."""
    reviews = [{"author": "a", "rating": 5, "text": "great place", "date": "2025-01-01"}] * 10
    place   = {"google_score": 4.5}
    sent    = {"sentiment_score": 0.6, "aspect_scores": {}, "per_review": []}
    guard   = {"trust_score": 0.9, "fake_review_probability": 0.05, "genuine_concerns": []}

    verified = pipeline.calculate_final_score(
        reviews, place, sent, guard,
        {"verification_status": "PASS", "accuracy": 0.9, "coverage": 1.0, "corrections": []},
    )
    unverified = pipeline.calculate_final_score(
        reviews, place, sent, guard, verify._unavailable_verification("no key"),
    )

    assert unverified["score"] < verified["score"]
    assert unverified["confidence"] < verified["confidence"]


def test_derived_concerns_do_not_double_penalise():
    """Concerns we derived from Model 1's sentiment are already in sentiment_comp."""
    reviews = [{"author": "a", "rating": 3, "text": "slow service", "date": "2025-01-01"}] * 10
    place   = {"google_score": 3.5}
    sent    = {"sentiment_score": 0.0, "aspect_scores": {}, "per_review": []}
    verif   = {"verification_status": "PASS", "accuracy": 0.9, "coverage": 1.0, "corrections": []}

    derived = pipeline.calculate_final_score(
        reviews, place, sent,
        {"trust_score": 0.8, "fake_review_probability": 0.1,
         "genuine_concerns": [{"aspect": "service", "severity": None, "derived": True}] * 3},
        verif,
    )
    graded = pipeline.calculate_final_score(
        reviews, place, sent,
        {"trust_score": 0.8, "fake_review_probability": 0.1,
         "genuine_concerns": [{"aspect": "service", "severity": "Major"}] * 3},
        verif,
    )
    assert derived["score_breakdown"]["risk_penalty"] == 0.0
    assert graded["score_breakdown"]["risk_penalty"] > 0


def test_guardrail_fallbacks_never_invent_confidence_or_severity():
    sentiment = {
        "positive_points": [{"claim": "Food is praised", "evidence_review_ids": ["r1"]}],
        "negative_points": [{"claim": "Parking is hard", "evidence_review_ids": ["r2"]}],
        "positive_keywords": ["tasty"],
    }
    reviews = [{"author": "a", "rating": 5, "text": "tasty food"}]
    out = guardrail._derive_guardrail_fallbacks({}, reviews, sentiment)

    assert out["genuine_positives"][0]["confidence"] is None
    assert out["genuine_positives"][0]["derived"] is True
    assert out["genuine_concerns"][0]["severity"] is None
    assert out["genuine_concerns"][0]["derived"] is True


def test_guardrail_fallbacks_are_empty_when_there_is_nothing_to_derive():
    out = guardrail._derive_guardrail_fallbacks({}, [], {})
    assert out["genuine_positives"] == []
    assert out["genuine_concerns"] == []


def test_corrections_are_not_applied_from_an_incomplete_verification():
    sent  = {"positive_keywords": ["clean"], "aspect_scores": {}}
    guard = {"genuine_concerns": []}
    v = verify._unavailable_verification("boom")
    v["corrections"] = [{"field": "keywords.positive", "original_claim": "clean",
                         "corrected_claim": "not supported", "evidence_review_ids": ["r1"]}]
    out_sent, _ = corrections.apply_corrections(sent, guard, v)
    assert out_sent["positive_keywords"] == ["clean"]


def test_import_has_no_credentials_side_effect():
    assert callable(config_mod.validate_config)
    assert isinstance(config_mod.validate_config(raise_on_error=False), list)
