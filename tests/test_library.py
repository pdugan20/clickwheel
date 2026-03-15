"""Tests for library scanning."""

from __future__ import annotations

from pathlib import Path

from clickwheel.library import (
    _first,
    _parse_track_number,
    _parse_year,
    find_audio_files,
    scan_file,
)


def test_first_with_values():
    assert _first(["hello"]) == "hello"


def test_first_with_multiple():
    assert _first(["a", "b"]) == "a"


def test_first_none():
    assert _first(None) is None


def test_first_empty():
    assert _first([]) is None


def test_parse_track_number_simple():
    assert _parse_track_number(["3"]) == 3


def test_parse_track_number_with_total():
    assert _parse_track_number(["3/12"]) == 3


def test_parse_track_number_none():
    assert _parse_track_number(None) is None


def test_parse_track_number_invalid():
    assert _parse_track_number(["abc"]) is None


def test_parse_year_full_date():
    assert _parse_year(["2020-01-15"]) == 2020


def test_parse_year_just_year():
    assert _parse_year(["2020"]) == 2020


def test_parse_year_none():
    assert _parse_year(None) is None


def test_parse_year_invalid():
    assert _parse_year(["abcd"]) is None


def test_find_audio_files(tmp_path: Path):
    (tmp_path / "song.mp3").touch()
    (tmp_path / "song.flac").touch()
    (tmp_path / "readme.txt").touch()
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "deep.m4a").touch()

    files = find_audio_files(tmp_path)
    extensions = {f.suffix for f in files}
    assert ".mp3" in extensions
    assert ".flac" in extensions
    assert ".m4a" in extensions
    assert ".txt" not in extensions
    assert len(files) == 3


def test_scan_file_mp3(music_dir_with_mp3: Path):
    mp3_files = list(music_dir_with_mp3.rglob("*.mp3"))
    assert len(mp3_files) == 1

    result = scan_file(mp3_files[0])
    assert result is not None
    assert result["title"] == "TestTrack"
    assert result["artist"] == "TestArtist"
    assert result["album"] == "TestAlbum"
    assert result["format"] == "mp3"
    assert result["file_size"] > 0


def test_scan_file_nonexistent(tmp_path: Path):
    result = scan_file(tmp_path / "nope.mp3")
    assert result is None


def test_scan_file_not_audio(tmp_path: Path):
    txt = tmp_path / "readme.txt"
    txt.write_text("not audio")
    result = scan_file(txt)
    assert result is None
