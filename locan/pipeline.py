"""
The analysis pipeline: scrape → sentiment → guardrail → verify → correct →
deterministic score → written recommendation.
"""

import json
import time
from dataclasses import replace

from locan import llm
from locan.aspects import aspect_set_for_place
from locan.cache import read_cache, write_cache
from locan.config import (
    FAST_MODEL,
    REQUIRE_VERIFICATION,
    STRONG_MODEL,
    VERDICT_MODEL,
    VERIFIER_MODEL,
)
from locan.corrections import apply_corrections
from locan.grounding import ground_sentiment
from locan.guardrail import guardrail_analysis
from locan.logging_utils import log
from locan.report import Panel, console, display_report
from locan.scoring import DEFAULT_CONFIG as DEFAULT_SCORING_CONFIG
from locan.scoring import ScoringConfig, score_location
from locan.scraper import scrape_reviews
from locan.sentiment import analyze_sentiment
from locan.usage import METER, format_cost
from locan.verify import verify_analysis

# ── MODULE 6: Deterministic Python Scoring & Recommendation ──────────────────

def calculate_final_score(
    reviews:      list,
    place_info:   dict,
    sentiment:    dict,
    guardrail:    dict,
    verification: dict,
    cfg:          ScoringConfig = DEFAULT_SCORING_CONFIG,
) -> dict:
    """
    DETERMINISTIC scoring. Neither Model A nor Model B decides the verdict.

    The maths lives in `scoring.py` (pure, no I/O, unit-tested); this wrapper
    only logs. Weights are declared in `ScoringConfig` and renormalised over the
    components that actually have data — a place with no aspect scores is no
    longer silently treated as a 5/10 on aspects.
    """
    result = score_location(reviews, place_info, sentiment, guardrail, verification, cfg)

    bd      = result["score_breakdown"]
    missing = bd.get("components_missing") or []
    log(
        f"[bold green]✓  Python scoring: {result['verdict']}  |  "
        f"Score: {result['score']}/10  |  Data sufficiency: {result['confidence']:.0%}[/bold green]"
    )
    log(
        f"[dim]   Components used: {', '.join(bd.get('components_used', []))}"
        + (f"  ·  no data for: {', '.join(missing)}" if missing else "")
        + f"  ·  risk penalty: -{bd.get('risk_penalty', 0)}[/dim]"
    )
    return result


# ── MODULE 7: Recommendation (Groq explanation only) ─────────────────────────

def generate_recommendation(
    location:      str,
    place_info:    dict,
    reviews:       list,
    sentiment:     dict,
    guardrail:     dict,
    final_scoring: dict,
) -> dict:
    """
    Groq generates the EXPLANATION TEXT (pros, cons, tips, verdict text).
    It does NOT decide the score or the verdict label — those come from Python.
    """
    log(
        f"\n[bold cyan]💡  Generating verdict & explanation (Groq / {VERDICT_MODEL})[/bold cyan]"
    )

    verdict    = final_scoring["verdict"]
    score      = final_scoring["score"]
    confidence = final_scoring["confidence"]

    context = {
        "location":          location,
        "place_name":        place_info.get("name", location),
        "category":          place_info.get("category", ""),
        "google_official":   place_info.get("google_score", 0),
        "reviews_analyzed":  len(reviews),
        "verdict":           verdict,           # Python-determined — do not override
        "visit_score":       score,             # Python-determined — do not override
        "confidence":        confidence,
        "overall_sentiment": sentiment.get("overall_sentiment"),
        "sentiment_score":   sentiment.get("sentiment_score"),
        "top_positive_kw":   sentiment.get("positive_keywords", [])[:6],
        "top_negative_kw":   sentiment.get("negative_keywords", [])[:4],
        "grounding":         sentiment.get("grounding", {}),
        "positive_points":   sentiment.get("positive_points", [])[:5],
        "negative_points":   sentiment.get("negative_points", [])[:5],
        "themes":            [
            {"name": t.get("name"), "sentiment": t.get("sentiment"),
             "evidence": (t.get("evidence",""))[:80]}
            for t in sentiment.get("themes", [])[:4]
            if isinstance(t, dict)
        ],
        "trust_score":       guardrail.get("trust_score"),
        "genuine_positives": [
            {"aspect": p.get("aspect"), "evidence": (p.get("evidence",""))[:80]}
            for p in guardrail.get("genuine_positives", [])[:4]
            if isinstance(p, dict)
        ],
        "genuine_concerns":  [
            {"aspect": c.get("aspect"), "severity": c.get("severity"),
             "evidence": (c.get("evidence",""))[:80]}
            for c in guardrail.get("genuine_concerns", [])[:3]
            if isinstance(c, dict)
        ],
        "score_breakdown":   final_scoring.get("score_breakdown", {}),
    }

    prompt = f"""You are an expert travel and experience advisor.
The Python scoring engine has ALREADY determined the verdict and score below.
Your job is to write the explanation text only — do NOT change the verdict or score.

ANALYSIS DATA:
{json.dumps(context, indent=2)}

Return EXACTLY this JSON (use the provided verdict and visit_score as-is):
{{
  "recommendation":   "{verdict}",
  "confidence":       {confidence},
  "visit_score":      {score},
  "one_line_verdict": "25-word or less honest verdict",
  "full_verdict":     "3-4 sentence balanced assessment",
  "best_for":         ["visitor type 1", "visitor type 2"],
  "avoid_if":         ["avoid if reason 1"],
  "pros": [
    {{"point": "pro description", "weight": "High|Medium|Low"}}
  ],
  "cons": [
    {{"point": "con description", "weight": "High|Medium|Low"}}
  ],
  "visitor_tips":     ["tip 1", "tip 2"],
  "best_time":        "best time to visit or null",
  "data_reliability": "High|Medium|Low",
  "score_breakdown": {{
    "sentiment_score": {final_scoring["score_breakdown"].get("sentiment_comp", 0)},
    "rating_score":    {final_scoring["score_breakdown"].get("rating_comp", 0)},
    "trust_score":     {final_scoring["score_breakdown"].get("trust_comp", 0)},
    "composite":       {score}
  }}
}}"""

    # Final explanation & verdict synthesis
    result = llm.call_groq(prompt, model=VERDICT_MODEL, max_tokens=2048)

    # Hard-enforce Python verdicts regardless of what Groq returned
    result["recommendation"] = verdict
    result["visit_score"]    = score
    result["confidence"]     = confidence
    result["score_breakdown"] = {
        "sentiment_score": final_scoring["score_breakdown"].get("sentiment_comp", 0),
        "rating_score":    final_scoring["score_breakdown"].get("rating_comp", 0),
        "trust_score":     final_scoring["score_breakdown"].get("trust_comp", 0),
        "composite":       score,
    }

    log("[green]✓  Explanation generated.[/green]")
    return result


# ── Main Pipeline ──────────────────────────────────────────────────────────────


def _log_grounding(sentiment: dict) -> None:
    """Report how much of the model's keyword output is backed by review text."""
    grounding = (sentiment or {}).get("grounding") or {}
    if not grounding:
        return
    positive = grounding.get("positive_keywords", {})
    negative = grounding.get("negative_keywords", {})
    ungrounded = positive.get("ungrounded", []) + negative.get("ungrounded", [])
    ratios = [r for r in (positive.get("grounded_ratio"), negative.get("grounded_ratio"))
              if r is not None]
    if ratios:
        pct = sum(ratios) / len(ratios) * 100
        tag = "green" if pct >= 70 else "yellow"
        log(f"[{tag}]   ✓ Keyword grounding: {pct:.0f}% of keywords appear verbatim in reviews[/{tag}]")
    if ungrounded:
        log(f"[dim]     Not found in text (paraphrase or invention): {', '.join(ungrounded[:6])}[/dim]")
    unsupported = grounding.get("aspects_without_lexical_support") or []
    if unsupported:
        log(f"[yellow]   ⚠ Aspects scored with no lexical support: {', '.join(unsupported)}[/yellow]")


def analyze(location: str, max_reviews: int = 30, progress_callback=None,
            force_refresh: bool = False, render_report: bool = False) -> dict:
    """
    Complete two-model pipeline:
      1. Apify — scrape reviews
      2. Model A (Groq) — sentiment analysis  [batched, all reviews]
      3. Model A (Groq) — guardrail analysis
      4. Model B (Groq / VERIFIER_MODEL) — independent verification
      5. apply_corrections — merge verified analysis
      6. Python scoring — deterministic final score + verdict
      7. Groq explanation — prose only, never overrides score
    """
    t0 = time.time()
    # Cost accounting covers this run only.
    METER.reset()
    # Rich panels are CLI presentation, not library behaviour: the Streamlit app
    # would otherwise dump them into the server's stdout on every run.
    if render_report:
        console.print(Panel(
            f"[bold]Location:[/bold]       {location}\n"
            f"[bold]Max reviews:[/bold]    {max_reviews}\n"
            f"[bold]Model 1 (Analyst):[/bold]  Groq / {STRONG_MODEL} (sentiment) + {FAST_MODEL} (guardrail)\n"
            f"[bold]Model 2 (Verifier):[/bold] Groq / {VERIFIER_MODEL} (independent review audit & fact-check)\n"
            f"[bold]Model 3 (Verdict):[/bold]  Groq / {VERDICT_MODEL} (final verdict & executive guide)\n"
            f"[bold]Verification:[/bold]   {'required' if REQUIRE_VERIFICATION else 'preferred (active)'}\n"
            f"[bold]Pipeline:[/bold]       Apify ➔ Model 1 (Analyst) ➔ Model 2 (Verifier) ➔ Python Scoring ➔ Model 3 (Verdict)",
            title="[bold blue]🌐 3-Model Location Review AI Analyzer[/bold blue]",
            expand=False,
        ))
    else:
        log(f"[cyan]Analyzing[/cyan] {location} (max {max_reviews} reviews)")

    # ── Stage 0: Cache lookup (hash of query + review count + schema) ──
    if not force_refresh:
        cached = read_cache(location, max_reviews)
        if cached is not None:
            if progress_callback:
                progress_callback(1, "Cache Hit", "Loading recent report from cache…")
                progress_callback(6, "Complete", "Report loaded from cache.")
            return cached

    # ── Stage 1: Scrape ──
    if progress_callback:
        progress_callback(1, "Scraping Reviews", "Collecting Google Maps reviews via Apify...")
    try:
        reviews, place_info, review_stats = scrape_reviews(location, max_reviews)
    except RuntimeError as e:
        return {"error": str(e)}

    if not reviews:
        return {"error": "No reviews found. Try a more specific location name."}

    # ── Stage 2: Model A — Sentiment (batched over all reviews) ──
    if progress_callback:
        progress_callback(2, "Model A — Sentiment", f"Analyzing {len(reviews)} reviews in batches...")
    # Aspect set follows the place category: a hotel is scored on rooms, a gym
    # on equipment. Unknown categories fall back to a generic set rather than
    # being asked about food quality.
    aspect_set = aspect_set_for_place(place_info)
    log(f"[dim]   Aspect set: {aspect_set.name} ({', '.join(aspect_set.keys)})[/dim]")

    sentiment = analyze_sentiment(reviews, aspect_set)

    # Extractive grounding: count what reviewers literally wrote, so the UI can
    # separate keywords that appear in the text from ones the model invented.
    sentiment = ground_sentiment(sentiment, reviews, aspect_set.lexicon)
    _log_grounding(sentiment)

    # ── Stage 3: Model A — Guardrail ──
    if progress_callback:
        progress_callback(3, "Model A — Guardrail", "Checking review authenticity and trust score...")
    guardrail = guardrail_analysis(reviews, sentiment)
    time.sleep(1)

    # ── Stage 4: Model B — Independent Verification ──
    if progress_callback:
        progress_callback(4, "Model B — Verification", "Independent verifier cross-auditing Model A...")
    verification = verify_analysis(reviews, sentiment, guardrail)

    # Handle REQUIRE_VERIFICATION
    if REQUIRE_VERIFICATION and verification.get("verification_status") == "UNAVAILABLE":
        return {
            "error": "Independent verification is currently unavailable.",
            "verification": verification,
            "place_info": place_info,
            "review_stats": review_stats,
        }

    # ── Stage 5: Apply corrections ──
    verified_sentiment, verified_guardrail = apply_corrections(
        sentiment, guardrail, verification
    )
    n_corrections = len([
        c for c in verification.get("corrections", [])
        if c.get("evidence_review_ids")
    ])
    if n_corrections:
        log(f"[cyan]  {n_corrections} evidence-supported correction(s) applied.[/cyan]")

    # Update analyzed count (= cleaned reviews actually fed to models)
    review_stats["analyzed_review_count"] = len(reviews)

    # ── Stage 6: Python scoring ──
    if progress_callback:
        progress_callback(5, "Python Scoring", "Computing deterministic final score and verdict...")
    # Scoring weights follow the same aspect set, so the weighted mean is taken
    # over aspects that exist for this kind of place.
    scoring_cfg = replace(DEFAULT_SCORING_CONFIG, aspect_weights=aspect_set.weights)
    final_scoring = calculate_final_score(
        reviews, place_info, verified_sentiment, verified_guardrail, verification,
        scoring_cfg,
    )

    # ── Stage 7: Groq explanation ──
    if progress_callback:
        progress_callback(6, "Generating Explanation", "Writing pros, cons, visitor tips...")
    rec = generate_recommendation(
        location, place_info, reviews,
        verified_sentiment, verified_guardrail, final_scoring
    )

    # Terminal report is CLI-only
    if render_report:
        display_report(
            location, place_info, reviews,
            verified_sentiment, verified_guardrail,
            rec, verification, review_stats
        )

    elapsed = time.time() - t0
    usage_summary = METER.summary()
    usage_summary["elapsed_seconds"] = round(elapsed, 1)
    log(
        f"\n[dim]⏱  Total time: {elapsed:.1f}s  ·  "
        f"{usage_summary['total_tokens']:,} tokens over {usage_summary['calls']} calls  ·  "
        f"~{format_cost(usage_summary['total_cost_usd'])}[/dim]"
    )

    # Save full JSON
    payload  = {
        "location":       location,
        "place_info":     place_info,
        "review_stats":   review_stats,
        "reviews":        reviews,
        "sentiment":      verified_sentiment,
        "guardrail":      verified_guardrail,
        # verification is already normalised by _normalise_verification /
        # _unavailable_verification — do NOT re-default any of it to PASS here.
        "verification":   {
            **verification,
            "corrections_count":         n_corrections,
            "missing_positive_evidence": verification.get("missing_positive_evidence", []),
            "missing_negative_evidence": verification.get("missing_negative_evidence", []),
        },
        "recommendation": rec,
        # Full deterministic breakdown (which components were used, effective
        # weights, penalties) so the UI can show how the score was built.
        "scoring":        final_scoring,
        # What this run actually cost, from the token counts the provider
        # reported (see locan/usage.py).
        "usage":          usage_summary,
        "model_info": {
            "three_model_pipeline": True,
            "model_1": {
                "role": "Primary Analyst (Model A)",
                "provider": "Groq",
                "sentiment_model": STRONG_MODEL,
                "guardrail_model": FAST_MODEL,
            },
            "model_2": {
                "role": "Independent Verifier (Model B)",
                "provider": "Groq",
                "model": VERIFIER_MODEL,
                "status": verification.get("verification_status", "UNKNOWN"),
            },
            "model_3": {
                "role": "Executive Verdict (Model C)",
                "provider": "Groq",
                "model": VERDICT_MODEL,
            },
            "model_a": {"provider": "Groq", "model": STRONG_MODEL, "fast_model": FAST_MODEL},
            "model_b": {"provider": "Groq", "model": VERIFIER_MODEL, "status": verification.get("verification_status", "UNKNOWN")},
            "verdict_model": {"provider": "Groq", "model": VERDICT_MODEL},
        },
    }
    saved_to = write_cache(location, max_reviews, payload)
    log(f"[dim]💾 Report saved → {saved_to}[/dim]")

    return payload
