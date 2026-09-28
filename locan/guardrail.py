"""Guardrail analysis: heuristic red flags plus the Model A guardrail pass."""

import json
from collections import Counter

from locan import llm
from locan.config import FAST_MODEL
from locan.logging_utils import log
from locan.reviews import (
    NEAR_DUPLICATE_THRESHOLD,
    _similar,
    _tokenise,
    validate_evidence_ids,
)

# ── MODULE 3: Guardrail Analysis (Model A / Groq) ────────────────────────────

def _heuristic_checks(reviews: list) -> dict:
    """Pure-Python pre-pass. Returns flags and stats fed into the guardrail prompt."""
    n = len(reviews)
    flags = []

    if n == 0:
        return {"flags": ["No reviews to analyze"], "stats": {}}

    ratings = [r["rating"] for r in reviews]
    texts   = [r["text"].lower() for r in reviews]
    authors = [r.get("author", "") for r in reviews]

    five_star_pct = ratings.count(5) / n
    one_star_pct  = ratings.count(1) / n
    if five_star_pct > 0.75:
        flags.append(f"Unusually high 5-star ratio ({five_star_pct:.0%}) — potential rating manipulation")
    if one_star_pct > 0.40:
        flags.append(f"High 1-star ratio ({one_star_pct:.0%}) — possible targeted negative campaign")
    if len(set(ratings)) == 1:
        flags.append("All reviews share the exact same star rating — highly suspicious uniformity")

    short_5star = [r for r in reviews if r["rating"] == 5 and len(r["text"]) < 12]
    if n > 0 and len(short_5star) / n > 0.30:
        flags.append(f"{len(short_5star)} very short 5-star reviews (< 12 chars) — likely filler boosts")

    # Tokenise once per review, not once per comparison: the inner loop used to
    # re-split both strings on every pair (~n²/2 redundant splits).
    check_n   = min(n, 30)
    token_sets = [_tokenise(t) for t in texts[:check_n]]
    duplicates = sum(
        1
        for i in range(check_n)
        for j in range(i + 1, check_n)
        if _similar(token_sets[i], token_sets[j], NEAR_DUPLICATE_THRESHOLD)
    )
    if duplicates >= 3:
        flags.append(f"{duplicates} near-duplicate review pairs (>55% word overlap)")

    ngram_counter: Counter = Counter()
    for txt in texts[:30]:
        words = txt.split()
        for k in range(len(words) - 2):
            ng = " ".join(words[k:k+3])
            if len(ng) > 8:
                ngram_counter[ng] += 1
    repeated_phrases = [ng for ng, cnt in ngram_counter.most_common(5) if cnt >= 4]
    if repeated_phrases:
        flags.append(f"Repeated phrases across reviews: {repeated_phrases[:3]} — coordinated language")

    unique_authors   = len(set(authors))
    single_rev_ratio = unique_authors / n if n > 0 else 1
    if single_rev_ratio < 0.7 and n > 8:
        flags.append(f"Low author diversity ({unique_authors} unique / {n} reviews) — possible sock-puppets")

    if n < 6:
        flags.append("Too few reviews for high-confidence analysis — treat results with caution")

    dates = [r.get("date", "")[:10] for r in reviews if r.get("date")]
    if len(dates) >= 5:
        unique_dates = len(set(dates))
        if unique_dates / len(dates) < 0.25:
            flags.append("Many reviews share the same date — possible coordinated review-bombing")

    avg_rating = sum(ratings) / n
    avg_len    = sum(len(t) for t in texts) / n

    stats = {
        "total_reviews":     n,
        "avg_rating":        round(avg_rating, 2),
        "five_star_pct":     round(five_star_pct, 2),
        "one_star_pct":      round(one_star_pct, 2),
        "avg_review_length": round(avg_len, 0),
        "unique_authors":    unique_authors,
        "duplicate_pairs":   duplicates,
        "repeated_phrases":  repeated_phrases[:3],
    }
    return {"flags": flags, "stats": stats}


def guardrail_analysis(reviews: list, sentiment: dict) -> dict:
    """
    MODEL A — Deep guardrail / authenticity analysis using Groq STRONG_MODEL.
    Uses up to 30 reviews for the LLM pass; heuristics run on all reviews.
    """
    log(
        f"\n[bold cyan]🛡  Model A — Guardrail analysis "
        f"(Groq / {FAST_MODEL})[/bold cyan]"
    )

    heuristics      = _heuristic_checks(reviews)
    heuristic_flags = heuristics["flags"]
    heuristic_stats = heuristics["stats"]

    # Send up to 18 representative reviews to the LLM (reduced to fit 6K TPM reliably)
    # Cap each review text at 120 chars to stay comfortably under 6K TPM limit
    review_sample = [
        {
            "id":     r.get("id") or f"r{i+1}",   # stable ID, never re-numbered
            "rating": r["rating"],
            "text":   r["text"][:120],            # 120 chars keeps us under the 6K TPM limit
        }
        for i, r in enumerate(reviews[:18])       # cap at 18 reviews to fit budget
    ]

    sentiment_context = {
        "overall":           sentiment.get("overall_sentiment"),
        "score":             sentiment.get("sentiment_score"),
        "positive_keywords": sentiment.get("positive_keywords", [])[:10],
        "negative_keywords": sentiment.get("negative_keywords", [])[:8],
        "themes":            sentiment.get("themes", [])[:5],
        "temporal_trend":    sentiment.get("temporal_trend", {}),
    }

    prompt = f"""Review integrity analysis. Sentiment context: {json.dumps(sentiment_context)}
Heuristic flags: {json.dumps(heuristic_flags)}
Stats: {json.dumps(heuristic_stats)}
Reviews (a sample; cite ONLY the "id" values shown here, they are not necessarily contiguous): {json.dumps(review_sample)}

Return ONLY this JSON:
{{
  "trust_score": 0.0,
  "credibility_score": 0.0,
  "fake_review_probability": 0.0,
  "review_quality": "High|Medium|Low",
  "bias_level": "Low|Medium|High",
  "bias_direction": "Positive|Negative|None",
  "linguistic_analysis": {{
    "templated_language_detected": false,
    "copy_paste_evidence": "description or null",
    "vocabulary_diversity": "High|Medium|Low",
    "writing_style_consistency": "Consistent (suspicious)|Varied (natural)|Mixed",
    "language_notes": "1-sentence observation"
  }},
  "rating_integrity": {{
    "distribution_natural": true,
    "anomalies": [],
    "inflated_stars_estimate": 0,
    "suppressed_stars_estimate": 0,
    "adjusted_true_rating": 0.0,
    "rating_notes": "1-sentence assessment"
  }},
  "reviewer_behavior": {{
    "sock_puppet_risk": "Low|Medium|High",
    "coordinated_posting_risk": "Low|Medium|High",
    "evidence": "description or None detected"
  }},
  "contradiction_analysis": [
    {{
      "aspect": "aspect name",
      "positive_claim": "what some reviewers say",
      "negative_claim": "what others say",
      "resolution": "which claim appears more credible and why"
    }}
  ],
  "aspect_credibility": {{
    "food_quality":    {{"credible": true,  "confidence": 0.9, "note": "brief note"}},
    "service":         {{"credible": true,  "confidence": 0.8, "note": "brief note"}},
    "ambience":        {{"credible": true,  "confidence": 0.7, "note": "brief note"}},
    "value_for_money": {{"credible": true,  "confidence": 0.8, "note": "brief note"}},
    "cleanliness":     {{"credible": true,  "confidence": 0.9, "note": "brief note"}},
    "crowd_wait_time": {{"credible": true,  "confidence": 0.6, "note": "brief note"}}
  }},
  "genuine_positives": [
    {{
      "aspect": "aspect name",
      "evidence": "what reviewers say",
      "confidence": 0.85,
      "supporting_review_ids": ["r1", "r3"]
    }}
  ],
  "genuine_concerns": [
    {{
      "aspect": "concern name",
      "evidence": "what reviewers say",
      "severity": "Minor|Moderate|Major",
      "supporting_review_ids": ["r2"]
    }}
  ],
  "suspicious_patterns": [],
  "verified_facts": [],
  "guardrail_summary": "2-sentence honest assessment",
  "analyst_recommendation": "1 sentence on trust level"
}}"""

    # Guardrail is structured JSON — 8B model is sufficient and saves 70B daily quota
    result = llm.call_groq(prompt, model=FAST_MODEL, max_tokens=4096)
    result = validate_evidence_ids(result, reviews, "Model A guardrail")
    result = _derive_guardrail_fallbacks(result, reviews, sentiment)

    ai_flags  = result.get("suspicious_patterns", [])
    all_flags = list(dict.fromkeys(heuristic_flags + ai_flags))
    result["suspicious_patterns"] = all_flags
    result["heuristic_stats"]     = heuristic_stats

    ts  = result.get("trust_score", 0)
    rq  = result.get("review_quality", "?")
    fp  = result.get("fake_review_probability", 0)
    adj = result.get("rating_integrity", {}).get("adjusted_true_rating", "?")
    log(
        f"[green]✓  Trust: {ts:.0%}  |  Quality: {rq}  |  "
        f"Fake prob: {fp:.0%}  |  Adj. rating: {adj}/5[/green]"
    )
    return result


def _derive_guardrail_fallbacks(result: dict, reviews: list, sentiment: dict) -> dict:
    """
    Fill *structurally* missing guardrail fields with clearly-labelled derivations
    from data we actually have.

    HARD RULE: nothing in here may invent an observation, a confidence, or a
    severity. If the guardrail model did not produce a field we either derive it
    from Model 1's own output (and mark it `derived: True`) or leave it empty.
    An empty section is honest; a fabricated one is not.
    """
    if not isinstance(result, dict):
        result = {}

    # 1. genuine_positives — derive from Model 1's positive_points only.
    #    No synthetic confidence: unknown confidence stays None.
    if not result.get("genuine_positives"):
        derived_pos = []
        for pt in sentiment.get("positive_points", []):
            if not isinstance(pt, dict):
                continue
            claim  = pt.get("claim", "")
            aspect = pt.get("aspect") or (claim.split(" - ")[0] if " - " in claim else claim[:35])
            derived_pos.append({
                "aspect":                aspect,
                "evidence":              claim,
                "confidence":            None,          # not assessed by the guardrail model
                "supporting_review_ids": pt.get("evidence_review_ids") or [],
                "derived":               True,
                "source":                "Model 1 sentiment (guardrail returned none)",
            })
        result["genuine_positives"] = derived_pos

    # 2. genuine_concerns — same treatment. Severity is NOT guessed.
    if not result.get("genuine_concerns"):
        derived_con = []
        for pt in sentiment.get("negative_points", []):
            if not isinstance(pt, dict):
                continue
            claim  = pt.get("claim", "")
            aspect = pt.get("aspect") or (claim.split(" - ")[0] if " - " in claim else claim[:35])
            derived_con.append({
                "aspect":                aspect,
                "evidence":              claim,
                "severity":              None,          # not assessed by the guardrail model
                "supporting_review_ids": pt.get("evidence_review_ids") or [],
                "derived":               True,
                "source":                "Model 1 sentiment (guardrail returned none)",
            })
        result["genuine_concerns"] = derived_con

    # 3. verified_facts — only statements computed directly from the review data.
    #    These are arithmetic, not model claims, so they are safe to state.
    if not result.get("verified_facts"):
        facts = []
        ratings = [r.get("rating") for r in reviews if r.get("rating")]
        if ratings:
            facts.append(
                f"Average rating of the analyzed sample is "
                f"{sum(ratings)/len(ratings):.1f}\u2605 across {len(reviews)} reviews."
            )
        if sentiment.get("positive_keywords"):
            facts.append(
                "Positive keywords extracted by Model 1: "
                + ", ".join(sentiment["positive_keywords"][:4]) + "."
            )
        if sentiment.get("negative_keywords"):
            facts.append(
                "Critical keywords extracted by Model 1: "
                + ", ".join(sentiment["negative_keywords"][:3]) + "."
            )
        result["verified_facts"] = facts

    return result
