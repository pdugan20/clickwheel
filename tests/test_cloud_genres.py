"""Tests for actions.apply_cloud_genres and the genre_matches cache."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import TALB, TCON, TIT2, TPE1, TPE2

from clickwheel import actions
from clickwheel.db import Database

_MP3_FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413


def _make_mp3(
    path: Path,
    *,
    artist: str = "Artist",
    album: str = "Album",
    albumartist: str | None = None,
    genre: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_MP3_FRAME * 10)
    audio = MutagenFile(str(path))
    audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text=["Track"]))
    audio.tags.add(TPE1(encoding=3, text=[artist]))
    audio.tags.add(TALB(encoding=3, text=[album]))
    if albumartist:
        audio.tags.add(TPE2(encoding=3, text=[albumartist]))
    if genre:
        audio.tags.add(TCON(encoding=3, text=[genre]))
    audio.save()


def _read_genre(path: Path) -> str | None:
    audio = MutagenFile(str(path), easy=True)
    vals = audio.tags.get("genre") if audio and audio.tags else None
    return str(vals[0]) if vals else None


def _track_row(path: Path, *, artist="Artist", album="Album", genre=None) -> dict:
    return {
        "path": str(path),
        "title": "Track",
        "artist": artist,
        "album": album,
        "album_artist": artist,
        "genre": genre,
        "track_number": 1,
        "disc_number": 1,
        "year": 2020,
        "duration_seconds": 1.0,
        "bitrate": 128000,
        "sample_rate": 44100,
        "format": "mp3",
        "file_size": len(_MP3_FRAME) * 10,
        "has_art": 1,
        "art_width": 500,
        "art_height": 500,
    }


# A pylast.Album / pylast.Tag mock just exposing what we use.
@dataclass
class _FakeTag:
    name: str


@dataclass
class _FakeTopItem:
    item: _FakeTag
    weight: int = 100


class _FakeAlbum:
    def __init__(self, tags: list[str]) -> None:
        self._tags = [_FakeTopItem(item=_FakeTag(name=t)) for t in tags]

    def get_top_tags(self, limit: int = 5):
        return self._tags[:limit]


class _FakeNetwork:
    """Stand-in for pylast.LastFMNetwork — returns canned tags per album."""

    def __init__(self, tags_by_album: dict[str, list[str]]) -> None:
        self.calls: list[tuple[str, str]] = []
        self._tags = tags_by_album

    def get_album(self, artist: str, album: str) -> _FakeAlbum:
        self.calls.append((artist, album))
        return _FakeAlbum(self._tags.get(album, []))


def _patch_network(monkeypatch, tags_by_album: dict[str, list[str]]) -> _FakeNetwork:
    fake = _FakeNetwork(tags_by_album)
    monkeypatch.setattr("pylast.LastFMNetwork", lambda **_kw: fake, raising=False)
    monkeypatch.setattr("clickwheel.actions.time.sleep", lambda _s: None)
    return fake


def test_skipped_when_no_api_key(tmp_path: Path, tmp_db: Database):
    """Empty api_key short-circuits before any work."""
    result = actions.apply_cloud_genres(tmp_db, tmp_path, api_key="")
    assert result.skipped_no_credentials is True
    assert result.albums_seen == 0


def test_genre_written_on_cache_miss(tmp_path: Path, tmp_db: Database, monkeypatch):
    album = tmp_path / "Test Album"
    track = album / "01.mp3"
    _make_mp3(track, artist="Artist", album="Test Album")
    tmp_db.upsert_track(_track_row(track, album="Test Album"))
    tmp_db.commit()

    fake = _patch_network(monkeypatch, {"Test Album": ["Rock", "1995", "favorites"]})

    result = actions.apply_cloud_genres(tmp_db, tmp_path, api_key="x")

    assert result.cache_misses == 1
    assert result.cache_hits == 0
    assert result.albums_matched == 1
    assert result.tracks_tagged == 1
    assert _read_genre(track) == "Rock"
    assert fake.calls == [("Artist", "Test Album")]
    # Cache populated for next run.
    cached = tmp_db.get_genre_match("Artist", "Test Album")
    assert cached["status"] == "matched"
    assert cached["genre"] == "Rock"


def test_cache_hit_avoids_network(tmp_path: Path, tmp_db: Database, monkeypatch):
    album = tmp_path / "Cached Album"
    track = album / "01.mp3"
    _make_mp3(track, artist="Artist", album="Cached Album")
    tmp_db.upsert_track(_track_row(track, album="Cached Album"))
    tmp_db.commit()

    tmp_db.save_genre_match("Artist", "Cached Album", genre="Jazz")

    fake = _patch_network(monkeypatch, {})

    result = actions.apply_cloud_genres(tmp_db, tmp_path, api_key="x")

    assert fake.calls == []
    assert result.cache_hits == 1
    assert result.cache_misses == 0
    assert _read_genre(track) == "Jazz"


def test_negative_cache_blocks_re_lookup(tmp_path: Path, tmp_db: Database, monkeypatch):
    album = tmp_path / "Obscure Album"
    track = album / "01.mp3"
    _make_mp3(track, artist="Nobody", album="Obscure Album")
    tmp_db.upsert_track(_track_row(track, artist="Nobody", album="Obscure Album"))
    tmp_db.commit()

    tmp_db.save_genre_match("Nobody", "Obscure Album", genre=None)

    fake = _patch_network(monkeypatch, {})

    result = actions.apply_cloud_genres(tmp_db, tmp_path, api_key="x")

    assert fake.calls == []
    assert result.cache_hits == 1
    assert result.unmatched == ["Nobody — Obscure Album"]
    assert _read_genre(track) is None


def test_per_album_skip_when_all_have_genre(
    tmp_path: Path, tmp_db: Database, monkeypatch
):
    """No MB / Last.fm call when every track already has a genre."""
    album = tmp_path / "Complete Album"
    track = album / "01.mp3"
    _make_mp3(track, artist="Artist", album="Complete Album", genre="Rock")
    tmp_db.upsert_track(_track_row(track, album="Complete Album", genre="Rock"))
    tmp_db.commit()

    fake = _patch_network(monkeypatch, {"Complete Album": ["Jazz"]})

    result = actions.apply_cloud_genres(tmp_db, tmp_path, api_key="x")

    assert fake.calls == []
    assert result.albums_skipped_complete == 1
    assert result.albums_matched == 0
    # Genre untouched.
    assert _read_genre(track) == "Rock"


def test_refresh_bypasses_cache(tmp_path: Path, tmp_db: Database, monkeypatch):
    album = tmp_path / "Stale Cache"
    track = album / "01.mp3"
    _make_mp3(track, artist="Artist", album="Stale Cache")
    tmp_db.upsert_track(_track_row(track, album="Stale Cache"))
    tmp_db.commit()

    tmp_db.save_genre_match("Artist", "Stale Cache", genre="OldGenre")

    fake = _patch_network(monkeypatch, {"Stale Cache": ["FreshGenre"]})

    result = actions.apply_cloud_genres(tmp_db, tmp_path, api_key="x", refresh=True)

    assert fake.calls == [("Artist", "Stale Cache")]
    assert result.cache_misses == 1
    assert _read_genre(track) == "Freshgenre"  # .title() applied
    cached = tmp_db.get_genre_match("Artist", "Stale Cache")
    assert cached["genre"] == "Freshgenre"


def test_junk_tags_skipped(tmp_path: Path, tmp_db: Database, monkeypatch):
    """Years and `favorites`-style tags are skipped; first real tag wins."""
    album = tmp_path / "Album With Junk Tags"
    track = album / "01.mp3"
    _make_mp3(track, artist="Artist", album="Album With Junk Tags")
    tmp_db.upsert_track(_track_row(track, album="Album With Junk Tags"))
    tmp_db.commit()

    _patch_network(
        monkeypatch,
        {"Album With Junk Tags": ["2003", "favorites", "seen live", "Indie"]},
    )

    result = actions.apply_cloud_genres(tmp_db, tmp_path, api_key="x")

    assert result.albums_matched == 1
    assert _read_genre(track) == "Indie"


def test_unmatched_album_cached(tmp_path: Path, tmp_db: Database, monkeypatch):
    """Albums with zero tags return unmatched and persist as such."""
    album = tmp_path / "Tagless Album"
    track = album / "01.mp3"
    _make_mp3(track, artist="Artist", album="Tagless Album")
    tmp_db.upsert_track(_track_row(track, album="Tagless Album"))
    tmp_db.commit()

    _patch_network(monkeypatch, {"Tagless Album": []})

    result = actions.apply_cloud_genres(tmp_db, tmp_path, api_key="x")

    assert result.unmatched == ["Artist — Tagless Album"]
    assert tmp_db.get_genre_match("Artist", "Tagless Album")["status"] == "unmatched"
    assert _read_genre(track) is None


def test_genre_not_overwritten(tmp_path: Path, tmp_db: Database, monkeypatch):
    """If a track has a genre but the album as a whole is incomplete,
    don't overwrite the existing genre."""
    album = tmp_path / "Mixed Album"
    has_genre = album / "01.mp3"
    no_genre = album / "02.mp3"
    _make_mp3(has_genre, artist="Artist", album="Mixed Album", genre="Punk")
    _make_mp3(no_genre, artist="Artist", album="Mixed Album")
    tmp_db.upsert_track(_track_row(has_genre, album="Mixed Album", genre="Punk"))
    no_genre_row = _track_row(no_genre, album="Mixed Album", genre=None)
    no_genre_row["path"] = str(no_genre)
    no_genre_row["track_number"] = 2
    tmp_db.upsert_track(no_genre_row)
    tmp_db.commit()

    _patch_network(monkeypatch, {"Mixed Album": ["Rock"]})

    result = actions.apply_cloud_genres(tmp_db, tmp_path, api_key="x")

    # Album wasn't skipped because not every track had a genre.
    assert result.albums_skipped_complete == 0
    # Only the untagged track got the new genre.
    assert result.tracks_tagged == 1
    assert _read_genre(has_genre) == "Punk"
    assert _read_genre(no_genre) == "Rock"
