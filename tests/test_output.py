"""Tests for output helpers."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from clickwheel import output


def _capture(fn, msg: str) -> str:
    """Capture output from an output helper by temporarily swapping the console."""
    buf = StringIO()
    original = output.console
    output.console = Console(file=buf, no_color=True)
    try:
        fn(msg)
        return buf.getvalue()
    finally:
        output.console = original


def test_error():
    result = _capture(output.error, "something broke")
    assert "[ERROR]" in result
    assert "something broke" in result


def test_warn():
    result = _capture(output.warn, "heads up")
    assert "[WARNING]" in result
    assert "heads up" in result


def test_success():
    result = _capture(output.success, "it worked")
    assert "it worked" in result


def test_info():
    result = _capture(output.info, "just info")
    assert "just info" in result


def test_status():
    result = _capture(output.status, "doing things")
    assert "doing things" in result


def test_dim():
    result = _capture(output.dim, "hint text")
    assert "hint text" in result


def test_confirm():
    result = _capture(output.confirm, "done")
    assert "done" in result


def test_table_and_print():
    buf = StringIO()
    original = output.console
    output.console = Console(file=buf, no_color=True)
    try:
        t = output.table(title="Test")
        t.add_column("Col")
        t.add_row("val")
        output.print_table(t)
        result = buf.getvalue()
        assert "Test" in result
        assert "val" in result
    finally:
        output.console = original
