"""Model A — batched deep sentiment analysis."""

import os
from concurrent.futures import ThreadPoolExecutor

from locan import llm
from locan.config import STRONG_MODEL
from locan.logging_utils import log
from locan.reviews import validate_evidence_ids

# Reviews per Groq call — keeps each batch inside the model's token limit.
SENTIMENT_BATCH_SIZE = 15

# Sentiment batches are independent and safe to run concurrently; the shared
# token bucket keeps the whole pool inside Groq's per-model quota.
SENTIMENT_MAX_WORKERS = int(os.getenv("SENTIMENT_MAX_WORKERS", "3"))

# Spread above which a batch is treated as polarised when merging.
POLARISED_BATCH_SPREAD = 0.6

# ── MODULE 2: Model A — Sentiment Analysis (Groq, batched) ───────────────────

def _sentiment_prompt_for_batch(batch: list, batch_offset: int) -> str:
    """Build the sentiment analysis prompt for one batch of reviews."""
    reviews_block = "\n---\n".join(
        f"[{r.get('id') or f'r{batch_offset + i + 1}'}] ⭐{r['rating']}/5  "
        f"date:{str(r.get('date',''))[:10]}\n{r['text'][:350]}"
        for i, r in enumerate(batch)
    )
    return f"""You are an expert review analyst. Perform DEEP multi-dimensional sentiment analysis
on the following location reviews. Review IDs are shown as [rN] — use them in evidence fields.
Return ONLY valid JSON matching this EXACT structure (no markdown, no explanation):

{{
  "per_review": [
    {{
      "id": "r1",
      "sentiment": "Positive|Negative|Neutral|Mixed",
      "score": 0.75,
      "emotion": "Excited|Happy|Satisfied|Neutral|Disappointed|Frustrated|Angry",
      "intensity": "Low|Medium|High",
      "key_phrase": "one crisp sentence capturing the review"
    }}
  ],
  "aspect_scores": {{
    "food_quality":    {{"score": 7.5, "reviews_mentioning": 5, "summary": "brief note or null", "evidence_review_ids": ["r1"]}},
    "service":         {{"score": 8.0, "reviews_mentioning": 3, "summary": "brief note or null", "evidence_review_ids": []}},
    "ambience":        {{"score": 6.5, "reviews_mentioning": 2, "summary": "brief note or null", "evidence_review_ids": []}},
    "value_for_money": {{"score": 7.0, "reviews_mentioning": 2, "summary": "brief note or null", "evidence_review_ids": []}},
    "cleanliness":     {{"score": 8.5, "reviews_mentioning": 1, "summary": "brief note or null", "evidence_review_ids": []}},
    "accessibility":   {{"score": 7.0, "reviews_mentioning": 1, "summary": "brief note or null", "evidence_review_ids": []}},
    "crowd_wait_time": {{"score": 5.5, "reviews_mentioning": 3, "summary": "brief note or null", "evidence_review_ids": []}}
  }},
  "themes": [
    {{
      "name": "theme name",
      "sentiment": "Positive|Negative|Mixed",
      "frequency": 3,
      "representative_quote": "exact short quote",
      "evidence": "1-sentence synthesis",
      "evidence_review_ids": ["r1", "r3"]
    }}
  ],
  "positive_points": [
    {{"claim": "Food is consistently praised", "evidence_review_ids": ["r1", "r4"]}}
  ],
  "negative_points": [
    {{"claim": "Parking is difficult", "evidence_review_ids": ["r2", "r7"]}}
  ],
  "positive_keywords": ["keyword1", "keyword2"],
  "negative_keywords": ["keyword1", "keyword2"],
  "standout_positive_quote": "most positive sentence verbatim",
  "standout_negative_quote": "most critical sentence verbatim",
  "overall_sentiment": "Positive|Negative|Neutral|Mixed",
  "sentiment_score": 0.65,
  "emotional_tone": "Excited|Happy|Satisfied|Disappointed|Angry|Neutral",
  "emotion_distribution": {{
    "Excited": 0, "Happy": 0, "Satisfied": 0,
    "Neutral": 0, "Disappointed": 0, "Frustrated": 0, "Angry": 0
  }},
  "crowd_profile": {{
    "dominant_visitor_type": "Families|Couples|Solo travellers|Business visitors|Tourists|Locals|Mixed",
    "mention_evidence": "brief evidence",
    "accessibility_notes": "any accessibility mentions"
  }},
  "temporal_trend": {{
    "recent_sentiment": "Positive|Negative|Neutral|Mixed",
    "recent_score": 0.7,
    "older_sentiment": "Positive|Negative|Neutral|Mixed",
    "older_score": 0.6,
    "trend": "Improving|Declining|Stable",
    "trend_explanation": "1-sentence reason"
  }},
  "review_diversity": "High|Medium|Low"
}}

RULES:
- Use null score and 0 reviews_mentioning if an aspect is never mentioned
- sentiment_score: -1.0 (very negative) to +1.0 (very positive)
- aspect scores: 0-10
- Include ALL evidence_review_ids that support each claim
- At least 3 themes if review count allows

REVIEWS:
{reviews_block}"""


def _merge_sentiment_batches(batch_results: list) -> dict:
    """Merge multiple batch sentiment results into one combined result."""
    if not batch_results:
        return {}
    if len(batch_results) == 1:
        return batch_results[0]

    merged = {
        "per_review":        [],
        "positive_keywords": [],
        "negative_keywords": [],
        "themes":            [],
        "positive_points":   [],
        "negative_points":   [],
        "emotion_distribution": {
            "Excited": 0, "Happy": 0, "Satisfied": 0,
            "Neutral": 0, "Disappointed": 0, "Frustrated": 0, "Angry": 0
        },
    }

    aspect_keys = ["food_quality","service","ambience","value_for_money",
                   "cleanliness","accessibility","crowd_wait_time"]
    aspect_accum = {k: {"scores": [], "mentions": 0, "evidence_ids": [], "summaries": []}
                    for k in aspect_keys}

    all_scores   = []
    trend_latest = None

    for br in batch_results:
        merged["per_review"].extend(br.get("per_review", []))

        # keywords — merge unique
        for kw in br.get("positive_keywords", []):
            if kw not in merged["positive_keywords"]:
                merged["positive_keywords"].append(kw)
        for kw in br.get("negative_keywords", []):
            if kw not in merged["negative_keywords"]:
                merged["negative_keywords"].append(kw)

        # themes — merge by name
        existing_theme_names = {t["name"] for t in merged["themes"] if isinstance(t, dict)}
        for t in br.get("themes", []):
            if isinstance(t, dict):
                if t.get("name") not in existing_theme_names:
                    merged["themes"].append(t)
                    existing_theme_names.add(t.get("name"))
                else:
                    # accumulate frequency
                    for mt in merged["themes"]:
                        if isinstance(mt, dict) and mt.get("name") == t.get("name"):
                            mt["frequency"] = mt.get("frequency", 0) + t.get("frequency", 0)
                            for eid in t.get("evidence_review_ids", []):
                                if eid not in mt.get("evidence_review_ids", []):
                                    mt.setdefault("evidence_review_ids", []).append(eid)
                            break

        # positive / negative points
        for pp in br.get("positive_points", []):
            merged["positive_points"].append(pp)
        for np_ in br.get("negative_points", []):
            merged["negative_points"].append(np_)

        # emotion distribution
        for emo, cnt in br.get("emotion_distribution", {}).items():
            if emo in merged["emotion_distribution"]:
                merged["emotion_distribution"][emo] += (cnt or 0)

        # aspect scores — weighted average
        for k in aspect_keys:
            asp = br.get("aspect_scores", {}).get(k, {})
            if isinstance(asp, dict) and asp.get("score") is not None:
                aspect_accum[k]["scores"].append(asp["score"])
                aspect_accum[k]["mentions"] += asp.get("reviews_mentioning", 0)
                aspect_accum[k]["evidence_ids"].extend(asp.get("evidence_review_ids", []))
                if asp.get("summary"):
                    aspect_accum[k]["summaries"].append(asp["summary"])

        # overall score
        s = br.get("sentiment_score")
        if s is not None:
            all_scores.append(s)

        # take temporal trend from first batch (most recent reviews)
        if trend_latest is None:
            trend_latest = br.get("temporal_trend")

        # standout quotes — take best from first non-empty
        if not merged.get("standout_positive_quote") and br.get("standout_positive_quote"):
            merged["standout_positive_quote"] = br["standout_positive_quote"]
        if not merged.get("standout_negative_quote") and br.get("standout_negative_quote"):
            merged["standout_negative_quote"] = br["standout_negative_quote"]

        # crowd profile — take first
        if not merged.get("crowd_profile") and br.get("crowd_profile"):
            merged["crowd_profile"] = br["crowd_profile"]

    # Finalise aspect scores
    merged_aspects = {}
    for k in aspect_keys:
        acc = aspect_accum[k]
        if acc["scores"]:
            avg_score = round(sum(acc["scores"]) / len(acc["scores"]), 2)
            summary   = acc["summaries"][0] if acc["summaries"] else None
            merged_aspects[k] = {
                "score":              avg_score,
                "reviews_mentioning": acc["mentions"],
                "summary":            summary,
                "evidence_review_ids": list(dict.fromkeys(acc["evidence_ids"])),
            }
        else:
            merged_aspects[k] = {"score": None, "reviews_mentioning": 0,
                                  "summary": None, "evidence_review_ids": []}
    merged["aspect_scores"] = merged_aspects

    # Overall sentiment score
    merged["sentiment_score"] = round(sum(all_scores) / len(all_scores), 3) if all_scores else 0.0

    # Overall sentiment label.
    # Averaging alone is misleading: batches of +0.9 and -0.6 average to +0.15
    # and would be labelled "Neutral", when the truth is that reviewers are
    # sharply split. Spread across batches therefore overrides the mean.
    s = merged["sentiment_score"]
    spread = (max(all_scores) - min(all_scores)) if len(all_scores) > 1 else 0.0
    if spread > POLARISED_BATCH_SPREAD:
        merged["overall_sentiment"] = "Mixed"
    elif s >= 0.4:
        merged["overall_sentiment"] = "Positive"
    elif s <= -0.3:
        merged["overall_sentiment"] = "Negative"
    elif -0.15 <= s <= 0.15:
        merged["overall_sentiment"] = "Neutral"
    else:
        merged["overall_sentiment"] = "Mixed"
    merged["batch_score_spread"] = round(spread, 3)

    if trend_latest:
        merged["temporal_trend"] = trend_latest

    return merged


def analyze_sentiment(reviews: list) -> dict:
    """
    MODEL A — Deep sentiment analysis using Groq (STRONG_MODEL).
    Processes ALL reviews via batching — no arbitrary [:20] truncation.
    Batch size is SENTIMENT_BATCH_SIZE (default 15) to stay within token limits.
    """
    log(
        f"\n[bold cyan]🧠  Model A — Sentiment analysis (Groq / {STRONG_MODEL})[/bold cyan]  "
        f"[dim]{len(reviews)} reviews[/dim]"
    )

    if not reviews:
        return {}

    # ── Split into batches ──
    batches = [reviews[i:i+SENTIMENT_BATCH_SIZE]
               for i in range(0, len(reviews), SENTIMENT_BATCH_SIZE)]

    def _run_batch(indexed):
        b_idx, batch = indexed
        offset = b_idx * SENTIMENT_BATCH_SIZE
        log(
            f"[dim]  Batch {b_idx+1}/{len(batches)} — reviews "
            f"r{offset+1}–r{offset+len(batch)}[/dim]"
        )
        prompt = _sentiment_prompt_for_batch(batch, offset)
        return b_idx, llm.call_groq(prompt, model=STRONG_MODEL, max_tokens=4096)

    # Batches are independent, so run them concurrently. The token-bucket limiter
    # inside call_groq enforces Groq's TPM/RPM budget, which the old flat
    # sleep(1.2) between serial calls only approximated.
    workers = max(1, min(SENTIMENT_MAX_WORKERS, len(batches)))
    if workers == 1 or len(batches) == 1:
        results = [_run_batch((i, b)) for i, b in enumerate(batches)]
    else:
        log(f"[dim]  Running {len(batches)} batches across {workers} workers[/dim]")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_run_batch, enumerate(batches)))

    # Order matters: batch 0 holds the most recent reviews and supplies the
    # temporal trend, so restore submission order before merging.
    batch_results = [r for _, r in sorted(results, key=lambda pair: pair[0])]

    merged = validate_evidence_ids(_merge_sentiment_batches(batch_results), reviews, "Model A sentiment")

    # ── Always compute rating distribution from raw data ──
    counts = {"5": 0, "4": 0, "3": 0, "2": 0, "1": 0}
    for r in reviews:
        k = str(max(1, min(5, int(r.get("rating", 3)))))
        counts[k] = counts.get(k, 0) + 1
    merged["rating_counts"] = counts

    # ── Log summary ──
    s  = merged.get("sentiment_score", 0)
    o  = merged.get("overall_sentiment", "Unknown")
    tr = merged.get("temporal_trend", {}).get("trend", "?")
    kw = ", ".join(merged.get("positive_keywords", [])[:5]) or "—"
    log(
        f"[green]✓  Model A sentiment: {o}  |  Score: {s:.2f}  |  "
        f"Trend: {tr}  |  Top keywords: {kw}[/green]"
    )
    return merged
