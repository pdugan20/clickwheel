"""Tests for the AppleScript-driven delete path. We mock
`subprocess.run` so the suite stays cross-platform (the production
code gates on darwin, but mock tests should run on Linux CI too).
"""

from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from clickwheel import applemusic as _am
from clickwheel.actions import AppleMusicAppleScriptError, delete_apple_music_playlist


def test_escape_applescript_string():
    assert _am._escape_applescript_string("plain") == "plain"
    assert _am._escape_applescript_string('with "quotes"') == 'with \\"quotes\\"'
    assert _am._escape_applescript_string("back\\slash") == "back\\\\slash"
    assert (
        _am._escape_applescript_string('mix "of" \\ both') == 'mix \\"of\\" \\\\ both'
    )


def test_run_osascript_returns_stdout(monkeypatch):
    """Happy path: osascript returns 0 with stdout that gets returned
    verbatim (stripped). Verify we pass `osascript -e <script>`."""
    seen_args = {}

    def _fake_run(args, **kwargs):
        seen_args["args"] = args
        seen_args["timeout"] = kwargs.get("timeout")
        return SimpleNamespace(returncode=0, stdout="42\n", stderr="")

    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(subprocess, "run", _fake_run)
    assert _am._run_osascript("tell application X to return 42") == "42"
    assert seen_args["args"][0] == "osascript"
    assert seen_args["args"][1] == "-e"


def test_run_osascript_raises_on_nonzero(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=1, stdout="", stderr="execution error: bad script"
        ),
    )
    with pytest.raises(_am.AppleScriptError) as exc:
        _am._run_osascript("garbage")
    assert "bad script" in str(exc.value)


def test_run_osascript_raises_on_non_darwin(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    with pytest.raises(_am.AppleScriptUnavailableError):
        _am._run_osascript("anything")


def test_run_osascript_raises_when_osascript_missing(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")

    def _missing(*a, **kw):
        raise FileNotFoundError("osascript")

    monkeypatch.setattr(subprocess, "run", _missing)
    with pytest.raises(_am.AppleScriptUnavailableError):
        _am._run_osascript("anything")


def test_delete_local_music_playlist_parses_count(monkeypatch):
    """Music.app returns the count of deleted playlists; we parse to
    int."""
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout="3\n", stderr=""),
    )
    assert _am.delete_local_music_playlist("Seattle Sound") == 3


def test_delete_local_music_playlist_escapes_quotes(monkeypatch):
    """A playlist name containing quotes round-trips into the script
    safely."""
    captured = {}

    def _fake(args, **kwargs):
        captured["script"] = args[2]
        return SimpleNamespace(returncode=0, stdout="1", stderr="")

    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(subprocess, "run", _fake)
    _am.delete_local_music_playlist('My "Best" Mix')
    # The interpolated name should appear escaped, not literally
    assert '\\"Best\\"' in captured["script"]
    assert 'My \\"Best\\" Mix' in captured["script"]


def test_delete_local_music_playlist_zero_match(monkeypatch):
    """Music.app reports 0 deletions when the name doesn't match
    anything."""
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout="0", stderr=""),
    )
    assert _am.delete_local_music_playlist("Nothing Here") == 0


def test_delete_local_music_playlist_non_integer_output(monkeypatch):
    """If osascript returns something we can't parse as int (shouldn't
    happen, but defend against it), wrap as AppleScriptError."""
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=0, stdout="not-a-number", stderr=""
        ),
    )
    with pytest.raises(_am.AppleScriptError):
        _am.delete_local_music_playlist("X")


# ---------------------------------------------------------------------------
# action layer (delete_apple_music_playlist) — wraps the helper errors
# ---------------------------------------------------------------------------


def test_action_delete_returns_result(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout="2", stderr=""),
    )
    result = delete_apple_music_playlist("Dupes")
    assert result.name == "Dupes"
    assert result.deleted == 2


def test_action_delete_wraps_unavailable(monkeypatch):
    monkeypatch.setattr("sys.platform", "linux")
    with pytest.raises(AppleMusicAppleScriptError) as exc:
        delete_apple_music_playlist("X")
    assert "macOS" in str(exc.value) or "osascript" in str(exc.value)


def test_action_delete_wraps_script_error(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=1, stdout="", stderr="permission denied"
        ),
    )
    with pytest.raises(AppleMusicAppleScriptError) as exc:
        delete_apple_music_playlist("X")
    assert "permission denied" in str(exc.value)
