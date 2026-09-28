"""Rich terminal report rendering (CLI only)."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# ── Report Display ─────────────────────────────────────────────────────────────

VERDICT_COLOR = {
    "HIGHLY RECOMMENDED": "bold green",
    "RECOMMENDED":        "green",
    "VISIT WITH CAUTION": "yellow",
    "NOT RECOMMENDED":    "red",
}

def display_report(location, place_info, reviews, sentiment, guardrail, rec, verification, review_stats):
    console.print()
    console.rule("[bold yellow]📊  LOCATION REVIEW ANALYSIS REPORT[/bold yellow]")

    # Place info
    console.print(Panel(
        f"[bold]{place_info.get('name', location)}[/bold]\n"
        f"📍 {place_info.get('address') or 'Address unavailable'}\n"
        f"⭐ Google score: {place_info.get('google_score', 'N/A')}/5  "
        f"({place_info.get('review_count', len(reviews))} total reviews on Google)\n"
        f"🏷  Category: {place_info.get('category') or 'N/A'}",
        title="[cyan]Place info[/cyan]", expand=False,
    ))

    # Review stats
    rs = review_stats
    console.print(Panel(
        f"Raw scraped: {rs.get('raw_scraped_count', 0)}  |  "
        f"Usable text: {rs.get('usable_text_review_count', 0)}  |  "
        f"Cleaned: {rs.get('cleaned_review_count', 0)}  |  "
        f"Analyzed: {rs.get('analyzed_review_count', 0)}",
        title="[cyan]Review counts[/cyan]", expand=False,
    ))

    # Verification summary
    v_status  = verification.get("verification_status", "UNAVAILABLE")
    v_acc     = verification.get("accuracy")
    v_acc_str = f"{v_acc:.0%}" if v_acc is not None else "N/A"
    v_hall    = verification.get("hallucination_detected")
    v_corr    = len(verification.get("corrections", []))
    console.print(Panel(
        f"Model B status: {v_status}  |  Accuracy: {v_acc_str}  |  "
        f"Hallucination: {v_hall}  |  Corrections applied: {v_corr}",
        title="[magenta]Model B — Verification[/magenta]", expand=False,
    ))

    # Recommendation banner
    label = rec.get("recommendation", "UNKNOWN")
    color = VERDICT_COLOR.get(label, "white")
    bd    = rec.get("score_breakdown", {})
    console.print(Panel(
        f"[{color}]{label}[/{color}]\n\n"
        f"Visit score  [bold]{rec.get('visit_score', '?')}/10[/bold]   ·   "
        f"Confidence  [bold]{rec.get('confidence', 0):.0%}[/bold]   ·   "
        f"Data reliability  [bold]{rec.get('data_reliability', '?')}[/bold]\n\n"
        f"[italic]{rec.get('one_line_verdict', '')}[/italic]\n\n"
        f"Sentiment {bd.get('sentiment_score','?')}/10  ·  "
        f"Rating {bd.get('rating_score','?')}/10  ·  "
        f"Trust {bd.get('trust_score','?')}/10",
        title="[yellow]⚡ Recommendation (Python scoring)[/yellow]", expand=False,
    ))

    # Pros / Cons
    pros = rec.get("pros", [])
    cons = rec.get("cons", [])
    tbl  = Table(title="Pros vs cons", show_header=True, expand=False)
    tbl.add_column("✅ Pros", style="green", width=42)
    tbl.add_column("❌ Cons", style="red",   width=42)
    for i in range(min(max(len(pros), len(cons)), 5)):
        p_item = pros[i] if i < len(pros) else ""
        c_item = cons[i] if i < len(cons) else ""
        p = p_item.get("point", str(p_item)) if isinstance(p_item, dict) else str(p_item)
        c = c_item.get("point", str(c_item)) if isinstance(c_item, dict) else str(c_item)
        tbl.add_row(p, c)
    console.print(tbl)

    console.print(Panel(
        rec.get("full_verdict", "No verdict generated."),
        title="[yellow]📝 Full verdict[/yellow]", expand=False,
    ))
    console.rule("[bold yellow]End of report[/bold yellow]")
