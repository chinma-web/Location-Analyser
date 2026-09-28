"""
Compare mode: two to four places, side by side.

The hard part is not building the table — it is refusing to declare a winner
the data does not support. Two places separated by 0.2 points, one of them
scored from nine reviews, is a tie; saying otherwise would be exactly the kind
of false precision the rest of this codebase has been stripped of.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_PLACES = 2
MAX_PLACES = 4

# Score gap (0-10) below which two places are called a tie. Roughly the
# resolution of the scoring engine: component rounding alone moves a score by
# ~0.1, and sampling 30 of a few thousand reviews moves it considerably more.
MEANINGFUL_GAP = 0.5

# Below this data-sufficiency figure a place's score is reported but excluded
# from "winner" claims.
MIN_CONFIDENCE_FOR_WINNER = 0.5


@dataclass
class Entry:
    """One place in a comparison, flattened out of a full analysis payload."""
    location: str
    name: str
    category: str = ""
    score: float | None = None
    verdict: str = ""
    confidence: float = 0.0
    trust: float | None = None
    google_rating: float | None = None
    reviews_analyzed: int = 0
    aspects: dict = None
    verification_status: str = "UNKNOWN"
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and isinstance(self.score, (int, float))

    def as_dict(self) -> dict:
        return {
            "location": self.location, "name": self.name, "category": self.category,
            "score": self.score, "verdict": self.verdict, "confidence": self.confidence,
            "trust": self.trust, "google_rating": self.google_rating,
            "reviews_analyzed": self.reviews_analyzed, "aspects": self.aspects or {},
            "verification_status": self.verification_status, "error": self.error,
        }


def entry_from_report(report: dict, location: str = "") -> Entry:
    """Flatten one analyze() payload into the handful of fields we compare on."""
    report = report or {}
    location = location or report.get("location", "") or ""

    if report.get("error"):
        return Entry(location=location, name=location, error=str(report["error"]))

    place = report.get("place_info") or {}
    scoring = report.get("scoring") or {}
    sentiment = report.get("sentiment") or {}
    guardrail = report.get("guardrail") or {}
    verification = report.get("verification") or {}

    aspects = {}
    for key, value in (sentiment.get("aspect_scores") or {}).items():
        score = value.get("score") if isinstance(value, dict) else None
        if isinstance(score, (int, float)):
            aspects[key] = float(score)

    return Entry(
        location=location,
        name=place.get("name") or location,
        category=place.get("category", ""),
        score=scoring.get("score"),
        verdict=scoring.get("verdict", ""),
        confidence=scoring.get("confidence") or 0.0,
        trust=guardrail.get("trust_score"),
        google_rating=place.get("google_score"),
        reviews_analyzed=len(report.get("reviews") or []),
        aspects=aspects,
        verification_status=verification.get("verification_status", "UNKNOWN"),
    )


def _rank(entries: list) -> list:
    """Scored places best-first; unscored ones keep their input order at the end."""
    scored = [e for e in entries if e.ok]
    scored.sort(key=lambda e: (-(e.score or 0), -e.confidence, e.name))
    return scored + [e for e in entries if not e.ok]


def aspect_matrix(entries: list) -> dict:
    """
    {aspect: {place_name: score}} over every aspect any place was scored on.

    Places of different categories have different aspect sets, so the matrix is
    sparse by design — a missing cell means "not applicable or never scored",
    never zero.
    """
    matrix: dict = {}
    for entry in entries:
        for aspect, score in (entry.aspects or {}).items():
            matrix.setdefault(aspect, {})[entry.name] = score
    return matrix


def aspect_winners(entries: list) -> dict:
    """
    Per-aspect best place — but only where the aspect was scored for at least
    two places and the gap clears MEANINGFUL_GAP.
    """
    winners = {}
    for aspect, scores in aspect_matrix(entries).items():
        if len(scores) < 2:
            continue
        ordered = sorted(scores.items(), key=lambda kv: -kv[1])
        (best_name, best), (_, runner_up) = ordered[0], ordered[1]
        winners[aspect] = {
            "winner": best_name if best - runner_up >= MEANINGFUL_GAP else None,
            "best_score": best,
            "gap": round(best - runner_up, 2),
            "scored_places": len(scores),
        }
    return winners


def _caveats(entries: list, ranked: list) -> list:
    """Everything that should make a reader distrust a naive reading of the table."""
    notes = []

    failed = [e for e in entries if e.error]
    if failed:
        notes.append(f"{len(failed)} place(s) could not be analysed: "
                     + "; ".join(f"{e.location} ({e.error})" for e in failed))

    thin = [e for e in entries if e.ok and e.confidence < MIN_CONFIDENCE_FOR_WINNER]
    if thin:
        notes.append("Low data sufficiency (excluded from the winner call): "
                     + ", ".join(f"{e.name} {e.confidence:.0%}" for e in thin))

    counts = {e.reviews_analyzed for e in entries if e.ok}
    if counts and max(counts) >= 2 * max(min(counts), 1):
        notes.append(f"Uneven sample sizes ({min(counts)}–{max(counts)} reviews): "
                     "scores from smaller samples are less stable.")

    categories = {e.category.lower() for e in entries if e.ok and e.category}
    if len(categories) > 1:
        notes.append("Different categories are being compared, so aspect sets differ "
                     "and the overall scores are not strictly like-for-like.")

    unverified = [e for e in entries if e.ok and e.verification_status not in ("PASS", "CORRECTED")]
    if unverified:
        notes.append("Verification did not complete for: "
                     + ", ".join(f"{e.name} ({e.verification_status})" for e in unverified))

    if len(ranked) >= 2 and ranked[0].ok and ranked[1].ok:
        gap = (ranked[0].score or 0) - (ranked[1].score or 0)
        if gap < MEANINGFUL_GAP:
            notes.append(f"Top two are within {gap:.2f} points — too close to separate.")

    return notes


def _headline(ranked: list) -> tuple:
    """(winner_name_or_None, sentence) — honest about ties and thin data."""
    eligible = [e for e in ranked if e.ok and e.confidence >= MIN_CONFIDENCE_FOR_WINNER]
    if not eligible:
        scored = [e for e in ranked if e.ok]
        if not scored:
            return None, "No place could be scored — nothing to compare."
        return None, ("No place has enough data for a confident call. "
                      f"Highest raw score: {scored[0].name} at {scored[0].score}/10.")

    best = eligible[0]
    if len(eligible) == 1:
        return best.name, (f"{best.name} is the only place with enough data to judge "
                           f"({best.score}/10, {best.verdict}).")

    gap = (best.score or 0) - (eligible[1].score or 0)
    if gap < MEANINGFUL_GAP:
        tied = [e.name for e in eligible if (best.score or 0) - (e.score or 0) < MEANINGFUL_GAP]
        return None, ("Too close to call: " + " and ".join(tied)
                      + f" are within {MEANINGFUL_GAP} points of each other.")
    return best.name, (f"{best.name} leads with {best.score}/10 versus "
                       f"{eligible[1].name} at {eligible[1].score}/10 "
                       f"(+{gap:.1f}).")


def build_comparison(reports: list, locations: list = None) -> dict:
    """
    Turn a list of analyze() payloads into a comparison.

    Pure: no I/O, no model calls. `locations` supplies the original queries so a
    failed analysis can still be labelled.
    """
    locations = locations or []
    entries = [entry_from_report(report, locations[i] if i < len(locations) else "")
               for i, report in enumerate(reports)]
    ranked = _rank(entries)
    winner, headline = _headline(ranked)

    return {
        "entries": [e.as_dict() for e in entries],
        "ranking": [e.name for e in ranked],
        "winner": winner,
        "headline": headline,
        "aspect_matrix": aspect_matrix(entries),
        "aspect_winners": aspect_winners(entries),
        "caveats": _caveats(entries, ranked),
        "places_compared": sum(1 for e in entries if e.ok),
    }


def validate_locations(locations: list) -> list:
    """Clean up user input; raise if the count is out of range."""
    cleaned, seen = [], set()
    for raw in locations or []:
        value = str(raw).strip()
        if value and value.lower() not in seen:
            cleaned.append(value)
            seen.add(value.lower())
    if not MIN_PLACES <= len(cleaned) <= MAX_PLACES:
        raise ValueError(f"Compare {MIN_PLACES}–{MAX_PLACES} distinct places "
                         f"(got {len(cleaned)}).")
    return cleaned


def compare_locations(locations: list, max_reviews: int = 30,
                      progress_callback=None, force_refresh: bool = False,
                      analyze_fn=None) -> dict:
    """
    Analyse several places and compare them.

    Runs sequentially on purpose: the places share one Groq token budget, so
    running them in parallel would not finish sooner, it would just spend the
    whole minute's quota in the first few seconds. Cached reports are reused,
    which is what makes repeat comparisons quick.
    """
    from locan.pipeline import analyze as _analyze

    analyze_fn = analyze_fn or _analyze
    locations = validate_locations(locations)

    reports = []
    for index, location in enumerate(locations):
        if progress_callback:
            progress_callback(index, len(locations), location)
        try:
            reports.append(analyze_fn(location, max_reviews, force_refresh=force_refresh))
        except Exception as exc:                      # noqa: BLE001 - one bad place must not sink the rest
            reports.append({"error": f"{type(exc).__name__}: {exc}"})

    comparison = build_comparison(reports, locations)
    comparison["reports"] = reports
    return comparison
