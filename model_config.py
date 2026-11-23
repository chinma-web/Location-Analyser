"""Groq model selection. Availability is not a promise about pricing or free quota."""
import os
import time
import threading
from groq import Groq

PREFERENCES = {
    'analyst': ['openai/gpt-oss-120b', 'openai/gpt-oss-20b', 'qwen/qwen3-32b', 'llama-3.3-70b-versatile', 'llama-3.1-8b-instant'],
    'guardrail': ['openai/gpt-oss-20b', 'openai/gpt-oss-120b', 'qwen/qwen3-32b', 'llama-3.1-8b-instant'],
    'verifier': ['qwen/qwen3.8-27b', 'qwen/qwen3-32b', 'openai/gpt-oss-20b', 'openai/gpt-oss-120b', 'llama-3.1-8b-instant'],
    'verdict': ['openai/gpt-oss-120b', 'openai/gpt-oss-20b', 'qwen/qwen3-32b', 'llama-3.3-70b-versatile'],
}
ENV = {'analyst':'STRONG_MODEL','guardrail':'FAST_MODEL','verifier':'VERIFIER_MODEL','verdict':'VERDICT_MODEL'}
DEFAULTS = {'analyst':'openai/gpt-oss-120b','guardrail':'openai/gpt-oss-20b','verifier':'openai/gpt-oss-20b','verdict':'openai/gpt-oss-120b'}
_cache = {}
_lock = threading.Lock()

def configured_models():
    return {role:os.getenv(env, '').strip() or DEFAULTS[role] for role,env in ENV.items()}

def fetch_catalog():
    key = os.getenv('GROQ_API_KEY', '')
    if not key:
        return None
    # Memory only, keyed by credential to avoid reusing another account's catalog.
    with _lock:
        entry = _cache.get(key)
        if entry and time.monotonic()-entry[0] < 300:
            return entry[1]
        try:
            with Groq(api_key=key, timeout=8, max_retries=0) as client:
                result = {m.id for m in client.models.list().data if getattr(m, 'active', True)}
        except Exception:
            result = None
        _cache.clear()
        _cache[key] = (time.monotonic(), result)
        return result

def resolve_models():
    requested = configured_models()
    catalog = fetch_catalog()
    roles = {}
    notes = []
    if catalog is None:
        return {'roles':requested,'catalog_verified':False,'notes':['Model catalog unavailable or key not configured. Using configured defaults; availability and free-tier quota are unverified.']}
    for role in ENV:
        # Prefer explicit overrides; otherwise allow the requested Qwen variant only
        # when the catalog actually includes its exact ID.
        explicit = os.getenv(ENV[role], '').strip()
        candidates = ([explicit] if explicit else []) + PREFERENCES[role]
        chosen = next((name for name in candidates if name in catalog), None)
        if chosen is None:
            raise RuntimeError(f'No supported text model is available for {role}. Configure {ENV[role]} with an accessible chat model ID.')
        roles[role] = chosen
        if explicit and chosen != explicit:
            notes.append(f'{ENV[role]} was unavailable; selected {chosen}.')
    return {'roles':roles,'catalog_verified':True,'notes':notes or ['Selected from the active Groq catalog. Account quotas and pricing still apply.']}
