"""Untrusted text (reviews, place names, LLM output) must never reach the DOM raw."""
import re
from pathlib import Path

from locan.ui import esc

PAYLOAD = '<img src=x onerror="alert(1)">'


def test_esc_neutralises_html():
    out = esc(PAYLOAD)
    assert "<img" not in out
    assert "&lt;img" in out
    assert '"' not in out          # quotes escaped too, so attribute breakout fails


def test_esc_handles_none_and_non_strings():
    assert esc(None) == ""
    assert esc(3) == "3"
    assert esc(["a"]) == "[&#x27;a&#x27;]"


def test_no_raw_interpolation_of_data_into_html_blocks():
    """
    Guard against regressions: any f-string HTML fragment in app.py that
    interpolates a .get(...) call must route it through esc().
    """
    src = Path(__file__).resolve().parents[1].joinpath("app.py").read_text()
    offenders = []
    for line in src.splitlines():
        stripped = line.strip()
        if not re.search(r"""f['"]<""", stripped):
            continue
        for expr in re.findall(r"\{([^{}]+)\}", stripped):
            if ".get(" in expr and "esc(" not in expr:
                offenders.append(stripped)
    assert not offenders, "unescaped interpolation into HTML:\n" + "\n".join(offenders)
