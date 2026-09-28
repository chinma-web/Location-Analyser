"""On-disk report cache, keyed by a hash of the normalised query."""

import hashlib
import json
import os
import time

from locan.logging_utils import log

# ── Report cache ──────────────────────────────────────────────────────────────
# The old scheme was `report_{first 30 alphanumerics of the query}.json` in the
# current working directory. Every Google Maps URL normalises to roughly
# "httpswwwgooglecommapsplace", so distinct places collided on one file and the
# app could confidently serve you a report for somewhere else entirely.

CACHE_DIR       = os.getenv("CACHE_DIR", "cache")
CACHE_TTL_HOURS = float(os.getenv("CACHE_TTL_HOURS", "168"))   # 7 days
# Bump when the pipeline's output shape or semantics change, to invalidate
# everything written by an older version.
CACHE_SCHEMA_VERSION = 2


def _normalise_cache_query(location: str) -> str:
    return " ".join((location or "").strip().lower().split())


def cache_key(location: str, max_reviews: int) -> str:
    """Collision-resistant key over the full query, review count and schema."""
    raw = json.dumps(
        [_normalise_cache_query(location), int(max_reviews), CACHE_SCHEMA_VERSION],
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def cache_path(location: str, max_reviews: int) -> str:
    return os.path.join(CACHE_DIR, f"report_{cache_key(location, max_reviews)}.json")


def read_cache(location: str, max_reviews: int):
    """Return a cached report, or None. Verifies the payload really matches."""
    path = cache_path(location, max_reviews)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        log(f"[yellow]⚠ Cache read failed ({e}) — re-running pipeline.[/yellow]")
        return None

    meta = data.get("cache_meta") or {}
    # Defend against a stale/hand-edited file landing on a matching hash.
    if meta.get("query") != _normalise_cache_query(location) \
            or meta.get("max_reviews") != int(max_reviews) \
            or meta.get("schema_version") != CACHE_SCHEMA_VERSION:
        log("[yellow]⚠ Cache entry does not match this query — ignoring.[/yellow]")
        return None

    age_h = (time.time() - meta.get("cached_at", 0)) / 3600
    if age_h > CACHE_TTL_HOURS:
        log(f"[dim]Cache entry is {age_h:.0f}h old (TTL {CACHE_TTL_HOURS:.0f}h) — refreshing.[/dim]")
        return None

    data["cache_meta"] = {**meta, "age_hours": round(age_h, 1), "served_from_cache": True}
    log(f"[bold green]⚡ Cache hit[/bold green] [dim]({age_h:.1f}h old) → {path}[/dim]")
    return data


def write_cache(location: str, max_reviews: int, payload: dict) -> str:
    path = cache_path(location, max_reviews)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload["cache_meta"] = {
        "query":          _normalise_cache_query(location),
        "original_query": location,
        "max_reviews":    int(max_reviews),
        "schema_version": CACHE_SCHEMA_VERSION,
        "cached_at":      time.time(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False, default=str)
    return path
