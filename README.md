# 📍 Location Analyser

Scrapes real Google Maps reviews for a place and turns them into an **evidence-backed verdict** — not a vibe. Three LLM stages do the reading; a **deterministic Python engine** decides the score.

> **Design principle:** models describe, Python decides. No LLM can change the verdict, and the app says so out loud when part of the analysis could not be verified.

---

## What it does

```
              ┌──────────────┐
  place name  │    Apify     │  Google Maps reviews
  or Maps URL │   scraper    │  + place metadata
              └──────┬───────┘
                     │  clean · de-duplicate · assign stable IDs (r1…rN)
                     ▼
      ┌──────────────────────────────┐
      │ Model 1 — Analyst (Groq)     │  sentiment · aspects · themes · keywords
      │ llama-3.3-70b + llama-3.1-8b │  + heuristic & LLM authenticity guardrail
      └──────────────┬───────────────┘
                     ▼
      ┌──────────────────────────────┐
      │ Model 2 — Verifier (Groq)    │  independently re-reads the raw reviews and
      │ llama-3.1-8b                 │  cross-audits Model 1's claims, per field
      └──────────────┬───────────────┘
                     │  only evidence-backed corrections are applied
                     ▼
      ┌──────────────────────────────┐
      │ locan/scoring.py — pure Py   │  ← the verdict is decided HERE
      │ deterministic, unit-tested   │
      └──────────────┬───────────────┘
                     ▼
      ┌──────────────────────────────┐
      │ Model 3 — Verdict (Groq)     │  writes pros/cons/tips ONLY
      │ llama-3.3-70b                │  cannot change the score
      └──────────────────────────────┘
```

**Output:** a visit score out of 10, a verdict label, aspect radar, emotion and rating
distributions, authenticity/trust analysis, a field-by-field verification audit, visitor
tips, and a downloadable JSON report.

---

## Quick start

```bash
git clone https://github.com/chinma-web/Location-Analyser.git
cd Location-Analyser

python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env        # then add your two API keys
```

You need two free-tier keys:

| Key | Where | Used for |
|---|---|---|
| `APIFY_API_TOKEN` | [console.apify.com](https://console.apify.com) | Google Maps review scraping (paid compute units after the free tier) |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) | all three model stages (generous free tier) |

### Run the web app

```bash
streamlit run app.py
```

### Run the CLI

```bash
python -m locan.cli "Cafe Goodluck, Pune" 40      # place + max reviews
python -m locan.cli "https://maps.app.goo.gl/..." # or a Maps URL
python -m locan.cli "Eiffel Tower" --no-cache     # bypass the report cache
```

---

## Configuration

All settings are environment variables (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `STRONG_MODEL` | `llama-3.3-70b-versatile` | Model 1 sentiment analysis |
| `FAST_MODEL` | `llama-3.1-8b-instant` | Model 1 guardrail pass |
| `VERIFIER_MODEL` | `llama-3.1-8b-instant` | Model 2 independent verifier |
| `VERDICT_MODEL` | `llama-3.3-70b-versatile` | Model 3 prose generation |
| `REQUIRE_VERIFICATION` | `false` | If `true`, refuse to return a report when Model 2 could not run |
| `CACHE_DIR` | `cache` | Where reports are cached |
| `CACHE_TTL_HOURS` | `168` | Cache lifetime (7 days) |
| `LOG_LEVEL` | `INFO` | `DEBUG` for per-stage detail |

Scoring weights, verdict thresholds and penalties are **not** environment variables —
they live in `ScoringConfig` in `locan/scoring.py`, where they can be documented and tested:

```python
from scoring import ScoringConfig, score_location

strict = ScoringConfig(verdict_thresholds=((9.0, "WORTH A DETOUR"),))
result = score_location(reviews, place_info, sentiment, guardrail, verification, cfg=strict)
```

---

## How the score is built

The composite is a weighted mean over six components, each 0–10:

| Component | Weight | Source |
|---|---|---|
| Sentiment | 30% | Model 1's overall sentiment, mapped from −1…+1 |
| Aspects | 25% | weighted mean of the aspects that were actually scored |
| Google rating | 15% | the place's own star rating (or the scraped sample mean) |
| Trust | 15% | guardrail authenticity, adjusted by verification coverage |
| Consistency | 10% | how much reviewers agree with each other (dispersion) |
| Recency | 5% | recent sentiment, only when a real temporal trend exists |

Then `final = clamp(weighted_mean − risk_penalty, 0, 10)`.

**Components with no data are dropped and the remaining weights renormalised** — a place
with no aspect coverage is not scored as if it were mediocre. The report tells you which
components were used:

```json
"components_used":    ["aspect", "rating", "sentiment", "trust"],
"components_missing": ["consistency", "recency"],
"effective_weights":  {"sentiment": 0.353, "aspect": 0.294, "rating": 0.176, "trust": 0.176}
```

Verdict bands: `≥8.0` highly recommended · `≥6.5` recommended · `≥4.5` visit with caution · below that, not recommended.

---

## Honesty guarantees

These are enforced by tests, because they are easy to break and tempting to fake:

- **Verification can fail visibly.** If Model 2 does not run — bad key, timeout, malformed JSON — the report says `UNAVAILABLE` with `accuracy: null` and every field `UNCHECKED`. It never renders as a green pass. Set `REQUIRE_VERIFICATION=true` to refuse the report entirely.
- **Nothing is backfilled with generated text.** An empty section stays empty. Content derived from another stage is tagged `derived: true`, and confidence/severity it was never given stay `null`.
- **Citations are validated.** Review IDs are assigned once and every stage cites the same ones; references to reviews that don't exist are stripped.
- **Unverified analyses score lower**, never higher.
- **`confidence` is a data-sufficiency heuristic**, not a calibrated probability, and is labelled as such.

---

## Development

```bash
pip install -r requirements-dev.txt
pytest                 # ~100 tests, no API keys or network required
ruff check .
```

| Module | Responsibility |
|---|---|
| `locan/config.py` | env vars, credential validation, lazy API clients |
| `locan/logging_utils.py` | markup-aware library logging |
| `locan/ratelimit.py` | token-bucket pacing for the Groq API |
| `locan/llm.py` | Groq transport, JSON repair, verifier call |
| `locan/geo.py` | Photon geocoding, place suggestions, URL expansion |
| `locan/reviews.py` | stable review IDs, evidence validation, text similarity |
| `locan/scraper.py` | Apify Google Maps scraping |
| `locan/sentiment.py` | Model A — batched sentiment |
| `locan/guardrail.py` | heuristic + LLM red-flag analysis |
| `locan/verify.py` | Model B — independent verification |
| `locan/corrections.py` | applying accepted corrections |
| `locan/scoring.py` | deterministic scoring — pure, no I/O, no network |
| `locan/pipeline.py` | `analyze()` — the end-to-end run |
| `locan/report.py` | Rich terminal rendering (CLI only) |
| `locan/cache.py` | on-disk report cache |
| `locan/aspects.py` | category-aware aspect sets (hotel/gym/clinic/…) |
| `locan/grounding.py` | extractive counting: keywords and aspects vs. real text |
| `locan/compare.py` | side-by-side comparison of 2–4 places |
| `locan/usage.py` | token and cost accounting |
| `locan/history.py` | browsable run history over the report cache |
| `locan/export.py` | Markdown / HTML / JSON export |
| `locan/cli.py` | command-line entry point |
| `locan/ui.py` | presentation helpers (HTML escaping) |
| `location.py` | backwards-compatibility shim re-exporting `locan` |
| `app.py` | Streamlit dashboard |
| `tests/` | pure-logic coverage: scoring, cleaning, heuristics, merging, cache, integrity |

CI runs lint + tests on Python 3.10 and 3.12 and asserts the modules import with no
credentials present.

---

## Caveats

- **Scraping Google Maps** via Apify may conflict with Google's Terms of Service. Check
  your jurisdiction and use case before deploying this publicly.
- **Reviewer names are stored** verbatim in the exported JSON. Strip or hash them before
  sharing reports.
- Apify consumes paid compute units beyond the free tier; a 40-review run is small but
  not free.
- The aspect vocabulary (`food_quality`, `service`, …) is restaurant-shaped and is a poor
  fit for museums, parks or clinics. Category-aware aspects are on the roadmap.
- Reviews are a biased sample of visitors. This tool measures *what reviewers said*, not
  the objective quality of a place.

See [`ANALYSIS.md`](ANALYSIS.md) for the full code review and the improvement roadmap.
