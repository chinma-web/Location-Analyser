"""
Smoke tests for the Streamlit script itself.

app.py is a 1,200-line top-level script: nothing in the rest of the suite
exercises it, so a typo in the dashboard only showed up in the browser. These
run the real script through Streamlit's own harness with a stubbed engine — no
network, no API keys.
"""
import os

import pytest

streamlit_testing = pytest.importorskip("streamlit.testing.v1")
AppTest = streamlit_testing.AppTest

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


def _app():
    return AppTest.from_file(APP, default_timeout=120)


def _sample_report(name="Cafe Goodluck", category="Restaurant"):
    reviews = [{"id": f"r{i}", "rating": 4 + (i % 2), "text": f"The coffee was good {i}",
                "author": f"A{i}", "date": f"2025-01-0{i % 9 + 1}"}
               for i in range(6)]
    return {
        "location": name,
        "place_info": {"name": name, "category": category, "google_score": 4.3,
                       "review_count": 1200, "address": "Pune", "subtypes": []},
        "review_stats": {"analyzed_review_count": len(reviews), "rating_distribution": {}},
        "reviews": reviews,
        "sentiment": {
            "overall_sentiment": "Positive", "sentiment_score": 0.55,
            "positive_keywords": ["coffee", "ambience"], "negative_keywords": ["wait"],
            "aspect_scores": {"food_quality": {"score": 8.0, "reviews_mentioning": 4,
                                               "summary": "good", "evidence_review_ids": ["r1"]},
                              "service": {"score": 6.5, "reviews_mentioning": 2,
                                          "summary": "mixed", "evidence_review_ids": ["r2"]}},
            "themes": [{"name": "Coffee", "sentiment": "Positive", "frequency": 4,
                        "representative_quote": "great coffee", "evidence": "many mentions"}],
            "emotion_distribution": {"Happy": 4, "Neutral": 2},
            "grounding": {
                "positive_keywords": {"grounded": [{"term": "coffee", "count": 6,
                                                    "review_count": 6, "review_ids": ["r0"],
                                                    "quotes": ["The coffee was good"],
                                                    "grounded": True}],
                                      "ungrounded": ["ambience"], "grounded_ratio": 0.5},
                "negative_keywords": {"grounded": [], "ungrounded": ["wait"],
                                      "grounded_ratio": 0.0},
                "top_terms": [{"term": "coffee", "review_count": 6, "count": 6}],
                "aspect_mentions": {"food_quality": {"review_ids": ["r0", "r1"],
                                                     "review_count": 2,
                                                     "terms": {"coffee": 6}, "quotes": ["x"]},
                                    "service": {"review_ids": [], "review_count": 0,
                                                "terms": {}, "quotes": []}},
                "aspects_without_lexical_support": ["service"],
            },
        },
        "guardrail": {"trust_score": 0.82, "fake_review_probability": 0.1,
                      "review_quality": "Good", "bias_level": "Low",
                      "genuine_positives": [], "genuine_concerns": [], "red_flags": []},
        "verification": {"verification_status": "PASS", "corrections": [],
                         "corrections_count": 0, "fields_verified": []},
        "recommendation": {"recommendation": "RECOMMENDED", "visit_score": 7.8,
                           "confidence": 0.8, "pros": ["Great coffee"], "cons": [],
                           "full_verdict": "Worth a visit.", "score_breakdown": {}},
        "scoring": {"score": 7.8, "verdict": "RECOMMENDED", "confidence": 0.8,
                    "score_breakdown": {"final_score": 7.8, "sentiment_comp": 7.7,
                                        "aspect_comp": 7.4, "components_used": ["sentiment"],
                                        "components_missing": [], "risk_penalty": 0}},
        "model_info": {},
    }


def test_app_renders_without_credentials():
    """Import-time config must never blow up the UI (the old sys.exit bug)."""
    app = _app().run()
    assert app.exception == []
    labels = [b.label for b in app.button]
    assert "🔤 Search by Name" in labels
    assert "⚖️ Compare places" in labels


def test_missing_keys_are_warned_about_not_fatal():
    app = _app().run()
    assert app.exception == []
    assert any("Missing" in w.value for w in app.warning)


def test_report_dashboard_renders_every_tab():
    app = _app()
    app.session_state["report_data"] = _sample_report()
    app.run()
    assert app.exception == []
    tab_labels = [t.label for t in app.tabs]
    assert "🔬 Evidence (no model)" in tab_labels
    assert len(tab_labels) == 7


def test_evidence_tab_shows_grounding_numbers():
    app = _app()
    app.session_state["report_data"] = _sample_report()
    app.run()
    assert app.exception == []
    text = " ".join(m.value for m in app.markdown)
    assert "counted directly from the review text" in text
    # unsupported aspect is called out
    assert any("no matching words" in w.value or "scepticism" in w.value
               for w in app.warning)


def test_dashboard_survives_a_hotel_report_with_different_aspects():
    """Aspect rendering must follow the category, not a hardcoded food list."""
    report = _sample_report("Taj Hotel", category="Hotel")
    report["sentiment"]["aspect_scores"] = {
        "rooms": {"score": 9.0, "reviews_mentioning": 3, "summary": "spacious",
                  "evidence_review_ids": []},
        "amenities": {"score": 7.0, "reviews_mentioning": 2, "summary": "pool",
                      "evidence_review_ids": []},
    }
    app = _app()
    app.session_state["report_data"] = report
    app.run()
    assert app.exception == []


def test_compare_dashboard_renders_results():
    from locan.compare import build_comparison

    comparison = build_comparison(
        [_sample_report("Cafe A"), _sample_report("Cafe B")], ["Cafe A", "Cafe B"])
    comparison["reports"] = []

    app = _app()
    app.session_state["search_mode"] = "compare"
    app.session_state["compare_data"] = comparison
    app.run()
    assert app.exception == []
    # the single-report dashboard must stay hidden in compare mode
    assert all("Executive Verdict" not in t.label for t in app.tabs)


def test_compare_mode_rejects_a_single_place():
    app = _app()
    app.session_state["search_mode"] = "compare"
    app.run()
    assert app.exception == []
    app.text_input(key="cmp_0").set_value("Only One Place")
    compare_button = next(b for b in app.button if b.label == "⚖️ Compare")
    compare_button.click().run()
    assert app.exception == []
    assert any("2–4 distinct places" in w.value for w in app.warning)
