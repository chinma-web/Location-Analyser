"""Category-aware aspect sets."""
import pytest

from locan.aspects import (
    ASPECT_SETS,
    FOOD,
    GENERIC,
    HOTEL,
    aspect_set_for,
    aspect_set_for_place,
    prompt_schema,
)
from locan.sentiment import _merge_sentiment_batches, _sentiment_prompt_for_batch

# ── category matching ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("category,expected", [
    ("Restaurant", "food_and_drink"),
    ("Coffee shop", "food_and_drink"),
    ("Café", "food_and_drink"),
    ("Hotel", "accommodation"),
    ("Hostel", "accommodation"),
    ("Gym", "fitness"),
    ("Yoga studio", "fitness"),
    ("Hospital", "healthcare"),
    ("Dentist", "healthcare"),
    ("Supermarket", "retail"),
    ("Museum", "attraction"),
    ("Hindu temple", "attraction"),
    ("Beauty salon", "services"),
])
def test_categories_pick_the_right_aspect_set(category, expected):
    assert aspect_set_for(category).name == expected


def test_unknown_categories_get_generic_not_restaurant():
    """Scoring a law firm on food quality is worse than scoring it on nothing."""
    chosen = aspect_set_for("Law firm")
    assert chosen is GENERIC
    assert "food_quality" not in chosen.keys


def test_empty_category_is_generic():
    assert aspect_set_for("") is GENERIC
    assert aspect_set_for(None) is GENERIC


def test_longest_match_wins():
    """'coffee shop' must not be resolved as a generic 'shop'."""
    assert aspect_set_for("Coffee shop").name == "food_and_drink"


def test_subtypes_are_considered():
    assert aspect_set_for("Establishment", ["Point of interest", "Gym"]).name == "fitness"


def test_aspect_set_for_place_reads_scraped_fields():
    place = {"category": "Hotel", "subtypes": ["Lodging"]}
    assert aspect_set_for_place(place) is HOTEL
    assert aspect_set_for_place({}) is GENERIC
    assert aspect_set_for_place(None) is GENERIC


# ── set structure ─────────────────────────────────────────────────────────────

def test_hotels_are_scored_on_rooms_not_food():
    keys = HOTEL.keys
    assert "rooms" in keys and "amenities" in keys
    assert "food_quality" not in keys


def test_every_set_is_well_formed():
    for aspect_set in ASPECT_SETS + (GENERIC,):
        assert aspect_set.keys, f"{aspect_set.name} has no aspects"
        assert len(set(aspect_set.keys)) == len(aspect_set.keys), "duplicate aspect keys"
        assert all(w > 0 for w in aspect_set.weights.values())
        assert all(aspect_set.lexicon[k] for k in aspect_set.lexicon)


def test_weights_and_labels_are_exposed():
    assert HOTEL.weights["rooms"] == 1.5
    assert HOTEL.label_for("rooms") == "Rooms"
    assert HOTEL.label_for("unknown_key") == "Unknown Key"


def test_aspect_sets_are_immutable():
    from dataclasses import FrozenInstanceError
    with pytest.raises(FrozenInstanceError):
        FOOD.aspects[0].weight = 99


# ── prompt schema ─────────────────────────────────────────────────────────────

def test_prompt_schema_lists_every_aspect_once():
    schema = prompt_schema(HOTEL)
    for key in HOTEL.keys:
        assert f'"{key}"' in schema
    assert schema.count("evidence_review_ids") == len(HOTEL.keys)


def test_prompt_schema_has_no_trailing_comma():
    lines = [ln.rstrip() for ln in prompt_schema(FOOD).splitlines() if ln.strip()]
    last_entry = [ln for ln in lines if "evidence_review_ids" in ln][-1]
    assert not last_entry.split("//")[0].rstrip().endswith(",")


def test_sentiment_prompt_follows_the_category():
    batch = [{"id": "r1", "rating": 5, "text": "lovely room"}]
    hotel_prompt = _sentiment_prompt_for_batch(batch, 0, HOTEL)
    assert '"rooms"' in hotel_prompt
    assert "food_quality" not in hotel_prompt

    food_prompt = _sentiment_prompt_for_batch(batch, 0, FOOD)
    assert '"food_quality"' in food_prompt
    assert '"rooms"' not in food_prompt


def test_sentiment_prompt_defaults_to_food_for_backwards_compatibility():
    prompt = _sentiment_prompt_for_batch([{"id": "r1", "rating": 4, "text": "ok"}], 0)
    assert '"food_quality"' in prompt


# ── merging honours the set ───────────────────────────────────────────────────

def test_merge_uses_the_aspect_keys_of_the_chosen_set():
    batches = [
        {"aspect_scores": {"rooms": {"score": 8.0, "reviews_mentioning": 2},
                           "service": {"score": 6.0, "reviews_mentioning": 1}}},
        {"aspect_scores": {"rooms": {"score": 6.0, "reviews_mentioning": 2}}},
    ]
    merged = _merge_sentiment_batches(batches, HOTEL)
    assert set(merged["aspect_scores"]) == set(HOTEL.keys)
    assert merged["aspect_scores"]["rooms"]["score"] == 7.0
    assert merged["aspect_scores"]["amenities"]["score"] is None


def test_merge_ignores_aspects_outside_the_set():
    batches = [{"aspect_scores": {"food_quality": {"score": 9.0, "reviews_mentioning": 3}}},
               {"aspect_scores": {"service": {"score": 5.0, "reviews_mentioning": 1}}}]
    merged = _merge_sentiment_batches(batches, HOTEL)
    assert "food_quality" not in merged["aspect_scores"]


# ── scoring integration ───────────────────────────────────────────────────────

def test_scoring_weights_can_follow_the_aspect_set():
    from dataclasses import replace

    from locan.scoring import DEFAULT_CONFIG, aspect_component

    cfg = replace(DEFAULT_CONFIG, aspect_weights=HOTEL.weights)
    sentiment = {"aspect_scores": {"rooms": {"score": 8.0}, "service": {"score": 6.0}}}
    # rooms 1.5, service 1.5 -> plain mean
    assert aspect_component(sentiment, cfg) == 7.0

    # the same payload under the default (restaurant) weights sees only service
    assert aspect_component(sentiment, DEFAULT_CONFIG) == 6.0
