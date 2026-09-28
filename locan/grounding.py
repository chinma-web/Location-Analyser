"""
Extractive grounding: counting what reviewers actually wrote.

Everything else in the pipeline asks a model what it thinks. This module only
counts. If Model A reports "great ambience" as a top keyword, we can say
exactly how many reviews contain that word and point at them — and if the
answer is zero, we can say that too.

Pure functions over review dicts: no I/O, no network, no LLM.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

# Words that carry no signal for a "what do reviewers talk about" list.
STOPWORDS = frozenset(["a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can", "could", "did", "do", "does", "for", "from", "get", "got", "had", "has", "have", "he", "her", "him", "his", "how", "i", "if", "in", "into", "is", "it", "its", "just", "me", "more", "most", "my", "no", "not", "of", "on", "once", "one", "only", "or", "other", "our", "out", "over", "own", "really", "same", "she", "should", "so", "some", "such", "than", "that", "the", "their", "them", "then", "there", "these", "they", "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "why", "will", "with", "would", "you", "your", "place", "very", "much", "also", "been", "being", "am", "were", "there", "here", "after", "before", "again", "each", "few"])

# Tokens that look like words: keeps apostrophes inside words, drops punctuation.
_WORD = re.compile(r"[a-z][a-z']+")

# Sentence boundary for pulling a quote around a match.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Mention:
    """Where and how often a term actually appears in the review corpus."""
    term: str
    count: int = 0                       # total occurrences across all reviews
    review_ids: list = field(default_factory=list)   # reviews containing it
    quotes: list = field(default_factory=list)       # short verbatim excerpts

    @property
    def review_count(self) -> int:
        return len(self.review_ids)

    @property
    def grounded(self) -> bool:
        return self.count > 0

    def as_dict(self) -> dict:
        return {
            "term": self.term,
            "count": self.count,
            "review_count": self.review_count,
            "review_ids": list(self.review_ids),
            "quotes": list(self.quotes),
            "grounded": self.grounded,
        }


def _review_text(review: dict) -> str:
    return str(review.get("text") or "")


def term_pattern(term: str) -> re.Pattern:
    r"""
    Word-boundary pattern for a term or phrase.

    Multi-word phrases tolerate any whitespace run between words, and a
    trailing optional "s" catches the singular/plural pair without dragging in
    a stemmer ("queue" matches "queues" but not "queueing" — deliberately
    conservative, since an over-eager match would inflate the counts we are
    using to keep the model honest).
    """
    words = [re.escape(w) for w in term.lower().split()]
    if not words:
        return re.compile(r"(?!x)x")            # never matches
    body = r"\s+".join(words)
    return re.compile(rf"\b{body}s?\b", re.IGNORECASE)


def _quote_around(text: str, match: re.Match, max_len: int = 160) -> str:
    """The sentence containing a match, trimmed to a readable length."""
    start = text.rfind(".", 0, match.start()) + 1
    end = text.find(".", match.end())
    sentence = text[start:(end + 1 if end != -1 else len(text))].strip()
    if not sentence:
        sentence = text.strip()
    if len(sentence) > max_len:
        sentence = sentence[:max_len].rsplit(" ", 1)[0] + "…"
    return sentence


def count_mentions(term: str, reviews: list, max_quotes: int = 3) -> Mention:
    """Count occurrences of `term` across reviews and collect example quotes."""
    pattern = term_pattern(term)
    mention = Mention(term=term)
    for index, review in enumerate(reviews):
        text = _review_text(review)
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        mention.count += len(matches)
        mention.review_ids.append(review.get("id") or f"r{index + 1}")
        if len(mention.quotes) < max_quotes:
            mention.quotes.append(_quote_around(text, matches[0]))
    return mention


def ground_keywords(keywords: list, reviews: list) -> dict:
    """
    Check a model-produced keyword list against the review text.

    Returns the keywords that genuinely appear (with counts, sorted by how many
    reviews mention them) and those that do not. An ungrounded keyword is not
    necessarily wrong — a model may paraphrase "staff were rude" as
    "poor service" — but it is an unsupported claim, and the UI should say so
    rather than presenting it as extracted evidence.
    """
    grounded, ungrounded = [], []
    for keyword in keywords:
        if not str(keyword).strip():
            continue
        mention = count_mentions(str(keyword), reviews)
        (grounded if mention.grounded else ungrounded).append(mention)
    grounded.sort(key=lambda m: (-m.review_count, -m.count, m.term))
    return {
        "grounded": [m.as_dict() for m in grounded],
        "ungrounded": [m.term for m in ungrounded],
        "grounded_ratio": round(len(grounded) / len(grounded + ungrounded), 3)
                          if (grounded or ungrounded) else None,
    }


def top_terms(reviews: list, limit: int = 15, min_reviews: int = 2) -> list:
    """
    The most widely-discussed words and two-word phrases, by *document*
    frequency — how many distinct reviews use them, not raw repetition, so one
    ranting reviewer cannot manufacture a theme.
    """
    doc_freq: Counter = Counter()
    total_freq: Counter = Counter()

    for review in reviews:
        words = [w for w in _WORD.findall(_review_text(review).lower())
                 if w not in STOPWORDS and len(w) > 2]
        bigrams = [f"{a} {b}" for a, b in zip(words, words[1:])]
        for term in set(words) | set(bigrams):
            doc_freq[term] += 1
        total_freq.update(words)
        total_freq.update(bigrams)

    # Drop a unigram when a bigram containing it is nearly as common: "wait
    # time" is more informative than "wait" when they co-occur.
    ranked = []
    bigrams_kept = {t for t, n in doc_freq.items() if " " in t and n >= min_reviews}
    for term, reviews_mentioning in doc_freq.items():
        if reviews_mentioning < min_reviews:
            continue
        if " " not in term and any(term in bg.split() and doc_freq[bg] >= reviews_mentioning * 0.8
                                   for bg in bigrams_kept):
            continue
        ranked.append({"term": term,
                       "review_count": reviews_mentioning,
                       "count": total_freq[term]})

    ranked.sort(key=lambda entry: (-entry["review_count"], -entry["count"], entry["term"]))
    return ranked[:limit]


# ── Aspect drill-down ─────────────────────────────────────────────────────────

# Terms that indicate a review is talking about a given aspect. Kept short and
# obvious on purpose: this is evidence retrieval, not classification.
ASPECT_LEXICON = {
    "food_quality":    ("food", "dish", "taste", "tasty", "flavour", "flavor", "menu",
                        "meal", "cooked", "delicious", "biryani", "coffee", "pizza",
                        "portion", "fresh", "stale"),
    "service":         ("service", "staff", "waiter", "waitress", "server", "rude",
                        "polite", "friendly", "attentive", "manager", "hospitality"),
    "ambience":        ("ambience", "ambiance", "atmosphere", "decor", "music", "vibe",
                        "interior", "seating", "cozy", "cosy", "noisy", "lighting"),
    "value_for_money": ("price", "pricey", "expensive", "cheap", "value", "overpriced",
                        "affordable", "worth", "bill", "cost", "budget"),
    "cleanliness":     ("clean", "cleanliness", "dirty", "hygiene", "hygienic", "filthy",
                        "washroom", "toilet", "restroom", "smell", "smelly"),
    "crowd_wait_time": ("wait", "waiting", "queue", "crowded", "crowd", "busy", "rush",
                        "reservation", "booking", "slow", "delay"),
    "accessibility":   ("parking", "park", "access", "accessible", "wheelchair", "ramp",
                        "location", "metro", "station", "entrance", "lift", "elevator"),
}


def aspect_mentions(reviews: list, lexicon: dict = None) -> dict:
    """
    For each aspect, which reviews talk about it and through which words.

    This backs the per-aspect drill-down in the UI: a user who does not believe
    the 6.5/10 for "value for money" can read the eleven reviews that mention
    price. It is also a sanity check on the model — an aspect scored from zero
    lexical mentions deserves scepticism.
    """
    lexicon = lexicon or ASPECT_LEXICON
    result = {}
    for aspect, terms in lexicon.items():
        review_ids, term_counts, quotes = [], Counter(), []
        for index, review in enumerate(reviews):
            text = _review_text(review)
            hit = False
            for term in terms:
                matches = list(term_pattern(term).finditer(text))
                if matches:
                    term_counts[term] += len(matches)
                    if not hit and len(quotes) < 3:
                        quotes.append(_quote_around(text, matches[0]))
                    hit = True
            if hit:
                review_ids.append(review.get("id") or f"r{index + 1}")
        result[aspect] = {
            "review_ids": review_ids,
            "review_count": len(review_ids),
            "terms": dict(term_counts.most_common()),
            "quotes": quotes,
        }
    return result


def ground_sentiment(sentiment: dict, reviews: list) -> dict:
    """
    Attach extractive evidence to a merged sentiment payload.

    Adds a "grounding" block; never modifies the model's own numbers. Callers
    decide how loudly to report a low grounded_ratio.
    """
    if not sentiment or not reviews:
        return sentiment

    grounding = {
        "positive_keywords": ground_keywords(sentiment.get("positive_keywords") or [], reviews),
        "negative_keywords": ground_keywords(sentiment.get("negative_keywords") or [], reviews),
        "top_terms": top_terms(reviews),
        "aspect_mentions": aspect_mentions(reviews),
    }

    # Flag aspects the model scored without any lexical support in the text.
    unsupported = []
    for aspect, entry in (sentiment.get("aspect_scores") or {}).items():
        score = entry.get("score") if isinstance(entry, dict) else None
        if isinstance(score, (int, float)):
            mentions = grounding["aspect_mentions"].get(aspect, {}).get("review_count", 0)
            if mentions == 0:
                unsupported.append(aspect)
    grounding["aspects_without_lexical_support"] = unsupported

    sentiment["grounding"] = grounding
    return sentiment
