"""Unit tests for add_tracks_to_ipod / add_artist_to_ipod.

Mirrors the test pattern in test_sync_progress.py: stubs the low-level
copy + iPod-read functions so we exercise the action's wiring (path
resolution, dedup against iPod, progress callbacks, error mapping)
without needing a real iPod or real files.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

pytest.importorskip("mcp", reason="mcp not installed")

from clickwheel import actions
from clickwheel.actions import PathsNotFoundError
from clickwheel.config import Config
from clickwheel.db import Database


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
        ipod_mount=tmp_path / "ipod-not-mounted",
        auto_scan=False,
    )
    db = Database(cfg.db_path)

    # Seed three indexed tracks. album_artist matches artist so artist
    # lookups don't bleed across (get_albums_by_artist matches on either).
    sample: dict[str, Any] = {
        "title": "T",
        "album": "A",
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
    for artist, title in [("ArtistA", "T1"), ("ArtistA", "T2"), ("ArtistB", "S1")]:
        db.upsert_track(
            {
                **sample,
                "path": f"/music/{artist}/{title}.mp3",
                "artist": artist,
                "album_artist": artist,
                "title": title,
            }
        )
    db.commit()
    db.close()

    monkeypatch.setattr("clickwheel.mcp._runtime.load_config", lambda: cfg)
    monkeypatch.setattr("clickwheel.mcp.tools.ipod.load_config", lambda: cfg)
    return cfg


def _stub_ipod_and_copy(monkeypatch, *, already_on_ipod=None, fail_paths=None):
    """Replace require_ipod / get_ipod_tracks / copy_tracks_to_ipod / write_ipod_db
    so the action runs end-to-end without a real device."""
    fail_paths = fail_paths or set()
    already_on_ipod = already_on_ipod or []  # list of (artist, album, title)

    monkeypatch.setattr(actions, "require_ipod", lambda _cfg: {"fake": "db"})

    def fake_get_tracks(_db):
        return [{"artist": a, "album": b, "title": c} for (a, b, c) in already_on_ipod]

    monkeypatch.setattr("clickwheel.ipod.get_ipod_tracks", fake_get_tracks)

    def fake_copy(tracks, _mount, on_progress):
        copied = []
        failed = []
        for i, t in enumerate(tracks, start=1):
            on_progress(i, len(tracks))
            if t["path"] in fail_paths:
                failed.append(t)
            else:
                copied.append((t, f"iPod_Control/Music/F00/{t['title']}.mp3"))
        return copied, failed

    monkeypatch.setattr("clickwheel.ipod.sync.copy_tracks_to_ipod", fake_copy)
    monkeypatch.setattr("clickwheel.ipod.sync.write_ipod_db", lambda *_a, **_k: True)

    # Disk-space check needs a real path — point at /tmp.
    import shutil as _shutil

    monkeypatch.setattr(
        _shutil,
        "disk_usage",
        lambda _p: type("U", (), {"total": 10**12, "used": 0, "free": 10**12})(),
    )


def test_add_tracks_to_ipod_happy_path(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.ipod import add_tracks_to_ipod

    _setup(tmp_path, monkeypatch)
    _stub_ipod_and_copy(monkeypatch)

    ctx = _FakeContext()
    paths = ["/music/ArtistA/T1.mp3", "/music/ArtistA/T2.mp3"]
    result = asyncio.run(add_tracks_to_ipod(paths=paths, ctx=ctx))

    sc = result.structured_content or {}
    assert sc["added"] == 2
    assert sc["failed"] == 0
    assert sc["already_present"] == 0
    assert sc["library_updated"] is True
    # Per-track progress fired for each.
    assert [c[0] for c in ctx.calls] == [1, 2]
    assert all(c[1] == 2 for c in ctx.calls)


def test_add_tracks_dedupes_against_ipod(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.ipod import add_tracks_to_ipod

    _setup(tmp_path, monkeypatch)
    # T1 already on iPod — only T2 should copy.
    _stub_ipod_and_copy(monkeypatch, already_on_ipod=[("ArtistA", "A", "T1")])

    ctx = _FakeContext()
    paths = ["/music/ArtistA/T1.mp3", "/music/ArtistA/T2.mp3"]
    result = asyncio.run(add_tracks_to_ipod(paths=paths, ctx=ctx))

    sc = result.structured_content or {}
    assert sc["added"] == 1
    assert sc["already_present"] == 1


def test_add_tracks_rejects_unknown_paths(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.ipod import add_tracks_to_ipod

    _setup(tmp_path, monkeypatch)

    ctx = _FakeContext()
    with pytest.raises(PathsNotFoundError) as exc:
        asyncio.run(
            add_tracks_to_ipod(
                paths=["/music/ArtistA/T1.mp3", "/music/Phantom/nope.mp3"],
                ctx=ctx,
            )
        )
    assert exc.value.unknown_paths == ["/music/Phantom/nope.mp3"]


def test_add_artist_to_ipod_happy_path(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.ipod import add_artist_to_ipod

    _setup(tmp_path, monkeypatch)
    _stub_ipod_and_copy(monkeypatch)

    ctx = _FakeContext()
    result = asyncio.run(add_artist_to_ipod(artist="ArtistA", ctx=ctx))

    sc = result.structured_content or {}
    assert sc["artist"] == "ArtistA"
    assert sc["found_in_library"] == 2
    assert sc["added"] == 2
    # Progress for both tracks.
    assert len(ctx.calls) == 2


def test_add_artist_to_ipod_unknown_artist(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.ipod import add_artist_to_ipod

    _setup(tmp_path, monkeypatch)
    _stub_ipod_and_copy(monkeypatch)

    ctx = _FakeContext()
    result = asyncio.run(add_artist_to_ipod(artist="Nobody", ctx=ctx))

    sc = result.structured_content or {}
    assert sc["found_in_library"] == 0
    assert sc["added"] == 0
    assert ctx.calls == []
