"""The old cache keyed on a 30-char alphanumeric slug and collided badly."""
import json
import time

import pytest

import location as L


@pytest.fixture(autouse=True)
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(L, "CACHE_DIR", str(tmp_path / "cache"))
    yield


# "https://www.google.com/maps/place/" survives punctuation-stripping as
# "httpswwwgooglecommapsplace" (26 chars), so the old 30-char slug preserved
# only ~4 characters of the actual place name.
URL_A = "https://www.google.com/maps/place/Cafe+Goodluck/@18.5,73.8,17z"
URL_B = "https://www.google.com/maps/place/Cafe+Madras/@13.0,80.2,17z"


def test_distinct_maps_urls_do_not_collide():
    """Under the old slug scheme both of these became 'report_httpswwwgooglecommapspl'."""
    old_slug = lambda q: "".join(c if c.isalnum() or c in " _-" else "" for c in q)[:30].strip()
    assert old_slug(URL_A) == old_slug(URL_B)          # the bug
    assert L.cache_key(URL_A, 30) != L.cache_key(URL_B, 30)   # the fix


def test_key_depends_on_review_count_and_schema():
    assert L.cache_key("Eiffel Tower", 30) != L.cache_key("Eiffel Tower", 60)


def test_key_is_whitespace_and_case_insensitive():
    assert L.cache_key("  Eiffel   Tower ", 30) == L.cache_key("eiffel tower", 30)


def test_roundtrip_and_metadata():
    L.write_cache("Eiffel Tower", 30, {"hello": "world"})
    got = L.read_cache("Eiffel Tower", 30)
    assert got["hello"] == "world"
    assert got["cache_meta"]["served_from_cache"] is True
    assert got["cache_meta"]["max_reviews"] == 30


def test_miss_for_a_different_query():
    L.write_cache("Eiffel Tower", 30, {"hello": "world"})
    assert L.read_cache("Colosseum", 30) is None


def test_expired_entries_are_ignored(monkeypatch):
    L.write_cache("Eiffel Tower", 30, {"hello": "world"})
    path = L.cache_path("Eiffel Tower", 30)
    payload = json.load(open(path))
    payload["cache_meta"]["cached_at"] = time.time() - (L.CACHE_TTL_HOURS + 1) * 3600
    json.dump(payload, open(path, "w"))
    assert L.read_cache("Eiffel Tower", 30) is None


def test_mismatched_payload_on_a_matching_path_is_rejected():
    L.write_cache("Eiffel Tower", 30, {"hello": "world"})
    path = L.cache_path("Eiffel Tower", 30)
    payload = json.load(open(path))
    payload["cache_meta"]["query"] = "somewhere else"
    json.dump(payload, open(path, "w"))
    assert L.read_cache("Eiffel Tower", 30) is None


def test_corrupt_file_does_not_raise():
    path = L.cache_path("Eiffel Tower", 30)
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write("{not json")
    assert L.read_cache("Eiffel Tower", 30) is None
