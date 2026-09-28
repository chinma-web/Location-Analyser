"""Extractive grounding: counts must come from the text, not the model."""
import pytest

from locan.grounding import (
    ASPECT_LEXICON,
    aspect_mentions,
    count_mentions,
    ground_keywords,
    ground_sentiment,
    term_pattern,
    top_terms,
)


def rv(text, rid=None):
    return {"id": rid, "text": text}


# ── term matching ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("term,text,hits", [
    ("service", "The service was great", 1),
    ("service", "Services were slow", 1),           # plural
    ("service", "SERVICE was fine", 1),             # case-insensitive
    ("service", "self-servicing machine", 0),       # not a substring match
    ("wait time", "the wait   time was long", 1),   # flexible whitespace
    ("wait time", "we had to wait, time passed", 0),
    ("food", "food, food and more food", 3),
])
def test_term_pattern_matches_words_not_substrings(term, text, hits):
    assert len(term_pattern(term).findall(text)) == hits


def test_empty_term_never_matches():
    assert term_pattern("").search("anything") is None


# ── count_mentions ────────────────────────────────────────────────────────────

def test_count_mentions_reports_occurrences_reviews_and_quotes():
    reviews = [
        rv("The coffee here is excellent. Best coffee in town.", "r1"),
        rv("Service was slow but fine.", "r2"),
        rv("Great coffee and pastries.", "r3"),
    ]
    mention = count_mentions("coffee", reviews)
    assert mention.count == 3                  # total occurrences
    assert mention.review_count == 2           # distinct reviews
    assert mention.review_ids == ["r1", "r3"]
    assert mention.grounded is True
    assert "coffee" in mention.quotes[0].lower()


def test_count_mentions_falls_back_to_positional_ids():
    mention = count_mentions("parking", [rv("no parking anywhere")])
    assert mention.review_ids == ["r1"]


def test_absent_term_is_not_grounded():
    mention = count_mentions("unicorn", [rv("nice food")])
    assert mention.count == 0 and mention.grounded is False


def test_quotes_are_trimmed_to_the_sentence():
    long_text = "Some intro sentence. The parking was a nightmare. Then we left."
    mention = count_mentions("parking", [rv(long_text)])
    assert mention.quotes == ["The parking was a nightmare."]


def test_quotes_are_length_capped():
    text = "parking " + "x" * 400
    quote = count_mentions("parking", [rv(text)]).quotes[0]
    assert len(quote) <= 161 and quote.endswith("…")


# ── ground_keywords ───────────────────────────────────────────────────────────

def test_ungrounded_keywords_are_separated_from_real_ones():
    reviews = [rv("amazing biryani", "r1"), rv("the biryani was dry", "r2"),
               rv("staff were rude", "r3")]
    result = ground_keywords(["biryani", "ambience", "staff"], reviews)

    assert [g["term"] for g in result["grounded"]] == ["biryani", "staff"]
    assert result["ungrounded"] == ["ambience"]
    assert result["grounded_ratio"] == pytest.approx(2 / 3, abs=0.01)


def test_grounded_keywords_sort_by_review_coverage():
    reviews = [rv("coffee coffee coffee", "r1"), rv("cake", "r2"), rv("cake", "r3")]
    grounded = ground_keywords(["coffee", "cake"], reviews)["grounded"]
    # cake appears in more reviews even though coffee has more raw occurrences
    assert [g["term"] for g in grounded] == ["cake", "coffee"]


def test_ground_keywords_handles_empty_and_blank_input():
    assert ground_keywords([], [rv("x")])["grounded_ratio"] is None
    assert ground_keywords(["", "   "], [rv("x")])["grounded"] == []


# ── top_terms ─────────────────────────────────────────────────────────────────

def test_top_terms_ranks_by_document_frequency_not_repetition():
    reviews = [
        rv("parking parking parking parking"),
        rv("the biryani was good"),
        rv("the biryani was great"),
        rv("biryani again"),
    ]
    terms = {t["term"]: t for t in top_terms(reviews)}
    assert terms["biryani"]["review_count"] == 3
    assert "parking" not in terms          # one ranting review is not a theme


def test_top_terms_drops_stopwords_and_short_words():
    reviews = [rv("the and was it a of"), rv("the and was it a of")]
    assert top_terms(reviews) == []


def test_top_terms_prefers_informative_bigrams():
    reviews = [rv("the wait time was long")] * 3
    terms = [t["term"] for t in top_terms(reviews)]
    assert "wait time" in terms
    assert "wait" not in terms             # subsumed by the bigram


def test_top_terms_respects_limit_and_min_reviews():
    reviews = [rv(f"unique{i} word") for i in range(10)]
    assert all(t["review_count"] >= 2 for t in top_terms(reviews))
    assert len(top_terms(reviews, limit=1)) <= 1


# ── aspect drill-down ─────────────────────────────────────────────────────────

def test_aspect_mentions_map_reviews_to_aspects():
    reviews = [
        rv("The food was delicious but service was rude", "r1"),
        rv("Very expensive for what you get", "r2"),
        rv("Toilets were filthy", "r3"),
    ]
    mentions = aspect_mentions(reviews)

    assert mentions["food_quality"]["review_ids"] == ["r1"]
    assert mentions["service"]["review_ids"] == ["r1"]
    assert mentions["value_for_money"]["review_ids"] == ["r2"]
    assert mentions["cleanliness"]["review_ids"] == ["r3"]
    assert mentions["ambience"]["review_count"] == 0


def test_aspect_mentions_report_which_terms_hit():
    reviews = [rv("rude staff, rude manager", "r1")]
    terms = aspect_mentions(reviews)["service"]["terms"]
    assert terms["rude"] == 2 and terms["staff"] == 1


def test_aspect_mentions_accept_a_custom_lexicon():
    reviews = [rv("the treadmills were broken", "r1")]
    custom = {"equipment": ("treadmill", "weights", "machine")}
    assert aspect_mentions(reviews, custom)["equipment"]["review_count"] == 1


def test_every_lexicon_aspect_is_queryable():
    empty = aspect_mentions([])
    assert set(empty) == set(ASPECT_LEXICON)
    assert all(entry["review_count"] == 0 for entry in empty.values())


# ── ground_sentiment ──────────────────────────────────────────────────────────

def test_ground_sentiment_attaches_evidence_without_touching_model_numbers():
    reviews = [rv("great coffee, rude staff", "r1"), rv("coffee is good", "r2")]
    sentiment = {
        "sentiment_score": 0.4,
        "positive_keywords": ["coffee", "ambience"],
        "negative_keywords": ["rude"],
        "aspect_scores": {"food_quality": {"score": 8.0}},
    }
    out = ground_sentiment(sentiment, reviews)

    assert out["sentiment_score"] == 0.4                      # untouched
    assert out["aspect_scores"]["food_quality"]["score"] == 8.0
    grounding = out["grounding"]
    assert [g["term"] for g in grounding["positive_keywords"]["grounded"]] == ["coffee"]
    assert grounding["positive_keywords"]["ungrounded"] == ["ambience"]
    assert grounding["aspect_mentions"]["service"]["review_count"] == 1


def test_aspects_scored_without_lexical_support_are_flagged():
    reviews = [rv("lovely spot", "r1")]
    sentiment = {"aspect_scores": {"accessibility": {"score": 7.0},
                                   "service": {"score": None}}}
    grounding = ground_sentiment(sentiment, reviews)["grounding"]
    assert grounding["aspects_without_lexical_support"] == ["accessibility"]


def test_ground_sentiment_is_a_noop_without_data():
    assert ground_sentiment({}, [rv("x")]) == {}
    assert ground_sentiment({"a": 1}, []) == {"a": 1}


# ── pipeline wiring ───────────────────────────────────────────────────────────

def test_pipeline_logs_grounding_quality(caplog):
    from locan import pipeline
    sentiment = {"grounding": {
        "positive_keywords": {"grounded": [{"term": "coffee"}], "ungrounded": ["ambience"],
                              "grounded_ratio": 0.5},
        "negative_keywords": {"grounded": [], "ungrounded": [], "grounded_ratio": None},
        "aspects_without_lexical_support": ["accessibility"],
    }}
    # the "not found in text" line is DEBUG (it starts with a [dim] tag)
    with caplog.at_level("DEBUG", logger="locan"):
        pipeline._log_grounding(sentiment)
    text = caplog.text
    assert "50%" in text
    assert "ambience" in text
    assert "accessibility" in text


def test_grounding_logging_is_silent_without_data(caplog):
    from locan import pipeline
    with caplog.at_level("DEBUG", logger="locan"):
        pipeline._log_grounding({})
        pipeline._log_grounding({"grounding": {}})
    assert caplog.text == ""
