"""
Category-aware aspect sets.

Every place was scored on the same seven restaurant aspects. A hotel got a
"food quality" score, a gym got "ambience", a hospital got "value for money" —
and because a missing aspect drops out of the weighted mean, the model was
quietly encouraged to invent scores for aspects nobody had mentioned.

An aspect set is chosen from the Google Maps category string and drives three
things: the prompt schema, the merge keys, and the scoring weights.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Aspect:
    """One scored dimension."""
    key: str
    label: str
    weight: float                    # relative importance inside the aspect score
    hint: str = ""                   # shown to the model in the prompt schema
    lexicon: tuple = ()              # words that signal this aspect in review text


@dataclass(frozen=True)
class AspectSet:
    """The aspects that make sense for one kind of place."""
    name: str
    aspects: tuple
    matches: tuple = field(default=())   # category substrings that select this set

    @property
    def keys(self) -> list:
        return [a.key for a in self.aspects]

    @property
    def weights(self) -> dict:
        return {a.key: a.weight for a in self.aspects}

    @property
    def lexicon(self) -> dict:
        return {a.key: a.lexicon for a in self.aspects if a.lexicon}

    def label_for(self, key: str) -> str:
        for aspect in self.aspects:
            if aspect.key == key:
                return aspect.label
        return key.replace("_", " ").title()


# ── Shared aspects ────────────────────────────────────────────────────────────

_SERVICE = Aspect("service", "Service", 1.5,
                  "staff attitude, competence, responsiveness",
                  ("service", "staff", "waiter", "waitress", "server", "rude", "polite",
                   "friendly", "attentive", "manager", "hospitality", "receptionist"))
_CLEANLINESS = Aspect("cleanliness", "Cleanliness", 1.0,
                      "hygiene of the premises and facilities",
                      ("clean", "cleanliness", "dirty", "hygiene", "hygienic", "filthy",
                       "washroom", "toilet", "restroom", "smell", "smelly", "dusty"))
_VALUE = Aspect("value_for_money", "Value for money", 1.0,
                "price relative to what you get",
                ("price", "pricey", "expensive", "cheap", "value", "overpriced",
                 "affordable", "worth", "bill", "cost", "budget", "rate"))
_ACCESSIBILITY = Aspect("accessibility", "Accessibility", 0.5,
                        "parking, transport links, step-free access",
                        ("parking", "park", "access", "accessible", "wheelchair", "ramp",
                         "location", "metro", "station", "entrance", "lift", "elevator"))
_WAIT = Aspect("crowd_wait_time", "Crowd / wait time", 0.8,
               "queues, crowding, how long things take",
               ("wait", "waiting", "queue", "crowded", "crowd", "busy", "rush",
                "reservation", "booking", "slow", "delay", "appointment"))
_AMBIENCE = Aspect("ambience", "Ambience", 1.2,
                   "decor, noise, comfort, atmosphere",
                   ("ambience", "ambiance", "atmosphere", "decor", "music", "vibe",
                    "interior", "seating", "cozy", "cosy", "noisy", "lighting"))


# ── Category-specific sets ────────────────────────────────────────────────────

FOOD = AspectSet(
    "food_and_drink",
    (
        Aspect("food_quality", "Food quality", 1.5,
               "taste, freshness, portion size, consistency",
               ("food", "dish", "taste", "tasty", "flavour", "flavor", "menu", "meal",
                "cooked", "delicious", "biryani", "coffee", "pizza", "portion",
                "fresh", "stale", "spicy", "dessert")),
        _SERVICE, _AMBIENCE, _VALUE, _CLEANLINESS, _WAIT, _ACCESSIBILITY,
    ),
    matches=("restaurant", "cafe", "café", "coffee", "bar", "pub", "bakery", "bistro",
             "food", "pizzeria", "diner", "eatery", "brewery", "ice cream", "dessert",
             "sweet shop", "juice", "tea house", "fast food", "takeaway", "canteen"),
)

HOTEL = AspectSet(
    "accommodation",
    (
        Aspect("rooms", "Rooms", 1.5,
               "size, comfort, condition, bedding, noise insulation",
               ("room", "bed", "bathroom", "shower", "ac", "air conditioning", "suite",
                "balcony", "view", "linen", "towel", "mattress", "wifi")),
        _SERVICE, _CLEANLINESS, _VALUE,
        Aspect("amenities", "Amenities", 1.0,
               "breakfast, pool, gym, wifi, parking and other facilities",
               ("breakfast", "pool", "gym", "wifi", "spa", "restaurant", "buffet",
                "parking", "facilities", "amenities", "laundry")),
        Aspect("location_quality", "Location", 1.2,
               "how convenient and pleasant the surroundings are",
               ("location", "nearby", "walk", "walking distance", "airport", "station",
                "beach", "centre", "center", "market", "safe", "neighbourhood")),
        _WAIT,
    ),
    matches=("hotel", "hostel", "resort", "guest house", "guesthouse", "lodge",
             "motel", "inn", "homestay", "serviced apartment", "bnb", "b&b"),
)

RETAIL = AspectSet(
    "retail",
    (
        Aspect("product_quality", "Product quality", 1.5,
               "condition, authenticity and range of what is sold",
               ("product", "quality", "item", "goods", "stock", "brand", "fresh",
                "variety", "selection", "genuine", "fake", "defective", "size")),
        _SERVICE, _VALUE,
        Aspect("stock_availability", "Stock & choice", 1.0,
               "whether what shoppers wanted was in stock",
               ("stock", "available", "availability", "out of stock", "sold out",
                "range", "options", "choice", "collection")),
        _CLEANLINESS, _WAIT, _ACCESSIBILITY,
    ),
    matches=("store", "shop", "supermarket", "market", "mall", "boutique", "retail",
             "grocery", "pharmacy", "bookstore", "showroom", "dealer", "outlet"),
)

HEALTH = AspectSet(
    "healthcare",
    (
        Aspect("care_quality", "Quality of care", 2.0,
               "clinical competence and outcomes as described by patients",
               ("doctor", "treatment", "diagnosis", "care", "surgery", "nurse",
                "consultation", "medicine", "recovery", "patient", "checkup")),
        Aspect("staff_attitude", "Staff attitude", 1.5,
               "empathy, communication, reception behaviour",
               ("staff", "nurse", "reception", "rude", "polite", "caring", "listened",
                "explained", "friendly", "attitude", "helpful")),
        _WAIT, _CLEANLINESS,
        Aspect("cost_transparency", "Cost & billing", 1.2,
               "fairness and clarity of charges",
               ("bill", "billing", "charges", "cost", "expensive", "insurance",
                "refund", "overcharged", "estimate", "price")),
        _ACCESSIBILITY,
    ),
    matches=("hospital", "clinic", "doctor", "dentist", "medical", "health",
             "diagnostic", "physio", "veterinary", "vet ", "pharmacy"),
)

FITNESS = AspectSet(
    "fitness",
    (
        Aspect("equipment", "Equipment", 1.5,
               "quantity, condition and variety of equipment",
               ("equipment", "machine", "treadmill", "weights", "dumbbell", "gear",
                "broken", "maintained", "new", "cardio", "rack")),
        Aspect("trainers", "Trainers & classes", 1.5,
               "coaching quality and class schedule",
               ("trainer", "coach", "instructor", "class", "session", "personal training",
                "guidance", "form", "yoga", "zumba")),
        _CLEANLINESS, _VALUE, _WAIT,
        Aspect("facilities", "Facilities", 1.0,
               "changing rooms, showers, lockers, air conditioning",
               ("locker", "shower", "changing", "washroom", "ac", "air conditioning",
                "sauna", "parking", "space", "crowded")),
    ),
    matches=("gym", "fitness", "yoga", "crossfit", "pilates", "sports club",
             "swimming", "martial arts", "dance studio"),
)

ATTRACTION = AspectSet(
    "attraction",
    (
        Aspect("experience", "Experience", 1.8,
               "how worthwhile and memorable the visit is",
               ("experience", "view", "beautiful", "worth", "amazing", "boring",
                "history", "tour", "guide", "exhibit", "scenery", "photo")),
        Aspect("upkeep", "Upkeep", 1.2,
               "maintenance and preservation of the site",
               ("maintained", "maintenance", "upkeep", "renovation", "garbage",
                "litter", "damaged", "restored", "condition", "clean")),
        _WAIT, _VALUE, _ACCESSIBILITY,
        Aspect("facilities", "Visitor facilities", 1.0,
               "toilets, signage, seating, refreshments",
               ("toilet", "washroom", "signage", "seating", "bench", "cafeteria",
                "water", "shade", "guide", "map")),
    ),
    matches=("park", "museum", "temple", "church", "mosque", "monument", "fort",
             "zoo", "garden", "beach", "tourist", "attraction", "landmark",
             "viewpoint", "gallery", "theatre", "cinema", "amusement"),
)

SERVICES = AspectSet(
    "services",
    (
        Aspect("work_quality", "Quality of work", 1.8,
               "whether the job was done properly",
               ("work", "job", "quality", "repair", "fixed", "service", "result",
                "professional", "finish", "workmanship", "problem")),
        _SERVICE, _VALUE, _WAIT,
        Aspect("reliability", "Reliability", 1.3,
               "keeping appointments, promises and timelines",
               ("appointment", "promised", "on time", "delay", "reliable", "honest",
                "cheated", "follow up", "response", "communication")),
        _ACCESSIBILITY,
    ),
    matches=("salon", "spa", "repair", "garage", "service centre", "service center",
             "bank", "atm", "agency", "consultant", "school", "college", "institute",
             "coaching", "office", "laundry", "courier", "workshop"),
)

GENERIC = AspectSet(
    "generic",
    (_SERVICE, _VALUE, _CLEANLINESS, _AMBIENCE, _WAIT, _ACCESSIBILITY),
)

ASPECT_SETS = (FOOD, HOTEL, RETAIL, HEALTH, FITNESS, ATTRACTION, SERVICES)


def aspect_set_for(category: str = "", subtypes=None) -> AspectSet:
    """
    Pick an aspect set from the Google category string (and its subtypes).

    Matching is substring-based on a lowercased haystack, longest match wins so
    that "coffee shop" beats a bare "shop". Unknown categories get the generic
    set rather than the restaurant one — scoring a law firm on food quality is
    worse than scoring it on nothing.
    """
    haystack = " ".join([str(category or "")] + [str(s) for s in (subtypes or [])]).lower()
    if not haystack.strip():
        return GENERIC

    best, best_len = GENERIC, 0
    for aspect_set in ASPECT_SETS:
        for needle in aspect_set.matches:
            if needle in haystack and len(needle) > best_len:
                best, best_len = aspect_set, len(needle)
    return best


def aspect_set_for_place(place_info: dict) -> AspectSet:
    """Convenience wrapper over a scraped place_info dict."""
    place_info = place_info or {}
    return aspect_set_for(place_info.get("category", ""), place_info.get("subtypes"))


def prompt_schema(aspect_set: AspectSet) -> str:
    """The aspect_scores block for the sentiment prompt, as JSON-ish text."""
    entries = []
    for aspect in aspect_set.aspects:
        entries.append(
            f'    "{aspect.key}": {{"score": null, "reviews_mentioning": 0, '
            f'"summary": "brief note or null", "evidence_review_ids": []}}'
        )
    lines = []
    for index, entry in enumerate(entries):
        comma = "," if index < len(entries) - 1 else ""
        hint = f"   // {aspect_set.aspects[index].hint}" if aspect_set.aspects[index].hint else ""
        lines.append(entry + comma + hint)
    return "{\n" + "\n".join(lines) + "\n  }"
