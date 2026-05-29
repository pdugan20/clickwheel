"""Tests for scrobble caching and dedup logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from clickwheel.db import Database
from clickwheel.scrobble import (
    PendingScrobble,
    cache_scrobbles,
    get_pending_scrobbles,
)


@pytest.fixture
def scrobble_db(tmp_path: Path) -> Database:
    """Database for scrobble tests."""
    return Database(tmp_path / "scrobble_test.db")


def _make_play(
    artist: str, title: str, ts: int, album: str = "Album"
) -> PendingScrobble:
    return PendingScrobble(
        artist=artist,
        title=title,
        album=album,
        timestamp=ts,
        duration=200,
    )


def test_cache_scrobbles_basic(scrobble_db: Database):
    plays = [
        _make_play("Artist", "Song1", 1000),
        _make_play("Artist", "Song2", 1200),
    ]
    cached = cache_scrobbles(scrobble_db.conn, plays)
    assert cached == 2


def test_cache_scrobbles_dedup(scrobble_db: Database):
    plays = [_make_play("Artist", "Song1", 1000)]
    cache_scrobbles(scrobble_db.conn, plays)
    # Cache same play again
    cached = cache_scrobbles(scrobble_db.conn, plays)
    assert cached == 0


def test_get_pending_scrobbles(scrobble_db: Database):
    plays = [
        _make_play("Artist", "Song1", 1000),
        _make_play("Artist", "Song2", 1200),
    ]
    cache_scrobbles(scrobble_db.conn, plays)
    pending = get_pending_scrobbles(scrobble_db.conn)
    assert len(pending) == 2
    assert pending[0]["artist"] == "Artist"


def test_pending_excludes_submitted(scrobble_db: Database):
    plays = [_make_play("Artist", "Song1", 1000)]
    cache_scrobbles(scrobble_db.conn, plays)
    # Mark as submitted
    scrobble_db.conn.execute(
        "UPDATE scrobble_cache SET submitted = 1 WHERE artist = 'Artist'"
    )
    scrobble_db.conn.commit()
    pending = get_pending_scrobbles(scrobble_db.conn)
    assert len(pending) == 0
