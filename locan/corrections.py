"""Apply Model B's accepted corrections to Model A's analysis."""

import re

from locan.logging_utils import log
from locan.verify import VERIFICATION_COMPLETED

# ── MODULE 5: Apply Corrections ───────────────────────────────────────────────

def apply_corrections(sentiment: dict, guardrail: dict, verification: dict) -> tuple:
    """
    Apply evidence-supported corrections from Model B to Model A's output.
    Returns (verified_sentiment, verified_guardrail).

    Rules:
    - Only apply a correction if evidence_review_ids is non-empty.
    - Never apply a correction without review evidence.
    - Does not change the final score (that is Python's job).
    """
    if not verification or verification.get("verification_status") not in VERIFICATION_COMPLETED:
        # Verifier never completed — nothing trustworthy to apply
        return sentiment.copy(), guardrail.copy()

    corrections = verification.get("corrections", [])
    if not corrections:
        return sentiment.copy(), guardrail.copy()

    v_sentiment = sentiment.copy()
    v_guardrail = guardrail.copy()

    for corr in corrections:
        # Only apply if there is actual review evidence
        evidence_ids = corr.get("evidence_review_ids", [])
        if not evidence_ids:
            log(
                f"[dim]  Skipping correction for '{corr.get('field')}' "
                f"— no evidence_review_ids provided[/dim]"
            )
            continue

        field   = corr.get("field", "")
        new_val = corr.get("corrected_claim", "")
        reason  = corr.get("reason", "")

        log(
            f"[cyan]  Applying correction: {field} — {reason[:80]}[/cyan]"
        )

        # ── Aspect sentiment corrections ──
        if field.startswith("aspects."):
            aspect_key = field.split(".", 1)[1]
            asp = v_sentiment.get("aspect_scores", {}).get(aspect_key)
            if isinstance(asp, dict) and new_val:
                # Only update if the corrected claim contains an explicit NEW score
                # that is meaningfully different from the existing one
                score_match = re.search(r'\b(\d+(?:\.\d+)?)\b', new_val)
                if score_match:
                    candidate = float(score_match.group(1))
                    if 0.0 <= candidate <= 10.0:
                        existing_score = asp.get("score")
                        # Only apply if the correction actually changes the score by > 0.5
                        if existing_score is None or abs(candidate - existing_score) > 0.5:
                            asp["score"]   = candidate
                            asp["summary"] = new_val[:120]
                            v_sentiment["aspect_scores"][aspect_key] = asp

        # ── Overall sentiment correction ──
        elif field == "sentiment" or field == "sentiment.overall":
            if "negative" in new_val.lower():
                v_sentiment["overall_sentiment"] = "Negative"
                if v_sentiment.get("sentiment_score", 0) > 0:
                    v_sentiment["sentiment_score"] = -abs(v_sentiment["sentiment_score"])
            elif "positive" in new_val.lower():
                v_sentiment["overall_sentiment"] = "Positive"
                if v_sentiment.get("sentiment_score", 0) < 0:
                    v_sentiment["sentiment_score"] = abs(v_sentiment["sentiment_score"])
            elif "mixed" in new_val.lower():
                v_sentiment["overall_sentiment"] = "Mixed"

        # ── Guardrail / trust corrections ──
        elif field.startswith("guardrail"):
            # Add the correction as a new genuine concern with evidence
            new_concern = {
                "aspect":              corr.get("field", "verified concern"),
                "evidence":            new_val[:200],
                "severity":            "Moderate",
                "supporting_review_ids": evidence_ids,
                "source":              "Model B correction",
            }
            concerns = v_guardrail.get("genuine_concerns", [])
            concerns.append(new_concern)
            v_guardrail["genuine_concerns"] = concerns

        # ── Keyword corrections — only remove if corrected_claim says unsupported ──
        elif field == "keywords.positive":
            bad_kw = corr.get("original_claim", "").lower().strip()
            corrected = corr.get("corrected_claim", "").lower()
            if "not" in corrected or "unsupported" in corrected or "absent" in corrected or "incorrect" in corrected:
                v_sentiment["positive_keywords"] = [
                    kw for kw in v_sentiment.get("positive_keywords", [])
                    if kw.lower() != bad_kw
                ]
        elif field == "keywords.negative":
            bad_kw = corr.get("original_claim", "").lower().strip()
            corrected = corr.get("corrected_claim", "").lower()
            if "not" in corrected or "unsupported" in corrected or "absent" in corrected or "incorrect" in corrected:
                v_sentiment["negative_keywords"] = [
                    kw for kw in v_sentiment.get("negative_keywords", [])
                    if kw.lower() != bad_kw
                ]

    return v_sentiment, v_guardrail
