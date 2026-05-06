"""Tests for the read-only MCP server tools.

We call tool functions directly — FastMCP's @mcp.tool() decorator registers
the function but returns it unchanged, so it remains callable. The full
stdio protocol is exercised separately in test_mcp_smoke.py.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mcp", reason="mcp not installed")

from clickwheel.actions import IpodNotFoundError, PlaylistNotFoundError  # noqa: E402
from clickwheel.config import Config  # noqa: E402
from clickwheel.db import Database  # noqa: E402


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

    monkeypatch.setattr("clickwheel.mcp.server.load_config", lambda: cfg)
    return cfg


def test_library_stats(tmp_path, monkeypatch):
    from clickwheel.mcp.server import library_stats

    _setup(tmp_path, monkeypatch)

    result = library_stats()
    assert result["stats"]["total_tracks"] == 2
    assert any(f["format"] == "mp3" for f in result["formats"])


def test_list_artists(tmp_path, monkeypatch):
    from clickwheel.mcp.server import list_artists

    _setup(tmp_path, monkeypatch)

    result = list_artists()
    names = {a["name"] for a in result}
    assert names == {"ArtistA", "ArtistB"}


def test_list_artists_respects_limit(tmp_path, monkeypatch):
    from clickwheel.mcp.server import list_artists

    _setup(tmp_path, monkeypatch)

    result = list_artists(limit=1)
    assert len(result) == 1


def test_list_albums_by_artist(tmp_path, monkeypatch):
    from clickwheel.mcp.server import list_albums_by_artist

    _setup(tmp_path, monkeypatch)

    result = list_albums_by_artist(artist="ArtistA")
    assert [a["album"] for a in result] == ["Album1"]


def test_list_tracks_by_album(tmp_path, monkeypatch):
    from clickwheel.mcp.server import list_tracks_by_album

    _setup(tmp_path, monkeypatch)

    result = list_tracks_by_album(artist="ArtistA", album="Album1")
    assert [t["title"] for t in result] == ["T1"]


def test_search_tracks_matches_artist(tmp_path, monkeypatch):
    from clickwheel.mcp.server import search_tracks

    _setup(tmp_path, monkeypatch)

    result = search_tracks(query="ArtistB")
    assert len(result) == 1
    assert result[0]["title"] == "S1"


def test_search_tracks_empty_query(tmp_path, monkeypatch):
    from clickwheel.mcp.server import search_tracks

    _setup(tmp_path, monkeypatch)

    assert search_tracks(query="   ") == []


def test_list_playlists_empty(tmp_path, monkeypatch):
    from clickwheel.mcp.server import list_playlists

    _setup(tmp_path, monkeypatch)

    assert list_playlists() == []


def test_list_and_get_playlist(tmp_path, monkeypatch):
    from clickwheel.mcp.server import get_playlist, list_playlists

    cfg = _setup(tmp_path, monkeypatch)

    db = Database(cfg.db_path)
    db.save_playlist("test", ["/music/A/Album1/01.mp3", "/music/B/Album2/01.mp3"])
    db.close()

    playlists = list_playlists()
    assert len(playlists) == 1
    assert playlists[0]["name"] == "test"
    assert playlists[0]["tracks"] == 2

    pl = get_playlist(name="test")
    assert pl["track_count"] == 2
    assert pl["size_bytes"] == 8_000_000
    assert {t["title"] for t in pl["tracks"]} == {"T1", "S1"}
    assert {a["name"] for a in pl["artists"]} == {"ArtistA", "ArtistB"}


def test_get_playlist_missing_raises(tmp_path, monkeypatch):
    from clickwheel.mcp.server import get_playlist

    _setup(tmp_path, monkeypatch)

    with pytest.raises(PlaylistNotFoundError):
        get_playlist(name="nope")


def test_get_pending_scrobbles_empty(tmp_path, monkeypatch):
    from clickwheel.mcp.server import get_pending_scrobbles

    _setup(tmp_path, monkeypatch)

    assert get_pending_scrobbles() == []


def test_library_health(tmp_path, monkeypatch):
    from clickwheel.mcp.server import library_health

    _setup(tmp_path, monkeypatch)

    result = library_health()
    assert result["library_dir_exists"] is True
    assert result["total_tracks"] == 2
    assert result["missing_tracks"] == 0
    assert result["last_scan_at"] is None  # never scanned
    assert "last_scan_iso" not in result


def test_get_ipod_contents_no_ipod(tmp_path, monkeypatch):
    from clickwheel.mcp.server import get_ipod_contents

    _setup(tmp_path, monkeypatch)

    with pytest.raises(IpodNotFoundError):
        get_ipod_contents()


def test_tools_registered_with_fastmcp():
    """All read tools should be registered with the FastMCP instance."""
    from clickwheel.mcp.server import mcp

    expected = {
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
    }
    registered = {tool.name for tool in mcp._tool_manager.list_tools()}
    assert expected <= registered
