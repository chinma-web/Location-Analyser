"""Compare mode — especially its refusal to invent a winner."""
import pytest

from locan.compare import (
    MAX_PLACES,
    MEANINGFUL_GAP,
    aspect_matrix,
    aspect_winners,
    build_comparison,
    compare_locations,
    entry_from_report,
    validate_locations,
)


def report(name, score, confidence=0.8, trust=0.9, reviews=30, aspects=None,
           category="Restaurant", verification="PASS"):
    return {
        "location": name,
        "place_info": {"name": name, "category": category, "google_score": 4.2},
        "scoring": {"score": score, "verdict": "RECOMMENDED", "confidence": confidence},
        "guardrail": {"trust_score": trust},
        "verification": {"verification_status": verification},
        "reviews": [{"id": f"r{i}"} for i in range(reviews)],
        "sentiment": {"aspect_scores": {k: {"score": v} for k, v in (aspects or {}).items()}},
    }


# ── flattening ────────────────────────────────────────────────────────────────

def test_entry_pulls_the_comparable_fields():
    entry = entry_from_report(report("Cafe A", 7.4, aspects={"service": 8.0}))
    assert entry.name == "Cafe A"
    assert entry.score == 7.4 and entry.verdict == "RECOMMENDED"
    assert entry.trust == 0.9 and entry.google_rating == 4.2
    assert entry.reviews_analyzed == 30
    assert entry.aspects == {"service": 8.0}
    assert entry.ok is True


def test_failed_analysis_becomes_a_non_ok_entry():
    entry = entry_from_report({"error": "No reviews found."}, "Nowhere")
    assert entry.ok is False and entry.error == "No reviews found."
    assert entry.name == "Nowhere"


def test_unscored_aspects_are_dropped_not_zeroed():
    payload = report("X", 6.0)
    payload["sentiment"]["aspect_scores"] = {"service": {"score": None},
                                             "ambience": {"score": 5.0}}
    assert entry_from_report(payload).aspects == {"ambience": 5.0}


# ── ranking and the winner call ───────────────────────────────────────────────

def test_clear_winner_is_reported():
    result = build_comparison([report("A", 8.6), report("B", 6.1)])
    assert result["winner"] == "A"
    assert result["ranking"] == ["A", "B"]
    assert "leads" in result["headline"]


def test_a_narrow_gap_is_a_tie_not_a_win():
    result = build_comparison([report("A", 7.4), report("B", 7.2)])
    assert result["winner"] is None
    assert "Too close to call" in result["headline"]
    assert any("too close to separate" in c for c in result["caveats"])


def test_gap_exactly_at_the_threshold_counts_as_a_win():
    result = build_comparison([report("A", 7.5), report("B", 7.5 - MEANINGFUL_GAP)])
    assert result["winner"] == "A"


def test_low_confidence_places_cannot_win():
    result = build_comparison([report("Thin", 9.5, confidence=0.3),
                               report("Solid", 7.0, confidence=0.9)])
    assert result["winner"] == "Solid"
    assert any("Low data sufficiency" in c for c in result["caveats"])


def test_when_nothing_is_confident_no_winner_is_declared():
    result = build_comparison([report("A", 9.0, confidence=0.2),
                               report("B", 8.0, confidence=0.1)])
    assert result["winner"] is None
    assert "No place has enough data" in result["headline"]


def test_all_failed_is_handled():
    result = build_comparison([{"error": "boom"}, {"error": "bang"}], ["A", "B"])
    assert result["winner"] is None
    assert result["places_compared"] == 0
    assert "No place could be scored" in result["headline"]


def test_a_single_usable_place_is_labelled_as_such():
    result = build_comparison([report("A", 8.0), {"error": "no reviews"}], ["A", "B"])
    assert result["winner"] == "A"
    assert "only place with enough data" in result["headline"]
    assert any("could not be analysed" in c for c in result["caveats"])


def test_failed_places_sort_last_but_are_kept():
    result = build_comparison([{"error": "x"}, report("A", 5.0)], ["Bad", "A"])
    assert result["ranking"] == ["A", "Bad"]
    assert len(result["entries"]) == 2


# ── aspects ───────────────────────────────────────────────────────────────────

def test_aspect_matrix_is_sparse_by_design():
    entries = [entry_from_report(report("Hotel", 8.0, aspects={"rooms": 9.0}, category="Hotel")),
               entry_from_report(report("Cafe", 7.0, aspects={"food_quality": 8.0}))]
    matrix = aspect_matrix(entries)
    assert matrix["rooms"] == {"Hotel": 9.0}
    assert "Cafe" not in matrix["rooms"]          # missing != zero


def test_aspect_winner_needs_two_places_and_a_real_gap():
    entries = [entry_from_report(report("A", 8.0, aspects={"service": 9.0, "value_for_money": 7.0})),
               entry_from_report(report("B", 7.0, aspects={"service": 6.0, "value_for_money": 6.9}))]
    winners = aspect_winners(entries)
    assert winners["service"]["winner"] == "A"
    assert winners["service"]["gap"] == 3.0
    assert winners["value_for_money"]["winner"] is None    # 0.1 apart


def test_aspect_scored_for_only_one_place_has_no_winner():
    entries = [entry_from_report(report("A", 8.0, aspects={"rooms": 9.0})),
               entry_from_report(report("B", 7.0, aspects={"service": 6.0}))]
    assert aspect_winners(entries) == {}


# ── caveats ───────────────────────────────────────────────────────────────────

def test_uneven_sample_sizes_are_flagged():
    result = build_comparison([report("A", 8.5, reviews=60), report("B", 6.0, reviews=8)])
    assert any("Uneven sample sizes" in c for c in result["caveats"])


def test_mixed_categories_are_flagged():
    result = build_comparison([report("A", 8.5), report("B", 6.0, category="Hotel")])
    assert any("Different categories" in c for c in result["caveats"])


def test_incomplete_verification_is_flagged():
    result = build_comparison([report("A", 8.5, verification="UNAVAILABLE"),
                               report("B", 6.0)])
    assert any("Verification did not complete" in c for c in result["caveats"])


def test_a_clean_comparison_has_no_noise_caveats():
    result = build_comparison([report("A", 8.6, reviews=30), report("B", 6.1, reviews=30)])
    assert result["caveats"] == []


# ── input validation ──────────────────────────────────────────────────────────

def test_validate_trims_dedupes_and_bounds():
    assert validate_locations([" A ", "B"]) == ["A", "B"]
    assert validate_locations(["A", "a", "B"]) == ["A", "B"]      # case-insensitive dedupe
    with pytest.raises(ValueError):
        validate_locations(["only one"])
    with pytest.raises(ValueError):
        validate_locations([f"p{i}" for i in range(MAX_PLACES + 1)])
    with pytest.raises(ValueError):
        validate_locations([])


# ── orchestration ─────────────────────────────────────────────────────────────

def test_compare_locations_runs_each_place_and_reports_progress():
    seen, progress = [], []

    def fake_analyze(location, max_reviews, force_refresh=False):
        seen.append((location, max_reviews, force_refresh))
        return report(location, 8.0 if location == "A" else 6.0)

    result = compare_locations(["A", "B"], max_reviews=25, force_refresh=True,
                               analyze_fn=fake_analyze,
                               progress_callback=lambda i, n, loc: progress.append((i, n, loc)))

    assert seen == [("A", 25, True), ("B", 25, True)]
    assert progress == [(0, 2, "A"), (1, 2, "B")]
    assert result["winner"] == "A"
    assert len(result["reports"]) == 2


def test_one_failing_place_does_not_sink_the_comparison():
    def fake_analyze(location, max_reviews, force_refresh=False):
        if location == "B":
            raise RuntimeError("scraper exploded")
        return report(location, 7.5)

    result = compare_locations(["A", "B"], analyze_fn=fake_analyze)
    assert result["places_compared"] == 1
    assert any("scraper exploded" in c for c in result["caveats"])
