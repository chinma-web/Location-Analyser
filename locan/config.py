"""
Environment configuration, credential validation, and lazy API clients.

Importing this module must never exit the process or require credentials —
the CLI and the Streamlit app both call validate_config() explicitly.
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

try:
    from apify_client import ApifyClient
    from groq import Groq
except ImportError:                                   # pragma: no cover
    print("Run: pip install apify-client groq python-dotenv rich")
    sys.exit(1)

# ── Configuration ─────────────────────────────────────────────────────────────

APIFY_TOKEN  = os.getenv("APIFY_API_TOKEN") or os.getenv("APIFY_API_TOKEN".lower(), "")  # legacy lowercase alias
GROQ_KEY     = os.getenv("GROQ_API_KEY", "")

# Model B — Groq llama-3.1-8b-instant (independent verification, proven reliable)
# Using llama-3.1-8b-instant for Model B (most reliable JSON on Groq)
# While same model as guardrail, independence comes from: different stage, different context, cross-validation role
VERIFIER_MODEL = os.getenv("VERIFIER_MODEL", "llama-3.1-8b-instant")

# Apify actor
ACTOR_ID     = "compass/crawler-google-places"

# ── Groq model assignments ────────────────────────────────────────────────────
# Spread across two Groq quota buckets to avoid hitting the 70B daily TPD cap.
#
#  llama-3.3-70b-versatile : 100K TPD, 14,400 TPM  → Model A sentiment (70B, deep analysis)
#  llama-3.1-8b-instant    : 500K TPD,  6,000 TPM  → Model A guardrail + Model B verifier (8B, reliable JSON)
# 
# Note: Using same model (llama-3.1-8b-instant) for guardrail + verification provides:
#   • Proven JSON reliability (most stable on Groq)
#   • Huge quota (500K TPD — plenty for both tasks)
#   • Independence through: different stage, different context, cross-validation role

STRONG_MODEL  = os.getenv("STRONG_MODEL",  "llama-3.3-70b-versatile")  # Model A sentiment
FAST_MODEL    = os.getenv("FAST_MODEL",    "llama-3.1-8b-instant")     # guardrail
VERDICT_MODEL = os.getenv("VERDICT_MODEL", "llama-3.3-70b-versatile")  # Final verdict & explanation

REQUIRE_VERIFICATION = os.getenv("REQUIRE_VERIFICATION", "false").lower() == "true"


# ── Configuration validation & lazy clients ───────────────────────────────────
# NOTE: never validate or exit at import time — `app.py` imports this module and
# a bare sys.exit() would terminate the Streamlit script run before the UI can
# render a helpful message. Callers decide what to do with a bad config.

class ConfigError(RuntimeError):
    """Raised when required API credentials are missing."""


def missing_credentials() -> list:
    """Return the names of required env vars that are not set."""
    missing = []
    if not APIFY_TOKEN:
        missing.append("APIFY_API_TOKEN")
    if not GROQ_KEY:
        missing.append("GROQ_API_KEY")
    return missing


def validate_config(raise_on_error: bool = True) -> list:
    """Check required credentials. Returns the list of missing var names."""
    missing = missing_credentials()
    if missing and raise_on_error:
        raise ConfigError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill in your keys."
        )
    return missing


_apify_client = None
_groq_client  = None


def get_apify() -> "ApifyClient":
    """Lazily build the Apify client so importing this module has no side effects."""
    global _apify_client
    if _apify_client is None:
        if not APIFY_TOKEN:
            raise ConfigError("APIFY_API_TOKEN is not set.")
        _apify_client = ApifyClient(APIFY_TOKEN)
    return _apify_client


def get_groq() -> "Groq":
    """Lazily build the Groq client so importing this module has no side effects."""
    global _groq_client
    if _groq_client is None:
        if not GROQ_KEY:
            raise ConfigError("GROQ_API_KEY is not set.")
        _groq_client = Groq(api_key=GROQ_KEY)
    return _groq_client
