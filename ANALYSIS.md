# Location-Analyser — Code Review & Improvement Roadmap

_Reviewed: 2026-09-28 · Commit `e7ab6cc` · 3,457 LOC across 3 files_

---

## 1. What the project is

A Streamlit app + CLI that:

1. **Scrapes** Google Maps reviews for a place via the Apify actor `compass/crawler-google-places`.
2. **Model 1 (Groq `llama-3.3-70b`)** — batched sentiment / aspect / theme analysis.
3. **Model 1 (Groq `llama-3.1-8b`)** — "guardrail" pass: fake-review heuristics + LLM authenticity judgement.
4. **Model 2 (Groq `llama-3.1-8b`)** — "independent verifier" that cross-audits Model 1 against raw review text.
5. **Deterministic Python scoring** — weighted composite → verdict label.
6. **Model 3 (Groq `llama-3.3-70b`)** — writes prose (pros/cons/tips) but cannot change the score.
7. Streamlit dashboard with 6 tabs, Plotly charts, JSON export. Photon/Komoot geocoding powers the city/place autocomplete.

### Genuine strengths

- **The core architectural idea is good and unusual.** Keeping the *verdict deterministic in Python* and demoting the LLM to a prose generator is the right call — most "AI review analyser" projects let the model hallucinate the score.
- **Evidence-ID plumbing** (`r1`, `r3` …) through sentiment → guardrail → verification is a real attempt at traceability.
- **Heuristic pre-pass** (`_heuristic_checks`) does rating-distribution, near-duplicate, n-gram and author-diversity checks in pure Python — cheap, deterministic, and not dependent on a model.
- **Batching** instead of the usual `reviews[:20]` truncation, with an explicit merge function.
- **Graceful degradation** everywhere; the app rarely hard-crashes mid-run.
- UI is genuinely dense and polished for a Streamlit app.

---

## 2. Critical issues (fix these first)

### 2.1 🔴 The "verification" layer fabricates its own results

This is the most serious problem, because verification is the project's headline feature.

- `_unavailable_verification()` (location.py ~L720) returns **`"verification_status": "PASS"` and `"accuracy": 0.92`** when Model 2 *failed to run at all* — wrong key, network error, bad JSON. The function name says UNAVAILABLE; the payload says PASS at 92 %.
- `_enrich_verification_data()` then **writes plausible-sounding observations into empty fields**, e.g.
  `"Model 1 overall sentiment 'Positive' accurately aligns with reviewer sentiment distribution."`
  and `"Checked 37 reviews for repetitive templated phrasing; organic natural reviews confirmed."`
  No model checked anything. The UI renders these under *"🔎 Extracted Review Observations"*.
- Same pattern in `_enrich_guardrail_data()` — invents `confidence: 0.92 - i*0.04` values and back-fills "verified facts".
- Consequence: `REQUIRE_VERIFICATION=true` is **dead code** (status is never `UNAVAILABLE`), and `calculate_final_score` multiplies trust by a fabricated 0.92 accuracy, and confidence gets a `+0.1` "verified" bonus it didn't earn.

**Fix:** verification must be able to fail loudly. Return `UNAVAILABLE`/`ERROR` with `accuracy: None`, render an honest banner, and have scoring *penalise* missing verification instead of rewarding a synthetic PASS. Delete the observation fabrication entirely — an empty field is more trustworthy than an invented one.

### 2.2 🔴 Review IDs don't line up between stages

- Sentiment batches label reviews `r{global_offset+i+1}` → IDs span the whole set.
- `guardrail_analysis` relabels `reviews[:18]` as `r1..r18`.
- `verify_analysis` relabels `reviews[:20]` as `r1..r20`.

So `r17` means three different reviews depending on which stage produced it, and the UI shows them side by side as if they were the same citation space. Every "evidence" claim past index 17 is unverifiable.

**Fix:** assign a stable `id` to each review once, immediately after cleaning, and pass that ID everywhere. Add a validator that drops any evidence ID that isn't in the known set.

### 2.3 🔴 `import location` can kill the Streamlit app

`location.py` L59-63 runs `sys.exit(1)` at **module import time** if keys are missing. `app.py` imports it at the top, so a missing key doesn't show the nice sidebar warning — it terminates the script run. Config validation belongs in a function called from `main()`/the CLI entry point.

### 2.4 🟠 HTML injection into the dashboard

31 `st.markdown(..., unsafe_allow_html=True)` calls interpolate **scraped review text, place names, and LLM output** directly into HTML. A review or place description containing `<img src=x onerror=...>` executes in the user's session. Escape with `html.escape()` (or stop hand-rolling HTML and use native Streamlit components).

### 2.5 🟠 Cache is collision-prone and unmanageable

`report_{slug}.json` is written to the **current working directory**, keyed on the first 30 alphanumeric chars of the query, with a hardcoded 7-day TTL, no cache-bypass button, and no `max_reviews` in the key. Every Google Maps URL collapses to roughly the same slug (`httpswwwgooglecommapsplace…`) → **URL mode will serve you another place's report**. Also not in `.gitignore`.

**Fix:** `cache/{sha256(normalised_query + max_reviews)[:16]}.json`, store `created_at` + query inside the payload, verify it on read, add a "Force refresh" checkbox, and gitignore `cache/`.

---

## 3. Correctness & scoring-model issues

| # | Issue | Why it matters |
|---|---|---|
| 1 | **Sentiment is triple-counted.** `sentiment_comp` (30 %), `recency_comp` (5 %, derived from the same `sentiment_score` when no trend), and `consistency_comp` (10 %, from per-review scores) all trace back to the same LLM signal. Effective weight ≈ 45 %. | Scores cluster; the weights don't mean what the docstring says. |
| 2 | **Unmentioned aspects default to 5.0** (`aspect_comp` fallback) and missing trust defaults to `0.7`. | A place with no data scores like a mediocre place, not an unknown one. |
| 3 | **`risk_penalty` double-dips.** Concerns are already reflected in sentiment, then subtracted again (up to −3.0). Because `_enrich_guardrail_data` *manufactures* concerns when the model returns none, a clean place can be penalised for having nothing wrong with it. | Systematic downward bias on quiet places. |
| 4 | **`rating_comp` mixes populations** — the Google score covers all N reviews, everything else covers the ≤100 scraped sample. | Fine, but should be documented/weighted for sample size. |
| 5 | **Verdict thresholds (8.0/6.5/4.5) and ~30 other magic numbers are inline.** | Untunable, untestable, undocumented. Move to a `ScoringConfig` dataclass. |
| 6 | **`confidence` formula is arbitrary** (`min(1, n/50)` plus ad-hoc bonuses). Not a probability, but rendered as a percentage. | Overstates rigour. Either derive it from sample variance or rename it "data sufficiency". |
| 7 | Batch merge averages `sentiment_score` **unweighted** across batches of unequal size. | Last partial batch gets the same weight as a full one. |
| 8 | `apply_corrections` regex-greps the *first number* out of a prose correction and treats it as an aspect score. `"only 3 of 20 reviews mention food"` → sets food_quality = 3.0. | Silent data corruption. Require a structured `corrected_score` field. |

---

## 4. Engineering / quality gaps

- **No tests at all.** The scoring engine is pure, deterministic, and side-effect free — it is *begging* for a pytest suite. Same for `_clean_reviews`, `_heuristic_checks`, `_merge_sentiment_batches`, and the JSON-repair logic in `call_groq`.
- **No README, no LICENSE, no CONTRIBUTING, no CI.** A newcomer can't run this project without reading 2,000 lines.
- **`location.py` is a 2,049-line god-module** mixing config, HTTP, scraping, prompts, merging, scoring, and Rich terminal rendering. Suggested split:
  ```
  locan/
    config.py      # dataclasses + env loading, no side effects
    geo.py         # Photon client + caching
    scraper.py     # Apify
    llm.py         # Groq client, retries, JSON repair
    analysis/      # sentiment.py, guardrail.py, verify.py, prompts/
    scoring.py     # pure functions, no I/O
    report.py      # Rich rendering
  app.py           # Streamlit only
  ```
- **Library code prints to a Rich console.** Use `logging`; let the CLI attach a `RichHandler`. Right now every Streamlit run spams stdout and the library can't be used as a library.
- **Unpinned deps, no lockfile, no `pyproject.toml`.** `streamlit-searchbox` is listed but never imported. `autocomplete_component/index.html` (317 lines) is dead code — nothing references it.
- **9 bare `except Exception` blocks that swallow and return `{}`.** An empty dict flows downstream and becomes a confident-looking verdict.
- **No rate-limit handling.** Groq 429s are caught by the generic handler and retried once after 2 s; there's no `Retry-After` respect, no exponential backoff, no token budgeting — despite the whole config file being organised around TPD/TPM quotas.
- **`call_verifier`'s docstring claims "Groq's native JSON mode"** but never passes `response_format={"type": "json_object"}`. Free reliability win.
- **Typos/stale docs:** `analyze()` docstring and the Stage-4 progress message still say "Model B (OpenRouter)".

---

## 5. Performance

| Hotspot | Current | Suggested |
|---|---|---|
| `_clean_reviews` | O(n²) Jaccard, re-splits strings each comparison | Pre-tokenise once; use MinHash/shingles or a `difflib` shortcut; skip pairs with large length deltas |
| `_heuristic_checks` duplicate scan | O(n²) with `set(text.split())` **inside** the inner loop (~n²/2 redundant splits) | Hoist the tokenisation — ~10× faster for free |
| Sentiment batches | Strictly serial + `sleep(1.2)` between each | `ThreadPoolExecutor(max_workers=3)` with a token-bucket limiter — 3–5× faster end-to-end |
| Photon autocomplete | Fires on **every** `on_change` keystroke, uncached, twice (city geocode + search) | `@st.cache_data(ttl=3600)` + 250 ms debounce + reuse the city geocode |
| Streamlit reruns | Whole script re-executes on each suggestion click | Fine for now, but move the results dashboard into `@st.fragment` |

---

## 6. UX / product observations

- The sidebar advertises "3-Model" and names each model — impressive to a reviewer, but the user mostly wants *"should I go?"*. Consider a compact hero verdict + progressive disclosure.
- **No comparison mode.** The single highest-value feature you could add: analyse 2–4 places and show a side-by-side aspect table. This is the thing a user actually wants when choosing a restaurant.
- **No history.** Every report is thrown away on refresh; a "recent analyses" list (you already write JSON to disk) is nearly free.
- **No map.** You already have lat/lon from Photon — `st.map` or a Plotly scattermapbox costs 5 lines.
- **Aspect vocabulary is restaurant-shaped** (`food_quality`) but the app accepts museums, parks, hospitals. Aspect sets should be chosen per `category`.
- No aspect can go above/below its LLM guess — an **extractive** pass (which reviews literally mention "parking"?) would ground the scores in counts rather than vibes.
- Cost/usage is invisible: show tokens used and Apify compute units per run.

---

## 7. Security & ops

- `.env.example` is good; add `st.secrets` support for Streamlit Cloud deployment.
- `expand_maps_url` follows arbitrary user-supplied redirects with `urllib` (GET, downloads the body). Use HEAD, cap redirects, and allowlist `google.com` / `goo.gl` hosts.
- No `Dockerfile`, no healthcheck, no deployment notes.
- Reviewer names (PII) are stored verbatim in the exported JSON and rendered in the dataframe. Consider hashing or an opt-out, and add a note about Google ToS / scraping legality — that's a real risk for anyone deploying this.

---

## 8. Prioritised roadmap

### P0 — Integrity (makes the product honest) — ✅ **DONE**
1. ✅ Remove all fabricated verification/guardrail content; make `UNAVAILABLE` a real, visible state. — `1b4a3ae`
2. ✅ Stable review IDs across all stages + evidence-ID validation. — `4fd338f`
3. ✅ Move config validation out of import time. — `af6f795`
4. ✅ Escape all user/LLM content rendered as HTML. — `db48336`
5. ✅ Fix cache keying (hash-based, in `cache/`, gitignored, with force-refresh). — `7f00254`

_26 tests now cover these fixes and run without API keys: `pytest tests/`._

### P1 — Confidence (makes it maintainable) — ✅ **DONE**
6. ✅ `pytest` suite for `scoring.py`, `_clean_reviews`, `_heuristic_checks`, `_merge_sentiment_batches`, JSON repair — no API keys needed. — `d1b84ca`, `d362a3e`
7. ✅ Extract `ScoringConfig` dataclass; document weights; de-duplicate the sentiment triple-count. — `d1b84ca`
8. ✅ `ruff` + GitHub Actions CI; dependency bounds in `pyproject.toml`. — `781a0ee`
9. ✅ Replace Rich prints in library code with `logging`. — `5f2bcd4`
10. ✅ README with architecture diagram, setup, configuration, and caveats.

_Two further bugs surfaced while writing the tests and were fixed: the consistency
component could never drop below 5.5/10 (wrong std-dev scale), and polarised review
batches were labelled "Neutral" instead of "Mixed"._

### P2 — Speed & polish — ✅ DONE
11. ✅ Parallel batch analysis + token-bucket rate limiter + `response_format=json_object`
    (`96baeb6`, json mode in the follow-up commit). Sentiment batches run on a
    `ThreadPoolExecutor` (`SENTIMENT_MAX_WORKERS`, default 3) and every Groq call
    acquires budget from a per-model token bucket sized from the documented TPM.
    429s now honour `Retry-After`. `RATE_LIMIT_DISABLED=1` bypasses it.
12. ✅ Hoist tokenisation out of the O(n²) loops; cache geocoding (`e0b269a`).
    400 reviews: `_clean_reviews` 256 ms → 65 ms (~4×), `_heuristic_checks`
    4.1 ms → 1.3 ms (~3×). Photon lookups are LRU-cached (256 entries).
    Bonus: `expand_maps_url` was a server-side SSRF — it now does a HEAD request
    against a Google-only host allowlist and re-checks the redirect target.
13. ✅ Split `location.py` into the `locan/` package (`3146e15`) — 17 modules,
    `location.py` kept as a compatibility shim. Also fixed the `location:main`
    console script, which pointed at a function that never existed.
14. ✅ Delete dead code (`autocomplete_component/`, `streamlit-searchbox`) (`781a0ee`).

### P3 — Product
15. **Compare mode** (2–4 places side by side).
16. Category-aware aspect sets.
17. Extractive keyword grounding (counts, not vibes) + per-aspect review drill-down.
18. Map view, run history, cost meter, PDF/Markdown export.

---

## 9. Honest overall take

This is a **well-above-average portfolio project with a genuinely interesting architecture** — the deterministic-scoring-with-LLM-prose split is a design decision most people three years into the job wouldn't make. The UI work is real, and the heuristic layer shows you understand that not everything should be an LLM call.

But there's a theme running through the code that's worth naming: **the codebase optimises for the appearance of rigour over rigour itself.** The verifier that PASSes when it didn't run, the observations written by string templates and labelled "extracted from reviews", the guardrail confidences computed as `0.92 - i*0.04`, the 92 %-accuracy metric with no ground truth behind it — these make demos look great and make the system's actual claims unfalsifiable. Ironically, it's a review-authenticity tool with an authenticity problem.

The fix is mostly *deletion*, not addition. Strip the fabrication, let empty be empty, let failure be visible, and then put a test suite around the deterministic core so the numbers you do show are defensible. A verifier that honestly reports "couldn't verify — 8B model returned malformed JSON, 2 of 5 fields unchecked" is far more impressive than one that always says PASS.

After that, the highest-leverage additions are **compare mode** and **extractive grounding** — the first is what users actually want, the second is what turns aspect scores from vibes into evidence.
