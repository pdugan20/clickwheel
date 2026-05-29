"""Tests for Phase 3 of the Apple Music integration — list and pull.
Network calls are monkeypatched at applemusic's `_request_json`
boundary; SQLite is real (tmp-path), exercising the cache + fuzzy
lookups.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clickwheel import applemusic as _am
from clickwheel.actions import (
    AppleMusicNotConfiguredError,
    AppleMusicPlaylistNotFoundError,
    PlaylistAlreadyExistsError,
    list_apple_music_playlists,
    pull_playlist_from_apple_music,
)
from clickwheel.config import Config
from clickwheel.db import Database


@pytest.fixture
def _gen_p8(tmp_path: Path) -> Path:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    p = tmp_path / "AuthKey_PULL.p8"
    p.write_bytes(pem)
    return p


@pytest.fixture
def am_cfg(tmp_path: Path, _gen_p8: Path) -> Config:
    return Config(
        music_dir=tmp_path / "m",
        project_dir=tmp_path,
        apple_music_enabled=True,
        apple_music_storefront="us",
        apple_music_key_id="K",
        apple_music_team_id="T",
        apple_music_key_file=str(_gen_p8),
        apple_music_user_token="user_tok",
    )


@pytest.fixture
def db_with_tracks(tmp_path: Path) -> Database:
    """SQLite with three tracks across two artists; no playlist yet."""
    db = Database(tmp_path / "t.db")
    base = {
        "album_artist": None,
        "genre": "Rock",
        "track_number": 1,
        "disc_number": 1,
        "year": 1991,
        "duration_seconds": 200.0,
        "bitrate": 320000,
        "sample_rate": 44100,
        "format": "mp3",
        "file_size": 5_000_000,
        "has_art": 1,
        "art_width": None,
        "art_height": None,
    }
    db.upsert_track(
        {
            **base,
            "path": "/m/n01.mp3",
            "title": "Smells Like Teen Spirit",
            "artist": "Nirvana",
            "album": "Nevermind",
        }
    )
    db.upsert_track(
        {
            **base,
            "path": "/m/n02.mp3",
            "title": "In Bloom",
            "artist": "Nirvana",
            "album": "Nevermind",
        }
    )
    db.upsert_track(
        {
            **base,
            "path": "/m/pj01.mp3",
            "title": "Alive",
            "artist": "Pearl Jam",
            "album": "Ten",
        }
    )
    db.commit()
    return db


# ---------------------------------------------------------------------------
# Database: reverse song-id lookup + fuzzy
# ---------------------------------------------------------------------------


def test_get_track_path_by_apple_song_id_returns_cached(db_with_tracks: Database):
    db_with_tracks.upsert_apple_music_song(
        "/m/n01.mp3", "1440783625", "catalog", 1.0, "us"
    )
    assert (
        db_with_tracks.get_track_path_by_apple_song_id("1440783625", "us")
        == "/m/n01.mp3"
    )


def test_get_track_path_by_apple_song_id_prefers_higher_confidence(
    db_with_tracks: Database,
):
    """Two paths mapped to the same song_id — the higher-confidence row
    wins."""
    db_with_tracks.upsert_apple_music_song(
        "/m/n01.mp3", "SAME_ID", "catalog", 0.8, "us"
    )
    db_with_tracks.upsert_apple_music_song(
        "/m/n02.mp3", "SAME_ID", "catalog", 0.95, "us"
    )
    assert (
        db_with_tracks.get_track_path_by_apple_song_id("SAME_ID", "us") == "/m/n02.mp3"
    )


def test_get_track_path_by_apple_song_id_storefront_scopes(
    db_with_tracks: Database,
):
    db_with_tracks.upsert_apple_music_song("/m/n01.mp3", "ID_US", "catalog", 1.0, "us")
    db_with_tracks.upsert_apple_music_song("/m/n02.mp3", "ID_US", "catalog", 1.0, "gb")
    assert db_with_tracks.get_track_path_by_apple_song_id("ID_US", "us") == "/m/n01.mp3"
    assert db_with_tracks.get_track_path_by_apple_song_id("ID_US", "gb") == "/m/n02.mp3"


def test_find_track_by_artist_title_case_insensitive(db_with_tracks: Database):
    assert (
        db_with_tracks.find_track_by_artist_title("NIRVANA", "smells like teen spirit")
        == "/m/n01.mp3"
    )


def test_find_track_by_artist_title_album_disambiguates(tmp_path: Path):
    """Same artist+title across two albums; album-aware match picks
    the right one."""
    db = Database(tmp_path / "t.db")
    base = {
        "album_artist": None,
        "genre": None,
        "track_number": 1,
        "disc_number": 1,
        "year": 1991,
        "duration_seconds": 200.0,
        "bitrate": 320000,
        "sample_rate": 44100,
        "format": "mp3",
        "file_size": 1000,
        "has_art": 0,
        "art_width": None,
        "art_height": None,
    }
    db.upsert_track(
        {
            **base,
            "path": "/a/studio.mp3",
            "title": "Alive",
            "artist": "Pearl Jam",
            "album": "Ten",
        }
    )
    db.upsert_track(
        {
            **base,
            "path": "/a/unplugged.mp3",
            "title": "Alive",
            "artist": "Pearl Jam",
            "album": "MTV Unplugged",
        }
    )
    db.commit()
    assert db.find_track_by_artist_title("Pearl Jam", "Alive", "Ten") == "/a/studio.mp3"
    assert (
        db.find_track_by_artist_title("Pearl Jam", "Alive", "MTV Unplugged")
        == "/a/unplugged.mp3"
    )


def test_find_track_by_artist_title_returns_none_when_missing(db_with_tracks: Database):
    assert (
        db_with_tracks.find_track_by_artist_title("Sleater-Kinney", "Dig Me Out")
        is None
    )


def test_fuzzy_find_track_matches_close_title(db_with_tracks: Database):
    """Apple's catalog calls it 'Heart-Shaped Box' but local file is
    'Heart Shaped Box'. Fuzzy should still find it once added."""
    base = {
        "album_artist": None,
        "genre": None,
        "track_number": 1,
        "disc_number": 1,
        "year": 1993,
        "duration_seconds": 200.0,
        "bitrate": 320000,
        "sample_rate": 44100,
        "format": "mp3",
        "file_size": 1000,
        "has_art": 0,
        "art_width": None,
        "art_height": None,
    }
    db_with_tracks.upsert_track(
        {
            **base,
            "path": "/m/iu03.mp3",
            "title": "Heart Shaped Box",
            "artist": "Nirvana",
            "album": "In Utero",
        }
    )
    db_with_tracks.commit()
    path, conf = db_with_tracks.fuzzy_find_track(
        "Nirvana", "Heart-Shaped Box", "In Utero"
    )
    assert path == "/m/iu03.mp3"
    assert conf > 0.9


def test_fuzzy_find_track_below_threshold_returns_none(db_with_tracks: Database):
    path, conf = db_with_tracks.fuzzy_find_track("Sleater-Kinney", "Dig Me Out")
    assert path is None
    assert conf == 0.0


# ---------------------------------------------------------------------------
# applemusic.py: list_user_playlists / read_user_playlist_tracks
# ---------------------------------------------------------------------------


def test_list_user_playlists_pages(monkeypatch):
    calls = []

    def _fake(url, headers, **kw):
        calls.append(url)
        # First page: 2 items + next cursor; second page: 1 item, no next.
        if "offset=0" in url:
            return {
                "data": [
                    {
                        "id": "p.aaa",
                        "attributes": {"name": "A", "trackCount": 5, "canEdit": True},
                    },
                    {
                        "id": "p.bbb",
                        "attributes": {
                            "name": "B",
                            "trackCount": 0,
                            "canEdit": False,
                            "description": {"standard": "desc"},
                        },
                    },
                ],
                "next": "/v1/me/library/playlists?offset=2",
            }
        if "offset=2" in url:
            return {
                "data": [{"id": "p.ccc", "attributes": {"name": "C", "trackCount": 1}}]
            }
        raise AssertionError(url)

    monkeypatch.setattr(_am, "_request_json", _fake)
    out = _am.list_user_playlists("dev", "user")
    assert [p.name for p in out] == ["A", "B", "C"]
    assert out[1].description == "desc"
    assert out[1].can_edit is False
    # When `trackCount` is in the payload, we surface the int (even 0).
    assert out[0].track_count == 5
    assert out[1].track_count == 0
    assert out[2].track_count == 1


def test_list_user_playlists_track_count_absent(monkeypatch):
    """Apple's listing endpoint commonly omits `trackCount` entirely —
    we surface that as None rather than a misleading 0. (The per-
    playlist endpoint is the authoritative source for the count.)"""

    def _fake(url, headers, **kw):
        return {
            "data": [{"id": "p.x", "attributes": {"name": "no count", "canEdit": True}}]
        }

    monkeypatch.setattr(_am, "_request_json", _fake)
    out = _am.list_user_playlists("dev", "user")
    assert len(out) == 1
    assert out[0].track_count is None


def test_read_user_playlist_tracks_prefers_catalog_id(monkeypatch):
    """When a track has playParams.catalogId, return that as song_id
    (kind='catalog'); otherwise the row's id is the library id."""

    def _fake(url, headers, **kw):
        return {
            "data": [
                {
                    "id": "i.libonly1",
                    "attributes": {
                        "artistName": "X",
                        "name": "Y",
                        "albumName": "Z",
                        "playParams": {"id": "i.libonly1"},
                    },
                },
                {
                    "id": "i.libwithcat",
                    "attributes": {
                        "artistName": "X",
                        "name": "Y2",
                        "albumName": "Z",
                        "playParams": {
                            "id": "i.libwithcat",
                            "catalogId": "1440783625",
                        },
                    },
                },
            ]
        }

    monkeypatch.setattr(_am, "_request_json", _fake)
    out = _am.read_user_playlist_tracks("dev", "user", "p.test")
    assert out[0]["song_id"] == "i.libonly1"
    assert out[0]["kind"] == "library"
    assert out[1]["song_id"] == "1440783625"
    assert out[1]["kind"] == "catalog"


# ---------------------------------------------------------------------------
# list_apple_music_playlists (action)
# ---------------------------------------------------------------------------


def test_list_action_requires_user_token(tmp_path: Path, _gen_p8: Path):
    cfg = Config(
        music_dir=tmp_path / "m",
        project_dir=tmp_path,
        apple_music_enabled=True,
        apple_music_team_id="T",
        apple_music_key_id="K",
        apple_music_key_file=str(_gen_p8),
    )
    with pytest.raises(AppleMusicNotConfiguredError):
        list_apple_music_playlists(cfg)


def test_list_action_passes_summaries(am_cfg: Config, monkeypatch):
    monkeypatch.setattr(
        _am,
        "_request_json",
        lambda url, headers, **kw: {
            "data": [
                {
                    "id": "p.x",
                    "attributes": {"name": "MyMix", "trackCount": 3, "canEdit": True},
                },
            ]
        },
    )
    out = list_apple_music_playlists(am_cfg)
    assert len(out) == 1
    assert out[0].name == "MyMix"
    assert out[0].playlist_id == "p.x"


# ---------------------------------------------------------------------------
# pull_playlist_from_apple_music (action)
# ---------------------------------------------------------------------------


def test_pull_happy_path_uses_cache_then_exact(
    am_cfg: Config, db_with_tracks: Database, monkeypatch
):
    # Seed cache for one track so we exercise the cache path:
    db_with_tracks.upsert_apple_music_song(
        "/m/n01.mp3", "cat_SLTS", "catalog", 1.0, "us"
    )

    def _fake(url, headers, method="GET", **kw):
        if "/me/library/playlists?" in url:
            return {
                "data": [
                    {
                        "id": "p.target",
                        "attributes": {
                            "name": "Pull Me",
                            "trackCount": 2,
                            "canEdit": True,
                            "description": {"standard": "desc"},
                        },
                    },
                ]
            }
        if "/me/library/playlists/p.target/tracks" in url:
            return {
                "data": [
                    {
                        "id": "i.aaa",
                        "attributes": {
                            "artistName": "Nirvana",
                            "name": "Smells Like Teen Spirit",
                            "albumName": "Nevermind",
                            "playParams": {"catalogId": "cat_SLTS"},
                        },
                    },
                    {
                        "id": "i.bbb",
                        "attributes": {
                            "artistName": "Pearl Jam",
                            "name": "Alive",
                            "albumName": "Ten",
                            "playParams": {"catalogId": "cat_alive"},
                        },
                    },
                ]
            }
        raise AssertionError(url)

    monkeypatch.setattr(_am, "_request_json", _fake)
    result = pull_playlist_from_apple_music(am_cfg, db_with_tracks, "Pull Me")
    assert result.matched == 2
    assert result.unmatched == 0
    # Cache row resolved via 'cache'; the other via 'exact' metadata.
    reasons = {t.reason for t in result.tracks}
    assert "cache" in reasons
    assert "exact" in reasons
    # Local playlist should now exist with both tracks.
    saved = [
        r["path"]
        for r in db_with_tracks.conn.execute(
            "SELECT t.path FROM tracks t "
            "JOIN playlist_tracks pt ON t.id = pt.track_id "
            "JOIN playlists p ON pt.playlist_id = p.id "
            "WHERE p.name = 'Pull Me' ORDER BY pt.position"
        )
    ]
    assert saved == ["/m/n01.mp3", "/m/pj01.mp3"]


def test_pull_fuzzy_fallback_when_exact_fails(
    am_cfg: Config, db_with_tracks: Database, monkeypatch
):
    """Apple says 'Heart-Shaped Box' but local file is 'Heart Shaped Box'.
    Exact lookup misses; fuzzy fallback catches it."""
    base = {
        "album_artist": None,
        "genre": None,
        "track_number": 1,
        "disc_number": 1,
        "year": 1993,
        "duration_seconds": 200.0,
        "bitrate": 320000,
        "sample_rate": 44100,
        "format": "mp3",
        "file_size": 1000,
        "has_art": 0,
        "art_width": None,
        "art_height": None,
    }
    db_with_tracks.upsert_track(
        {
            **base,
            "path": "/m/iu03.mp3",
            "title": "Heart Shaped Box",
            "artist": "Nirvana",
            "album": "In Utero",
        }
    )
    db_with_tracks.commit()

    def _fake(url, headers, **kw):
        if "/me/library/playlists?" in url:
            return {
                "data": [
                    {"id": "p.x", "attributes": {"name": "Mixed", "trackCount": 1}}
                ]
            }
        if "/me/library/playlists/p.x/tracks" in url:
            return {
                "data": [
                    {
                        "id": "i.iu03",
                        "attributes": {
                            "artistName": "Nirvana",
                            "name": "Heart-Shaped Box",
                            "albumName": "In Utero",
                            "playParams": {"catalogId": "cat_hsb"},
                        },
                    }
                ]
            }
        raise AssertionError(url)

    monkeypatch.setattr(_am, "_request_json", _fake)
    result = pull_playlist_from_apple_music(am_cfg, db_with_tracks, "Mixed")
    assert result.matched == 1
    assert result.tracks[0].reason == "fuzzy"


def test_pull_reports_unmatched(am_cfg: Config, db_with_tracks: Database, monkeypatch):
    """An Apple Music track with no local equivalent ends up unmatched."""

    def _fake(url, headers, **kw):
        if "/me/library/playlists?" in url:
            return {
                "data": [
                    {"id": "p.x", "attributes": {"name": "Ghost", "trackCount": 1}}
                ]
            }
        if "/me/library/playlists/p.x/tracks" in url:
            return {
                "data": [
                    {
                        "id": "i.unknown",
                        "attributes": {
                            "artistName": "Sleater-Kinney",
                            "name": "Dig Me Out",
                            "albumName": "Dig Me Out",
                            "playParams": {"catalogId": "cat_dmo"},
                        },
                    }
                ]
            }
        raise AssertionError(url)

    monkeypatch.setattr(_am, "_request_json", _fake)
    result = pull_playlist_from_apple_music(am_cfg, db_with_tracks, "Ghost")
    assert result.matched == 0
    assert result.unmatched == 1
    assert result.tracks[0].reason == "unmatched"


def test_pull_missing_playlist_raises(
    am_cfg: Config, db_with_tracks: Database, monkeypatch
):
    monkeypatch.setattr(
        _am,
        "_request_json",
        lambda url, headers, **kw: {
            "data": [{"id": "p.x", "attributes": {"name": "Other", "trackCount": 0}}]
        },
    )
    with pytest.raises(AppleMusicPlaylistNotFoundError):
        pull_playlist_from_apple_music(am_cfg, db_with_tracks, "DoesNotExist")


def test_pull_refuses_overwrite_by_default(
    am_cfg: Config, db_with_tracks: Database, monkeypatch
):
    db_with_tracks.save_playlist("Existing", [])
    db_with_tracks.commit()

    def _fake(url, headers, **kw):
        if "/me/library/playlists?" in url:
            return {
                "data": [
                    {"id": "p.x", "attributes": {"name": "Existing", "trackCount": 0}}
                ]
            }
        if "/me/library/playlists/p.x/tracks" in url:
            return {"data": []}
        raise AssertionError(url)

    monkeypatch.setattr(_am, "_request_json", _fake)
    with pytest.raises(PlaylistAlreadyExistsError):
        pull_playlist_from_apple_music(am_cfg, db_with_tracks, "Existing")

    # overwrite=True succeeds:
    result = pull_playlist_from_apple_music(
        am_cfg, db_with_tracks, "Existing", overwrite=True
    )
    assert result.replaced is True


def test_pull_backfills_cache(am_cfg: Config, db_with_tracks: Database, monkeypatch):
    """When a pull resolves an Apple track via exact metadata match, the
    song_map cache is updated so subsequent push round-trips skip the
    network."""

    def _fake(url, headers, **kw):
        if "/me/library/playlists?" in url:
            return {
                "data": [
                    {"id": "p.x", "attributes": {"name": "Backfill", "trackCount": 1}}
                ]
            }
        if "/me/library/playlists/p.x/tracks" in url:
            return {
                "data": [
                    {
                        "id": "i.alive",
                        "attributes": {
                            "artistName": "Pearl Jam",
                            "name": "Alive",
                            "albumName": "Ten",
                            "playParams": {"catalogId": "cat_alive"},
                        },
                    }
                ]
            }
        raise AssertionError(url)

    monkeypatch.setattr(_am, "_request_json", _fake)
    assert db_with_tracks.get_apple_music_song("/m/pj01.mp3") is None
    pull_playlist_from_apple_music(am_cfg, db_with_tracks, "Backfill")
    row = db_with_tracks.get_apple_music_song("/m/pj01.mp3")
    assert row is not None
    assert row["song_id"] == "cat_alive"
