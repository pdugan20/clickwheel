"""Tests for the auto-scan feature."""

from __future__ import annotations

import time

from clickwheel.actions import scan_library
from clickwheel.autoscan import (
    _max_child_mtime,
    cheap_probe_says_changed,
    maybe_auto_scan,
    should_auto_scan,
)
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

    result = scan_library(cfg, db, full=False)
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

    result1 = scan_library(cfg, db, full=False)
    assert result1.added == 1

    result2 = scan_library(cfg, db, full=False)
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

    scan_library(cfg, db, full=False)

    # Delete the file
    mp3 = list(music_dir_with_mp3.rglob("*.mp3"))[0]
    mp3.unlink()

    result = scan_library(cfg, db, full=False)
    assert result.missing == 1

    db.close()


def test_maybe_auto_scan_skips_when_fresh(tmp_path, music_dir_with_mp3):
    """Auto-scan skips if the last scan was recent AND the probe says
    nothing changed at the top level."""
    cfg = Config(
        music_dir=music_dir_with_mp3,
        project_dir=tmp_path,
        auto_scan_staleness_minutes=5,
    )
    db = Database(tmp_path / "test.db")

    # Both signals say "fresh": recent scan timestamp AND probe baseline
    # matches current state.
    db.set_scan_meta("last_scan_completed", str(time.time()))
    db.set_scan_meta(
        "last_probe_max_child_mtime", str(_max_child_mtime(music_dir_with_mp3))
    )

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


# ---------------------------------------------------------------------------
# Cheap probe + two-tier autoscan strategy (added 2026-05-07)
# ---------------------------------------------------------------------------


def test_max_child_mtime_returns_max(tmp_path):
    """_max_child_mtime returns the max mtime of music_dir + first-level
    children."""
    music = tmp_path / "music"
    music.mkdir()
    (music / "Artist A").mkdir()
    (music / "Artist B").mkdir()

    mt = _max_child_mtime(music)
    assert mt is not None
    # Bumping the mtime of a child increases the result.
    new_dir = music / "Artist C"
    new_dir.mkdir()
    mt2 = _max_child_mtime(music)
    assert mt2 >= mt


def test_max_child_mtime_unreachable_returns_none(tmp_path):
    """Returns None if music_dir doesn't exist."""
    assert _max_child_mtime(tmp_path / "nonexistent") is None


def test_cheap_probe_first_run_returns_true(tmp_path):
    """Without a stored baseline, the probe assumes change so the first
    real scan can establish a baseline."""
    music = tmp_path / "music"
    music.mkdir()
    cfg = Config(music_dir=music, project_dir=tmp_path)
    db = Database(tmp_path / "test.db")
    assert cheap_probe_says_changed(cfg, db) is True
    db.close()


def test_cheap_probe_no_change_returns_false(tmp_path):
    """After storing a baseline, an unchanged dir returns False."""
    music = tmp_path / "music"
    music.mkdir()
    (music / "Artist A").mkdir()
    cfg = Config(music_dir=music, project_dir=tmp_path)
    db = Database(tmp_path / "test.db")

    current = _max_child_mtime(music)
    db.set_scan_meta("last_probe_max_child_mtime", str(current))

    assert cheap_probe_says_changed(cfg, db) is False
    db.close()


def test_cheap_probe_new_artist_returns_true(tmp_path):
    """Adding a new top-level dir bumps music_dir's mtime → probe detects it."""
    music = tmp_path / "music"
    music.mkdir()
    (music / "Artist A").mkdir()
    cfg = Config(music_dir=music, project_dir=tmp_path)
    db = Database(tmp_path / "test.db")

    baseline = _max_child_mtime(music)
    db.set_scan_meta("last_probe_max_child_mtime", str(baseline))

    # Force a noticeable mtime bump (mtime resolution is 1s on some FSs).
    time.sleep(1.1)
    (music / "Artist B").mkdir()

    assert cheap_probe_says_changed(cfg, db) is True
    db.close()


def test_cheap_probe_unreachable_returns_none(tmp_path):
    cfg = Config(music_dir=tmp_path / "nonexistent", project_dir=tmp_path)
    db = Database(tmp_path / "test.db")
    assert cheap_probe_says_changed(cfg, db) is None
    db.close()


def test_should_auto_scan_first_run(tmp_path, music_dir_with_mp3):
    """Never-scanned DB returns ('first_run')."""
    cfg = Config(music_dir=music_dir_with_mp3, project_dir=tmp_path)
    db = Database(tmp_path / "test.db")
    run, reason = should_auto_scan(cfg, db)
    assert run is True
    assert reason == "first_run"
    db.close()


def test_should_auto_scan_share_unavailable(tmp_path):
    cfg = Config(music_dir=tmp_path / "nonexistent", project_dir=tmp_path)
    db = Database(tmp_path / "test.db")
    run, reason = should_auto_scan(cfg, db)
    assert run is False
    assert reason == "share_unavailable"
    db.close()


def test_should_auto_scan_disabled(tmp_path, music_dir_with_mp3):
    cfg = Config(music_dir=music_dir_with_mp3, project_dir=tmp_path, auto_scan=False)
    db = Database(tmp_path / "test.db")
    run, reason = should_auto_scan(cfg, db)
    assert run is False
    assert reason is None
    db.close()


def test_should_auto_scan_falls_back_to_timer(tmp_path, music_dir_with_mp3):
    """Even when probe says 'no change', a stale timer triggers a scan
    so in-place metadata edits eventually get re-read."""
    cfg = Config(
        music_dir=music_dir_with_mp3,
        project_dir=tmp_path,
        auto_scan_staleness_minutes=1,  # stale after 60s for test
    )
    db = Database(tmp_path / "test.db")
    # Probe baseline matches current state (no top-level change).
    db.set_scan_meta(
        "last_probe_max_child_mtime", str(_max_child_mtime(music_dir_with_mp3))
    )
    # Last scan was 2 minutes ago — past the 1-minute threshold.
    db.set_scan_meta("last_scan_completed", str(time.time() - 120))

    run, reason = should_auto_scan(cfg, db)
    assert run is True
    assert reason == "stale"
    db.close()


def test_should_auto_scan_probe_detected_change(tmp_path, music_dir_with_mp3):
    """Probe detecting a top-level change runs a scan even when the
    timer says fresh."""
    cfg = Config(
        music_dir=music_dir_with_mp3,
        project_dir=tmp_path,
        auto_scan_staleness_minutes=1440,
    )
    db = Database(tmp_path / "test.db")
    # Recent scan timestamp — timer says fresh.
    db.set_scan_meta("last_scan_completed", str(time.time()))
    # But the stored probe baseline is from the past, so probe says
    # things changed (current_max > stored).
    db.set_scan_meta("last_probe_max_child_mtime", "0")

    run, reason = should_auto_scan(cfg, db)
    assert run is True
    assert reason == "probe_detected_change"
    db.close()


def test_should_auto_scan_skips_when_fresh_and_unchanged(tmp_path, music_dir_with_mp3):
    """Recent scan + probe says no change → don't scan."""
    cfg = Config(
        music_dir=music_dir_with_mp3,
        project_dir=tmp_path,
        auto_scan_staleness_minutes=1440,
    )
    db = Database(tmp_path / "test.db")
    db.set_scan_meta("last_scan_completed", str(time.time()))
    db.set_scan_meta(
        "last_probe_max_child_mtime", str(_max_child_mtime(music_dir_with_mp3))
    )

    run, reason = should_auto_scan(cfg, db)
    assert run is False
    assert reason is None
    db.close()


def test_scan_library_writes_probe_baseline(tmp_path, music_dir_with_mp3):
    """A successful scan must record the current max-child-mtime so
    subsequent cheap probes have a baseline to compare against."""
    cfg = Config(music_dir=music_dir_with_mp3, project_dir=tmp_path)
    db = Database(tmp_path / "test.db")

    assert db.get_scan_meta("last_probe_max_child_mtime") is None
    scan_library(cfg, db, full=False)
    stored = db.get_scan_meta("last_probe_max_child_mtime")
    assert stored is not None
    assert float(stored) > 0
    db.close()


def test_default_staleness_is_24h():
    """Default staleness should be 24h (1440 min) per the v0.5.x design."""
    from clickwheel.config import DEFAULT_AUTO_SCAN_STALENESS_MINUTES

    assert DEFAULT_AUTO_SCAN_STALENESS_MINUTES == 1440
