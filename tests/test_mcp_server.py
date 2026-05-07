"""Tests for the read-only MCP server tools.

We call tool functions directly — FastMCP's @mcp.tool() decorator registers
the function but returns it unchanged, so it remains callable. The full
stdio protocol is exercised separately in test_mcp_smoke.py.

Tools return a CallToolResult with a text summary + structured data. The
`_call()` helper unwraps the structured payload so assertions read like
they did before this layer was added.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

pytest.importorskip("mcp", reason="mcp not installed")

from clickwheel.actions import IpodNotFoundError, PlaylistNotFoundError  # noqa: E402
from clickwheel.config import Config  # noqa: E402
from clickwheel.db import Database  # noqa: E402


def _call(fn, **kwargs):
    """Invoke a tool function and return the structured payload an MCP
    client would consume. Unwraps `{"result": [...]}` wrapping that lists
    pick up automatically."""
    if inspect.iscoroutinefunction(fn):
        result = asyncio.run(fn(**kwargs))
    else:
        result = fn(**kwargs)
    sc = result.structuredContent or {}
    if list(sc.keys()) == ["result"]:
        return sc["result"]
    return sc


def _call_text(fn, **kwargs) -> str:
    """Return the rendered text summary of a tool call."""
    if inspect.iscoroutinefunction(fn):
        result = asyncio.run(fn(**kwargs))
    else:
        result = fn(**kwargs)
    return result.content[0].text if result.content else ""


def _setup(tmp_path, monkeypatch, *, populate=True):
    """Build a Config + DB in tmp_path and patch mcp.server to use it."""
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    cfg = Config(
        music_dir=music_dir,
        project_dir=tmp_path,
        ipod_mount=tmp_path / "ipod-not-mounted",
        auto_scan=False,
    )
    db_path = cfg.db_path
    db = Database(db_path)

    if populate:
        sample = {
            "path": "/music/A/Album1/01.mp3",
            "title": "T1",
            "artist": "ArtistA",
            "album": "Album1",
            "album_artist": "ArtistA",
            "genre": "Rock",
            "track_number": 1,
            "disc_number": 1,
            "year": 2020,
            "duration_seconds": 180.0,
            "bitrate": 320000,
            "sample_rate": 44100,
            "format": "mp3",
            "file_size": 5_000_000,
            "has_art": 1,
            "art_width": 500,
            "art_height": 500,
        }
        db.upsert_track(sample)
        db.upsert_track(
            {
                **sample,
                "path": "/music/B/Album2/01.mp3",
                "title": "S1",
                "artist": "ArtistB",
                "album": "Album2",
                "album_artist": "ArtistB",
                "file_size": 3_000_000,
            }
        )
        db.commit()
    db.close()

    monkeypatch.setattr("clickwheel.mcp._runtime.load_config", lambda: cfg)
    return cfg


def test_library_stats(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.library import library_stats

    _setup(tmp_path, monkeypatch)

    result = _call(library_stats)
    assert result["stats"]["total_tracks"] == 2
    assert any(f["format"] == "mp3" for f in result["formats"])


def test_library_stats_text_summary(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.library import library_stats

    _setup(tmp_path, monkeypatch)

    text = _call_text(library_stats)
    assert "2 tracks" in text
    assert "2 artists" in text


def test_list_artists(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.library import list_artists

    _setup(tmp_path, monkeypatch)

    result = _call(list_artists)
    names = {a["name"] for a in result}
    assert names == {"ArtistA", "ArtistB"}


def test_list_artists_respects_limit(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.library import list_artists

    _setup(tmp_path, monkeypatch)

    result = _call(list_artists, limit=1)
    assert len(result) == 1


def test_list_albums_by_artist(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.library import list_albums_by_artist

    _setup(tmp_path, monkeypatch)

    result = _call(list_albums_by_artist, artist="ArtistA")
    assert [a["album"] for a in result] == ["Album1"]


def test_list_tracks_by_album(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.library import list_tracks_by_album

    _setup(tmp_path, monkeypatch)

    result = _call(list_tracks_by_album, artist="ArtistA", album="Album1")
    assert [t["title"] for t in result] == ["T1"]


def test_search_tracks_matches_artist(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.library import search_tracks

    _setup(tmp_path, monkeypatch)

    result = _call(search_tracks, query="ArtistB")
    assert len(result) == 1
    assert result[0]["title"] == "S1"


def test_search_tracks_empty_query(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.library import search_tracks

    _setup(tmp_path, monkeypatch)

    assert _call(search_tracks, query="   ") == []
    assert "Empty query" in _call_text(search_tracks, query="   ")


def test_search_tracks_no_results_says_so(tmp_path, monkeypatch):
    """Negative-result text — empty array used to be silent, now explains."""
    from clickwheel.mcp.tools.library import search_tracks

    _setup(tmp_path, monkeypatch)

    text = _call_text(search_tracks, query="zzz_no_match_xyz")
    assert "No tracks match" in text


def test_list_playlists_empty(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.playlist import list_playlists

    _setup(tmp_path, monkeypatch)

    assert _call(list_playlists) == []
    assert "No playlists" in _call_text(list_playlists)


def test_list_and_get_playlist(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.playlist import get_playlist, list_playlists

    cfg = _setup(tmp_path, monkeypatch)

    db = Database(cfg.db_path)
    db.save_playlist("test", ["/music/A/Album1/01.mp3", "/music/B/Album2/01.mp3"])
    db.close()

    playlists = _call(list_playlists)
    assert len(playlists) == 1
    assert playlists[0]["name"] == "test"
    assert playlists[0]["tracks"] == 2

    pl = _call(get_playlist, name="test")
    assert pl["track_count"] == 2
    assert pl["size_bytes"] == 8_000_000
    assert {t["title"] for t in pl["tracks"]} == {"T1", "S1"}
    assert {a["name"] for a in pl["artists"]} == {"ArtistA", "ArtistB"}


def test_get_playlist_missing_raises(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.playlist import get_playlist

    _setup(tmp_path, monkeypatch)

    with pytest.raises(PlaylistNotFoundError):
        get_playlist(name="nope")


def test_get_pending_scrobbles_empty(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.scrobble import get_pending_scrobbles

    _setup(tmp_path, monkeypatch)

    assert _call(get_pending_scrobbles) == []
    assert "No pending scrobbles" in _call_text(get_pending_scrobbles)


def test_library_health(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.library import library_health

    _setup(tmp_path, monkeypatch)

    result = _call(library_health)
    assert result["library_dir_exists"] is True
    assert result["total_tracks"] == 2
    assert result["missing_tracks"] == 0
    assert result["last_scan_at"] is None  # never scanned
    assert "last_scan_iso" not in result
    # Negative-result text surfaces the never-scanned condition.
    assert "never scanned" in _call_text(library_health)


def test_get_ipod_contents_no_ipod(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.ipod import get_ipod_contents

    _setup(tmp_path, monkeypatch)

    with pytest.raises(IpodNotFoundError):
        get_ipod_contents()


def test_tools_registered_with_fastmcp():
    """All read + mutation tools should be registered with the FastMCP instance."""
    from clickwheel.mcp.server import mcp

    expected = {
        # read
        "library_stats",
        "list_artists",
        "list_albums_by_artist",
        "list_tracks_by_album",
        "search_tracks",
        "list_playlists",
        "get_playlist",
        "get_ipod_contents",
        "get_pending_scrobbles",
        "library_health",
        # mutation
        "create_playlist",
        "update_playlist",
        "delete_playlist",
        "add_artist_to_playlist",
        "remove_artist_from_playlist",
        "submit_scrobbles",
        "sync_playlist_to_ipod",
        "eject_ipod",
    }
    registered = {tool.name for tool in mcp._tool_manager.list_tools()}
    assert expected <= registered


def test_destructive_tools_have_destructive_annotation():
    """delete_playlist and sync_playlist_to_ipod should be flagged
    destructiveHint=True so MCP clients can gate auto-approval."""
    from clickwheel.mcp.server import mcp

    by_name = {t.name: t for t in mcp._tool_manager.list_tools()}
    for name in ("delete_playlist", "sync_playlist_to_ipod"):
        ann = by_name[name].annotations
        assert ann is not None and ann.destructiveHint is True, name


def test_read_tools_have_read_only_annotation():
    """All read tools should be flagged readOnlyHint=True."""
    from clickwheel.mcp.server import mcp

    by_name = {t.name: t for t in mcp._tool_manager.list_tools()}
    for name in (
        "library_stats",
        "list_artists",
        "list_albums_by_artist",
        "list_tracks_by_album",
        "search_tracks",
        "library_health",
        "list_playlists",
        "get_playlist",
        "get_ipod_contents",
        "get_pending_scrobbles",
    ):
        ann = by_name[name].annotations
        assert ann is not None and ann.readOnlyHint is True, name


def test_eject_ipod_no_ipod(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.ipod import eject_ipod

    _setup(tmp_path, monkeypatch)

    with pytest.raises(IpodNotFoundError):
        eject_ipod()


def test_build_playlist_prompt_registered():
    """The build_playlist prompt should register on the FastMCP instance."""
    from clickwheel.mcp.server import mcp

    names = {p.name for p in mcp._prompt_manager.list_prompts()}
    assert "build_playlist" in names


def test_build_playlist_prompt_body():
    """The prompt body should template in user-provided args and include
    the anti-hallucination + tool-chaining rules."""
    from clickwheel.mcp.prompts import build_playlist

    messages = build_playlist(vibe="late-night jazz", target_minutes=45, name="quiet")
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    body = messages[0]["content"]
    assert "late-night jazz" in body
    assert "45 minutes" in body
    assert "'quiet'" in body
    # Key behavioral rules surface in the prompt.
    assert "library_stats" in body
    assert "search_tracks" in body
    assert "create_playlist" in body
    assert "sync_playlist_to_ipod" in body
    assert "NEVER invent" in body or "Don't invent" in body or "never" in body.lower()


# ---------------------------------------------------------------------------
# Mutation tools
# ---------------------------------------------------------------------------


class _FakeElicitResult:
    def __init__(self, *, action: str, confirm: bool | None = None) -> None:
        self.action = action
        if confirm is None:
            self.data = None
        else:
            from types import SimpleNamespace

            self.data = SimpleNamespace(confirm=confirm)


class _FakeCtx:
    """Mock FastMCP Context that returns a canned elicit response."""

    def __init__(self, *, action: str = "accept", confirm: bool = True) -> None:
        self._action = action
        self._confirm = confirm
        self.last_message: str | None = None

    async def elicit(self, message, schema):  # noqa: ARG002
        self.last_message = message
        return _FakeElicitResult(action=self._action, confirm=self._confirm)


def test_create_playlist(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.playlist import create_playlist

    _setup(tmp_path, monkeypatch)

    result = _call(
        create_playlist,
        name="new",
        track_paths=["/music/A/Album1/01.mp3", "/music/B/Album2/01.mp3"],
    )
    assert result == {"name": "new", "track_count": 2}


def test_create_playlist_already_exists(tmp_path, monkeypatch):
    from clickwheel.actions import PlaylistAlreadyExistsError
    from clickwheel.mcp.tools.playlist import create_playlist

    cfg = _setup(tmp_path, monkeypatch)
    db = Database(cfg.db_path)
    db.save_playlist("dupe", ["/music/A/Album1/01.mp3"])
    db.close()

    with pytest.raises(PlaylistAlreadyExistsError):
        create_playlist(name="dupe", track_paths=["/music/A/Album1/01.mp3"])


def test_update_playlist_new(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.playlist import update_playlist

    _setup(tmp_path, monkeypatch)

    result = _call(
        update_playlist, name="fresh", track_paths=["/music/A/Album1/01.mp3"]
    )
    assert result["name"] == "fresh"
    assert result["track_count"] == 1
    assert result["replaced"] is False


def test_update_playlist_replaces(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.playlist import update_playlist

    cfg = _setup(tmp_path, monkeypatch)
    db = Database(cfg.db_path)
    db.save_playlist("p", ["/music/A/Album1/01.mp3"])
    db.close()

    result = _call(update_playlist, name="p", track_paths=["/music/B/Album2/01.mp3"])
    assert result["replaced"] is True
    assert result["track_count"] == 1


def test_delete_playlist_confirm_true(tmp_path, monkeypatch):
    """confirm=True skips elicitation and deletes immediately."""
    from clickwheel.mcp.tools.playlist import delete_playlist

    cfg = _setup(tmp_path, monkeypatch)
    db = Database(cfg.db_path)
    db.save_playlist("doomed", ["/music/A/Album1/01.mp3"])
    db.close()

    result = _call(delete_playlist, ctx=_FakeCtx(), name="doomed", confirm=True)
    assert result == {"deleted": True, "name": "doomed"}


def test_delete_playlist_user_declines(tmp_path, monkeypatch):
    """User declines via elicitation → playlist stays."""
    from clickwheel.mcp.tools.playlist import delete_playlist

    cfg = _setup(tmp_path, monkeypatch)
    db = Database(cfg.db_path)
    db.save_playlist("kept", ["/music/A/Album1/01.mp3"])
    db.close()

    ctx = _FakeCtx(action="decline")
    result = _call(delete_playlist, ctx=ctx, name="kept")
    assert result == {"deleted": False, "reason": "user declined"}

    # Verify playlist still exists
    db = Database(cfg.db_path)
    assert db.get_playlist("kept")
    db.close()


def test_delete_playlist_user_accepts_via_elicit(tmp_path, monkeypatch):
    """User accepts via elicitation → playlist deleted, message includes track count."""
    from clickwheel.mcp.tools.playlist import delete_playlist

    cfg = _setup(tmp_path, monkeypatch)
    db = Database(cfg.db_path)
    db.save_playlist("ok", ["/music/A/Album1/01.mp3", "/music/B/Album2/01.mp3"])
    db.close()

    ctx = _FakeCtx(action="accept", confirm=True)
    result = _call(delete_playlist, ctx=ctx, name="ok")
    assert result["deleted"] is True
    assert "2 track" in (ctx.last_message or "")


def test_delete_playlist_missing(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.playlist import delete_playlist

    _setup(tmp_path, monkeypatch)

    result = _call(delete_playlist, ctx=_FakeCtx(), name="ghost")
    assert result == {"deleted": False, "reason": "Playlist 'ghost' not found."}


def test_add_artist_to_playlist(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.playlist import add_artist_to_playlist

    _setup(tmp_path, monkeypatch)

    result = _call(add_artist_to_playlist, playlist="myset", artist="ArtistA")
    assert result["added"] == 1
    assert result["playlist"] == "myset"
    assert result["artist"] == "ArtistA"


def test_remove_artist_from_playlist(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.playlist import remove_artist_from_playlist

    cfg = _setup(tmp_path, monkeypatch)
    db = Database(cfg.db_path)
    db.add_artist_to_playlist("myset", "ArtistA")
    db.close()

    result = _call(remove_artist_from_playlist, playlist="myset", artist="ArtistA")
    assert result["removed"] == 1


def test_submit_scrobbles_no_ipod(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.scrobble import submit_scrobbles

    _setup(tmp_path, monkeypatch)

    with pytest.raises(IpodNotFoundError):
        submit_scrobbles(dry_run=True)


def test_sync_playlist_to_ipod_no_ipod(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.ipod import sync_playlist_to_ipod

    _setup(tmp_path, monkeypatch)

    with pytest.raises(IpodNotFoundError):
        asyncio.run(sync_playlist_to_ipod(ctx=_FakeCtx(), playlist="any", confirm=True))
