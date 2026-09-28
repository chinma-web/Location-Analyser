"""
Report export.

JSON was the only way to get a report out, which is fine for a machine and
useless for sending to someone. Markdown covers sharing and version control;
the HTML wrapper exists so the browser's own "Print → Save as PDF" produces a
decent document without dragging a PDF engine into the dependency list.

Pure string building: give it a report payload, get text back.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone

from locan.aspects import aspect_set_for_place
from locan.usage import format_cost


def _fmt(value, suffix: str = "", dash: str = "—") -> str:
    if value is None or value == "":
        return dash
    if isinstance(value, float):
        return f"{value:g}{suffix}"
    return f"{value}{suffix}"


def _pct(value) -> str:
    return f"{value:.0%}" if isinstance(value, (int, float)) else "—"


def to_markdown(report: dict, include_reviews: bool = False) -> str:
    """Render a full analysis payload as a self-contained Markdown document."""
    report = report or {}
    place = report.get("place_info") or {}
    scoring = report.get("scoring") or {}
    sentiment = report.get("sentiment") or {}
    guardrail = report.get("guardrail") or {}
    verification = report.get("verification") or {}
    rec = report.get("recommendation") or {}
    usage = report.get("usage") or {}
    aspect_set = aspect_set_for_place(place)

    name = place.get("name") or report.get("location") or "Unknown place"
    lines = [f"# {name}", ""]

    if report.get("error"):
        lines += [f"> **Analysis failed:** {report['error']}", ""]
        return "\n".join(lines)

    subtitle = " · ".join(filter(None, [place.get("category"), place.get("address")]))
    if subtitle:
        lines += [f"*{subtitle}*", ""]

    # ── Verdict ──
    lines += [
        "## Verdict",
        "",
        f"**{scoring.get('verdict', 'UNKNOWN')}** — **{_fmt(scoring.get('score'))}/10**  ",
        f"Data sufficiency: {_pct(scoring.get('confidence'))} · "
        f"Reviews analysed: {len(report.get('reviews') or [])} · "
        f"Google rating: {_fmt(place.get('google_score'))}",
        "",
        "> The score and verdict are computed by a deterministic Python function, "
        "not by a language model. The prose below is model-written.",
        "",
    ]

    if rec.get("full_verdict"):
        lines += [rec["full_verdict"], ""]

    pros, cons = rec.get("pros") or [], rec.get("cons") or []
    if pros or cons:
        lines += ["### Pros and cons", ""]
        for item in pros:
            lines.append(f"- 👍 {item}")
        for item in cons:
            lines.append(f"- 👎 {item}")
        lines.append("")

    # ── Score breakdown ──
    breakdown = scoring.get("score_breakdown") or {}
    if breakdown:
        lines += ["## How the score was built", "", "| Component | Value |", "|---|---|"]
        for key, label in [("sentiment_comp", "Sentiment"), ("aspect_comp", "Aspects"),
                           ("rating_comp", "Google rating"), ("trust_comp", "Trust"),
                           ("consistency_comp", "Consistency"), ("recency_comp", "Recency")]:
            value = breakdown.get(key)
            if isinstance(value, (int, float)):
                lines.append(f"| {label} | {value}/10 |")
        if breakdown.get("risk_penalty"):
            lines.append(f"| Risk penalty | −{breakdown['risk_penalty']} |")
        lines.append(f"| **Final** | **{_fmt(scoring.get('score'))}/10** |")
        missing = breakdown.get("components_missing") or []
        lines.append("")
        if missing:
            lines += [f"*No data for: {', '.join(missing)} — these were dropped and the "
                      "remaining weights renormalised.*", ""]

    # ── Aspects ──
    aspects = sentiment.get("aspect_scores") or {}
    scored = {k: v for k, v in aspects.items()
              if isinstance((v or {}).get("score"), (int, float))}
    if scored:
        lines += [f"## Aspects ({aspect_set.name.replace('_', ' ')})", "",
                  "| Aspect | Score | Reviews mentioning | Note |", "|---|---|---|---|"]
        for key, entry in scored.items():
            lines.append(f"| {aspect_set.label_for(key)} | {entry['score']}/10 "
                         f"| {entry.get('reviews_mentioning', 0)} "
                         f"| {entry.get('summary') or '—'} |")
        lines.append("")

    # ── Evidence ──
    grounding = sentiment.get("grounding") or {}
    if grounding:
        lines += ["## Evidence (counted from the review text, no model involved)", ""]
        for label, block in [("Positive", grounding.get("positive_keywords") or {}),
                             ("Negative", grounding.get("negative_keywords") or {})]:
            found = block.get("grounded") or []
            if found:
                terms = ", ".join(f"{g['term']} ({g['review_count']})" for g in found[:10])
                lines.append(f"- **{label} keywords found in text:** {terms}")
            if block.get("ungrounded"):
                lines.append(f"- **{label} keywords *not* found in any review:** "
                             + ", ".join(block["ungrounded"]))
        unsupported = grounding.get("aspects_without_lexical_support") or []
        if unsupported:
            lines.append("- **Aspects scored with no matching words in the reviews:** "
                         + ", ".join(aspect_set.label_for(a) for a in unsupported))
        top = grounding.get("top_terms") or []
        if top:
            lines.append("- **Most discussed terms:** "
                         + ", ".join(f"{t['term']} ({t['review_count']})" for t in top[:10]))
        lines.append("")

    # ── Trust ──
    lines += [
        "## Trust and authenticity",
        "",
        f"- Trust score: {_pct(guardrail.get('trust_score'))}",
        f"- Fake-review risk: {_pct(guardrail.get('fake_review_probability'))}",
        f"- Review quality: {_fmt(guardrail.get('review_quality'))}",
        f"- Bias level: {_fmt(guardrail.get('bias_level'))}",
        "",
    ]
    red_flags = guardrail.get("red_flags") or []
    if red_flags:
        lines.append("**Red flags**")
        lines.append("")
        for flag in red_flags:
            if isinstance(flag, dict):
                lines.append(f"- {flag.get('flag') or flag.get('type', 'Flag')}: "
                             f"{flag.get('detail') or flag.get('evidence', '')}")
            else:
                lines.append(f"- {flag}")
        lines.append("")

    # ── Verification ──
    status = verification.get("verification_status", "UNKNOWN")
    lines += ["## Independent verification (Model B)", "",
              f"- Status: **{status}**",
              f"- Corrections applied: {verification.get('corrections_count', 0)}"]
    if verification.get("verification_notes") or verification.get("reason"):
        lines.append(f"- Notes: {verification.get('verification_notes') or verification['reason']}")
    lines.append("")

    # ── Cost ──
    if usage:
        lines += ["## Run cost", "",
                  f"- Tokens: {usage.get('total_tokens', 0):,} over "
                  f"{usage.get('calls', 0)} model calls",
                  f"- Estimated cost: {format_cost(usage.get('total_cost_usd', 0))}",
                  f"- Wall clock: {_fmt(usage.get('elapsed_seconds'), 's')}", ""]
        if usage.get("any_estimated"):
            lines.append("*Some token counts were estimated because the provider did not "
                         "report usage.*")
            lines.append("")

    if include_reviews:
        lines += ["## Reviews analysed", ""]
        for review in report.get("reviews") or []:
            stars = "★" * int(review.get("rating") or 0)
            lines.append(f"- **{review.get('id', '?')}** {stars} — {review.get('text', '')}")
        lines.append("")

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines += ["---", "", f"*Generated by Location Analyser on {generated}.*"]
    return "\n".join(lines)


_HTML_STYLE = """
body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; line-height: 1.55;
       max-width: 820px; margin: 40px auto; padding: 0 20px; color: #111; }
h1 { border-bottom: 2px solid #38bdf8; padding-bottom: 6px; }
h2 { margin-top: 32px; color: #0f172a; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; }
th, td { border: 1px solid #cbd5e1; padding: 6px 10px; text-align: left; font-size: 0.92rem; }
th { background: #f1f5f9; }
blockquote { border-left: 4px solid #38bdf8; margin: 12px 0; padding: 4px 14px;
             background: #f8fafc; color: #334155; }
code { background: #f1f5f9; padding: 1px 4px; border-radius: 3px; }
@media print { body { margin: 0; max-width: none; } }
"""


def _markdown_to_html(markdown: str) -> str:
    """
    Minimal Markdown → HTML for the subset to_markdown emits.

    A full Markdown library would be a dependency for one feature; this handles
    headings, tables, lists, blockquotes, bold/italic and rules, which is all
    the generated document uses.
    """
    out, in_list, in_table = [], False, False

    def close_blocks():
        nonlocal in_list, in_table
        if in_list:
            out.append("</ul>")
            in_list = False
        if in_table:
            out.append("</table>")
            in_table = False

    def inline(text: str) -> str:
        text = html.escape(text)
        for pattern, tag in (("**", "strong"), ("*", "em")):
            parts = text.split(pattern)
            if len(parts) >= 3:
                rebuilt = parts[0]
                for index, part in enumerate(parts[1:], start=1):
                    rebuilt += f"<{tag}>{part}</{tag}>" if index % 2 else part
                text = rebuilt
        return text

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            close_blocks()
            continue
        if line.startswith("#"):
            close_blocks()
            level = len(line) - len(line.lstrip("#"))
            out.append(f"<h{level}>{inline(line[level:].strip())}</h{level}>")
        elif line.startswith("---"):
            close_blocks()
            out.append("<hr>")
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue                       # separator row
            if not in_table:
                out.append("<table>")
                in_table = True
                out.append("<tr>" + "".join(f"<th>{inline(c)}</th>" for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
        elif line.startswith("> "):
            close_blocks()
            out.append(f"<blockquote>{inline(line[2:])}</blockquote>")
        elif line.startswith("- "):
            if in_table:
                close_blocks()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{inline(line[2:])}</li>")
        else:
            close_blocks()
            out.append(f"<p>{inline(line)}</p>")
    close_blocks()
    return "\n".join(out)


def to_html(report: dict, include_reviews: bool = False) -> str:
    """
    Standalone HTML document — print it from the browser to get a PDF.

    Deliberately not a real PDF: weasyprint/reportlab would add a heavy
    dependency (and system libraries) to produce something the browser already
    renders correctly from this file.
    """
    place = (report or {}).get("place_info") or {}
    title = place.get("name") or (report or {}).get("location") or "Location report"
    body = _markdown_to_html(to_markdown(report, include_reviews=include_reviews))
    return (
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{html.escape(str(title))} — Location Analyser</title>\n"
        f"<style>{_HTML_STYLE}</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def to_json(report: dict) -> str:
    """The full payload, pretty-printed."""
    return json.dumps(report or {}, indent=2, default=str)


def suggested_filename(report: dict, extension: str) -> str:
    """A filesystem-safe name like `cafe-goodluck-2026-09-28.md`."""
    place = (report or {}).get("place_info") or {}
    name = (place.get("name") or (report or {}).get("location") or "report").lower()
    slug = "".join(char if char.isalnum() else "-" for char in name).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{slug or 'report'}-{stamp}.{extension.lstrip('.')}"
