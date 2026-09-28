"""Library code must log, not print, and must not own the terminal."""
import logging

import pytest

import location as L


def test_markup_is_stripped_for_plain_handlers():
    assert L.strip_markup("[green]✓ done[/green]") == "✓ done"
    assert L.strip_markup("[bold red]bad[/bold red] thing") == "bad thing"


@pytest.mark.parametrize("message,level", [
    ("[red]Groq error[/red]", logging.ERROR),
    ("[yellow]⚠ retrying[/yellow]", logging.WARNING),
    ("[dim]cache hit[/dim]", logging.DEBUG),
    ("[green]✓ scraped[/green]", logging.INFO),
    ("no tags at all", logging.INFO),
])
def test_level_is_inferred_from_the_leading_tag(message, level, caplog):
    with caplog.at_level(logging.DEBUG, logger="locan"):
        L.log(message)
    assert caplog.records[-1].levelno == level


def test_library_does_not_print_to_stdout(capsys, caplog):
    with caplog.at_level(logging.DEBUG, logger="locan"):
        L.log("[green]✓ quiet please[/green]")
    assert capsys.readouterr().out == ""


def test_configure_logging_is_idempotent():
    L.configure_logging()
    first = len(L.logger.handlers)
    L.configure_logging()
    assert len(L.logger.handlers) == first


def test_analyze_does_not_render_the_cli_report_by_default():
    import inspect
    sig = inspect.signature(L.analyze)
    assert sig.parameters["render_report"].default is False
