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
# _run_beets_fix — scoping, timeouts, missing-beets handling
# ---------------------------------------------------------------------------


def _fix_cfg(tmp_path):
    from clickwheel.config import Config

    music = tmp_path / "music"
    music.mkdir()
    return Config(music_dir=music, project_dir=tmp_path, auto_scan=False)


def test_run_beets_fix_missing_beets_exits_cleanly(tmp_path, monkeypatch):
    """A missing `beet` binary raises FileNotFoundError from subprocess;
    the pipeline must catch it and exit 1, not surface a traceback."""
    import subprocess

    import pytest
    import typer

    from clickwheel.cli import _run_beets_fix

    cfg = _fix_cfg(tmp_path)

    def fake_run(*_a, **_kw):
        raise FileNotFoundError(2, "No such file or directory", "beet")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(typer.Exit) as exc:
        _run_beets_fix(cfg, str(cfg.music_dir / "SomeAlbum"))
    assert exc.value.exit_code == 1


def test_run_beets_fix_phase_timeout_is_reported_not_raised(tmp_path, monkeypatch):
    """A beets phase that exceeds the timeout must be reported as a failed
    step — never propagate as an unhandled exception or hang."""
    import subprocess
    import types

    from clickwheel.cli import _run_beets_fix

    cfg = _fix_cfg(tmp_path)

    def fake_run(cmd, **_kw):
        if "version" in cmd:
            return types.SimpleNamespace(returncode=0, stderr="")
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(subprocess, "run", fake_run)

    # Must return normally — the TimeoutExpired is caught per phase.
    _run_beets_fix(cfg, str(cfg.music_dir / "SomeAlbum"))


def test_run_beets_fix_scopes_every_call_to_a_temp_library(tmp_path, monkeypatch):
    """Every beets invocation must run against a fresh temp library, never
    the persistent one — that's what keeps fetchart/embedart/etc. scoped
    to the target instead of the whole accumulated collection."""
    import subprocess
    import types
    from pathlib import Path

    from clickwheel.cli import _run_beets_fix

    cfg = _fix_cfg(tmp_path)
    persistent_db = str(cfg.project_dir / "beets" / "library.db")
    calls: list[list[str]] = []

    def fake_run(cmd, **_kw):
        calls.append([str(x) for x in cmd])
        return types.SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    _run_beets_fix(cfg, str(cfg.music_dir / "SomeAlbum"))

    beet_calls = [c for c in calls if "version" not in c]
    assert beet_calls, "expected at least the import + four phase calls"
    for c in beet_calls:
        assert Path(c[0]).name == "beet", f"not a beet call: {c}"
        assert c[1] == "-l", f"call not scoped with -l: {c}"
        assert c[2] != persistent_db, "must not use the persistent library"
        assert "clickwheel-beets-" in c[2], f"not a temp library: {c[2]}"


def test_run_beets_fix_resolves_beet_next_to_interpreter(tmp_path, monkeypatch):
    """`beet` must be resolved alongside the running interpreter, not via a
    bare PATH lookup — a pipx-installed clickwheel does not put its venv bin
    on PATH, so a bare `beet` would not be found even with [fix] installed."""
    import subprocess
    import sys
    import types

    from clickwheel.cli import _run_beets_fix

    cfg = _fix_cfg(tmp_path)

    # Fake a venv bin dir holding the interpreter and its `beet` sibling.
    fake_bin = tmp_path / "venvbin"
    fake_bin.mkdir()
    (fake_bin / "python").write_text("")
    fake_beet = fake_bin / "beet"
    fake_beet.write_text("")
    monkeypatch.setattr(sys, "executable", str(fake_bin / "python"))

    calls: list[list[str]] = []

    def fake_run(cmd, **_kw):
        calls.append([str(x) for x in cmd])
        return types.SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    _run_beets_fix(cfg, str(cfg.music_dir / "SomeAlbum"))

    assert calls, "expected at least the version check"
    for c in calls:
        assert c[0] == str(fake_beet), f"beet not resolved next to interpreter: {c}"
