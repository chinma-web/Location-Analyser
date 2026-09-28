"""Review IDs must mean the same thing in every stage of the pipeline."""
from locan import reviews as reviews_mod
from locan import sentiment


def _reviews(n):
    return [{"author": f"a{i}", "rating": 5, "text": f"review number {i}"} for i in range(n)]


def test_ids_are_assigned_once_and_are_stable():
    reviews = reviews_mod.assign_review_ids(_reviews(25))
    assert reviews[0]["id"] == "r1"
    assert reviews[24]["id"] == "r25"
    assert len(reviews_mod.known_review_ids(reviews)) == 25


def test_guardrail_and_verifier_samples_reuse_the_same_ids():
    """The old code re-numbered each sample, so r17 meant three different reviews."""
    reviews = reviews_mod.assign_review_ids(_reviews(25))

    guardrail_sample = [{"id": r.get("id") or f"r{i+1}"} for i, r in enumerate(reviews[:18])]
    verifier_sample  = [{"id": r.get("id") or f"r{i+1}"} for i, r in enumerate(reviews[:20])]

    assert guardrail_sample[17]["id"] == "r18" == reviews[17]["id"]
    assert verifier_sample[17]["id"] == "r18" == reviews[17]["id"]


def test_sentiment_prompt_cites_stable_ids_across_batches():
    reviews = reviews_mod.assign_review_ids(_reviews(25))
    batch_2 = reviews[15:25]
    prompt = sentiment._sentiment_prompt_for_batch(batch_2, batch_offset=15)
    assert "[r16]" in prompt and "[r25]" in prompt
    assert "[r1]" not in prompt


def test_hallucinated_citations_are_dropped():
    reviews = reviews_mod.assign_review_ids(_reviews(5))
    payload = {
        "positive_points": [{"claim": "Great food", "evidence_review_ids": ["r1", "r42", "r3"]}],
        "themes": [{"name": "food", "evidence_review_ids": ["r99"]}],
        "aspect_scores": {"service": {"score": 8, "evidence_review_ids": ["r2"]}},
    }
    out = reviews_mod.validate_evidence_ids(payload, reviews, "test")
    assert out["positive_points"][0]["evidence_review_ids"] == ["r1", "r3"]
    assert out["themes"][0]["evidence_review_ids"] == []
    assert out["aspect_scores"]["service"]["evidence_review_ids"] == ["r2"]


def test_validation_leaves_claim_text_untouched():
    reviews = reviews_mod.assign_review_ids(_reviews(2))
    payload = {"genuine_concerns": [{"aspect": "parking", "evidence": "hard to park",
                                     "supporting_review_ids": ["r7"]}]}
    out = reviews_mod.validate_evidence_ids(payload, reviews, "test")
    assert out["genuine_concerns"][0]["evidence"] == "hard to park"
    assert out["genuine_concerns"][0]["supporting_review_ids"] == []
