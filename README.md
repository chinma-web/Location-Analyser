# Placewise · Location Review Analyser

An academic project that makes place reviews easier to interpret. The new React dashboard presents a summary verdict, visitor sentiment, evidence-linked highlights, experience-factor scores, and an explainable methodology. The original Streamlit interface remains available in `app.py`.

## Start the new interface

Requirements: Python 3.11+, Node.js 20.19+ (22 recommended).

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cd frontend
npm ci
cd ..
```

Start the API from the repository root:

```bash
.venv/bin/uvicorn api.server:app --host 0.0.0.0 --port 8000
```

In a second terminal:

```bash
cd frontend
npm run dev -- --port 5173
```

Open **http://localhost:5173**. The frontend sends requests to relative `/api` paths; Vite proxies them to the Python API. The UI can therefore also be used through a remote development preview without browser-facing localhost API calls.

### No keys? Use instant demo

The dashboard starts with **The Courtyard Café**, an explicitly fictional place with 12 illustrative reviews and prewritten analysis. No external services, credentials, or scraping are needed. This is appropriate for explaining the interface and project methodology, **not** for claiming real-world model accuracy. The sample is labeled throughout the UI and exported JSON.

### Live analysis

Copy `.env.example` to `.env` and configure `APIFY_API_TOKEN` and `GROQ_API_KEY`, then restart the API. Never put keys in frontend environment variables. Choose **Live analysis** and enter a precise place name with city, or preferably an HTTPS Google Maps place URL.

- **Quick scan (default):** requests up to 15 newest reviews and one place, bypassing the extra Photon geocoding request for text queries. Less collection work and one sentiment batch rather than several.
- **Deep scan:** requests up to 40 reviews and uses the original geocoding/search flow, which can collect multiple candidates. Name similarity selects the best result rather than review count. Always check the displayed name/address; ambiguous queries can still resolve incorrectly.
- **Report reuse:** exact matching requests use a seven-day local cache keyed by location, review count, scan mode, configured models, pipeline version, and verification policy.
- **Fetch fresh data:** use analysis settings to bypass that cache.
- Provider latency still varies. There is **no measured speedup guarantee**; cached/demo reports avoid scraping, while quick scan reduces its workload. Stage-based progress is not an ETA.

Cache data is stored in ignored `.cache/reports/`, not in tracked report files. Delete that directory to clear the cache. New reports include total and scraping-stage durations in exported metadata (scraping-stage duration includes collection setup).

## Presentation flow

1. Open **Instant demo**: explain the verdict and the difference between the place rating and the calculated visit score.
2. Show sentiment and the two highlight columns: positives versus trade-offs.
3. Select a highlight or experience factor to open its linked reviews.
4. Open **How it works** to explain the collection → analysis → audit → deterministic scoring → explanation pipeline.
5. Optionally run a live quick scan, then repeat it to demonstrate the matching-report cache. Have the fictional demo ready in case an external provider is unavailable.
6. Export JSON to show the underlying data and clearly distinguish sample versus live results.

## Architecture

```text
React + Vite (frontend/)
        │ same-origin /api requests
        ▼
FastAPI (api/server.py)
        ├── GET /api/demo       → fictional, offline fixture
        ├── GET /api/health     → live credential availability (no secret values)
        ├── POST /api/analyze   → background job
        └── GET /api/jobs/{id}  → stage progress / result
                                  │
                                  ▼
                         Python engine (location.py)
                         Apify → Groq → scoring → explanation
```

The API runs one live analysis at a time, keeps job state in memory for up to an hour, and uses local disk for report caching. Run one API worker. This is deliberately a local academic-demo architecture, not a multi-user production deployment. Restarting the API loses in-progress job tracking; cached reports remain on disk.

## Trust and limitations

- Missing/failed audits remain `UNKNOWN` or `UNAVAILABLE`; they must not turn into a fabricated PASS or accuracy percentage.
- Live audits process full-review batches and use a model from the same provider. Failed or incomplete batches remain explicitly unavailable. They are limited cross-checks, not independent factual validation.
- Sentiment and factor scores are model judgments. A deterministic formula is reproducible but not scientifically calibrated.
- Newest-first reviews are not representative of all visitors. Review count is limited by text availability and deduplication.
- Quick scan favors speed over breadth; specific input is important.
- Fraud/anomaly heuristics are not proof of fake reviews.
- The legacy engine still has opportunities for stricter schema validation, claim-grounding checks, and statistically validated scoring. This redesign does not claim to solve those research problems.

## Checks

```bash
pip install -r requirements-dev.txt
python -m pytest -q
cd frontend && npm run build
```

Tests cover honest demo labeling, citation resolution, API input/error behavior, unavailable-verifier handling, Google Maps URL validation, single-place quick-scan requests, cache parameters, and forced refresh. No tests spend provider credits.

To launch the original UI: `streamlit run app.py` (requires live credentials).

## City/place autocomplete and Groq model selection

Live search now offers separate **City / Area** and **Place / Business** comboboxes, plus a Maps-link mode. Suggestions use the existing Photon logic extracted into the shared, key-free `geocoding.py` module. The engine retains compatibility wrappers for the legacy Streamlit UI. FastAPI endpoints:

- `GET /api/suggestions/cities?q=Pu`
- `GET /api/suggestions/places?q=Cafe&city=Pune`
- `GET /api/models` — effective role preferences and catalog verification status

Suggestions are debounced, cancel stale browser requests, support keyboard navigation, and report provider failure separately from zero matches. Changing the city clears the old place. Photon responses are cached for five-minute buckets with a bounded in-memory cache. Manual entry works when the provider is unavailable. No paid-provider keys are needed for geocoding, but the backend needs outbound access to `photon.komoot.io`. Photon uses OpenStreetMap data and is not an authoritative Google Place ID resolver; always confirm the resulting business name/address.

Defaults now prefer **`openai/gpt-oss-120b`** for analysis/explanation and **`openai/gpt-oss-20b`** for guardrail work. The verifier first checks for the exact requested **`qwen/qwen3.8-27b`**, then `qwen/qwen3-32b`, then supported GPT-OSS/Llama fallbacks. **The requested Qwen ID is not assumed to exist.** Explicit `.env` role overrides take precedence when present in Groq's active model catalog. An unavailable override falls back to a supported catalog entry with a diagnostic note. If the catalog cannot be checked, configured/default IDs remain explicitly unverified; if it contains no supported model, the selection fails with a configuration message. The catalog result is cached in memory for five minutes.

Groq calls use JSON-object output and completion-token limits, with low reasoning effort and additional output headroom for GPT-OSS. Existing `.env` files are not overwritten: remove old Llama overrides or replace them to use the new defaults. **Model listing cannot establish free-tier billing eligibility or remaining quota.** This app does not claim that any listed model is free for a particular account. Analysis settings show the selected role lineup and verification status; live reports record the selection metadata.

## Complete analysis views (Streamlit parity)

The React interface now includes all six original Streamlit report areas: **Executive verdict, Deep sentiment, Authenticity, Visitor guide, Verification & audit, and Raw data & export**. The colorful overview remains a summary; it no longer substitutes for the detailed report. Use the report tabs or sidebar to open the complete lists, charts, model diagnostics, evidence, and raw data. Collection counts, audit status, model roles, confidence, reliability, and expandable place metadata are visible across sections. See [`docs/frontend-parity.md`](docs/frontend-parity.md) for the feature-by-feature mapping and intentional accuracy safeguards.

The original **10–100 review limit (step 5)** is restored in Analysis settings and passed through FastAPI. Quick scan still presets 15 and deep search 40; either can use a custom review limit. Selecting a tab does not perform another scrape. Charts support hover details, expansion, SVG downloads, and readable values. Raw reviews support search, sorting, pagination, and filtered CSV download in addition to lossless full-report JSON export.

### Browser regression tests

With the Python API running on port 8000:

```bash
cd frontend
npm ci
npx playwright install chromium
npm run test:e2e
```

Playwright starts or reuses the Vite server on port 5173. Tests use the fictional demo and mocked live submissions, not paid provider calls. The optional `CHROMIUM_EXECUTABLE_PATH` environment variable selects an existing Chromium executable. Test artifacts are ignored by Git.

## Elaborate, coverage-first analysis

Review text is no longer clipped to 800 characters at collection or 350/120/150 characters at later stages. Sentiment and guardrail passes read every cleaned text review in count/character-budgeted batches; oversized individual reviews are kept intact rather than silently clipped. Per-review sentiment must include grounded topic observations and quotes found in that review. Missing/duplicate IDs, invalid scores, or ungrounded quotes trigger one corrective retry and then an explicit error, not a partial result presented as complete.

A topic inventory preserves positive, negative, neutral, and mixed observations, including a complaint inside a positive review and topics appearing after review 20. All batch aspect summaries, crowd/accessibility notes and evidence IDs survive aggregation. Sentiment averages use per-review scores; aspect aggregation is mention-weighted. Date-based trends use all available scored, dated reviews and require at least six reviews spanning seven days.

Guardrail and verification also process all review batches. Audit coverage is acknowledged per batch; a failed batch prevents a global PASS. Global heuristic checks include the entire cleaned sample. Automated checks cannot establish factual authenticity or independently validate semantic correctness.

The explanation model receives the complete topic inventory and points, rather than a top-three/top-five excerpt. It is asked for a substantive balanced verdict and a detailed assessment and visitor-guide entry for every extracted topic, with review IDs, frequency, trade-offs, visitor fit and unknowns. If a topic is omitted, synthesis is retried once. Remaining omissions are marked as such: source-derived evidence stays visible, but missing advice is not invented. Python still owns the numerical verdict/score.

Use **Review & topic coverage** to inspect processing counts and missing narrative topics, **Executive verdict** for the topic-by-topic assessment, **Deep sentiment** for all original topic observations, and **Visitor guide** for topic-specific guidance. These checks establish processing coverage, not a guarantee that a model found every possible interpretation of every review.

This deliberately increases model calls/output compared with the old sampled pipeline, particularly for 40–100 reviews. The quick scan still limits collection by default, and the versioned cache avoids repeat work. Live generation quality and account rate limits must be evaluated with configured provider keys; offline tests use mocks and the explicitly fictional demo.
