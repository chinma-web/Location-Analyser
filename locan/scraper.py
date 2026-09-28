"""Apify Google Maps review scraping and review statistics."""

import urllib.parse

from locan.config import ACTOR_ID, get_apify
from locan.geo import expand_maps_url, get_place_suggestions
from locan.logging_utils import log
from locan.reviews import _clean_reviews, assign_review_ids
from locan.usage import METER

# ── MODULE 1: Apify Scraper ───────────────────────────────────────────────────

def scrape_reviews(location: str, max_reviews: int = 40) -> tuple:
    """
    Scrape Google Maps reviews for `location` using Apify.
    Returns (reviews, place_info, review_stats).

    review_stats contains:
        raw_scraped_count       — total items returned by Apify for the best place
        usable_text_review_count — reviews that have non-empty text
        cleaned_review_count    — after dedup / spam filtering
        analyzed_review_count   — set later after cleaning (same as cleaned here)
    """
    log(f"\n[bold cyan]📡  Step 1 — Scraping:[/bold cyan] {location}")

    is_url      = location.strip().startswith("http")
    is_place_id = location.strip().lower().startswith("place_id:")

    if is_url:
        expanded = expand_maps_url(location.strip())
        run_input = {
            "startUrls":           [{"url": expanded}],
            "maxCrawledPlaces":    1,
            "maxReviews":          max_reviews,
            "reviewsSort":         "newest",
            "language":            "en",
            "includeOpeningHours": True,
        }
    elif is_place_id:
        run_input = {
            "searchStringsArray":  [location.strip()],
            "maxCrawledPlaces":    1,
            "maxReviews":          max_reviews,
            "reviewsSort":         "newest",
            "language":            "en",
            "includeOpeningHours": True,
        }
    else:
        place_query = location.strip()
        sugg        = get_place_suggestions(place_query, city="", limit=1)

        if sugg and sugg[0].get("lat") and sugg[0].get("lon"):
            place_lat  = sugg[0]["lat"]
            place_lon  = sugg[0]["lon"]
            place_name = sugg[0]["search_name"]
            log(f"[dim]🌐 Place geocoded: {place_name} -> lat={place_lat:.5f}, lon={place_lon:.5f}[/dim]")
            maps_url = (
                f"https://www.google.com/maps/search/"
                f"{urllib.parse.quote(place_query)}"
                f"/@{place_lat},{place_lon},17z"
            )
            run_input = {
                "startUrls":           [{"url": maps_url}],
                "maxCrawledPlaces":    3,
                "maxReviews":          max_reviews,
                "reviewsSort":         "newest",
                "language":            "en",
                "includeOpeningHours": True,
            }
        else:
            log("[yellow]⚠ Place geocoding failed — using plain text search[/yellow]")
            run_input = {
                "searchStringsArray":  [location.strip()],
                "maxCrawledPlaces":    5,
                "maxReviews":          max_reviews,
                "reviewsSort":         "newest",
                "language":            "en",
                "includeOpeningHours": True,
            }

    try:
        run = get_apify().actor(ACTOR_ID).call(run_input=run_input)
        METER.record_scrape()
        if isinstance(run, dict):
            dataset_id = run.get("defaultDatasetId") or run.get("default_dataset_id")
        else:
            dataset_id = getattr(run, "default_dataset_id", getattr(run, "defaultDatasetId", None))
            if not dataset_id and hasattr(run, "get"):
                dataset_id = run.get("defaultDatasetId")
        if not dataset_id:
            raise ValueError(f"Could not retrieve dataset ID from run: {run}")

        all_places = list(get_apify().dataset(dataset_id).iterate_items())
        if not all_places:
            log("[red]✗  No places returned by Apify.[/red]")
            return [], {}, _empty_review_stats()

        best = max(all_places, key=lambda p: p.get("reviewsCount") or 0)

        place_info = {
            "name":               best.get("title") or location,
            "address":            best.get("address") or "",
            "google_score":       best.get("totalScore") or 0,
            "review_count":       best.get("reviewsCount") or 0,
            "category":           best.get("categoryName") or "",
            "subtypes":           best.get("categories") or [],
            "description":        best.get("description") or "",
            "price":              best.get("price") or "",
            "opening_hours":      best.get("openingHours") or [],
            "website":            best.get("website") or "",
            "phone":              best.get("phone") or "",
            "location_type":      best.get("locationType") or "",
            "latitude":           (best.get("location") or {}).get("lat"),
            "longitude":          (best.get("location") or {}).get("lng"),
            "permanently_closed": best.get("permanentlyClosed") or False,
            "temporarily_closed": best.get("temporarilyClosed") or False,
        }

        # ── Build raw list ──
        raw_reviews = best.get("reviews") or []
        raw_scraped_count = len(raw_reviews)

        # ── Usable = has non-empty text ──
        usable = []
        for r in raw_reviews:
            text = (r.get("text") or "").strip()
            if text:
                usable.append({
                    "author": r.get("name") or "Anonymous",
                    "rating": r.get("stars") or 3,
                    "text":   text[:800],
                    "date":   r.get("publishedAtDate") or None,
                    "likes":  r.get("likesCount") or 0,
                })
        usable_text_review_count = len(usable)

        # ── Clean: remove near-duplicates (>70% Jaccard) and obvious spam ──
        cleaned = assign_review_ids(_clean_reviews(usable))
        cleaned_review_count = len(cleaned)

        review_stats = {
            "raw_scraped_count":        raw_scraped_count,
            "usable_text_review_count": usable_text_review_count,
            "cleaned_review_count":     cleaned_review_count,
            "analyzed_review_count":    cleaned_review_count,  # updated in analyze()
        }

        name = place_info.get("name", location)
        log(
            f"[green]✓  Scraped {raw_scraped_count} raw  |  "
            f"{usable_text_review_count} usable  |  "
            f"{cleaned_review_count} after cleaning  for \"{name}\"[/green]"
        )
        return cleaned, place_info, review_stats

    except Exception as e:
        log(f"[red]✗  Apify scraping failed: {e}[/red]")
        raise RuntimeError(f"Unable to collect reviews right now. Apify error: {e}") from e


def _empty_review_stats() -> dict:
    return {
        "raw_scraped_count":        0,
        "usable_text_review_count": 0,
        "cleaned_review_count":     0,
        "analyzed_review_count":    0,
    }
