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
- Live audits cover at most 20 shortened reviews and use a model from the same provider. They are limited cross-checks, not independent factual validation.
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
