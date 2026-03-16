"""Tests for the auto-scan feature."""

from __future__ import annotations

import time

from clickwheel.autoscan import incremental_scan, maybe_auto_scan
from clickwheel.config import Config
from clickwheel.db import Database
from clickwheel.library import scan_file


def test_incremental_scan_finds_new_files(tmp_path, music_dir_with_mp3):
    """Incremental scan picks up new audio files."""
    cfg = Config(
        music_dir=music_dir_with_mp3,
        project_dir=tmp_path,
    )
    db = Database(tmp_path / "test.db")

    result = incremental_scan(cfg, db)
    assert result.added == 1
    assert result.unchanged == 0
    assert result.total == 1

    db.close()


def test_incremental_scan_skips_unchanged(tmp_path, music_dir_with_mp3):
    """Second scan skips files that haven't changed."""
    cfg = Config(
        music_dir=music_dir_with_mp3,
        project_dir=tmp_path,
    )
    db = Database(tmp_path / "test.db")

    result1 = incremental_scan(cfg, db)
    assert result1.added == 1

    result2 = incremental_scan(cfg, db)
    assert result2.added == 0
    assert result2.unchanged == 1

    db.close()


def test_incremental_scan_detects_missing(tmp_path, music_dir_with_mp3):
    """Scan marks files as missing when they disappear from disk."""
    cfg = Config(
        music_dir=music_dir_with_mp3,
        project_dir=tmp_path,
    )
    db = Database(tmp_path / "test.db")

    incremental_scan(cfg, db)

    # Delete the file
    mp3 = list(music_dir_with_mp3.rglob("*.mp3"))[0]
    mp3.unlink()

    result = incremental_scan(cfg, db)
    assert result.missing == 1

    db.close()


def test_maybe_auto_scan_skips_when_fresh(tmp_path, music_dir_with_mp3):
    """Auto-scan skips if the last scan was recent."""
    cfg = Config(
        music_dir=music_dir_with_mp3,
        project_dir=tmp_path,
        auto_scan_staleness_minutes=5,
    )
    db = Database(tmp_path / "test.db")

    # Set last scan to now
    db.set_scan_meta("last_scan_completed", str(time.time()))

    result = maybe_auto_scan(cfg, db)
    assert result is None  # skipped

    db.close()


def test_maybe_auto_scan_runs_when_stale(tmp_path, music_dir_with_mp3):
    """Auto-scan runs if the last scan is old enough."""
    cfg = Config(
        music_dir=music_dir_with_mp3,
        project_dir=tmp_path,
        auto_scan_staleness_minutes=5,
    )
    db = Database(tmp_path / "test.db")

    # Set last scan to 10 minutes ago
    db.set_scan_meta("last_scan_completed", str(time.time() - 600))

    result = maybe_auto_scan(cfg, db)
    assert result is not None
    assert result.added == 1

    db.close()


def test_maybe_auto_scan_disabled(tmp_path, music_dir_with_mp3):
    """Auto-scan respects the auto_scan=False config."""
    cfg = Config(
        music_dir=music_dir_with_mp3,
        project_dir=tmp_path,
        auto_scan=False,
    )
    db = Database(tmp_path / "test.db")

    result = maybe_auto_scan(cfg, db)
    assert result is None

    db.close()


def test_maybe_auto_scan_missing_music_dir(tmp_path):
    """Auto-scan warns and skips when music dir doesn't exist."""
    cfg = Config(
        music_dir=tmp_path / "nonexistent",
        project_dir=tmp_path,
    )
    db = Database(tmp_path / "test.db")

    result = maybe_auto_scan(cfg, db)
    assert result is None

    db.close()


def test_db_mtime_tracking(tmp_path, music_dir_with_mp3):
    """DB stores and retrieves mtime correctly."""
    db = Database(tmp_path / "test.db")
    mp3 = list(music_dir_with_mp3.rglob("*.mp3"))[0]

    track = scan_file(mp3)
    assert track is not None
    assert "mtime" in track

    db.upsert_track(track)
    db.commit()

    db_mtime, db_size = db.get_track_mtime(str(mp3))
    assert db_mtime == track["mtime"]
    assert db_size == track["file_size"]

    db.close()


def test_scan_meta_roundtrip(tmp_db):
    """scan_meta table stores and retrieves values."""
    tmp_db.set_scan_meta("test_key", "test_value")
    assert tmp_db.get_scan_meta("test_key") == "test_value"
    assert tmp_db.get_scan_meta("nonexistent") is None
