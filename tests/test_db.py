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


def test_get_artists_ignores_corrupt_albumartist(tmp_db: Database, sample_track: dict):
    """When album_artist == album, the per-track `artist` should win."""
    corrupt = {
        **sample_track,
        "path": "/music/A/American Idiot/01 American Idiot.mp3",
        "artist": "Green Day",
        "album_artist": "American Idiot",
        "album": "American Idiot",
    }
    tmp_db.upsert_track(corrupt)
    tmp_db.commit()
    names = [a["name"] for a in tmp_db.get_artists()]
    assert names == ["Green Day"]


def test_get_artists_groups_corrupt_with_clean(tmp_db: Database, sample_track: dict):
    """A corrupt track and a clean track by the same artist should
    aggregate into a single row, not two."""
    clean = {
        **sample_track,
        "path": "/music/GreenDay/Dookie/01 Burnout.mp3",
        "artist": "Green Day",
        "album_artist": "Green Day",
        "album": "Dookie",
    }
    corrupt = {
        **sample_track,
        "path": "/music/AmericanIdiot/01 American Idiot.mp3",
        "artist": "Green Day",
        "album_artist": "American Idiot",
        "album": "American Idiot",
    }
    tmp_db.upsert_track(clean)
    tmp_db.upsert_track(corrupt)
    tmp_db.commit()
    artists = tmp_db.get_artists()
    assert len(artists) == 1
    assert artists[0]["name"] == "Green Day"
    assert artists[0]["tracks"] == 2
    assert artists[0]["albums"] == 2


def test_find_corrupt_albumartists(tmp_db: Database, sample_track: dict):
    """Returns rows matching the broken pattern, filtered by path prefix
    and excluding self-titled / null-albumartist / clean rows."""
    rows = [
        # corrupt under /music — should be returned
        {
            **sample_track,
            "path": "/music/Green Day/American Idiot/01.mp3",
            "artist": "Green Day",
            "album_artist": "American Idiot",
            "album": "American Idiot",
        },
        # corrupt under /music — should be returned
        {
            **sample_track,
            "path": "/music/Jay-Z/Reasonable Doubt/01.mp3",
            "artist": "Jay-Z",
            "album_artist": "Reasonable Doubt",
            "album": "Reasonable Doubt",
        },
        # clean — same artist as albumartist — excluded
        {
            **sample_track,
            "path": "/music/Green Day/Dookie/01.mp3",
            "artist": "Green Day",
            "album_artist": "Green Day",
            "album": "Dookie",
        },
        # self-titled — albumartist == album but also == artist — excluded
        {
            **sample_track,
            "path": "/music/Black Sabbath/Black Sabbath/01.mp3",
            "artist": "Black Sabbath",
            "album_artist": "Black Sabbath",
            "album": "Black Sabbath",
        },
        # null albumartist — excluded
        {
            **sample_track,
            "path": "/music/Misc/Unknown/01.mp3",
            "artist": "Somebody",
            "album_artist": None,
            "album": "Unknown",
        },
    ]
    for r in rows:
        tmp_db.upsert_track(r)
    tmp_db.commit()

    found = tmp_db.find_corrupt_albumartists("/music")
    paths = [r["path"] for r in found]
    assert paths == [
        "/music/Green Day/American Idiot/01.mp3",
        "/music/Jay-Z/Reasonable Doubt/01.mp3",
    ]

    # Scoped prefix filters out Jay-Z.
    scoped = tmp_db.find_corrupt_albumartists("/music/Green Day")
    assert [r["path"] for r in scoped] == [
        "/music/Green Day/American Idiot/01.mp3",
    ]


def test_mb_match_roundtrip(tmp_db: Database):
    """save → get → save (overwrite) → get."""
    assert tmp_db.get_mb_match("Artist", "Album") is None
    tmp_db.save_mb_match("Artist", "Album", mbid="abc", year=2001)
    hit = tmp_db.get_mb_match("Artist", "Album")
    assert hit["status"] == "matched"
    assert hit["mbid"] == "abc"
    assert hit["year"] == 2001

    # Overwriting an existing match flips status/year correctly.
    tmp_db.save_mb_match("Artist", "Album", mbid="def", year=2024)
    hit2 = tmp_db.get_mb_match("Artist", "Album")
    assert hit2["mbid"] == "def"
    assert hit2["year"] == 2024


def test_mb_match_negative(tmp_db: Database):
    """An unmatched album persists as status='unmatched'."""
    tmp_db.save_mb_match("Nobody", "Nothing", mbid=None, year=None)
    hit = tmp_db.get_mb_match("Nobody", "Nothing")
    assert hit["status"] == "unmatched"
    assert hit["mbid"] is None


def test_clear_mb_cache(tmp_db: Database):
    tmp_db.save_mb_match("A", "B", mbid="x", year=2000)
    tmp_db.save_mb_match("C", "D", mbid=None, year=None)
    removed = tmp_db.clear_mb_cache()
    assert removed == 2
    assert tmp_db.get_mb_match("A", "B") is None
    assert tmp_db.get_mb_match("C", "D") is None


def test_genre_match_roundtrip(tmp_db: Database):
    assert tmp_db.get_genre_match("A", "B") is None
    tmp_db.save_genre_match("A", "B", genre="Rock")
    hit = tmp_db.get_genre_match("A", "B")
    assert hit["status"] == "matched"
    assert hit["genre"] == "Rock"

    tmp_db.save_genre_match("A", "B", genre="Jazz")
    assert tmp_db.get_genre_match("A", "B")["genre"] == "Jazz"


def test_genre_match_negative(tmp_db: Database):
    tmp_db.save_genre_match("Nobody", "Nothing", genre=None)
    hit = tmp_db.get_genre_match("Nobody", "Nothing")
    assert hit["status"] == "unmatched"
    assert hit["genre"] is None


def test_clear_genre_cache(tmp_db: Database):
    tmp_db.save_genre_match("A", "B", genre="Rock")
    tmp_db.save_genre_match("C", "D", genre=None)
    assert tmp_db.clear_genre_cache() == 2
    assert tmp_db.get_genre_match("A", "B") is None


def test_album_genres_complete(tmp_db: Database, sample_track: dict):
    p1, p2 = "/music/A/Album/01.mp3", "/music/A/Album/02.mp3"
    base = {**sample_track, "artist": "A", "album_artist": "A", "album": "Album"}
    tmp_db.upsert_track({**base, "path": p1, "genre": "Rock"})
    tmp_db.upsert_track({**base, "path": p2, "genre": "Rock"})
    tmp_db.commit()
    assert tmp_db.album_genres_complete([p1, p2]) is True

    tmp_db.upsert_track({**base, "path": p2, "genre": None})
    tmp_db.commit()
    assert tmp_db.album_genres_complete([p1, p2]) is False

    tmp_db.upsert_track({**base, "path": p2, "genre": "  "})  # whitespace only
    tmp_db.commit()
    assert tmp_db.album_genres_complete([p1, p2]) is False


def test_album_metadata_complete(tmp_db: Database, sample_track: dict):
    """True only when every passed path is indexed AND has art AND has year."""
    p1 = "/music/A/Album/01.mp3"
    p2 = "/music/A/Album/02.mp3"
    base = {**sample_track, "album_artist": "A", "artist": "A", "album": "Album"}
    tmp_db.upsert_track({**base, "path": p1, "has_art": 1, "year": 2010})
    tmp_db.upsert_track({**base, "path": p2, "has_art": 1, "year": 2010})
    tmp_db.commit()
    assert tmp_db.album_metadata_complete([p1, p2]) is True

    # One missing art: not complete.
    tmp_db.upsert_track({**base, "path": p2, "has_art": 0, "year": 2010})
    tmp_db.commit()
    assert tmp_db.album_metadata_complete([p1, p2]) is False

    # Year zero counts as missing.
    tmp_db.upsert_track({**base, "path": p2, "has_art": 1, "year": 0})
    tmp_db.commit()
    assert tmp_db.album_metadata_complete([p1, p2]) is False

    # Unknown path → cannot claim completeness.
    assert tmp_db.album_metadata_complete([p1, "/not/indexed.mp3"]) is False


def test_find_corrupt_albumartists_escapes_like_wildcards(
    tmp_db: Database, sample_track: dict
):
    """A `_` in the prefix must be treated literally — without escaping,
    SQLite's LIKE would match any character at that position, sweeping
    in unrelated trees."""
    in_scope = {
        **sample_track,
        "path": "/music/Foo_Bar/Album/01.mp3",
        "artist": "Foo_Bar",
        "album_artist": "Album",
        "album": "Album",
    }
    sibling = {
        **sample_track,
        "path": "/music/FooXBar/Album/01.mp3",
        "artist": "FooXBar",
        "album_artist": "Album",
        "album": "Album",
    }
    tmp_db.upsert_track(in_scope)
    tmp_db.upsert_track(sibling)
    tmp_db.commit()

    found = tmp_db.find_corrupt_albumartists("/music/Foo_Bar")
    paths = [r["path"] for r in found]
    assert paths == ["/music/Foo_Bar/Album/01.mp3"]


def test_find_corrupt_albumartists_excludes_missing(
    tmp_db: Database, sample_track: dict
):
    """A broken-pattern row flagged missing on disk shouldn't surface."""
    tmp_db.upsert_track(
        {
            **sample_track,
            "path": "/music/Green Day/American Idiot/01.mp3",
            "artist": "Green Day",
            "album_artist": "American Idiot",
            "album": "American Idiot",
        }
    )
    tmp_db.commit()
    tmp_db.mark_missing({"/music/Green Day/American Idiot/01.mp3"})

    assert tmp_db.find_corrupt_albumartists("/music") == []


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


# ---------------------------------------------------------------------------
# missing_since contract — see the comment block in db.py.
# Library queries filter missing tracks; playlist-state queries preserve
# them so users can see dead refs and run heal_playlist.
# ---------------------------------------------------------------------------


def test_get_stats_excludes_missing(populated_db: Database):
    """Missing tracks don't pad the playable-library counts."""
    populated_db.mark_missing({"/music/A/Album1/01 T1.mp3"})
    stats = populated_db.get_stats()
    # Was 5 in populated_db; one now flagged missing.
    assert stats["total_tracks"] == 4


def test_get_format_breakdown_excludes_missing(populated_db: Database):
    populated_db.mark_missing({"/music/A/Album1/01 T1.mp3"})
    formats = populated_db.get_format_breakdown()
    mp3 = next(f for f in formats if f["format"] == "mp3")
    assert mp3["count"] == 4


def test_get_artists_excludes_artists_with_all_missing(populated_db: Database):
    """An artist whose every track is flagged missing disappears from
    the picker — we don't want users selecting unplayable music."""
    # ArtistB has 2 tracks in populated_db; mark both missing.
    populated_db.mark_missing(
        {"/music/B/Album2/01 S1.mp3", "/music/B/Album2/02 S2.mp3"}
    )
    artists = populated_db.get_artists()
    names = {a["name"] for a in artists}
    assert "ArtistA" in names
    assert "ArtistB" not in names


def test_get_artists_counts_only_playable(populated_db: Database):
    populated_db.mark_missing({"/music/A/Album1/01 T1.mp3"})
    artists = populated_db.get_artists()
    artist_a = next(a for a in artists if a["name"] == "ArtistA")
    assert artist_a["tracks"] == 2  # was 3 before, one flagged missing


def test_get_albums_by_artist_excludes_albums_with_all_missing(
    populated_db: Database,
):
    populated_db.mark_missing(
        {"/music/B/Album2/01 S1.mp3", "/music/B/Album2/02 S2.mp3"}
    )
    albums = populated_db.get_albums_by_artist("ArtistB")
    assert albums == []


def test_get_tracks_by_album_skips_missing(populated_db: Database):
    populated_db.mark_missing({"/music/A/Album1/01 T1.mp3"})
    tracks = populated_db.get_tracks_by_album("ArtistA", "Album1")
    paths = {t["path"] for t in tracks}
    assert "/music/A/Album1/01 T1.mp3" not in paths
    assert "/music/A/Album1/02 T2.mp3" in paths


def test_add_artist_to_playlist_skips_missing(populated_db: Database):
    """The bug from Phase 5 manual testing: heal removed dead refs, then
    add_artist_to_playlist re-added them because the SELECT didn't filter
    missing_since. Now it does."""
    populated_db.save_playlist("p", [])
    populated_db.mark_missing({"/music/A/Album1/01 T1.mp3"})
    added = populated_db.add_artist_to_playlist("p", "ArtistA")
    # ArtistA had 3 tracks; one is flagged missing → only 2 added.
    assert added == 2
    paths = {t["path"] for t in populated_db.get_playlist("p")}
    assert "/music/A/Album1/01 T1.mp3" not in paths


def test_get_playlist_preserves_dead_refs(populated_db: Database):
    """Inverse of the contract: playlist-state queries DO include dead
    refs so users can see them via `clickwheel playlist <name>` and
    decide to run heal."""
    populated_db.save_playlist(
        "p",
        ["/music/A/Album1/01 T1.mp3", "/music/A/Album1/02 T2.mp3"],
    )
    populated_db.mark_missing({"/music/A/Album1/01 T1.mp3"})
    tracks = populated_db.get_playlist("p")
    paths = {t["path"] for t in tracks}
    assert "/music/A/Album1/01 T1.mp3" in paths
    assert "/music/A/Album1/02 T2.mp3" in paths


def test_list_playlists_includes_dead_refs_in_counts(populated_db: Database):
    """Same contract: list_playlists count reflects what's stored, not
    what's playable."""
    populated_db.save_playlist(
        "p",
        ["/music/A/Album1/01 T1.mp3", "/music/A/Album1/02 T2.mp3"],
    )
    populated_db.mark_missing({"/music/A/Album1/01 T1.mp3"})
    playlists = populated_db.list_playlists()
    p = next(pl for pl in playlists if pl["name"] == "p")
    assert p["tracks"] == 2  # not 1


def test_remove_artist_from_playlist_can_remove_dead_refs(
    populated_db: Database,
):
    """User should be able to remove dead refs by artist (e.g. as part of
    a manual cleanup), so this query also doesn't filter missing."""
    populated_db.save_playlist(
        "p",
        ["/music/A/Album1/01 T1.mp3", "/music/A/Album1/02 T2.mp3"],
    )
    populated_db.mark_missing({"/music/A/Album1/01 T1.mp3"})
    removed = populated_db.remove_artist_from_playlist("p", "ArtistA")
    assert removed == 2
    assert populated_db.get_playlist("p") == []


# ---------------------------------------------------------------------------
# Playlist descriptions
# ---------------------------------------------------------------------------


def test_playlist_description_save_and_get(populated_db: Database):
    populated_db.save_playlist(
        "described", ["/music/A/Album1/01 T1.mp3"], description="late-night picks"
    )
    assert populated_db.get_playlist_description("described") == "late-night picks"


def test_get_playlist_description_unset_is_none(populated_db: Database):
    populated_db.save_playlist("plain", ["/music/A/Album1/01 T1.mp3"])
    assert populated_db.get_playlist_description("plain") is None
    # No such playlist also returns None rather than raising.
    assert populated_db.get_playlist_description("ghost") is None


def test_save_playlist_none_description_preserves_existing(populated_db: Database):
    paths = ["/music/A/Album1/01 T1.mp3"]
    populated_db.save_playlist("p", paths, description="keep me")
    # Re-saving without a description must NOT clobber the existing one.
    populated_db.save_playlist("p", paths)
    assert populated_db.get_playlist_description("p") == "keep me"


def test_set_playlist_description(populated_db: Database):
    populated_db.save_playlist("p", ["/music/A/Album1/01 T1.mp3"])
    assert populated_db.set_playlist_description("p", "new text") is True
    assert populated_db.get_playlist_description("p") == "new text"
    # No such playlist -> False, no error.
    assert populated_db.set_playlist_description("ghost", "x") is False


def test_list_playlists_includes_description(populated_db: Database):
    populated_db.save_playlist("p", ["/music/A/Album1/01 T1.mp3"], description="my mix")
    pl = next(p for p in populated_db.list_playlists() if p["name"] == "p")
    assert pl["description"] == "my mix"
