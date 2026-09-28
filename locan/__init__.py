"""
Location Review AI Analyzer.

Two-model architecture:
  Model A — Groq (llama-3.3-70b-versatile) — primary analyst
  Model B — Groq (llama-3.1-8b-instant)    — independent verifier
Final recommendation: deterministic Python scoring only.

Submodules:
  config          env vars, credential validation, lazy API clients
  logging_utils   markup-aware library logging
  ratelimit       token-bucket pacing for the Groq API
  llm             Groq transport, JSON repair, verifier call
  geo             Photon geocoding, place suggestions, URL expansion
  reviews         stable review IDs, evidence validation, text similarity
  scraper         Apify Google Maps scraping
  sentiment       Model A batched sentiment
  guardrail       heuristic + LLM red-flag analysis
  verify          Model B verification
  corrections     applying accepted corrections
  scoring         pure deterministic scoring engine
  pipeline        analyze() — the end-to-end run
  report          Rich terminal rendering
  cache           on-disk report cache
  ui              HTML escaping for the Streamlit layer
"""

from locan.cache import CACHE_TTL_HOURS, cache_key, cache_path, read_cache, write_cache
from locan.config import (
    ConfigError,
    get_apify,
    get_groq,
    missing_credentials,
    validate_config,
)
from locan.geo import expand_maps_url, geocode_city, get_city_suggestions, get_place_suggestions
from locan.logging_utils import configure_logging, log, logger, strip_markup
from locan.pipeline import analyze
from locan.reviews import assign_review_ids, known_review_ids, validate_evidence_ids
from locan.scoring import DEFAULT_CONFIG, ScoringConfig, score_location

__all__ = [
    "CACHE_TTL_HOURS", "ConfigError", "DEFAULT_CONFIG", "ScoringConfig", "analyze",
    "assign_review_ids", "cache_key", "cache_path", "configure_logging",
    "expand_maps_url", "geocode_city", "get_apify", "get_city_suggestions", "get_groq",
    "get_place_suggestions", "known_review_ids", "log", "logger", "missing_credentials",
    "read_cache", "score_location", "strip_markup", "validate_config",
    "validate_evidence_ids", "write_cache",
]
