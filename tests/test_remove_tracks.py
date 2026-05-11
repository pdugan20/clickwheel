"""Unit tests for remove_tracks_from_ipod / remove_artist_from_ipod /
remove_ipod_playlist. Same mock-the-iPod-edge approach as the add
tests."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

pytest.importorskip("mcp", reason="mcp not installed")

from clickwheel import actions  # noqa: E402
from clickwheel.actions import PlaylistNotFoundError  # noqa: E402
from clickwheel.config import Config  # noqa: E402
from clickwheel.db import Database  # noqa: E402


class _FakeContext:
    def __init__(self) -> None:
        self.calls: list[tuple[float, float | None, str | None]] = []

    async def report_progress(
        self,
        progress: float,
        total: float | None = None,
        message: str | None = None,
    ) -> None:
        self.calls.append((progress, total, message))


def _setup(tmp_path, monkeypatch):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    cfg = Config(
        music_dir=music_dir,
        project_dir=tmp_path,
        ipod_mount=tmp_path / "ipod",
        auto_scan=False,
    )
    cfg.ipod_mount.mkdir()
    db = Database(cfg.db_path)

    sample: dict[str, Any] = {
        "title": "T",
        "album": "Pinkerton",
        "genre": "Rock",
        "track_number": 1,
        "disc_number": 1,
        "year": 1996,
        "duration_seconds": 180.0,
        "bitrate": 320000,
        "sample_rate": 44100,
        "format": "mp3",
        "file_size": 5_000_000,
        "has_art": 1,
        "art_width": 500,
        "art_height": 500,
    }
    for title in ["El Scorcho", "The Good Life", "Across the Sea"]:
        db.upsert_track(
            {
                **sample,
                "path": f"/music/Weezer/{title}.mp3",
                "artist": "Weezer",
                "album_artist": "Weezer",
                "title": title,
            }
        )
    db.commit()
    db.close()

    monkeypatch.setattr("clickwheel.mcp._runtime.load_config", lambda: cfg)
    monkeypatch.setattr("clickwheel.mcp.tools.ipod.load_config", lambda: cfg)
    return cfg


def _stub_ipod(monkeypatch, *, ipod_tracks=None, existing_playlists=None):
    ipod_tracks = ipod_tracks or []
    existing_playlists = existing_playlists or []

    monkeypatch.setattr(actions, "require_ipod", lambda _cfg: {"fake": "db"})
    monkeypatch.setattr(
        "clickwheel.ipod.get_ipod_tracks", lambda _db: list(ipod_tracks)
    )
    monkeypatch.setattr(
        "clickwheel.ipod.get_ipod_playlists",
        lambda _db: list(existing_playlists),
    )
    # write_ipod_db is the boundary — we just record the call shape.
    captured: dict[str, Any] = {}

    def fake_write(*_a, **kw):
        captured.update(kw)
        return True

    monkeypatch.setattr("clickwheel.ipod.sync.write_ipod_db", fake_write)
    monkeypatch.setattr(
        "clickwheel.ipod.sync.unlink_ipod_track_files",
        lambda _mount, locs: len(locs),
    )
    return captured


def test_remove_tracks_happy_path(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.ipod import remove_tracks_from_ipod

    _setup(tmp_path, monkeypatch)
    ipod = [
        {
            "artist": "Weezer",
            "album": "Pinkerton",
            "title": "El Scorcho",
            "location": ":iPod_Control:Music:F00/01.mp3",
            "size": 5_000_000,
        },
        {
            "artist": "Weezer",
            "album": "Pinkerton",
            "title": "The Good Life",
            "location": ":iPod_Control:Music:F00/02.mp3",
            "size": 4_500_000,
        },
    ]
    captured = _stub_ipod(monkeypatch, ipod_tracks=ipod)

    ctx = _FakeContext()
    paths = [
        "/music/Weezer/El Scorcho.mp3",
        "/music/Weezer/The Good Life.mp3",
    ]
    result = asyncio.run(remove_tracks_from_ipod(paths=paths, ctx=ctx))

    sc = result.structuredContent or {}
    assert sc["removed"] == 2
    assert sc["not_matched"] == 0
    assert sc["bytes_freed"] == 9_500_000
    # The right locations should have made it into write_ipod_db.
    assert captured["remove_track_locations"] == {
        ":iPod_Control:Music:F00/01.mp3",
        ":iPod_Control:Music:F00/02.mp3",
    }
    # Per-track progress fired.
    assert len(ctx.calls) == 2


def test_remove_tracks_reports_unmatched(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.ipod import remove_tracks_from_ipod

    _setup(tmp_path, monkeypatch)
    # Only one track is on the iPod; the other path's triple doesn't match.
    ipod = [
        {
            "artist": "Weezer",
            "album": "Pinkerton",
            "title": "El Scorcho",
            "location": ":iPod_Control:Music:F00/01.mp3",
            "size": 5_000_000,
        },
    ]
    _stub_ipod(monkeypatch, ipod_tracks=ipod)

    ctx = _FakeContext()
    paths = [
        "/music/Weezer/El Scorcho.mp3",
        "/music/Weezer/The Good Life.mp3",
        "/music/Phantom/notindexed.mp3",
    ]
    result = asyncio.run(remove_tracks_from_ipod(paths=paths, ctx=ctx))

    sc = result.structuredContent or {}
    assert sc["removed"] == 1
    # Two unmatched: one path not in library, one in library but not on iPod.
    assert sc["not_matched"] == 2


def test_remove_artist_from_ipod(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.ipod import remove_artist_from_ipod

    _setup(tmp_path, monkeypatch)
    ipod = [
        {
            "artist": "Weezer",
            "album_artist": "Weezer",
            "album": "Pinkerton",
            "title": "El Scorcho",
            "location": ":iPod_Control:Music:F00/01.mp3",
            "size": 5_000_000,
        },
        {
            "artist": "Weezer",
            "album_artist": "Weezer",
            "album": "Blue Album",
            "title": "Buddy Holly",
            "location": ":iPod_Control:Music:F00/03.mp3",
            "size": 4_000_000,
        },
        {
            "artist": "Wilco",
            "album_artist": "Wilco",
            "album": "Sky Blue Sky",
            "title": "Impossible Germany",
            "location": ":iPod_Control:Music:F00/04.mp3",
            "size": 6_000_000,
        },
    ]
    _stub_ipod(monkeypatch, ipod_tracks=ipod)

    ctx = _FakeContext()
    result = asyncio.run(remove_artist_from_ipod(artist="Weezer", ctx=ctx))

    sc = result.structuredContent or {}
    assert sc["artist"] == "Weezer"
    assert sc["removed"] == 2
    assert sc["bytes_freed"] == 9_000_000
    # Wilco should be untouched.
    assert len(ctx.calls) == 2


def test_remove_artist_no_matches(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.ipod import remove_artist_from_ipod

    _setup(tmp_path, monkeypatch)
    _stub_ipod(monkeypatch, ipod_tracks=[])

    ctx = _FakeContext()
    result = asyncio.run(remove_artist_from_ipod(artist="Nobody", ctx=ctx))

    sc = result.structuredContent or {}
    assert sc["removed"] == 0
    assert ctx.calls == []


def test_remove_ipod_playlist(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.ipod import remove_ipod_playlist

    _setup(tmp_path, monkeypatch)
    captured = _stub_ipod(
        monkeypatch,
        existing_playlists=[
            {
                "name": "test-mix",
                "track_count": 3,
                "is_smart": False,
                "item_track_ids": [],
            }
        ],
    )

    result = remove_ipod_playlist(name="test-mix")
    sc = result.structuredContent or {}
    assert sc["removed_playlist"] is True
    assert sc["library_updated"] is True
    assert captured["remove_playlist_names"] == {"test-mix"}


def test_remove_ipod_playlist_not_found(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.ipod import remove_ipod_playlist

    _setup(tmp_path, monkeypatch)
    _stub_ipod(monkeypatch, existing_playlists=[])

    with pytest.raises(PlaylistNotFoundError):
        remove_ipod_playlist(name="ghost")
