"""Tests for database operations."""

from __future__ import annotations

from clickwheel.db import Database


def test_upsert_and_get_stats(tmp_db: Database, sample_track: dict):
    tmp_db.upsert_track(sample_track)
    tmp_db.commit()
    stats = tmp_db.get_stats()
    assert stats["total_tracks"] == 1
    assert stats["artists"] == 1
    assert stats["albums"] == 1
    assert stats["total_bytes"] == 5_000_000


def test_upsert_updates_existing(tmp_db: Database, sample_track: dict):
    tmp_db.upsert_track(sample_track)
    tmp_db.commit()
    sample_track["title"] = "Updated"
    tmp_db.upsert_track(sample_track)
    tmp_db.commit()
    stats = tmp_db.get_stats()
    assert stats["total_tracks"] == 1


def test_clear_tracks(tmp_db: Database, sample_track: dict):
    tmp_db.upsert_track(sample_track)
    tmp_db.commit()
    tmp_db.clear_tracks()
    stats = tmp_db.get_stats()
    assert stats["total_tracks"] == 0


def test_get_format_breakdown(tmp_db: Database, sample_track: dict):
    tmp_db.upsert_track(sample_track)
    tmp_db.commit()
    formats = tmp_db.get_format_breakdown()
    assert len(formats) == 1
    assert formats[0]["format"] == "mp3"
    assert formats[0]["count"] == 1


def test_get_artists(populated_db: Database):
    artists = populated_db.get_artists()
    names = [a["name"] for a in artists]
    assert "ArtistA" in names
    assert "ArtistB" in names


def test_get_albums_by_artist(populated_db: Database):
    albums = populated_db.get_albums_by_artist("ArtistA")
    assert len(albums) == 1
    assert albums[0]["album"] == "Album1"
    assert albums[0]["tracks"] == 3


def test_get_tracks_by_album(populated_db: Database):
    tracks = populated_db.get_tracks_by_album("ArtistA", "Album1")
    assert len(tracks) == 3
    assert tracks[0]["track_number"] == 1


def test_save_and_get_playlist(populated_db: Database):
    paths = [
        "/music/A/Album1/01 T1.mp3",
        "/music/A/Album1/02 T2.mp3",
    ]
    populated_db.save_playlist("test", paths)
    tracks = populated_db.get_playlist("test")
    assert len(tracks) == 2
    assert tracks[0]["title"] == "T1"


def test_list_playlists(populated_db: Database):
    populated_db.save_playlist("pl1", ["/music/A/Album1/01 T1.mp3"])
    populated_db.save_playlist("pl2", ["/music/B/Album2/01 S1.mp3"])
    playlists = populated_db.list_playlists()
    assert len(playlists) == 2
    names = [p["name"] for p in playlists]
    assert "pl1" in names
    assert "pl2" in names


def test_delete_playlist(populated_db: Database):
    populated_db.save_playlist("deleteme", ["/music/A/Album1/01 T1.mp3"])
    assert populated_db.delete_playlist("deleteme") is True
    assert populated_db.delete_playlist("deleteme") is False
    assert populated_db.get_playlist("deleteme") == []


def test_delete_nonexistent_playlist(populated_db: Database):
    assert populated_db.delete_playlist("nope") is False


def test_add_artist_to_playlist(populated_db: Database):
    populated_db.save_playlist("test", [])
    added = populated_db.add_artist_to_playlist("test", "ArtistA")
    assert added == 3
    tracks = populated_db.get_playlist("test")
    assert len(tracks) == 3


def test_add_artist_no_duplicates(populated_db: Database):
    populated_db.save_playlist("test", ["/music/A/Album1/01 T1.mp3"])
    added = populated_db.add_artist_to_playlist("test", "ArtistA")
    assert added == 2  # only 2 new, 1 already there


def test_remove_artist_from_playlist(populated_db: Database):
    populated_db.save_playlist(
        "test",
        [
            "/music/A/Album1/01 T1.mp3",
            "/music/A/Album1/02 T2.mp3",
            "/music/B/Album2/01 S1.mp3",
        ],
    )
    removed = populated_db.remove_artist_from_playlist("test", "ArtistA")
    assert removed == 2
    tracks = populated_db.get_playlist("test")
    assert len(tracks) == 1
    assert tracks[0]["artist"] == "ArtistB"


def test_remove_nonexistent_artist(populated_db: Database):
    populated_db.save_playlist("test", ["/music/A/Album1/01 T1.mp3"])
    removed = populated_db.remove_artist_from_playlist("test", "Nobody")
    assert removed == 0


def test_get_playlist_size(populated_db: Database):
    populated_db.save_playlist(
        "test",
        [
            "/music/A/Album1/01 T1.mp3",
            "/music/B/Album2/01 S1.mp3",
        ],
    )
    size = populated_db.get_playlist_size("test")
    assert size == 8_000_000  # 5M + 3M


def test_get_playlist_artists(populated_db: Database):
    populated_db.save_playlist(
        "test",
        [
            "/music/A/Album1/01 T1.mp3",
            "/music/A/Album1/02 T2.mp3",
            "/music/B/Album2/01 S1.mp3",
        ],
    )
    artists = populated_db.get_playlist_artists("test")
    assert len(artists) == 2
    names = {a["name"] for a in artists}
    assert names == {"ArtistA", "ArtistB"}


def test_metadata_quality_stats(tmp_db: Database, sample_track: dict):
    # Track with missing genre
    no_genre = {**sample_track, "path": "/music/x.mp3", "genre": ""}
    tmp_db.upsert_track(sample_track)
    tmp_db.upsert_track(no_genre)
    tmp_db.commit()
    stats = tmp_db.get_stats()
    assert stats["missing_genre"] == 1
    assert stats["with_art"] == 2
