"""Small presentation helpers for the Streamlit UI (kept importable/testable)."""

from html import escape as _html_escape


def esc(value) -> str:
    """
    Escape anything before it is interpolated into an `unsafe_allow_html` block.

    Review text, place names, and LLM output are all untrusted: a review
    containing `<img src=x onerror=alert(1)>` would otherwise execute inside the
    user's Streamlit session.
    """
    if value is None:
        return ""
    return _html_escape(str(value), quote=True)
