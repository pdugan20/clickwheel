"""Smoke tests — verify CLI entry points work."""

from __future__ import annotations

from typer.testing import CliRunner

from clickwheel.cli import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Sync your music library" in result.output


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "clickwheel" in result.output


def test_scan_help():
    result = runner.invoke(app, ["scan", "--help"])
    assert result.exit_code == 0
    assert "Scan your music library" in result.output


def test_fix_help():
    result = runner.invoke(app, ["fix", "--help"])
    assert result.exit_code == 0


def test_select_help():
    result = runner.invoke(app, ["select", "--help"])
    assert result.exit_code == 0


def test_playlist_help():
    result = runner.invoke(app, ["playlist", "--help"])
    assert result.exit_code == 0


def test_delete_help():
    result = runner.invoke(app, ["delete", "--help"])
    assert result.exit_code == 0


def test_edit_help():
    result = runner.invoke(app, ["edit", "--help"])
    assert result.exit_code == 0


def test_diff_help():
    result = runner.invoke(app, ["diff", "--help"])
    assert result.exit_code == 0


def test_sync_help():
    result = runner.invoke(app, ["sync", "--help"])
    assert result.exit_code == 0


def test_ls_help():
    result = runner.invoke(app, ["ls", "--help"])
    assert result.exit_code == 0


def test_eject_help():
    result = runner.invoke(app, ["eject", "--help"])
    assert result.exit_code == 0


def test_scrobble_help():
    result = runner.invoke(app, ["scrobble", "--help"])
    assert result.exit_code == 0
