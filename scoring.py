"""
Deterministic scoring engine.

Nothing in this module talks to a network, a model, or the filesystem: given the
same inputs it always returns the same verdict. That is the whole point of the
project's architecture — the LLMs describe, Python decides — so this is the part
that most deserves to be pure, configurable, and tested.

Two design rules:

1. **Every tunable lives in `ScoringConfig`.** Previously ~30 magic numbers were
   scattered through one 170-line function, so the weights documented in the
   docstring were not the weights actually applied.

2. **A component that has no data is dropped, not defaulted.** The old engine
   substituted 5.0/10 for missing aspect scores and consistency, which quietly
   dragged every under-documented place toward "mediocre" and made "we don't
   know" indistinguishable from "it's average". Now the remaining weights are
   renormalised over whatever evidence actually exists, and the breakdown
   reports which components were used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

# Statuses that represent a real, completed independent audit. Kept here (rather
# than imported from location.py) so this module stays dependency-free.
VERIFICATION_COMPLETED = ("PASS", "CORRECTED", "FAIL")


@dataclass(frozen=True)
class ScoringConfig:
    """All tunables for the composite score. Frozen: treat as a value object."""

    # ── Component weights ────────────────────────────────────────────────────
    # Applied only to components that have data, then renormalised to sum to 1.
    weights: Mapping[str, float] = field(default_factory=lambda: {
        "sentiment":   0.30,   # Model 1's overall sentiment, mapped to 0-10
        "aspect":      0.25,   # weighted mean of the aspects that were scored
        "rating":      0.15,   # Google's own star rating (or the scraped mean)
        "trust":       0.15,   # guardrail authenticity, adjusted for verification
        "consistency": 0.10,   # agreement *between* reviewers (dispersion, not level)
        "recency":     0.05,   # only when a genuine temporal trend exists
    })

    # Relative importance of each aspect inside the aspect component.
    aspect_weights: Mapping[str, float] = field(default_factory=lambda: {
        "food_quality":    1.5,
        "service":         1.5,
        "ambience":        1.2,
        "value_for_money": 1.0,
        "cleanliness":     1.0,
        "crowd_wait_time": 0.8,
        "accessibility":   0.5,
    })

    # ── Trust ────────────────────────────────────────────────────────────────
    # Unknown trust is neutral, never optimistic: absence of evidence about
    # authenticity is not evidence of authenticity.
    default_trust_score: float = 0.5
    default_fake_probability: float = 0.2
    fake_probability_factor: float = 0.5     # how hard fake-risk pulls trust down
    unverified_trust_multiplier: float = 0.85  # applied when Model 2 did not complete

    # ── Risk penalties (subtracted from the 0-10 composite) ──────────────────
    severity_penalties: Mapping[str, float] = field(default_factory=lambda: {
        "Major": 1.5, "Moderate": 0.8, "Minor": 0.2,
    })
    evidenced_correction_penalty: float = 0.3
    max_risk_penalty: float = 3.0

    # ── Consistency ──────────────────────────────────────────────────────────
    consistency_min_reviews: int = 3
    # Per-review sentiment lives on -1..+1, so the maximum possible standard
    # deviation is 1.0 (a perfectly polarised set). A factor of 10 therefore maps
    # "total disagreement" to 0/10. The previous factor of 5 was calibrated for
    # some other range and bottomed out at 5.5/10, so the component could never
    # actually signal that reviewers disagreed.
    consistency_std_factor: float = 10.0

    # ── Recency ──────────────────────────────────────────────────────────────
    declining_trend_penalty: float = 1.5
    improving_trend_bonus: float = 1.0

    # ── Verdict thresholds (inclusive lower bounds, descending) ──────────────
    verdict_thresholds: tuple = (
        (8.0, "HIGHLY RECOMMENDED"),
        (6.5, "RECOMMENDED"),
        (4.5, "VISIT WITH CAUTION"),
    )
    lowest_verdict: str = "NOT RECOMMENDED"

    # ── Confidence ───────────────────────────────────────────────────────────
    # This is a data-sufficiency heuristic, not a probability. Named honestly in
    # the breakdown as `data_sufficiency`.
    confidence_full_sample: int = 50      # review count at which sample size stops helping
    consistency_confidence_bonus: float = 0.15
    high_trust_confidence_bonus: float = 0.10
    high_trust_threshold: float = 0.80
    verification_confidence_bonus: float = 0.10   # scaled by audit coverage
    corrected_confidence_penalty: float = 0.05
    failed_confidence_penalty: float = 0.20
    unverified_confidence_penalty: float = 0.15
    # Minimum reviews before we are willing to call the data adequate at all.
    min_reviews_for_confidence: int = 5


DEFAULT_CONFIG = ScoringConfig()


# ── Component calculations (each returns a 0-10 score, or None if no data) ────

def sentiment_component(sentiment: dict) -> Optional[float]:
    """Map Model 1's -1..+1 sentiment score onto 0-10."""
    raw = sentiment.get("sentiment_score")
    if not isinstance(raw, (int, float)):
        return None
    return round((max(-1.0, min(1.0, raw)) + 1) / 2 * 10, 2)


def aspect_component(sentiment: dict, cfg: ScoringConfig = DEFAULT_CONFIG) -> Optional[float]:
    """Weighted mean over aspects that were actually scored. None if none were."""
    asp_scores = sentiment.get("aspect_scores") or {}
    weighted_sum = weight_total = 0.0
    for key, weight in cfg.aspect_weights.items():
        entry = asp_scores.get(key)
        score = entry.get("score") if isinstance(entry, dict) else None
        if isinstance(score, (int, float)):
            weighted_sum += score * weight
            weight_total += weight
    if weight_total == 0:
        return None
    return round(weighted_sum / weight_total, 2)


def rating_component(place_info: dict, reviews: list) -> Optional[float]:
    """Google's 5-star rating on a 0-10 scale, else the scraped sample mean."""
    google_score = place_info.get("google_score")
    if isinstance(google_score, (int, float)) and google_score > 0:
        return round(float(google_score) * 2, 2)
    sample = [r.get("rating") for r in reviews if isinstance(r.get("rating"), (int, float))]
    if sample:
        return round(sum(sample) / len(sample) * 2, 2)
    return None


def trust_component(
    guardrail: dict,
    verification: dict,
    cfg: ScoringConfig = DEFAULT_CONFIG,
) -> Optional[float]:
    """
    Authenticity score, adjusted by how much independent verification happened.

    A completed audit that self-reports an accuracy scales trust by it. A run
    where verification did not complete is *discounted*, never boosted — the old
    engine multiplied trust by a fabricated 0.92 accuracy in exactly that case.
    """
    raw_trust = guardrail.get("trust_score")
    raw_fake  = guardrail.get("fake_review_probability")
    if not isinstance(raw_trust, (int, float)) and not isinstance(raw_fake, (int, float)):
        return None   # the guardrail told us nothing — don't invent a trust level

    trust = raw_trust if isinstance(raw_trust, (int, float)) else cfg.default_trust_score
    fake  = raw_fake  if isinstance(raw_fake,  (int, float)) else cfg.default_fake_probability

    comp = (trust - fake * cfg.fake_probability_factor) * 10

    status   = verification.get("verification_status")
    accuracy = verification.get("accuracy")
    if status in VERIFICATION_COMPLETED and isinstance(accuracy, (int, float)):
        comp *= 0.5 + accuracy * 0.5
    elif status not in VERIFICATION_COMPLETED:
        comp *= cfg.unverified_trust_multiplier

    return round(max(0.0, min(10.0, comp)), 2)


def consistency_component(
    sentiment: dict,
    cfg: ScoringConfig = DEFAULT_CONFIG,
) -> Optional[float]:
    """
    How much reviewers agree with each other (low dispersion → high score).

    This is deliberately a *dispersion* measure. It shares an input with the
    sentiment component, so it must never be read as a second opinion on how
    good the place is.
    """
    per_review = sentiment.get("per_review") or []
    scores = [p.get("score") for p in per_review
              if isinstance(p, dict) and isinstance(p.get("score"), (int, float))]
    if len(scores) < cfg.consistency_min_reviews:
        return None
    mean = sum(scores) / len(scores)
    std_dev = (sum((s - mean) ** 2 for s in scores) / len(scores)) ** 0.5
    return round(max(0.0, 10 - std_dev * cfg.consistency_std_factor), 2)


def recency_component(
    sentiment: dict,
    cfg: ScoringConfig = DEFAULT_CONFIG,
) -> Optional[float]:
    """
    Recent sentiment, adjusted by trend direction.

    Returns None unless the model reported a real `recent_score`. The old code
    fell back to the overall sentiment score here, which meant the same signal
    was counted as sentiment (30%), as recency (5%) and — via per-review scores —
    inside consistency (10%): an effective sentiment weight of ~45%, not 30%.
    """
    trend = sentiment.get("temporal_trend") or {}
    recent = trend.get("recent_score")
    if not isinstance(recent, (int, float)):
        return None
    comp = (max(-1.0, min(1.0, recent)) + 1) / 2 * 10
    label = trend.get("trend")
    if label == "Declining":
        comp -= cfg.declining_trend_penalty
    elif label == "Improving":
        comp += cfg.improving_trend_bonus
    return round(max(0.0, min(10.0, comp)), 2)


def risk_penalty(
    guardrail: dict,
    verification: dict,
    cfg: ScoringConfig = DEFAULT_CONFIG,
) -> float:
    """
    Penalty for graded concerns and evidence-backed corrections.

    Concerns merely *derived* from Model 1's sentiment carry severity=None and
    are skipped: they are already inside the sentiment component, so charging
    for them here would penalise the same signal twice.
    """
    penalty = 0.0
    for concern in guardrail.get("genuine_concerns") or []:
        if not isinstance(concern, dict) or concern.get("derived"):
            continue
        penalty += cfg.severity_penalties.get(concern.get("severity"), 0.0)
    for correction in verification.get("corrections") or []:
        if isinstance(correction, dict) and correction.get("evidence_review_ids"):
            penalty += cfg.evidenced_correction_penalty
    return round(min(penalty, cfg.max_risk_penalty), 2)


def verdict_for(score: float, cfg: ScoringConfig = DEFAULT_CONFIG) -> str:
    for threshold, label in cfg.verdict_thresholds:
        if score >= threshold:
            return label
    return cfg.lowest_verdict


def data_sufficiency(
    n_reviews: int,
    components: dict,
    guardrail: dict,
    verification: dict,
    cfg: ScoringConfig = DEFAULT_CONFIG,
) -> float:
    """
    How much the inputs support the verdict: sample size, reviewer agreement,
    trust, and how much of the analysis was independently audited.

    Surfaced as "confidence" in the UI, but it is a data-sufficiency heuristic
    and not a calibrated probability.
    """
    conf = min(1.0, n_reviews / cfg.confidence_full_sample)
    if n_reviews < cfg.min_reviews_for_confidence:
        conf *= 0.5

    consistency = components.get("consistency")
    if isinstance(consistency, (int, float)) and consistency >= 7:
        conf = min(1.0, conf + cfg.consistency_confidence_bonus)

    trust = guardrail.get("trust_score")
    if isinstance(trust, (int, float)) and trust >= cfg.high_trust_threshold:
        conf = min(1.0, conf + cfg.high_trust_confidence_bonus)

    # Verification only helps in proportion to how much was really audited.
    status   = verification.get("verification_status")
    coverage = verification.get("coverage")
    coverage = coverage if isinstance(coverage, (int, float)) else 0.0
    accuracy = verification.get("accuracy")

    if status == "PASS":
        conf = min(1.0, conf + cfg.verification_confidence_bonus * coverage)
        if isinstance(accuracy, (int, float)):
            conf = min(1.0, conf * (0.7 + accuracy * 0.3))
    elif status == "CORRECTED":
        conf = max(0.0, conf - cfg.corrected_confidence_penalty)
    elif status == "FAIL":
        conf = max(0.0, conf - cfg.failed_confidence_penalty)
    else:   # UNAVAILABLE / UNKNOWN — nothing was independently checked
        conf = max(0.0, conf - cfg.unverified_confidence_penalty)

    return round(max(0.0, min(1.0, conf)), 3)


# ── Public entry point ────────────────────────────────────────────────────────

def score_location(
    reviews: list,
    place_info: dict,
    sentiment: dict,
    guardrail: dict,
    verification: dict,
    cfg: ScoringConfig = DEFAULT_CONFIG,
) -> dict:
    """Compute the composite score, verdict, and a fully transparent breakdown."""
    components = {
        "sentiment":   sentiment_component(sentiment),
        "aspect":      aspect_component(sentiment, cfg),
        "rating":      rating_component(place_info, reviews),
        "trust":       trust_component(guardrail, verification, cfg),
        "consistency": consistency_component(sentiment, cfg),
        "recency":     recency_component(sentiment, cfg),
    }

    available = {k: v for k, v in components.items() if isinstance(v, (int, float))}
    weight_total = sum(cfg.weights.get(k, 0.0) for k in available)

    if weight_total > 0:
        # Renormalise over the components we actually have evidence for.
        effective_weights = {k: cfg.weights.get(k, 0.0) / weight_total for k in available}
        composite = sum(available[k] * w for k, w in effective_weights.items())
    else:
        effective_weights = {}
        composite = 0.0

    penalty = risk_penalty(guardrail, verification, cfg)
    final_score = round(max(0.0, min(10.0, composite - penalty)), 2)
    verdict = verdict_for(final_score, cfg)
    confidence = data_sufficiency(len(reviews), components, guardrail, verification, cfg)

    breakdown = {
        # Legacy keys, kept so existing report JSON and the UI keep working.
        "sentiment_comp":   components["sentiment"],
        "aspect_comp":      components["aspect"],
        "rating_comp":      components["rating"],
        "trust_comp":       components["trust"],
        "consistency_comp": components["consistency"],
        "recency_comp":     components["recency"],
        "risk_penalty":     penalty,
        "composite_raw":    round(composite, 2),
        "final_score":      final_score,
        # Transparency: what was used, and with what effective weight.
        "components_used":     sorted(available),
        "components_missing":  sorted(k for k in components if k not in available),
        "effective_weights":   {k: round(w, 4) for k, w in effective_weights.items()},
        "configured_weights":  dict(cfg.weights),
    }

    return {
        "verdict":         verdict,
        "score":           final_score,
        "confidence":      confidence,
        "data_sufficiency": confidence,   # honest alias
        "score_breakdown": breakdown,
    }
