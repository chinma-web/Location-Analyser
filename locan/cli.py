"""Command-line entry point: `location-analyser "Cafe Goodluck Pune" 40`."""

import sys

from locan.config import validate_config
from locan.logging_utils import configure_logging, log
from locan.pipeline import analyze
from locan.report import console


def parse_args(argv: list) -> tuple:
    """
    Returns (location, max_reviews, force_refresh).

    `--no-cache` / `--force` bypass the report cache; a trailing integer is the
    review count. Everything else is joined into the location query.
    """
    force = any(flag in argv for flag in ("--no-cache", "--force"))
    args = [a for a in argv[1:] if a not in ("--no-cache", "--force")]

    location, max_reviews = "", 30
    if args:
        if len(args) > 1 and args[-1].isdigit():
            location, max_reviews = " ".join(args[:-1]), int(args[-1])
        else:
            location = " ".join(args)
    return location, max_reviews, force


def prompt_for_missing(location: str, max_reviews: int) -> tuple:
    """Interactively ask for anything not supplied on the command line."""
    if location:
        return location, max_reviews
    try:
        location = console.input("\n[bold]Enter location to analyze:[/bold] ").strip()
    except (EOFError, KeyboardInterrupt):
        location = ""
    if not location:
        log("[red]No location entered.[/red]")
        raise SystemExit(1)
    try:
        entered = console.input("[bold]Max reviews (default 30):[/bold] ").strip()
        max_reviews = int(entered) if entered.isdigit() else 30
    except (EOFError, KeyboardInterrupt):
        max_reviews = 30
    return location, max_reviews


def main(argv: list = None) -> int:
    argv = sys.argv if argv is None else argv
    configure_logging(rich_output=True)

    missing = validate_config(raise_on_error=False)
    if missing:
        log("[red bold]ERROR:[/red bold] Missing API keys: " + ", ".join(missing))
        log("Create a .env file (see .env.example) with APIFY_API_TOKEN and GROQ_API_KEY")
        return 1

    location, max_reviews, force = parse_args(argv)
    location, max_reviews = prompt_for_missing(location, max_reviews)
    analyze(location, max_reviews, force_refresh=force, render_report=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
