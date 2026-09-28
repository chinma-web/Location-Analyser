"""
Groq transport: shared call helper, JSON repair, the Model B verifier call,
and rate-limit handling.
"""

import json
import os
import re
import time

from locan import config
from locan.config import FAST_MODEL, STRONG_MODEL, VERIFIER_MODEL
from locan.logging_utils import log
from locan.ratelimit import limiter_for

# Fallback wait (seconds) when Groq rate-limits us without a Retry-After hint.
RATE_LIMIT_BACKOFF = float(os.getenv("RATE_LIMIT_BACKOFF", "5"))

# ── Shared Groq helper ────────────────────────────────────────────────────────


def _retry_after_seconds(message: str):
    """Pull a 'try again in 1.5s' / 'retry after 12' hint out of a Groq error."""
    match = re.search(r"(?:try again in|retry after)\s*([0-9.]+)\s*(ms|s|seconds?)?", message, re.I)
    if not match:
        return None
    value = float(match.group(1))
    if (match.group(2) or "").lower() == "ms":
        value /= 1000.0
    return min(value, 60.0)   # never sleep longer than a minute on one hint


def call_groq(prompt: str, model: str = FAST_MODEL, max_tokens: int = 4096) -> dict:
    """Call Groq and parse the JSON response. Retries once on parse failure."""
    limiter = limiter_for(model)
    for attempt in range(2):
        try:
            limiter.acquire(prompt, max_tokens)
            res = config.get_groq().chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Respond ONLY with valid JSON. No markdown, no explanation."},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.2,
                max_tokens=max_tokens,
            )
            raw = res.choices[0].message.content.strip()

            # Strip reasoning model thinking tags if present (e.g. DeepSeek R1)
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

            # Strip markdown fences
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw

            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass

            start = raw.find("{")
            end   = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(raw[start:end+1])
                except json.JSONDecodeError:
                    pass

            if start != -1:
                fragment = raw[start:]
                opens     = fragment.count("{") - fragment.count("}")
                arr_opens = fragment.count("[") - fragment.count("]")
                in_str = False
                for ch in fragment:
                    if ch == '"':
                        in_str = not in_str
                if in_str:
                    fragment += '"'
                fragment += "]" * max(0, arr_opens) + "}" * max(0, opens)
                try:
                    return json.loads(fragment)
                except json.JSONDecodeError:
                    pass

            if attempt == 0:
                time.sleep(1)
                continue

            log("[yellow]⚠  JSON parse failed — returning empty result[/yellow]")
            return {}

        except Exception as e:
            err_str = str(e).lower()
            if "decommissioned" in err_str or "not found" in err_str:
                log(f"[yellow]⚠ Model `{model}` is deprecated or unavailable on Groq. Falling back to `{STRONG_MODEL}`...[/yellow]")
                try:
                    res = config.get_groq().chat.completions.create(
                        model=STRONG_MODEL if model != STRONG_MODEL else FAST_MODEL,
                        messages=[
                            {"role": "system", "content": "Respond ONLY with valid JSON. No markdown, no explanation."},
                            {"role": "user",   "content": prompt},
                        ],
                        temperature=0.2,
                        max_tokens=max_tokens,
                    )
                    raw = res.choices[0].message.content.strip()
                    if raw.startswith("```"):
                        parts = raw.split("```")
                        raw = parts[1].lstrip("json").strip() if len(parts) > 1 else raw
                    start = raw.find("{")
                    end = raw.rfind("}")
                    if start != -1 and end != -1 and end > start:
                        return json.loads(raw[start:end+1])
                    return json.loads(raw)
                except Exception as fb_err:
                    log(f"[red]Fallback model call failed: {fb_err}[/red]")
            elif "429" in err_str or "rate limit" in err_str or "too many requests" in err_str:
                # Respect Retry-After when the API supplies it, otherwise back off.
                retry_after = _retry_after_seconds(str(e)) or (RATE_LIMIT_BACKOFF * (attempt + 1))
                log(f"[yellow]⚠ Rate limited by Groq — waiting {retry_after:.1f}s[/yellow]")
                time.sleep(retry_after)
                if attempt == 0:
                    continue
                return {}
            else:
                log(f"[red]Groq error: {e}[/red]")
            if attempt == 0:
                time.sleep(2)
                continue
            return {}
    return {}


# ── Model B verifier call — Groq with JSON mode ──────────────────────────────

def call_verifier(system_prompt: str, user_prompt: str, max_tokens: int = 1500) -> dict:
    """
    Call Model B verifier (Groq with llama-3.1-8b-instant by default — most reliable JSON).
    Uses Groq's native JSON mode for reliable structured output.
    Returns parsed JSON dict, or raises RuntimeError on failure.
    """
    if not config.GROQ_KEY:
        raise RuntimeError("GROQ_API_KEY is not set in environment.")

    client = config.get_groq()
    
    limiter_for(VERIFIER_MODEL).acquire(system_prompt + user_prompt, max_tokens)
    try:
        response = client.chat.completions.create(
            model=VERIFIER_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=max_tokens,
            # Groq's native JSON mode — the docstring always claimed we used it,
            # but the parameter was never actually passed.
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
    except Exception as e:
        raise RuntimeError(f"Groq verifier call failed: {e}") from e

    if not raw:
        raise RuntimeError("Verifier returned empty content.")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try extracting first JSON object
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start:end+1])
            except json.JSONDecodeError:
                pass
        raise RuntimeError(
            f"Verifier response is not valid JSON. Raw (first 400): {raw[:400]}"
        ) from None
