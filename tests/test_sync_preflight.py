"""Pre-flight checks on `actions.sync_playlist`.

These guard against the two ways a sync used to silently waste minutes:
- Music share unmounted → 22 timeouts in `copy_tracks_to_ipod` before
  failing with no actionable error.
- Playlist references stale paths (files moved/deleted since indexing)
  → same 22-timeout pattern, but mountable share.

Both now raise typed errors before any I/O so callers can surface a
clear message and point at `heal_playlist` / re-mounting.
"""

from __future__ import annotations

import pytest

from clickwheel.actions import (
    Diff,
    LibraryNotFoundError,
    MissingTracksError,
    sync_playlist,
)
from clickwheel.config import Config
from clickwheel.db import Database


def _cfg_with_music(tmp_path):
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    return Config(
        music_dir=music_dir,
        project_dir=tmp_path,
        ipod_mount=tmp_path / "ipod-not-mounted",
        auto_scan=False,
    )


def test_sync_raises_library_not_found_when_music_dir_missing(tmp_path):
    """Sync bails fast with LibraryNotFoundError when the music share isn't
    mounted — no per-file timeout, no iPod access attempted."""
    cfg = _cfg_with_music(tmp_path)
    db = Database(cfg.db_path)
    db.save_playlist("p", [])

    # Make the music dir disappear (simulates unmounted SMB share).
    cfg.music_dir.rmdir()

    with pytest.raises(LibraryNotFoundError) as exc_info:
        sync_playlist(cfg, db, "p")
    assert "isn't mounted" in str(exc_info.value)
    db.close()


def test_sync_raises_missing_tracks_when_playlist_has_dead_refs(tmp_path):
    """Sync bails with MissingTracksError when the playlist references files
    flagged missing on disk. Error carries the offending tracks."""
    cfg = _cfg_with_music(tmp_path)
    db = Database(cfg.db_path)

    # Two indexed tracks; one has its file flagged missing.
    sample = {
        "path": "/music/A.mp3",
        "title": "A",
        "artist": "Artist",
        "album": "Album",
        "album_artist": "Artist",
        "duration_seconds": 180.0,
        "format": "mp3",
        "file_size": 1_000_000,
        "has_art": 0,
    }
    db.upsert_track(sample)
    db.upsert_track({**sample, "path": "/music/B.mp3", "title": "B"})
    db.commit()
    db.save_playlist("p", ["/music/A.mp3", "/music/B.mp3"])
    db.mark_missing({"/music/A.mp3"})

    # Hand-craft a Diff that includes the missing path in to_add.
    missing_track = dict(
        db.conn.execute(
            "SELECT * FROM tracks WHERE path = ?", ("/music/A.mp3",)
        ).fetchone()
    )
    diff = Diff(playlist="p", to_add=[missing_track])

    with pytest.raises(MissingTracksError) as exc_info:
        sync_playlist(cfg, db, "p", diff=diff)

    assert len(exc_info.value.missing_tracks) == 1
    assert exc_info.value.missing_tracks[0]["path"] == "/music/A.mp3"
    assert "heal" in str(exc_info.value).lower()
    db.close()


def test_sync_skips_missing_check_when_dead_track_is_already_on_ipod(tmp_path):
    """If a dead-ref track is already on the iPod, sync doesn't need its
    source file. Only block when the dead ref is in the to_add set.

    We pass an empty `to_add` Diff to simulate "everything's already on
    the iPod"; the call will then fail downstream (no real iPod), but
    importantly it should NOT raise MissingTracksError on the way there.
    """
    cfg = _cfg_with_music(tmp_path)
    db = Database(cfg.db_path)

    sample = {
        "path": "/music/A.mp3",
        "title": "A",
        "artist": "Artist",
        "album": "Album",
        "album_artist": "Artist",
        "duration_seconds": 180.0,
        "format": "mp3",
        "file_size": 1_000_000,
        "has_art": 0,
    }
    db.upsert_track(sample)
    db.commit()
    db.save_playlist("p", ["/music/A.mp3"])
    db.mark_missing({"/music/A.mp3"})

    diff = Diff(playlist="p", to_add=[])

    # Some downstream error will fire (no iPod, no disk_usage on a fake
    # path) — we just assert it's NOT MissingTracksError.
    with pytest.raises(Exception) as exc_info:
        sync_playlist(cfg, db, "p", diff=diff)
    assert not isinstance(exc_info.value, MissingTracksError)
    db.close()
