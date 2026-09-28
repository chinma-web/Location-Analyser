"""Model B — independent verification of Model A's output."""

import json

from locan import llm
from locan.config import GROQ_KEY, VERIFIER_MODEL
from locan.logging_utils import log
from locan.reviews import validate_evidence_ids

# ── MODULE 4: Model 2 (Model B) — Groq Independent Verifier ──────────────────

# The five claim families Model 2 is asked to audit.
VERIFIED_FIELDS = ("sentiment", "aspects", "keywords", "guardrail", "evidence")

# Overall statuses. UNAVAILABLE means the verifier never produced a usable answer;
# UNKNOWN means it answered but with a status we don't recognise.
VERIFICATION_STATUSES = ("PASS", "CORRECTED", "FAIL", "UNAVAILABLE", "UNKNOWN")

# Statuses that represent a real, completed independent audit.
VERIFICATION_COMPLETED = ("PASS", "CORRECTED", "FAIL")


def _log_verification(result: dict, note: str = "") -> None:
    """Print a verification summary that never implies more than actually happened."""
    status   = result.get("verification_status", "UNKNOWN")
    acc      = result.get("accuracy")
    acc_str  = f"{acc:.0%}" if isinstance(acc, (int, float)) else "not reported"
    hall     = result.get("hallucination_detected")
    hall_str = "unknown" if hall is None else str(hall)
    n_corr   = len(result.get("corrections", []))
    n_ok     = len(result.get("fields_checked", []))
    suffix   = f" ({note})" if note else ""
    colour   = "green" if status in VERIFICATION_COMPLETED else "yellow"
    log(
        f"[{colour}]✓  Model 2 Verifier (Groq){suffix}: {status}  |  "
        f"Fields audited: {n_ok}/{len(VERIFIED_FIELDS)}  |  Self-reported accuracy: {acc_str}  |  "
        f"Hallucination: {hall_str}  |  Corrections: {n_corr}[/{colour}]"
    )
    unchecked = result.get("fields_unchecked", [])
    if unchecked:
        log(f"[dim]   Unchecked fields (verifier said nothing usable): {', '.join(unchecked)}[/dim]")


VERIFIER_SYSTEM_PROMPT = """You are Model 2 (Independent Verifier), cross-auditing Model 1's analysis against real Google Maps reviews.
Do NOT assume Model 1 is correct. Extract factual observations directly from the review text for each field.
Check:
1. Sentiment: Does overall sentiment match review ratings and text?
2. Aspects: Are food/service/ambience/value scores substantiated by reviews?
3. Keywords: Are extracted keywords genuinely frequent in review text?
4. Guardrail: Are reviews authentic with organic variation and believable tone?
5. Evidence: Do cited claims accurately reflect reviewer statements?

Return ONLY valid JSON matching this schema:
{
  "verification_status": "PASS|CORRECTED|FAIL",
  "accuracy": 0.92,
  "sentiment":  {"status": "PASS|CORRECTED|FAIL", "observations": ["1-2 factual observations from reviews"], "issues": []},
  "aspects":    {"status": "PASS|CORRECTED|FAIL", "observations": ["1-2 factual observations from reviews"], "issues": []},
  "keywords":   {"status": "PASS|CORRECTED|FAIL", "observations": ["1-2 factual observations from reviews"], "issues": []},
  "guardrail":  {"status": "PASS|CORRECTED|FAIL", "observations": ["1-2 factual observations from reviews"], "issues": []},
  "evidence":   {"status": "PASS|FAIL",           "observations": ["1-2 factual observations from reviews"], "unsupported_claims": [], "issues": []},
  "hallucination_detected": false,
  "corrections": [],
  "missing_positive_evidence": [],
  "missing_negative_evidence": [],
  "verification_notes": "1-sentence verification summary"
}"""


def verify_analysis(reviews: list, model_a_sentiment: dict, model_a_guardrail: dict) -> dict:
    """
    MODEL B — Independent verification via Groq (VERIFIER_MODEL).
    Uses a different Groq model from Model A for independent verification.
    Receives ORIGINAL reviews + trimmed Model A analysis.
    Returns verification JSON or an UNAVAILABLE status dict on failure.
    Does NOT generate a recommendation or score.
    """
    log(
        f"\n[bold magenta]🔍  Model B — Independent verification "
        f"(Groq / {VERIFIER_MODEL})[/bold magenta]"
    )

    if not GROQ_KEY:
        log("[yellow]⚠  GROQ_API_KEY not set — Model B verification unavailable.[/yellow]")
        return _unavailable_verification("GROQ_API_KEY is not configured.")

    # ── Trim reviews: cap at 20, text at 150 chars ────────────────────────────
    review_sample = reviews[:20]
    review_list = [
        {
            "id":     r.get("id") or f"r{i+1}",   # stable ID, never re-numbered
            "rating": r["rating"],
            "text":   r["text"][:150],
        }
        for i, r in enumerate(review_sample)
    ]

    # ── Trim Model A summary to essentials only ───────────────────────────────
    # Aspects: keep score + mentions + first evidence ID only
    asp_trimmed = {}
    for k, v in model_a_sentiment.get("aspect_scores", {}).items():
        if isinstance(v, dict) and v.get("score") is not None:
            asp_trimmed[k] = {
                "score":    v.get("score"),
                "mentions": v.get("reviews_mentioning", 0),
                "ids":      (v.get("evidence_review_ids") or [])[:2],
            }

    # Positive / negative points: claim + first 2 IDs only
    def _trim_points(pts):
        out = []
        for p in (pts or [])[:4]:
            if isinstance(p, dict):
                out.append({"claim": (p.get("claim") or "")[:80],
                            "ids": (p.get("evidence_review_ids") or [])[:2]})
        return out

    # Concerns: aspect + severity + first 2 IDs
    concerns_trimmed = [
        {"aspect": c.get("aspect",""), "severity": c.get("severity",""),
         "ids": (c.get("supporting_review_ids") or [])[:2]}
        for c in model_a_guardrail.get("genuine_concerns", [])[:4]
        if isinstance(c, dict)
    ]

    model_a_summary = {
        "sentiment": {
            "overall": model_a_sentiment.get("overall_sentiment"),
            "score":   model_a_sentiment.get("sentiment_score"),
        },
        "aspects":        asp_trimmed,
        "pos_keywords":   model_a_sentiment.get("positive_keywords", [])[:6],
        "neg_keywords":   model_a_sentiment.get("negative_keywords", [])[:6],
        "positive_points": _trim_points(model_a_sentiment.get("positive_points", [])),
        "negative_points": _trim_points(model_a_sentiment.get("negative_points", [])),
        "trust_score":     model_a_guardrail.get("trust_score"),
        "concerns":        concerns_trimmed,
    }

    user_prompt = f"""=== REVIEWS (up to 20, verify Model 1 against these) ===
{json.dumps(review_list, indent=2)}

=== MODEL 1 OUTPUT (verify this) ===
{json.dumps(model_a_summary, indent=2)}

OUTPUT ONLY THE JSON BELOW. DO NOT include any explanation, reasoning, or markdown. Start with {{ and end with }}.

{{
  "verification_status": "PASS|CORRECTED|FAIL",
  "accuracy": 0.92,
  "sentiment":  {{"status": "PASS|CORRECTED|FAIL", "observations": ["observations from reviews"], "issues": []}},
  "aspects":    {{"status": "PASS|CORRECTED|FAIL", "observations": ["observations from reviews"], "issues": []}},
  "keywords":   {{"status": "PASS|CORRECTED|FAIL", "observations": ["observations from reviews"], "issues": []}},
  "guardrail":  {{"status": "PASS|CORRECTED|FAIL", "observations": ["observations from reviews"], "issues": []}},
  "evidence":   {{"status": "PASS|FAIL",           "observations": ["observations from reviews"], "unsupported_claims": [], "issues": []}},
  "hallucination_detected": false,
  "corrections": [
    {{
      "field": "e.g. aspects.food_quality",
      "original_claim": "Model 1 claim",
      "corrected_claim": "what reviews actually support",
      "reason": "brief reason",
      "evidence_review_ids": ["r1"]
    }}
  ],
  "missing_positive_evidence": [],
  "missing_negative_evidence": [],
  "verification_notes": "1 sentence summary"
}}

RULES: Only correct claims unsupported by review text. Every correction needs evidence_review_ids. No recommendation."""

    try:
        result = _normalise_verification(llm.call_verifier(VERIFIER_SYSTEM_PROMPT, user_prompt, max_tokens=1500))
        result = validate_evidence_ids(result, reviews, "Model B verification")
        _log_verification(result)
        return result
    except RuntimeError as e:
        err_msg = str(e)
        if "null content" in err_msg.lower() and len(review_list) > 10:
            log("[yellow]⚠  Model 2 returned null, retrying with fewer reviews...[/yellow]")
            retry_list = review_list[:10]
            retry_prompt = user_prompt.replace(json.dumps(review_list, indent=2), json.dumps(retry_list, indent=2))
            try:
                result = _normalise_verification(
                    llm.call_verifier(VERIFIER_SYSTEM_PROMPT, retry_prompt, max_tokens=1500)
                )
                result = validate_evidence_ids(result, reviews, "Model B verification")
                _log_verification(result, note="10-review retry")
                return result
            except RuntimeError as e2:
                log(f"[yellow]⚠  Model 2 unavailable: {e2}[/yellow]")
                return _unavailable_verification(str(e2))
        
        log(f"[yellow]⚠  Model 2 unavailable: {e}[/yellow]")
        return _unavailable_verification(str(e))


def _normalise_verification(verif: dict) -> dict:
    """
    Normalise the verifier's raw JSON into the shape the rest of the app expects.

    HARD RULE: this function must never invent an observation, a status, or an
    accuracy figure. Fields the verifier did not report are marked UNCHECKED with
    empty observations. A blank audit is an honest audit; a synthetic one silently
    turns "we could not verify this" into "we verified this".
    """
    if not isinstance(verif, dict):
        verif = {}

    status = verif.get("verification_status") or verif.get("status") or "UNKNOWN"
    if status not in VERIFICATION_STATUSES:
        status = "UNKNOWN"
    verif["verification_status"] = status
    verif["status"] = status

    acc = verif.get("accuracy")
    verif["accuracy"] = float(acc) if isinstance(acc, (int, float)) else None

    if not isinstance(verif.get("hallucination_detected"), bool):
        verif["hallucination_detected"] = None   # unknown, not False

    corrections = verif.get("corrections")
    verif["corrections"] = corrections if isinstance(corrections, list) else []

    checked_fields, unchecked_fields = [], []
    for field in VERIFIED_FIELDS:
        fdata = verif.get(field)
        if not isinstance(fdata, dict):
            fdata = {}

        obs = [o for o in (fdata.get("observations") or []) if isinstance(o, str) and o.strip()]
        issues = [i for i in (fdata.get("issues") or []) if i]

        fstatus = fdata.get("status")
        if fstatus not in ("PASS", "CORRECTED", "FAIL"):
            # The verifier said nothing usable about this field — say so.
            fstatus = "UNCHECKED"

        fdata["status"] = fstatus
        fdata["observations"] = obs
        fdata["issues"] = issues
        if field == "evidence":
            fdata["unsupported_claims"] = fdata.get("unsupported_claims") or []
        verif[field] = fdata

        (unchecked_fields if fstatus == "UNCHECKED" else checked_fields).append(field)

    verif["fields_checked"]   = checked_fields
    verif["fields_unchecked"] = unchecked_fields
    verif["coverage"]         = round(len(checked_fields) / len(VERIFIED_FIELDS), 2)

    if not verif.get("verification_notes"):
        if unchecked_fields:
            verif["verification_notes"] = (
                f"Verifier reported on {len(checked_fields)}/{len(VERIFIED_FIELDS)} fields; "
                f"unchecked: {', '.join(unchecked_fields)}."
            )
        else:
            verif["verification_notes"] = "Verifier reported on all fields."

    return verif


def _unavailable_verification(reason: str) -> dict:
    """
    Build an honest 'this did not run' payload.

    Previously this returned status=PASS with accuracy=0.92, which meant a verifier
    that crashed, timed out, or was never configured still rendered as a green
    92%-accurate independent audit, and made REQUIRE_VERIFICATION unreachable.
    """
    def blank():
        return {"status": "UNCHECKED", "observations": [], "issues": []}

    return {
        "verification_status":    "UNAVAILABLE",
        "status":                 "UNAVAILABLE",
        "accuracy":               None,
        "reason":                 reason,
        "sentiment":              blank(),
        "aspects":                blank(),
        "keywords":               blank(),
        "guardrail":              blank(),
        "evidence":               {**blank(), "unsupported_claims": []},
        "hallucination_detected": None,
        "corrections":            [],
        "fields_checked":         [],
        "fields_unchecked":       list(VERIFIED_FIELDS),
        "coverage":               0.0,
        "verification_notes":     f"Independent verification did not run: {reason}",
    }
