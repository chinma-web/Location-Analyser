"""
Run history.

Every analysis already writes a JSON report into the cache directory, but the
only way to find an old one was to re-type the exact query with the exact
review count. This reads the cache back as a browsable list.

It is deliberately a view over the cache rather than a second store: one place
where reports live, no synchronisation problem, and clearing the cache clears
the history.
"""

from __future__ import annotations

import glob
import json
import os
import time

from locan.cache import CACHE_DIR, CACHE_SCHEMA_VERSION
from locan.logging_utils import log


def _summarise(path: str, payload: dict) -> dict:
    place = payload.get("place_info") or {}
    scoring = payload.get("scoring") or {}
    usage = payload.get("usage") or {}
    meta = payload.get("cache_meta") or {}
    saved_at = meta.get("cached_at") or os.path.getmtime(path)

    return {
        "path": path,
        "location": payload.get("location") or place.get("name") or "",
        "name": place.get("name") or payload.get("location") or "",
        "category": place.get("category", ""),
        "score": scoring.get("score"),
        "verdict": scoring.get("verdict", ""),
        "confidence": scoring.get("confidence"),
        "reviews_analyzed": len(payload.get("reviews") or []),
        "saved_at": saved_at,
        "age_hours": round((time.time() - saved_at) / 3600, 1),
        "cost_usd": usage.get("total_cost_usd"),
        "total_tokens": usage.get("total_tokens"),
        "max_reviews": meta.get("max_reviews"),
        "schema_version": meta.get("schema_version", 1),
        "stale": meta.get("schema_version", 1) != CACHE_SCHEMA_VERSION,
    }


def list_runs(cache_dir: str = None, limit: int = 50) -> list:
    """
    Past runs, newest first.

    Unreadable or half-written files are skipped rather than raising: a corrupt
    cache entry should cost you one history row, not the page.
    """
    cache_dir = cache_dir or CACHE_DIR
    runs = []
    for path in glob.glob(os.path.join(cache_dir, "report_*.json")):
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                continue
            runs.append(_summarise(path, payload))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            log(f"[dim]Skipping unreadable cache file {path}: {exc}[/dim]")
    runs.sort(key=lambda run: run["saved_at"], reverse=True)
    return runs[:limit]


def load_run(path: str) -> dict:
    """Load a full report by path. Returns {} if it cannot be read."""
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        log(f"[yellow]Could not load run {path}: {exc}[/yellow]")
        return {}


def delete_run(path: str) -> bool:
    """Remove one cached run. Returns whether anything was deleted."""
    try:
        os.remove(path)
        return True
    except OSError:
        return False


def history_stats(runs: list) -> dict:
    """Totals across the listed runs — what the tool has cost you so far."""
    costs = [r["cost_usd"] for r in runs if isinstance(r.get("cost_usd"), (int, float))]
    tokens = [r["total_tokens"] for r in runs if isinstance(r.get("total_tokens"), (int, float))]
    scores = [r["score"] for r in runs if isinstance(r.get("score"), (int, float))]
    return {
        "runs": len(runs),
        "total_cost_usd": round(sum(costs), 4),
        "total_tokens": sum(tokens),
        "runs_with_cost_data": len(costs),
        "average_score": round(sum(scores) / len(scores), 2) if scores else None,
    }
