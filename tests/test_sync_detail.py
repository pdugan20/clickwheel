"""Pure-function tests for the sync-result `detail` subtitle helpers.

These cover the byte-formatter and the "bytes · N albums" composer that
each iPod-write tool calls before pushing into `_sync_state.start()`.
"""

from __future__ import annotations

from clickwheel._sync_detail import detail_for_tracks, fmt_bytes


def test_fmt_bytes_gb():
    assert fmt_bytes(1_400_000_000) == "1.3 GB"
    assert fmt_bytes(2 * 1024**3) == "2.0 GB"


def test_fmt_bytes_mb():
    # 145 MB → "145 MB", no decimal
    assert fmt_bytes(152_000_000) == "145 MB"
    assert fmt_bytes(2 * 1024**2) == "2 MB"


def test_fmt_bytes_kb():
    assert fmt_bytes(8 * 1024) == "8 KB"


def test_detail_empty_track_list():
    assert detail_for_tracks([]) == ""


def test_detail_single_album():
    tracks = [
        {"album": "Pinkerton", "file_size": 5_000_000},
        {"album": "Pinkerton", "file_size": 4_500_000},
        {"album": "Pinkerton", "file_size": 5_100_000},
    ]
    detail = detail_for_tracks(tracks)
    assert "·" in detail
    assert "MB" in detail
    assert detail.endswith("1 album")


def test_detail_multiple_albums():
    tracks = [
        {"album": "Pinkerton", "file_size": 5_000_000},
        {"album": "Blue Album", "file_size": 4_500_000},
        {"album": "Maladroit", "file_size": 5_100_000},
    ]
    detail = detail_for_tracks(tracks)
    assert detail.endswith("3 albums")
    assert "MB" in detail


def test_detail_no_album_field():
    """Tracks with missing/null album shouldn't inflate the album count."""
    tracks = [
        {"album": None, "file_size": 5_000_000},
        {"album": "", "file_size": 4_500_000},
        {"album": "Pinkerton", "file_size": 5_100_000},
    ]
    detail = detail_for_tracks(tracks)
    assert detail.endswith("1 album")


def test_detail_bytes_only_when_no_albums():
    tracks = [{"album": None, "file_size": 5_000_000}]
    detail = detail_for_tracks(tracks)
    assert "MB" in detail
    assert "album" not in detail
