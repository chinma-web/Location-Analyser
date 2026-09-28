"""
Geocoding and place lookup via Photon (komoot), plus safe Google Maps URL
expansion. Photon responses are LRU-cached: autocomplete fires on every
keystroke.
"""

import functools
import json
import urllib.parse
import urllib.request

from locan.logging_utils import log

# ── Geocoder helpers (Photon / komoot) ───────────────────────────────────────

# Autocomplete fires on every keystroke and the place lookup geocodes the city
# again each time, so the same handful of queries hit Photon over and over.
# Geocoding results are stable, so an in-process LRU is the right cache: it
# survives Streamlit reruns (the module stays imported) and keeps us well inside
# Komoot's fair-use policy.
GEOCODE_CACHE_SIZE = 256


@functools.lru_cache(maxsize=GEOCODE_CACHE_SIZE)
def _photon_request_cached(params_items: tuple, timeout: int = 6) -> str:
    """Cached transport layer. Returns the raw JSON body (hashable, immutable)."""
    url = "https://photon.komoot.io/api/?" + urllib.parse.urlencode(dict(params_items))
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:   # noqa: S310 (fixed host)
        return resp.read().decode()


def _photon_request(params: dict, timeout: int = 6) -> dict:
    # sorted() so equivalent queries share a cache entry regardless of key order
    body = _photon_request_cached(tuple(sorted(params.items())), timeout)
    return json.loads(body)


def geocode_cache_info() -> str:
    info = _photon_request_cached.cache_info()
    return f"hits={info.hits} misses={info.misses} size={info.currsize}"


def clear_geocode_cache() -> None:
    _photon_request_cached.cache_clear()


def geocode_city(city: str) -> tuple:
    if not city or not city.strip():
        return None, None
    try:
        data = _photon_request({"q": city.strip(), "limit": 1, "lang": "en"})
        feats = data.get("features", [])
        if feats:
            coords = feats[0].get("geometry", {}).get("coordinates", [])
            if len(coords) == 2:
                return coords[1], coords[0]
    except Exception as e:
        log(f"[yellow]City geocode error: {e}[/yellow]")
    return None, None


def get_place_suggestions(query: str, city: str = "", limit: int = 7) -> list:
    if not query or len(query.strip()) < 2:
        return []

    q = f"{query.strip()} {city.strip()}" if city.strip() else query.strip()
    params: dict = {"q": q, "limit": limit * 2, "lang": "en"}

    city_lat, city_lon = None, None
    if city.strip():
        city_lat, city_lon = geocode_city(city)
        if city_lat is not None:
            params["lat"] = city_lat
            params["lon"] = city_lon

    try:
        data = _photon_request(params)
    except Exception as e:
        log(f"[yellow]Photon autocomplete error: {e}[/yellow]")
        return []

    city_lower = city.strip().lower()
    preferred, fallback = [], []
    seen: set = set()

    for feat in data.get("features", []):
        props  = feat.get("properties", {})
        coords = feat.get("geometry", {}).get("coordinates", [None, None])
        name    = props.get("name", "").strip()
        p_city  = (props.get("city") or props.get("town") or
                   props.get("village") or props.get("county") or "").strip()
        state   = props.get("state", "").strip()
        country = props.get("country", "").strip()

        if not name:
            continue

        label_parts  = [p for p in [name, p_city, state, country] if p]
        display      = ", ".join(label_parts)
        search_parts = [p for p in [name, p_city, country] if p]
        search_name  = ", ".join(search_parts) if search_parts else display

        if search_name in seen:
            continue
        seen.add(search_name)

        entry = {
            "display_name": display,
            "search_name":  search_name,
            "lat":          coords[1],
            "lon":          coords[0],
            "type":         props.get("type", ""),
            "category":     props.get("osm_key", ""),
        }

        location_text = f"{name} {p_city} {state} {country}".lower()
        if city_lower and city_lower in location_text:
            preferred.append(entry)
        else:
            fallback.append(entry)

    combined = preferred + fallback
    return combined[:limit]


def get_city_suggestions(query: str, limit: int = 6) -> list:
    if not query or len(query.strip()) < 2:
        return []

    params = {"q": query.strip(), "limit": limit * 3, "lang": "en"}
    try:
        data = _photon_request(params)
    except Exception as e:
        log(f"[yellow]City suggestions error: {e}[/yellow]")
        return []

    city_types = {"city", "town", "village", "municipality", "borough",
                  "suburb", "district", "county", "state", "administrative"}
    results, seen = [], set()

    for feat in data.get("features", []):
        props   = feat.get("properties", {})
        name    = props.get("name", "").strip()
        country = props.get("country", "").strip()
        osm_val = props.get("osm_value", "").lower()
        osm_key = props.get("osm_key", "").lower()

        if osm_key not in ("place", "boundary") and osm_val not in city_types:
            continue

        label = f"{name}, {country}" if country else name
        if label in seen or not name:
            continue
        seen.add(label)
        results.append(label)

        if len(results) >= limit:
            break

    return results


# ── URL expander ──────────────────────────────────────────────────────────────

# Only these hosts are followed when expanding a shortened Maps link. Without an
# allowlist the app will fetch any URL a user pastes, which is an SSRF vector if
# this is ever deployed server-side.
ALLOWED_MAPS_HOSTS = (
    "google.com", "www.google.com", "maps.google.com",
    "goo.gl", "maps.app.goo.gl", "g.co",
)


def _host_allowed(url: str) -> bool:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return any(host == allowed or host.endswith("." + allowed) for allowed in ALLOWED_MAPS_HOSTS)


def expand_maps_url(url: str) -> str:
    """Resolve a shortened Google Maps link to its final URL."""
    if not _host_allowed(url):
        log(f"[yellow]Refusing to expand non-Google host: {urllib.parse.urlparse(url).hostname}[/yellow]")
        return url
    try:
        # HEAD: we only want the redirect target, not the whole page body.
        req = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "Mozilla/5.0 (compatible; LocationAnalyzer/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:   # noqa: S310 (allowlisted host)
            final_url = resp.url
        if not _host_allowed(final_url):
            log("[yellow]Redirect left the allowlist — using the original URL[/yellow]")
            return url
        log(f"[dim]🔗 Expanded URL: {final_url[:80]}…[/dim]")
        return final_url
    except Exception as e:
        log(f"[yellow]URL expand warning: {e} — using original URL[/yellow]")
        return url
