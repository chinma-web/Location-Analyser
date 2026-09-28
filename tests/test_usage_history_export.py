"""Cost meter, run history, and report export."""
import json
import os
import threading
import time

import pytest

from locan.export import (
    _markdown_to_html,
    suggested_filename,
    to_html,
    to_json,
    to_markdown,
)
from locan.history import delete_run, history_stats, list_runs, load_run
from locan.usage import (
    PRICING,
    ModelUsage,
    UsageMeter,
    format_cost,
    record_estimate,
    record_response,
)

# ── usage meter ───────────────────────────────────────────────────────────────

def test_meter_accumulates_per_model():
    meter = UsageMeter()
    meter.record("llama-3.3-70b-versatile", 1000, 500)
    meter.record("llama-3.3-70b-versatile", 2000, 100)
    meter.record("llama-3.1-8b-instant", 500, 50)

    summary = meter.summary()
    assert summary["calls"] == 3
    assert summary["prompt_tokens"] == 3500
    assert summary["completion_tokens"] == 650
    assert summary["total_tokens"] == 4150
    assert len(summary["by_model"]) == 2


def test_cost_uses_the_published_per_model_rates():
    usage = ModelUsage("llama-3.3-70b-versatile", prompt_tokens=1_000_000,
                       completion_tokens=1_000_000)
    input_rate, output_rate = PRICING["llama-3.3-70b-versatile"]
    assert usage.cost_usd == pytest.approx(input_rate + output_rate)


def test_unknown_models_are_free_and_flagged_rather_than_guessed():
    meter = UsageMeter()
    meter.record("some-new-model", 10_000, 10_000)
    summary = meter.summary()
    assert summary["llm_cost_usd"] == 0
    assert summary["any_unpriced"] is True


def test_scrape_cost_is_included():
    meter = UsageMeter()
    meter.record_scrape()
    summary = meter.summary()
    assert summary["scrape_cost_usd"] > 0
    assert summary["total_cost_usd"] == summary["scrape_cost_usd"]


def test_reset_clears_everything():
    meter = UsageMeter()
    meter.record("llama-3.1-8b-instant", 100, 100)
    meter.record_scrape()
    meter.reset()
    summary = meter.summary()
    assert summary["calls"] == 0 and summary["scrapes"] == 0


def test_meter_is_thread_safe():
    """Sentiment batches record concurrently."""
    meter = UsageMeter()

    def worker():
        for _ in range(50):
            meter.record("llama-3.1-8b-instant", 10, 5)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    summary = meter.summary()
    assert summary["calls"] == 400
    assert summary["total_tokens"] == 400 * 15


def test_negative_or_missing_counts_are_clamped():
    meter = UsageMeter()
    meter.record("llama-3.1-8b-instant", -50, None)
    assert meter.summary()["total_tokens"] == 0


def test_record_response_reads_the_provider_numbers():
    from locan import usage as usage_mod

    class _Usage:
        prompt_tokens, completion_tokens = 120, 30

    class _Response:
        usage = _Usage()

    usage_mod.METER.reset()
    record_response("llama-3.1-8b-instant", _Response())
    summary = usage_mod.METER.summary()
    assert summary["prompt_tokens"] == 120 and summary["completion_tokens"] == 30
    assert summary["any_estimated"] is False
    usage_mod.METER.reset()


def test_response_without_usage_is_not_invented():
    from locan import usage as usage_mod

    usage_mod.METER.reset()
    record_response("llama-3.1-8b-instant", object())
    assert usage_mod.METER.summary()["calls"] == 0
    usage_mod.METER.reset()


def test_estimates_are_marked_as_estimates():
    from locan import usage as usage_mod

    usage_mod.METER.reset()
    record_estimate("llama-3.1-8b-instant", "x" * 400, "y" * 40)
    summary = usage_mod.METER.summary()
    assert summary["total_tokens"] == 110
    assert summary["any_estimated"] is True
    usage_mod.METER.reset()


@pytest.mark.parametrize("cost,expected", [
    (0, "$0.00"), (0.0031, "<$0.01 (0.31¢)"), (1.5, "$1.50"),
])
def test_cost_formatting(cost, expected):
    assert format_cost(cost) == expected


# ── history ───────────────────────────────────────────────────────────────────

def _write_report(directory, key, payload, mtime=None):
    path = os.path.join(directory, f"report_{key}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


def _payload(name, score=7.5, cached_at=None, cost=0.002):
    return {
        "location": name,
        "place_info": {"name": name, "category": "Restaurant"},
        "scoring": {"score": score, "verdict": "RECOMMENDED", "confidence": 0.8},
        "reviews": [{"id": "r1"}, {"id": "r2"}],
        "usage": {"total_cost_usd": cost, "total_tokens": 5000},
        "cache_meta": {"cached_at": cached_at or time.time(), "schema_version": 2,
                       "max_reviews": 30},
    }


def test_history_lists_runs_newest_first(tmp_path):
    now = time.time()
    _write_report(tmp_path, "a", _payload("Older", cached_at=now - 7200))
    _write_report(tmp_path, "b", _payload("Newer", cached_at=now - 60))

    runs = list_runs(str(tmp_path))
    assert [r["name"] for r in runs] == ["Newer", "Older"]
    assert runs[1]["age_hours"] == pytest.approx(2.0, abs=0.1)
    assert runs[0]["max_reviews"] == 30


def test_history_surfaces_score_and_cost(tmp_path):
    _write_report(tmp_path, "a", _payload("Cafe", score=8.1, cost=0.004))
    run = list_runs(str(tmp_path))[0]
    assert run["score"] == 8.1 and run["verdict"] == "RECOMMENDED"
    assert run["cost_usd"] == 0.004 and run["reviews_analyzed"] == 2


def test_corrupt_cache_files_cost_one_row_not_the_page(tmp_path):
    _write_report(tmp_path, "good", _payload("Fine"))
    (tmp_path / "report_bad.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "report_list.json").write_text("[1,2,3]", encoding="utf-8")

    runs = list_runs(str(tmp_path))
    assert [r["name"] for r in runs] == ["Fine"]


def test_history_marks_entries_from_an_older_schema(tmp_path):
    stale = _payload("Old schema")
    stale["cache_meta"]["schema_version"] = 1
    _write_report(tmp_path, "s", stale)
    assert list_runs(str(tmp_path))[0]["stale"] is True


def test_history_respects_the_limit_and_missing_dir(tmp_path):
    for i in range(5):
        _write_report(tmp_path, f"r{i}", _payload(f"P{i}"))
    assert len(list_runs(str(tmp_path), limit=3)) == 3
    assert list_runs(str(tmp_path / "does-not-exist")) == []


def test_load_and_delete_a_run(tmp_path):
    path = _write_report(tmp_path, "a", _payload("Cafe"))
    assert load_run(path)["location"] == "Cafe"
    assert delete_run(path) is True
    assert not os.path.exists(path)
    assert delete_run(path) is False
    assert load_run(path) == {}


def test_history_stats_totals():
    runs = [{"cost_usd": 0.002, "total_tokens": 1000, "score": 8.0},
            {"cost_usd": 0.003, "total_tokens": 2000, "score": 6.0},
            {"score": None}]
    stats = history_stats(runs)
    assert stats["runs"] == 3
    assert stats["total_cost_usd"] == 0.005
    assert stats["total_tokens"] == 3000
    assert stats["average_score"] == 7.0
    assert stats["runs_with_cost_data"] == 2


# ── export ────────────────────────────────────────────────────────────────────

def _full_report():
    return {
        "location": "Cafe Goodluck",
        "place_info": {"name": "Cafe Goodluck", "category": "Restaurant",
                       "address": "Pune", "google_score": 4.3},
        "reviews": [{"id": "r1", "rating": 5, "text": "Great coffee"}],
        "scoring": {"score": 7.8, "verdict": "RECOMMENDED", "confidence": 0.8,
                    "score_breakdown": {"sentiment_comp": 7.7, "aspect_comp": 7.4,
                                        "risk_penalty": 0.5,
                                        "components_missing": ["recency"]}},
        "sentiment": {"aspect_scores": {"food_quality": {"score": 8.0,
                                                         "reviews_mentioning": 4,
                                                         "summary": "consistent"}},
                      "grounding": {"positive_keywords": {"grounded": [
                                        {"term": "coffee", "review_count": 6}],
                                        "ungrounded": ["ambience"]},
                                    "negative_keywords": {"grounded": [], "ungrounded": []},
                                    "top_terms": [{"term": "coffee", "review_count": 6}],
                                    "aspects_without_lexical_support": ["accessibility"]}},
        "guardrail": {"trust_score": 0.82, "fake_review_probability": 0.1,
                      "review_quality": "Good", "bias_level": "Low",
                      "red_flags": [{"flag": "Burst", "detail": "12 reviews in a day"}]},
        "verification": {"verification_status": "CORRECTED", "corrections_count": 2},
        "recommendation": {"full_verdict": "Worth a visit.", "pros": ["Coffee"],
                           "cons": ["Queues"]},
        "usage": {"total_tokens": 41234, "calls": 7, "total_cost_usd": 0.0031,
                  "elapsed_seconds": 42.5, "any_estimated": False},
    }


def test_markdown_contains_the_headline_facts():
    md = to_markdown(_full_report())
    assert md.startswith("# Cafe Goodluck")
    assert "RECOMMENDED" in md and "7.8/10" in md
    assert "deterministic Python function" in md      # the honesty note
    assert "| Food quality | 8.0/10 |" in md
    assert "CORRECTED" in md


def test_markdown_reports_grounding_and_missing_components():
    md = to_markdown(_full_report())
    assert "coffee (6)" in md
    assert "ambience" in md                            # ungrounded keyword named
    assert "no matching words" in md
    assert "No data for: recency" in md


def test_markdown_includes_cost_and_optional_reviews():
    assert "41,234" in to_markdown(_full_report())
    assert "Great coffee" not in to_markdown(_full_report())
    assert "Great coffee" in to_markdown(_full_report(), include_reviews=True)


def test_markdown_handles_a_failed_report():
    md = to_markdown({"location": "Nowhere", "error": "No reviews found."})
    assert "Analysis failed" in md and "No reviews found." in md


def test_markdown_handles_an_empty_payload():
    assert to_markdown({}).startswith("# Unknown place")
    assert to_markdown(None)


def test_html_is_a_standalone_document():
    doc = to_html(_full_report())
    assert doc.startswith("<!DOCTYPE html>")
    assert "<title>Cafe Goodluck — Location Analyser</title>" in doc
    assert "<table>" in doc and "<h1>" in doc


def test_html_escapes_hostile_content():
    report = _full_report()
    report["place_info"]["name"] = "<script>alert(1)</script>"
    doc = to_html(report)
    assert "<script>alert(1)</script>" not in doc
    assert "&lt;script&gt;" in doc


def test_markdown_to_html_handles_each_block_type():
    html_out = _markdown_to_html(
        "# Title\n\n## Sub\n\n> quote\n\n- one\n- two\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n"
        "**bold** text\n\n---"
    )
    assert "<h1>Title</h1>" in html_out and "<h2>Sub</h2>" in html_out
    assert "<blockquote>quote</blockquote>" in html_out
    assert html_out.count("<li>") == 2
    assert "<th>A</th>" in html_out and "<td>1</td>" in html_out
    assert "<strong>bold</strong>" in html_out and "<hr>" in html_out


def test_json_export_round_trips():
    assert json.loads(to_json(_full_report()))["location"] == "Cafe Goodluck"
    assert json.loads(to_json(None)) == {}


def test_filenames_are_slugified_and_dated():
    name = suggested_filename(_full_report(), "md")
    assert name.startswith("cafe-goodluck-") and name.endswith(".md")
    assert suggested_filename({}, ".html").endswith(".html")
    assert "--" not in suggested_filename({"location": "A  &&  B"}, "md")
