"""Tests for Phase 2 of the Apple Music integration — catalog matching
(ISRC + fuzzy + library) and the match/push actions. Network calls are
monkeypatched at applemusic's `_request_json` boundary; SQLite is
real (tmp-path), exercising the song_map cache.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clickwheel import applemusic as _am
from clickwheel.actions import (
    AppleMusicNoMatchesError,
    AppleMusicNotConfiguredError,
    match_playlist_to_apple_music,
    sync_playlist_to_apple_music,
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
    p = tmp_path / "AuthKey_TEST.p8"
    p.write_bytes(pem)
    return p


@pytest.fixture
def am_cfg(tmp_path: Path, _gen_p8: Path) -> Config:
    """Apple-Music-enabled config with a synthetic .p8 and a user token
    so push paths can run."""
    return Config(
        music_dir=tmp_path / "music",
        project_dir=tmp_path,
        apple_music_enabled=True,
        apple_music_storefront="us",
        apple_music_key_id="K",
        apple_music_team_id="T",
        apple_music_key_file=str(_gen_p8),
        apple_music_user_token="user_tok",
    )


@pytest.fixture
def db_with_playlist(tmp_path: Path) -> Database:
    """SQLite database pre-populated with two tracks and a playlist
    referencing both. Track paths are synthetic — read_isrc returns
    None for them since they don't exist on disk."""
    db = Database(tmp_path / "test.db")
    track = {
        "title": "T",
        "artist": "A",
        "album": "B",
        "album_artist": "A",
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
        "art_width": None,
        "art_height": None,
    }
    db.upsert_track(
        {**track, "path": "/music/A/01.mp3", "title": "Smells Like Teen Spirit"}
    )
    db.upsert_track({**track, "path": "/music/A/02.mp3", "title": "In Bloom"})
    db.commit()
    db.save_playlist("Test", ["/music/A/01.mp3", "/music/A/02.mp3"], "desc")
    return db


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def test_score_handles_empty():
    assert _am._score("", "anything") == 0.0
    assert _am._score("anything", "") == 0.0
    assert _am._score("", "") == 0.0


def test_score_exact_match():
    assert _am._score("Nirvana", "nirvana") == 1.0


def test_composite_confidence_weights_title_highest():
    """Title is the primary signal; same artist + different title
    scores lower than same title + different artist."""
    same_artist_diff_title = _am._composite_confidence(
        "Nirvana",
        "Smells Like Teen Spirit",
        "",
        "Nirvana",
        "Polly",
        "",
    )
    same_title_diff_artist = _am._composite_confidence(
        "Nirvana",
        "Smells Like Teen Spirit",
        "",
        "Weird Al",
        "Smells Like Teen Spirit",
        "",
    )
    assert same_title_diff_artist > same_artist_diff_title


def test_normalize_isrc_strips_and_uppercases():
    assert _am._normalize_isrc(" us-dw1-94-00251 ") == "USDW1940025 1".replace(" ", "")
    assert _am._normalize_isrc("usdw19400251") == "USDW19400251"


# ---------------------------------------------------------------------------
# catalog_by_isrc / catalog_fuzzy_search / library_search
# ---------------------------------------------------------------------------


def test_catalog_by_isrc_hit(monkeypatch):
    def _fake(url, headers, **kw):
        assert "filter%5Bisrc%5D=USDW19400251" in url
        return {
            "data": [
                {
                    "id": "1440783625",
                    "attributes": {
                        "artistName": "Nirvana",
                        "name": "Smells Like Teen Spirit",
                        "albumName": "Nevermind",
                        "isrc": "USDW19400251",
                    },
                }
            ]
        }

    monkeypatch.setattr(_am, "_request_json", _fake)
    hit = _am.catalog_by_isrc("dev", "USDW19400251", "us")
    assert hit is not None
    assert hit.song_id == "1440783625"
    assert hit.kind == "catalog"
    assert hit.confidence == 1.0
    assert hit.matched_artist == "Nirvana"


def test_catalog_by_isrc_miss(monkeypatch):
    monkeypatch.setattr(_am, "_request_json", lambda url, headers, **kw: {"data": []})
    assert _am.catalog_by_isrc("dev", "FAKE12345678", "us") is None


def test_catalog_fuzzy_search_picks_best_score(monkeypatch):
    """Three candidates returned; matcher picks the one with the highest
    composite score."""

    def _fake(url, headers, **kw):
        return {
            "results": {
                "songs": {
                    "data": [
                        {
                            "id": "1",
                            "attributes": {
                                "artistName": "Weird Al Yankovic",
                                "name": "Smells Like Nirvana",
                                "albumName": "Off the Deep End",
                            },
                        },
                        {
                            "id": "2",
                            "attributes": {
                                "artistName": "Nirvana",
                                "name": "Smells Like Teen Spirit",
                                "albumName": "Nevermind",
                            },
                        },
                        {
                            "id": "3",
                            "attributes": {
                                "artistName": "Nirvana",
                                "name": "Lithium",
                                "albumName": "Nevermind",
                            },
                        },
                    ]
                }
            }
        }

    monkeypatch.setattr(_am, "_request_json", _fake)
    hit = _am.catalog_fuzzy_search(
        "dev", "Nirvana", "Smells Like Teen Spirit", "Nevermind", "us"
    )
    assert hit is not None
    assert hit.song_id == "2"
    assert hit.kind == "catalog"
    assert hit.confidence > 0.9


def test_catalog_fuzzy_search_below_threshold_returns_none(monkeypatch):
    """All candidates score below MATCH_MIN_CONFIDENCE → None."""

    def _fake(url, headers, **kw):
        return {
            "results": {
                "songs": {
                    "data": [
                        {
                            "id": "1",
                            "attributes": {
                                "artistName": "Different Artist",
                                "name": "Different Title",
                                "albumName": "Different Album",
                            },
                        }
                    ]
                }
            }
        }

    monkeypatch.setattr(_am, "_request_json", _fake)
    assert (
        _am.catalog_fuzzy_search("dev", "Nirvana", "Lithium", "Nevermind", "us") is None
    )


def test_library_search_returns_library_songs(monkeypatch):
    def _fake(url, headers, **kw):
        assert "/me/library/search" in url
        return {
            "results": {
                "library-songs": {
                    "data": [
                        {
                            "id": "i.abc123",
                            "attributes": {
                                "artistName": "Nirvana",
                                "name": "Smells Like Teen Spirit",
                                "albumName": "Nevermind",
                            },
                        }
                    ]
                }
            }
        }

    monkeypatch.setattr(_am, "_request_json", _fake)
    hit = _am.library_search(
        "dev", "user", "Nirvana", "Smells Like Teen Spirit", "Nevermind"
    )
    assert hit is not None
    assert hit.kind == "library"
    assert hit.song_id == "i.abc123"


# ---------------------------------------------------------------------------
# match_track orchestrator
# ---------------------------------------------------------------------------


def test_match_track_isrc_short_circuit(monkeypatch):
    """When ISRC hits, fuzzy and library aren't called."""

    calls = []

    def _fake(url, headers, **kw):
        calls.append(url)
        if "filter%5Bisrc" in url:
            return {
                "data": [
                    {
                        "id": "ISRC_HIT",
                        "attributes": {
                            "artistName": "X",
                            "name": "Y",
                            "albumName": "Z",
                        },
                    }
                ]
            }
        raise AssertionError(f"unexpected call: {url}")

    monkeypatch.setattr(_am, "_request_json", _fake)
    hit = _am.match_track(
        dev_token="dev",
        user_token="user",
        storefront="us",
        artist="X",
        title="Y",
        album="Z",
        isrc="ABC123",
        icml=True,
    )
    assert hit is not None
    assert hit.song_id == "ISRC_HIT"
    assert len(calls) == 1  # only the ISRC call


def test_match_track_fuzzy_fallback(monkeypatch):
    """No ISRC → fuzzy is the next step. Library is only consulted if
    catalog comes back empty."""

    def _fake(url, headers, **kw):
        if "/catalog/" in url and "search" in url:
            return {
                "results": {
                    "songs": {
                        "data": [
                            {
                                "id": "FUZZY_HIT",
                                "attributes": {
                                    "artistName": "Nirvana",
                                    "name": "Lithium",
                                    "albumName": "Nevermind",
                                },
                            }
                        ]
                    }
                }
            }
        raise AssertionError(f"unexpected call: {url}")

    monkeypatch.setattr(_am, "_request_json", _fake)
    hit = _am.match_track(
        dev_token="dev",
        user_token="user",
        storefront="us",
        artist="Nirvana",
        title="Lithium",
        album="Nevermind",
        isrc=None,
        icml=True,
    )
    assert hit is not None
    assert hit.song_id == "FUZZY_HIT"


def test_match_track_library_only_when_icml(monkeypatch):
    """ICML off → library_search isn't invoked even if catalog comes back
    empty."""

    def _fake(url, headers, **kw):
        if "/catalog/" in url:
            return {"results": {"songs": {"data": []}}}
        if "/me/library/search" in url:
            raise AssertionError("library should not be called when icml is False")
        return {}

    monkeypatch.setattr(_am, "_request_json", _fake)
    assert (
        _am.match_track(
            dev_token="dev",
            user_token="user",
            storefront="us",
            artist="X",
            title="Y",
            isrc=None,
            icml=False,
        )
        is None
    )


# ---------------------------------------------------------------------------
# Database song_map cache
# ---------------------------------------------------------------------------


def test_song_map_upsert_and_get(tmp_path: Path):
    db = Database(tmp_path / "t.db")
    assert db.get_apple_music_song("/p/01.mp3") is None
    db.upsert_apple_music_song("/p/01.mp3", "1440783625", "catalog", 1.0, "us")
    row = db.get_apple_music_song("/p/01.mp3")
    assert row is not None
    assert row["song_id"] == "1440783625"
    assert row["kind"] == "catalog"
    assert row["confidence"] == 1.0
    # Replace should overwrite, not duplicate
    db.upsert_apple_music_song("/p/01.mp3", "999", "catalog", 0.9, "us")
    row = db.get_apple_music_song("/p/01.mp3")
    assert row["song_id"] == "999"
    db.clear_apple_music_song("/p/01.mp3")
    assert db.get_apple_music_song("/p/01.mp3") is None


# ---------------------------------------------------------------------------
# match_playlist_to_apple_music
# ---------------------------------------------------------------------------


def test_match_playlist_populates_cache(
    am_cfg: Config, db_with_playlist: Database, monkeypatch
):
    """Happy path: both tracks fuzzy-match, song_map cache fills,
    second call hits cache (no network)."""

    def _fake_catalog(url, headers, **kw):
        if "/catalog/" in url and "search" in url:
            # Echo back the title in the term so the match scores high
            term = url.split("term=")[1].split("&")[0].replace("%20", " ")
            return {
                "results": {
                    "songs": {
                        "data": [
                            {
                                "id": f"cat_{abs(hash(term)) % 10000}",
                                "attributes": {
                                    "artistName": "A",
                                    "name": term.split(" ", 1)[1]
                                    if " " in term
                                    else term,
                                    "albumName": "B",
                                },
                            }
                        ]
                    }
                }
            }
        if "/me/library/songs" in url:
            return {"data": []}  # iCML probe — return ON
        if "/me/library/search" in url:
            return {"results": {"library-songs": {"data": []}}}
        raise AssertionError(f"unexpected: {url}")

    monkeypatch.setattr(_am, "_request_json", _fake_catalog)
    result = match_playlist_to_apple_music(am_cfg, db_with_playlist, "Test")
    assert result.total == 2
    assert result.matched + result.low_confidence + result.unmatched == 2
    # All matches should be cached now
    assert db_with_playlist.get_apple_music_song("/music/A/01.mp3") is not None

    # Second call with same fake; expect cache to short-circuit (we
    # don't enforce zero network calls because the iCML probe still
    # fires, but cached rows should report `cached=True`).
    result2 = match_playlist_to_apple_music(am_cfg, db_with_playlist, "Test")
    cached_rows = [t for t in result2.tracks if t.cached]
    assert len(cached_rows) == 2


def test_match_playlist_refresh_ignores_cache(
    am_cfg: Config, db_with_playlist: Database, monkeypatch
):
    """`refresh=True` re-runs matching even when the cache has entries."""
    # Pre-populate cache
    db_with_playlist.upsert_apple_music_song(
        "/music/A/01.mp3", "OLD_ID", "catalog", 0.99, "us"
    )

    fresh_calls = []

    def _fake(url, headers, **kw):
        fresh_calls.append(url)
        if "/catalog/" in url and "search" in url:
            return {
                "results": {
                    "songs": {
                        "data": [
                            {
                                "id": "NEW_ID",
                                "attributes": {
                                    "artistName": "A",
                                    "name": "Smells Like Teen Spirit",
                                    "albumName": "B",
                                },
                            }
                        ]
                    }
                }
            }
        if "/me/library/songs" in url:
            return {"data": []}
        return {"results": {"library-songs": {"data": []}}}

    monkeypatch.setattr(_am, "_request_json", _fake)
    result = match_playlist_to_apple_music(
        am_cfg, db_with_playlist, "Test", refresh=True
    )
    # No cached rows when refresh=True
    assert all(not t.cached for t in result.tracks)


# ---------------------------------------------------------------------------
# sync_playlist_to_apple_music
# ---------------------------------------------------------------------------


def test_sync_playlist_pushes_matched_tracks(
    am_cfg: Config, db_with_playlist: Database, monkeypatch
):
    """End-to-end push: matcher returns hits for both tracks, push
    POSTs them and returns the new playlist's id."""

    posted_payloads: list[dict] = []

    def _fake(url, headers, method="GET", data=None, **kw):
        if "/catalog/" in url and "search" in url:
            return {
                "results": {
                    "songs": {
                        "data": [
                            {
                                "id": "cat_1",
                                "attributes": {
                                    "artistName": "A",
                                    "name": "Smells Like Teen Spirit",
                                    "albumName": "B",
                                },
                            }
                        ]
                    }
                }
            }
        if "/me/library/songs" in url:
            return {"data": []}
        if "/me/library/search" in url:
            return {"results": {"library-songs": {"data": []}}}
        if "/me/library/playlists" in url and method == "POST":
            import json

            posted_payloads.append(json.loads(data.decode("utf-8")))
            return {"data": [{"id": "p.new123", "type": "library-playlists"}]}
        raise AssertionError(f"unexpected: {url}  method={method}")

    monkeypatch.setattr(_am, "_request_json", _fake)
    result = sync_playlist_to_apple_music(
        am_cfg, db_with_playlist, "Test", min_confidence=0.5
    )
    assert result.pushed > 0
    assert result.apple_music_playlist_id == "p.new123"
    assert len(posted_payloads) == 1
    payload = posted_payloads[0]
    assert payload["attributes"]["name"] == "Test"
    assert payload["attributes"]["description"] == "desc"


def test_sync_playlist_no_matches_raises(
    am_cfg: Config, db_with_playlist: Database, monkeypatch
):
    """Zero matches at threshold → AppleMusicNoMatchesError, no POST."""

    posted = []

    def _fake(url, headers, method="GET", data=None, **kw):
        if "/catalog/" in url and "search" in url:
            # all candidates score below threshold
            return {
                "results": {
                    "songs": {
                        "data": [
                            {
                                "id": "no_match",
                                "attributes": {
                                    "artistName": "Different",
                                    "name": "Wholly Unrelated",
                                    "albumName": "Other",
                                },
                            }
                        ]
                    }
                }
            }
        if "/me/library/songs" in url:
            return {"data": []}
        if "/me/library/search" in url:
            return {"results": {"library-songs": {"data": []}}}
        if "/me/library/playlists" in url and method == "POST":
            posted.append(url)
            return {"data": [{"id": "x"}]}
        raise AssertionError(f"unexpected: {url}")

    monkeypatch.setattr(_am, "_request_json", _fake)
    with pytest.raises(AppleMusicNoMatchesError):
        sync_playlist_to_apple_music(am_cfg, db_with_playlist, "Test")
    assert posted == []  # POST was never reached


def test_sync_playlist_requires_user_token(
    tmp_path: Path, db_with_playlist: Database, _gen_p8: Path
):
    """Without a user token, sync raises AppleMusicNotConfiguredError
    before any matching runs."""
    cfg = Config(
        music_dir=tmp_path / "m",
        project_dir=tmp_path,
        apple_music_enabled=True,
        apple_music_team_id="T",
        apple_music_key_id="K",
        apple_music_key_file=str(_gen_p8),
        # apple_music_user_token intentionally blank
    )
    with pytest.raises(AppleMusicNotConfiguredError):
        sync_playlist_to_apple_music(cfg, db_with_playlist, "Test")
