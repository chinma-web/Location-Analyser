"""
Library logging.

Engine code emits Rich-markup strings through log(); the level is inferred from
the leading tag so the 40+ existing call sites did not have to change. The
plain handler strips markup, the CLI opts into a Rich handler.
"""

import logging
import os
import re

from rich.console import Console

# ── Logging ───────────────────────────────────────────────────────────────────
# Library code must not own the terminal. Everything below goes through the
# standard logging module so the CLI can render it with Rich, Streamlit can send
# it to stderr, and tests can silence it — previously every run printed directly
# to stdout no matter who was calling.

logger = logging.getLogger("locan")
logger.addHandler(logging.NullHandler())

# Level is inferred from the leading Rich tag, so call sites stay readable.
_LEVEL_BY_TAG = {
    "red":     logging.ERROR,
    "yellow":  logging.WARNING,
    "dim":     logging.DEBUG,
    "cyan":    logging.INFO,
    "green":   logging.INFO,
    "magenta": logging.INFO,
    "blue":    logging.INFO,
}
_TAG_RE   = re.compile(r"\[/?([a-zA-Z0-9_#\s]+)\]")
_LEAD_TAG = re.compile(r"^\[(?:bold\s+|italic\s+)?([a-zA-Z]+)")


def strip_markup(message: str) -> str:
    """Remove Rich markup so plain handlers don't print literal [green] tags."""
    return _TAG_RE.sub("", message)


def log(message: str) -> None:
    """Log a Rich-markup message, inferring its level from the leading tag."""
    match = _LEAD_TAG.match(message.strip())
    level = _LEVEL_BY_TAG.get(match.group(1).lower(), logging.INFO) if match else logging.INFO
    logger.log(level, message)


class _StripMarkupFormatter(logging.Formatter):
    def format(self, record):
        record.msg = strip_markup(str(record.msg))
        return super().format(record)


def configure_logging(level: str = None, rich_output: bool = False) -> None:
    """
    Attach a handler to the `locan` logger. Safe to call more than once.

    rich_output=True is for the CLI (colour, markup); the default plain handler
    strips markup and is what the Streamlit app and scripts should use.
    """
    level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    for handler in list(logger.handlers):
        if not isinstance(handler, logging.NullHandler):
            logger.removeHandler(handler)

    if rich_output:
        try:
            from rich.logging import RichHandler
            handler = RichHandler(console=Console(stderr=True), markup=True, show_path=False,
                                  show_time=False, show_level=False)
            handler.setFormatter(logging.Formatter("%(message)s"))
        except ImportError:
            handler = logging.StreamHandler()
            handler.setFormatter(_StripMarkupFormatter("%(message)s"))
    else:
        handler = logging.StreamHandler()
        handler.setFormatter(_StripMarkupFormatter("%(levelname)s  %(message)s"))

    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False
