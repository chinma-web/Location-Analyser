# Streamlit → React feature parity

The overview is a summary, **not** a replacement for the full analysis. The six original report sections are available as report tabs and sidebar destinations. Changing tabs never scrapes again.

| Original Streamlit feature (`app.py`) | React equivalent |
| --- | --- |
| Name search, city selection, place suggestions | Live search: City / Area + Place / Business; shared Photon service |
| Google Maps URL mode | Live search: Paste Maps link |
| Maximum review slider, 10–100 in steps of five | Analysis settings → Max reviews to scrape; validated by FastAPI and passed to the engine |
| Model configuration/status | Settings model lineup, persistent per-report role strip, raw model metadata |
| Stage progress and provider errors | Background job progress and error alerts |
| Raw / usable / cleaned / analyzed counters | Persistent collection summary; repeated in authenticity and raw data |
| Verdict, confidence, reliability | Executive verdict and persistent report context |
| Verification banner, hallucination flag, correction count | Persistent audit strip plus complete audit page |
| Category icon, subtypes, description, price, phone, closure status | Category-aware overview icon; expandable metadata; closure warning visible outside the disclosure |
| Place name, address, Google rating and total Google reviews, website | Expandable Place metadata, safe external links |
| Opening hours (scraped metadata) | Expandable Place metadata → Opening hours |
| **Executive Verdict**: weighted strengths and drawbacks | Executive verdict → Genuine strengths / Concerns & drawbacks (complete lists) |
| Full assessment and analyst note | Executive verdict → Balanced assessment and Analyst note |
| Score breakdown and aspect chart | Executive verdict → interactive score bars, values disclosure, Python breakdown fields |
| Standout positive / negative quotes | Executive verdict → Standout reviewer quotes |
| All positive and negative points with review IDs | Executive verdict → All points, with evidence navigation and unresolved-citation warnings |
| **Deep Sentiment**: emotion donut and star histogram | Deep sentiment → Emotion distribution and Rating distribution |
| Aspect radar, detailed scores, mention counts, summaries, evidence | Deep sentiment → Aspect-based scores radar and full evidence table |
| Recent / older sentiment, scores, trend and explanation | Deep sentiment → Temporal sentiment trend (labeled model interpretation) |
| Crowd profile and accessibility | Deep sentiment → Crowd profile; Visitor guide → Visitor profile & accessibility |
| Themes, sentiment, frequency, evidence text, representative quotes, review IDs | Deep sentiment → Key themes |
| Positive / negative keywords | Deep sentiment → keyword chip panels |
| Per-review sentiment output | Deep sentiment → individual score, emotion, intensity, key phrase and source table |
| **Guardrail & Authenticity**: trust, risk, quality, bias, adjusted rating | Authenticity → complete guardrail metrics, clearly labeled estimates |
| Heuristic statistics, duplicates | Authenticity → Review statistics and heuristic fields |
| Linguistics, copy-paste evidence, vocabulary, writing style and notes | Authenticity → Linguistic analysis |
| Rating distribution assessment, inflation/suppression estimates, anomalies, notes | Authenticity → Rating integrity |
| Sock-puppet / coordination risks and evidence | Authenticity → Reviewer behaviour |
| Contradictory claims and model resolution | Authenticity → expandable Contradictions in reviews |
| Aspect credibility table | Authenticity → Per-aspect credibility |
| Suspicious patterns | Authenticity → Suspicious patterns |
| Genuine positives and concerns, confidence/severity, IDs | Authenticity → evidence-linked positive/concern lists |
| Verified facts field | Authenticity → Reported facts (not falsely described as independently verified) |
| Guardrail summary and analyst recommendation | Authenticity summary and Executive verdict analyst note |
| **Visitor Guide**: best for, avoid if, best time, tips | Complete Visitor guide tab (no summary truncation) |
| **Verification & Audit**: status, reported agreement, hallucination flag, applied count | Audit summary; counts distinguish recorded proposals from engine-reported applied corrections |
| Five field checks, observations, issues, unsupported claims | Audit → Field-by-field cross-verification |
| Before/after corrections, reasons, evidence IDs | Audit → Corrections detail; click valid IDs to inspect reviews |
| Missing positive/negative evidence, audit notes | Audit → Missed signals and summary notes |
| **Raw Data & Export**: full review table | Raw data → searchable, sortable, paginated table with full review text and all supplied columns |
| Verification JSON | Raw data → Verification JSON |
| Complete JSON export | Persistent Export report and Raw data → Download full report |
| Interactive chart inspection / export | Chart tooltips, legends, values, expansion and SVG export |

## Intentional accuracy safeguards

Feature parity does not mean restoring misleading defaults. Missing data is explicitly unavailable; an unavailable audit never becomes PASS or 94% accurate. Model-reported “accuracy” is labeled agreement, suspicious-review scores are estimates rather than fraud findings, and adjusted ratings are not called ground truth. Citation navigation checks that IDs exist. The raw JSON retains original fields unchanged.

Overview cards intentionally show short previews; complete strengths, concerns, points, tips, metadata, and model output are available in their detailed destinations. No extra scraping or inference is needed to open any report section. Chart code is loaded on demand.

## Regression checks

- Python tests validate the original review-count range, custom-count propagation, fully populated illustrative report fields, and citation resolution.
- `frontend/e2e/report-parity.spec.js` checks all six report sections, charts, metadata, evidence navigation, raw review search/sort/pagination, CSV and lossless JSON downloads, 100-review request propagation, mobile layouts, and incomplete/unavailable reports.
- Demo content remains explicitly fictional. Demo field-level audits are not executed checks.
