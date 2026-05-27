"""Tests for actions.repair_albumartist."""

from __future__ import annotations

from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import TALB, TIT2, TPE1, TPE2

from clickwheel import actions
from clickwheel.db import Database

_MP3_FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 413


def _make_mp3(
    path: Path,
    *,
    artist: str | None,
    album: str | None,
    albumartist: str | None,
) -> None:
    """Write a minimal MP3 at `path` with the given tags."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_MP3_FRAME * 10)
    audio = MutagenFile(str(path))
    audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text=["Track"]))
    if artist:
        audio.tags.add(TPE1(encoding=3, text=[artist]))
    if album:
        audio.tags.add(TALB(encoding=3, text=[album]))
    if albumartist:
        audio.tags.add(TPE2(encoding=3, text=[albumartist]))
    audio.save()


def _read_albumartist(path: Path) -> str | None:
    audio = MutagenFile(str(path), easy=True)
    vals = audio.tags.get("albumartist") if audio and audio.tags else None
    return str(vals[0]) if vals else None


def _track_row(
    path: Path,
    *,
    artist: str | None,
    album: str | None,
    albumartist: str | None,
) -> dict:
    """Build a minimal track dict for db.upsert_track."""
    return {
        "path": str(path),
        "title": "Track",
        "artist": artist,
        "album": album,
        "album_artist": albumartist,
        "genre": None,
        "track_number": 1,
        "disc_number": 1,
        "year": None,
        "duration_seconds": 1.0,
        "bitrate": 128000,
        "sample_rate": 44100,
        "format": "mp3",
        "file_size": len(_MP3_FRAME) * 10,
        "has_art": 0,
        "art_width": None,
        "art_height": None,
    }


def _seed(db: Database, path: Path, **tags: str | None) -> None:
    """Write the MP3 and add a matching row to the index."""
    _make_mp3(path, **tags)
    db.upsert_track(_track_row(path, **tags))
    db.commit()


def test_repair_rewrites_albumartist_when_equal_to_album(
    tmp_path: Path, tmp_db: Database
):
    p = tmp_path / "01.mp3"
    _seed(
        tmp_db,
        p,
        artist="Green Day",
        album="American Idiot",
        albumartist="American Idiot",
    )

    result = actions.repair_albumartist(tmp_db, tmp_path)

    assert result.scanned == 1
    assert result.repaired == 1
    assert result.failed == []
    assert _read_albumartist(p) == "Green Day"


def test_repair_ignores_correct_albumartist(tmp_path: Path, tmp_db: Database):
    """A clean row isn't returned by find_corrupt_albumartists at all,
    so the repair pass never even opens the file."""
    p = tmp_path / "01.mp3"
    _seed(tmp_db, p, artist="Green Day", album="Dookie", albumartist="Green Day")

    result = actions.repair_albumartist(tmp_db, tmp_path)

    assert result.scanned == 0
    assert result.repaired == 0
    assert _read_albumartist(p) == "Green Day"


def test_repair_ignores_missing_albumartist(tmp_path: Path, tmp_db: Database):
    """Files with NULL albumartist are already handled by the display
    fallback (`COALESCE(album_artist, artist)`); the index query
    filters them out."""
    p = tmp_path / "01.mp3"
    _seed(tmp_db, p, artist="Green Day", album="Dookie", albumartist=None)

    result = actions.repair_albumartist(tmp_db, tmp_path)

    assert result.scanned == 0
    assert result.repaired == 0
    assert _read_albumartist(p) is None


def test_repair_ignores_self_titled_album(tmp_path: Path, tmp_db: Database):
    """Black Sabbath / Black Sabbath: albumartist == album, but also
    == artist, so the index filter (album_artist != artist) excludes it."""
    p = tmp_path / "01.mp3"
    _seed(
        tmp_db,
        p,
        artist="Black Sabbath",
        album="Black Sabbath",
        albumartist="Black Sabbath",
    )

    result = actions.repair_albumartist(tmp_db, tmp_path)

    assert result.scanned == 0
    assert result.repaired == 0
    assert _read_albumartist(p) == "Black Sabbath"


def test_repair_scope_filters_by_path_prefix(tmp_path: Path, tmp_db: Database):
    """Only broken files under `target` should be touched."""
    in_scope = tmp_path / "Green Day" / "Dookie" / "01.mp3"
    out_of_scope = tmp_path / "Jay-Z" / "Reasonable Doubt" / "01.mp3"
    _seed(tmp_db, in_scope, artist="Green Day", album="Dookie", albumartist="Dookie")
    _seed(
        tmp_db,
        out_of_scope,
        artist="Jay-Z",
        album="Reasonable Doubt",
        albumartist="Reasonable Doubt",
    )

    result = actions.repair_albumartist(tmp_db, tmp_path / "Green Day")

    assert result.scanned == 1
    assert result.repaired == 1
    assert _read_albumartist(in_scope) == "Green Day"
    assert _read_albumartist(out_of_scope) == "Reasonable Doubt"


def test_repair_skips_stale_db_row(tmp_path: Path, tmp_db: Database):
    """A file flagged broken in the DB but already clean on disk
    (e.g. fixed externally between scans) is silently skipped — no
    write, no failure."""
    p = tmp_path / "01.mp3"
    _make_mp3(p, artist="Green Day", album="Dookie", albumartist="Green Day")
    # DB still has the stale broken state
    tmp_db.upsert_track(
        _track_row(p, artist="Green Day", album="Dookie", albumartist="Dookie")
    )
    tmp_db.commit()

    result = actions.repair_albumartist(tmp_db, tmp_path)

    assert result.scanned == 1
    assert result.repaired == 0
    assert result.failed == []
    assert _read_albumartist(p) == "Green Day"


def test_repair_on_track_callback_fires(tmp_path: Path, tmp_db: Database):
    p = tmp_path / "01.mp3"
    _seed(
        tmp_db,
        p,
        artist="Green Day",
        album="American Idiot",
        albumartist="American Idiot",
    )
    seen: list[Path] = []

    actions.repair_albumartist(tmp_db, tmp_path, on_track=seen.append)

    assert seen == [p]
