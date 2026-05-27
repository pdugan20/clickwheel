"""Tests for CLI helper functions."""

from __future__ import annotations

from io import StringIO

from rich.console import Console

from clickwheel import output
from clickwheel.actions import calc_size_of_paths
from clickwheel.cli import _fmt_size
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
    assert calc_size_of_paths(populated_db, paths) == 8_000_000


def test_calc_size_missing_path(populated_db: Database):
    paths = ["/music/nonexistent.mp3"]
    assert calc_size_of_paths(populated_db, paths) == 0


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


# ---------------------------------------------------------------------------
# _print_scan_delta — per-scan change summary
# ---------------------------------------------------------------------------


def _capture_scan_delta(result, full):
    """Run _print_scan_delta against a captured console and return the text."""
    from clickwheel.cli import _print_scan_delta

    buf = StringIO()
    original = output.console
    output.console = Console(file=buf, no_color=True)
    try:
        _print_scan_delta(result, full)
        return buf.getvalue()
    finally:
        output.console = original


def test_scan_delta_reports_added_updated_unchanged():
    from clickwheel.actions import ScanResult

    out = _capture_scan_delta(
        ScanResult(total=100, added=28, updated=3, unchanged=69), full=False
    )
    assert "28 added" in out
    assert "3 updated" in out
    assert "69 unchanged" in out
    assert "missing" not in out


def test_scan_delta_reports_missing_when_present():
    from clickwheel.actions import ScanResult

    out = _capture_scan_delta(
        ScanResult(total=98, added=0, updated=0, unchanged=96, missing=2),
        full=False,
    )
    assert "2 now missing" in out


def test_scan_delta_no_changes_is_called_out_explicitly():
    from clickwheel.actions import ScanResult

    out = _capture_scan_delta(
        ScanResult(total=100, added=0, updated=0, unchanged=100), full=False
    )
    assert "no changes" in out.lower()


def test_scan_delta_full_scan_reports_total_indexed():
    from clickwheel.actions import ScanResult

    out = _capture_scan_delta(ScanResult(total=12878, added=12878), full=True)
    assert "Full scan" in out
    assert "12,878" in out
