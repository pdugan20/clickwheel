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
    # sync_playlist_to_ipod imports load_config directly (it can't use
    # open_session because it reopens the DB in a worker thread). Patch
    # that binding too so tests stay independent of whether the dev
    # machine has an iPod mounted at the real cfg.ipod_mount path.
    monkeypatch.setattr("clickwheel.mcp.tools.ipod.load_config", lambda: cfg)
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

    # get_playlist returns the summary only (no full tracks array — use
    # list_playlist_tracks to drill in).
    pl = _call(get_playlist, name="test")
    assert pl["track_count"] == 2
    assert pl["size_bytes"] == 8_000_000
    assert "tracks" not in pl
    assert {a["name"] for a in pl["artists"]} == {"ArtistA", "ArtistB"}


def test_list_playlist_tracks(tmp_path, monkeypatch):
    from clickwheel.actions import PlaylistNotFoundError
    from clickwheel.mcp.tools.playlist import list_playlist_tracks

    cfg = _setup(tmp_path, monkeypatch)
    db = Database(cfg.db_path)
    db.save_playlist("test", ["/music/A/Album1/01.mp3", "/music/B/Album2/01.mp3"])
    db.close()

    tracks = _call(list_playlist_tracks, name="test")
    assert {t["title"] for t in tracks} == {"T1", "S1"}

    # Pagination
    page1 = _call(list_playlist_tracks, name="test", limit=1, offset=0)
    page2 = _call(list_playlist_tracks, name="test", limit=1, offset=1)
    assert len(page1) == 1
    assert len(page2) == 1
    assert page1[0]["title"] != page2[0]["title"]

    # Past the end
    empty = _call(list_playlist_tracks, name="test", offset=100)
    assert empty == []

    # Missing playlist
    with pytest.raises(PlaylistNotFoundError):
        list_playlist_tracks(name="ghost")


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


def test_list_ipod_tracks_no_ipod(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.ipod import list_ipod_tracks

    _setup(tmp_path, monkeypatch)

    with pytest.raises(IpodNotFoundError):
        list_ipod_tracks()


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
        "list_playlist_tracks",
        "get_ipod_contents",
        "list_ipod_tracks",
        "get_pending_scrobbles",
        "library_health",
        # mutation
        "create_playlist",
        "update_playlist",
        "delete_playlist",
        "heal_playlist",
        "add_artist_to_playlist",
        "remove_artist_from_playlist",
        "submit_scrobbles",
        "sync_playlist_to_ipod",
        "eject_ipod",
    }
    registered = {tool.name for tool in mcp._tool_manager.list_tools()}
    assert expected <= registered


def test_mcp_open_session_never_autoscans(tmp_path, monkeypatch):
    """The MCP server must never autoscan — chat tool calls always serve
    cached data. Users refresh by running `clickwheel scan` from the CLI.
    """
    from clickwheel.mcp._runtime import open_session

    cfg = _setup(tmp_path, monkeypatch)
    # Force conditions that would normally trigger an autoscan: no
    # last_scan_completed, no probe baseline. If open_session is
    # accidentally autoscanning, this would attempt to walk the
    # (empty) music_dir and write scan_meta entries.
    db = Database(cfg.db_path)
    db.set_scan_meta("last_scan_completed", "")  # clear
    db.close()

    # Drain the context manager — no errors, no scan.
    with open_session() as (_cfg, db):
        pass

    db = Database(cfg.db_path)
    # If autoscan ran, scan_library would have written this back.
    last = db.get_scan_meta("last_scan_completed")
    assert last == "" or last is None
    db.close()


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
        "list_playlist_tracks",
        "get_ipod_contents",
        "list_ipod_tracks",
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
#
# Destructive tools (delete_playlist, sync_playlist_to_ipod) used to elicit
# server-side confirmation. That was the wrong primitive — Claude Code (and
# other compliant clients) gate `destructiveHint=true` tools natively, and
# our extra elicitation produced a confusing double-prompt UX. Tools are now
# regular functions; the client owns the Allow/Deny step.
# ---------------------------------------------------------------------------


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


def test_delete_playlist(tmp_path, monkeypatch):
    """Tool deletes the playlist and returns the expected shape. The client
    is responsible for gating the call via the destructiveHint annotation."""
    from clickwheel.mcp.tools.playlist import delete_playlist

    cfg = _setup(tmp_path, monkeypatch)
    db = Database(cfg.db_path)
    db.save_playlist("doomed", ["/music/A/Album1/01.mp3"])
    db.close()

    result = _call(delete_playlist, name="doomed")
    assert result == {"deleted": True, "name": "doomed"}

    db = Database(cfg.db_path)
    assert not db.get_playlist("doomed")
    db.close()


def test_delete_playlist_missing(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.playlist import delete_playlist

    _setup(tmp_path, monkeypatch)

    result = _call(delete_playlist, name="ghost")
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

    # The async tool takes a Context for progress reporting. Pass a stub
    # whose report_progress is a no-op coroutine; we only care that the
    # iPod-not-mounted error still propagates.
    class _StubCtx:
        async def report_progress(self, *_a, **_k):
            return None

    with pytest.raises(IpodNotFoundError):
        asyncio.run(sync_playlist_to_ipod(playlist="any", ctx=_StubCtx()))


def test_heal_playlist_clean(tmp_path, monkeypatch):
    """Healing a playlist with no dead refs is a no-op."""
    from clickwheel.mcp.tools.playlist import heal_playlist

    cfg = _setup(tmp_path, monkeypatch)
    db = Database(cfg.db_path)
    db.save_playlist("clean", ["/music/A/Album1/01.mp3", "/music/B/Album2/01.mp3"])
    db.close()

    result = _call(heal_playlist, name="clean")
    assert result["dropped"] == 0
    assert result["remaining"] == 2
    assert result["dropped_tracks"] == []


def test_heal_playlist_drops_missing(tmp_path, monkeypatch):
    """Tracks flagged missing_since are removed from the playlist."""
    from clickwheel.mcp.tools.playlist import heal_playlist

    cfg = _setup(tmp_path, monkeypatch)
    db = Database(cfg.db_path)
    db.save_playlist("p", ["/music/A/Album1/01.mp3", "/music/B/Album2/01.mp3"])
    db.mark_missing({"/music/A/Album1/01.mp3"})
    db.close()

    result = _call(heal_playlist, name="p")
    assert result["dropped"] == 1
    assert result["remaining"] == 1
    assert len(result["dropped_tracks"]) == 1
    assert result["dropped_tracks"][0]["path"] == "/music/A/Album1/01.mp3"

    # And the playlist now has only the remaining track.
    db = Database(cfg.db_path)
    remaining = db.get_playlist("p")
    db.close()
    assert [t["path"] for t in remaining] == ["/music/B/Album2/01.mp3"]


def test_heal_playlist_missing_playlist(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.playlist import heal_playlist

    _setup(tmp_path, monkeypatch)

    with pytest.raises(PlaylistNotFoundError):
        heal_playlist(name="ghost")


# ---------------------------------------------------------------------------
# Plex tools
# ---------------------------------------------------------------------------


def _setup_plex(tmp_path, monkeypatch, *, enabled: bool = True) -> Config:
    """Variant of _setup() that returns a Plex-configured Config."""
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    cfg = Config(
        music_dir=music_dir,
        project_dir=tmp_path,
        ipod_mount=tmp_path / "ipod-not-mounted",
        auto_scan=False,
        plex_enabled=enabled,
        plex_url="http://example.invalid:32400",
        plex_token="t",
        plex_library_name="Music",
    )
    db = Database(cfg.db_path)
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
    db.commit()
    db.close()
    monkeypatch.setattr("clickwheel.mcp._runtime.load_config", lambda: cfg)
    return cfg


def test_plex_health_disabled(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.plex import plex_health

    _setup_plex(tmp_path, monkeypatch, enabled=False)
    result = _call(plex_health)
    assert result["ok"] is False
    assert result["stages"][0]["name"] == "config"


def test_plex_health_all_pass(tmp_path, monkeypatch):
    """Stub plexapi so all five stages succeed; verify the tool wraps
    the result into the expected MCP shape. The plexapi extra check is
    bypassed so this test works whether or not [plex] is installed."""
    from clickwheel import plex as _plex
    from clickwheel.mcp.tools.plex import plex_health

    cfg = _setup_plex(tmp_path, monkeypatch)
    monkeypatch.setattr(_plex, "_import_plexapi", lambda: None)

    class _Part:
        file = "/music/A/Album1/01.mp3"

    class _Media:
        parts = [_Part()]

    class _Track:
        media = [_Media()]

    # plexapi attrs are camelCase by external API convention.
    class _Section:
        type = "artist"
        title = "Music"
        key = "4"
        totalSize = 1  # noqa: N815

        def searchTracks(self, **kwargs):  # noqa: N802
            return [_Track()]

    class _Library:
        @staticmethod
        def sections():
            return [_Section()]

    class _Server:
        friendlyName = "test"  # noqa: N815
        version = "1.0"
        library = _Library()

    monkeypatch.setattr(_plex, "connect", lambda url, token: _Server())

    result = _call(plex_health)
    assert result["ok"] is True
    assert [s["name"] for s in result["stages"]] == [
        "config",
        "plexapi extra",
        "connect",
        "music section",
        "sample track",
    ]
    assert cfg.plex_url  # use cfg so the lint doesn't grumble


def test_sync_playlist_to_plex_returns_plex_not_configured_error(tmp_path, monkeypatch):
    """Disabled config -> structured error payload, NOT an unhandled
    exception."""
    from clickwheel.mcp.tools.plex import sync_playlist_to_plex

    _setup_plex(tmp_path, monkeypatch, enabled=False)
    result = _call(sync_playlist_to_plex, playlist="anything")
    assert result["error"] == "plex_not_configured"


def test_sync_playlist_to_plex_success(tmp_path, monkeypatch):
    from clickwheel import plex as _plex
    from clickwheel.mcp.tools.plex import sync_playlist_to_plex

    cfg = _setup_plex(tmp_path, monkeypatch)
    monkeypatch.setattr(_plex, "_import_plexapi", lambda: None)
    db = Database(cfg.db_path)
    db.save_playlist("p", ["/music/A/Album1/01.mp3"])
    db.commit()
    db.close()

    class _Section:
        type = "artist"
        title = "Music"
        key = "4"

    class _Library:
        @staticmethod
        def sections():
            return [_Section()]

    class _Server:
        library = _Library()

    class _UploadedPlaylist:
        leafCount = 1  # noqa: N815
        ratingKey = 42  # noqa: N815
        title = "p"

    monkeypatch.setattr(_plex, "connect", lambda url, token: _Server())
    monkeypatch.setattr(
        _plex,
        "upload_playlist",
        lambda plex, section, name, m3u: _UploadedPlaylist(),
    )

    result = _call(sync_playlist_to_plex, playlist="p")
    assert result["pushed"] == 1
    assert result["resolved"] == 1
    assert result["plex_rating_key"] == 42
    assert "test" not in result.get("error", "")


# ---------------------------------------------------------------------------
# Output-schema conformance
#
# Every tool annotates a Pydantic return model, so FastMCP emits an
# outputSchema. The MCP spec requires structuredContent to conform to that
# schema, so each test below validates a real tool result against the model
# the tool declares as its return type.
# ---------------------------------------------------------------------------

import types  # noqa: E402
import typing  # noqa: E402

from pydantic import TypeAdapter  # noqa: E402


class _StubCtx:
    """Minimal Context stand-in for the async iPod tools."""

    async def report_progress(self, *_a, **_k):
        return None


def _conform(fn, **kwargs):
    """Call a tool and validate its structuredContent against the Pydantic
    model named in the tool's return annotation. Returns the payload."""
    if inspect.iscoroutinefunction(fn):
        result = asyncio.run(fn(**kwargs))
    else:
        result = fn(**kwargs)
    ann = typing.get_type_hints(fn)["return"]
    sc = result.structuredContent
    assert sc is not None, f"{fn.__name__}: no structuredContent"
    payload = sc["result"] if typing.get_origin(ann) is list else sc
    TypeAdapter(ann).validate_python(payload)
    return payload


def test_all_tools_emit_output_schema():
    from clickwheel.mcp._runtime import mcp

    tools = asyncio.run(mcp.list_tools())
    assert len(tools) == 29
    for t in tools:
        assert t.outputSchema, f"{t.name}: no outputSchema"
        assert t.outputSchema.get("properties"), f"{t.name}: schema has no properties"


def test_conformance_library_tools(tmp_path, monkeypatch):
    from clickwheel.mcp.tools import library as lib

    _setup(tmp_path, monkeypatch)

    _conform(lib.library_stats)
    _conform(lib.list_artists)
    _conform(lib.list_albums_by_artist, artist="ArtistA")
    _conform(lib.list_tracks_by_album, artist="ArtistA", album="Album1")
    _conform(lib.search_tracks, query="T1")
    _conform(lib.library_health)


def test_conformance_playlist_tools(tmp_path, monkeypatch):
    from clickwheel.mcp.tools import playlist as pl

    cfg = _setup(tmp_path, monkeypatch)
    db = Database(cfg.db_path)
    db.save_playlist("mix", ["/music/A/Album1/01.mp3", "/music/B/Album2/01.mp3"])
    db.close()

    _conform(pl.list_playlists)
    _conform(pl.get_playlist, name="mix")
    _conform(pl.list_playlist_tracks, name="mix")
    _conform(pl.create_playlist, name="fresh", track_paths=["/music/A/Album1/01.mp3"])
    _conform(pl.update_playlist, name="mix", track_paths=["/music/A/Album1/01.mp3"])
    _conform(pl.add_artist_to_playlist, playlist="mix", artist="ArtistB")
    _conform(pl.remove_artist_from_playlist, playlist="mix", artist="ArtistB")
    _conform(pl.heal_playlist, name="mix")
    _conform(pl.delete_playlist, name="mix")


def test_conformance_scrobbles_and_eject(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.ipod import eject_ipod
    from clickwheel.mcp.tools.scrobble import get_pending_scrobbles

    _setup(tmp_path, monkeypatch)

    _conform(get_pending_scrobbles)
    # No iPod mounted: eject returns the graceful "already disconnected"
    # EjectResult shape rather than raising.
    _conform(eject_ipod)


def test_conformance_plex_tools(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.plex import plex_health, sync_playlist_to_plex

    _setup_plex(tmp_path, monkeypatch, enabled=False)

    _conform(plex_health)
    # Disabled config: structured error variant of PlexSyncResult.
    _conform(sync_playlist_to_plex, playlist="anything")


def test_conformance_ipod_read_tools(tmp_path, monkeypatch):
    """iPod read tools need a device; stub the actions layer they wrap."""
    from clickwheel.mcp.tools import ipod as ip

    _setup(tmp_path, monkeypatch)
    fake_track = {
        "artist": "ArtistA",
        "album_artist": "ArtistA",
        "album": "Album1",
        "title": "T1",
        "size": 5_000_000,
    }
    monkeypatch.setattr(
        "clickwheel.actions.read_ipod_contents",
        lambda cfg: {
            "tracks": [fake_track],
            "capacity_bytes": 80_000_000_000,
            "used_bytes": 5_000_000,
            "free_bytes": 79_995_000_000,
        },
    )
    monkeypatch.setattr(
        "clickwheel.actions.list_ipod_playlists",
        lambda cfg: [
            {
                "name": "Road Trip",
                "track_count": 1,
                "total_bytes": 5_000_000,
                "is_smart": False,
            }
        ],
    )
    monkeypatch.setattr(
        "clickwheel.actions.list_ipod_tracks",
        lambda cfg, artist=None, limit=50, offset=0: [fake_track],
    )

    _conform(ip.get_ipod_contents)
    _conform(ip.list_ipod_playlists)
    _conform(ip.list_ipod_tracks)


def test_conformance_ipod_mutation_tools(tmp_path, monkeypatch):
    """iPod write tools need a device; stub the actions layer they wrap so
    the tools' real result-dict-building runs and is schema-validated."""
    from clickwheel import actions
    from clickwheel.mcp.tools import ipod as ip

    cfg = _setup(tmp_path, monkeypatch)
    db = Database(cfg.db_path)
    db.save_playlist("mix", ["/music/A/Album1/01.mp3"])
    db.close()

    sync_result = actions.SyncResult(
        copied=[({"file_size": 5_000_000}, "ok")],
        failed=[],
        kept_in_place_count=0,
        library_updated=True,
    )
    remove_result = actions.RemoveResult(
        removed=[{"artist": "ArtistA", "album": "Album1", "title": "T1"}],
        not_matched=[],
        bytes_freed=5_000_000,
        library_updated=True,
    )

    monkeypatch.setattr(
        "clickwheel.actions.compute_diff",
        lambda cfg, db, playlist: actions.Diff(playlist=playlist),
    )
    monkeypatch.setattr(
        "clickwheel.actions.sync_playlist",
        lambda cfg, db, playlist, **kw: sync_result,
    )
    monkeypatch.setattr(
        "clickwheel.actions.add_tracks_to_ipod",
        lambda cfg, db, paths, **kw: sync_result,
    )
    monkeypatch.setattr(
        "clickwheel.actions.collect_tracks_for_artist",
        lambda db, artist: ["/music/A/Album1/01.mp3"],
    )
    monkeypatch.setattr(
        "clickwheel.actions.remove_tracks_from_ipod",
        lambda cfg, db, paths, **kw: remove_result,
    )
    monkeypatch.setattr(
        "clickwheel.actions.remove_artist_from_ipod",
        lambda cfg, artist, **kw: remove_result,
    )
    monkeypatch.setattr(
        "clickwheel.actions.remove_ipod_playlist",
        lambda cfg, name: remove_result,
    )

    ctx = _StubCtx()
    _conform(ip.sync_playlist_to_ipod, playlist="mix", ctx=ctx)
    _conform(ip.add_tracks_to_ipod, paths=["/music/A/Album1/01.mp3"], ctx=ctx)
    _conform(ip.add_artist_to_ipod, artist="ArtistA", ctx=ctx)
    _conform(ip.remove_tracks_from_ipod, paths=["/music/A/Album1/01.mp3"], ctx=ctx)
    _conform(ip.remove_artist_from_ipod, artist="ArtistA", ctx=ctx)
    _conform(ip.remove_ipod_playlist, name="mix")


def test_conformance_submit_scrobbles(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.scrobble import submit_scrobbles

    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "clickwheel.actions.collect_ipod_plays",
        lambda cfg, db: {"plays_found": 0, "new_cached": 0, "oldest_age_days": None},
    )
    monkeypatch.setattr(
        "clickwheel.actions.submit_pending_scrobbles",
        lambda cfg, db: types.SimpleNamespace(
            submitted=0, failed=0, remaining_pending=0
        ),
    )

    _conform(submit_scrobbles, dry_run=True)
    _conform(submit_scrobbles, dry_run=False)
