"""Tests for CLI helper functions."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from clickwheel import output
from clickwheel.cli import _calc_size, _fmt_size
from clickwheel.db import Database


def test_fmt_size_gb():
    assert _fmt_size(2 * 1024 * 1024 * 1024) == "2.0 GB"


def test_fmt_size_mb():
    assert _fmt_size(150 * 1024 * 1024) == "150.0 MB"


def test_fmt_size_kb():
    assert _fmt_size(512 * 1024) == "512.0 KB"


def test_fmt_size_zero():
    assert _fmt_size(0) == "0.0 KB"


def test_calc_size(populated_db: Database):
    paths = [
        "/music/A/Album1/01 T1.mp3",  # 5M
        "/music/B/Album2/01 S1.mp3",  # 3M
    ]
    assert _calc_size(populated_db, paths) == 8_000_000


def test_calc_size_missing_path(populated_db: Database):
    paths = ["/music/nonexistent.mp3"]
    assert _calc_size(populated_db, paths) == 0


def test_capacity_bar_green():
    """Under 80% should use confirm (green)."""
    buf = StringIO()
    original = output.console
    output.console = Console(file=buf, no_color=True)
    try:
        from clickwheel.cli import _print_capacity_bar

        _print_capacity_bar(30 * 1024**3, 64 * 1024**3)
        result = buf.getvalue()
        # Should not contain ERROR or WARNING
        assert "[ERROR]" not in result
        assert "[WARNING]" not in result
    finally:
        output.console = original


def test_capacity_bar_yellow():
    """80-99% should use warn."""
    buf = StringIO()
    original = output.console
    output.console = Console(file=buf, no_color=True)
    try:
        from clickwheel.cli import _print_capacity_bar

        _print_capacity_bar(56 * 1024**3, 64 * 1024**3)
        result = buf.getvalue()
        assert "[WARNING]" in result
    finally:
        output.console = original


def test_capacity_bar_over():
    """100%+ should use warn (not error)."""
    buf = StringIO()
    original = output.console
    output.console = Console(file=buf, no_color=True)
    try:
        from clickwheel.cli import _print_capacity_bar

        _print_capacity_bar(70 * 1024**3, 64 * 1024**3)
        result = buf.getvalue()
        assert "[WARNING]" in result
        assert "[ERROR]" not in result
    finally:
        output.console = original
