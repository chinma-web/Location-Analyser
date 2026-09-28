"""
Stable review identity and text-similarity helpers.

Review IDs are content-derived, so evidence references survive re-ordering and
re-fetching; every LLM stage is validated against the known ID set.
"""


from locan.logging_utils import log

# ── Stable review identity ────────────────────────────────────────────────────
# Every stage must cite the SAME review when it says "r7". Previously the
# sentiment stage numbered reviews by global batch offset, the guardrail stage
# re-numbered reviews[:18] as r1..r18 and the verifier re-numbered reviews[:20],
# so an evidence ID meant three different things depending on who emitted it.

def assign_review_ids(reviews: list) -> list:
    """Stamp a stable `id` on each review. Call once, right after cleaning."""
    for i, r in enumerate(reviews):
        r["id"] = f"r{i + 1}"
    return reviews


def known_review_ids(reviews: list) -> set:
    return {r["id"] for r in reviews if isinstance(r, dict) and r.get("id")}


def _drop_unknown_ids(node, known: set, dropped: list):
    """Recursively strip evidence IDs that don't refer to a real review."""
    if isinstance(node, dict):
        for key, val in node.items():
            if key.endswith("review_ids") and isinstance(val, list):
                kept = [i for i in val if i in known]
                dropped.extend([i for i in val if i not in known])
                node[key] = kept
            else:
                _drop_unknown_ids(val, known, dropped)
    elif isinstance(node, list):
        for item in node:
            _drop_unknown_ids(item, known, dropped)
    return node


def validate_evidence_ids(payload: dict, reviews: list, stage: str) -> dict:
    """
    Remove hallucinated citations (e.g. "r42" when only 20 reviews exist).
    An unsupported claim keeps its text but loses its fake evidence, so the UI
    can no longer imply a citation that does not exist.
    """
    known, dropped = known_review_ids(reviews), []
    _drop_unknown_ids(payload, known, dropped)
    if dropped:
        uniq = sorted(set(dropped))
        log(
            f"[yellow]\u26a0  {stage}: dropped {len(dropped)} citation(s) to "
            f"non-existent reviews ({', '.join(uniq[:8])}{'…' if len(uniq) > 8 else ''})[/yellow]"
        )
    return payload


DUPLICATE_JACCARD_THRESHOLD = 0.70   # dedupe during cleaning
NEAR_DUPLICATE_THRESHOLD    = 0.55   # softer threshold for the "suspicious" heuristic


def _tokenise(text: str) -> frozenset:
    """Lowercase word set used for all Jaccard comparisons."""
    return frozenset(text.lower().split())


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    if intersection == 0:
        return 0.0
    return intersection / (len(a) + len(b) - intersection)


def _similar(a: frozenset, b: frozenset, threshold: float) -> bool:
    """
    Jaccard similarity test with a cheap length-ratio pre-filter.

    |A∩B| <= min(|A|,|B|), so J <= min/max. If the size ratio alone cannot reach
    the threshold the pair is skipped before any set operation runs — reviews of
    very different lengths are the common case.
    """
    if not a or not b:
        return False
    small, large = (len(a), len(b)) if len(a) < len(b) else (len(b), len(a))
    if small / large <= threshold:
        return False
    return _jaccard(a, b) > threshold


def _clean_reviews(reviews: list) -> list:
    """
    Remove near-duplicate reviews (>70% Jaccard word overlap), keeping the first.

    Still O(n²) in the worst case, but each review is tokenised exactly once
    instead of once per comparison, and the length pre-filter rejects most pairs
    before touching a set. Previously this re-split the same strings n²/2 times.
    """
    if not reviews:
        return []
    kept, kept_tokens = [], []
    for review in reviews:
        tokens = _tokenise(review["text"])
        if any(_similar(tokens, prev, DUPLICATE_JACCARD_THRESHOLD) for prev in kept_tokens):
            continue
        kept.append(review)
        kept_tokens.append(tokens)
    return kept
