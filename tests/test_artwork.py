"""Tests for cloud artwork: MusicBrainz lookup, Cover Art Archive fetch,
the mutagen embed helper, and the apply_cloud_artwork orchestration."""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path

from clickwheel import actions, artwork
from clickwheel.library import write_album_metadata

# A 1x1 JPEG and the PNG magic — enough to exercise the embed paths.
_TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300"
    "0806060706050807070709090a0c140d0c0b0b0c1912130f14"
    "1d1a1f1e1d1a1c1c20242e2720222c231c1c2837292c303134"
    "34341f27393d38323c2e333432ffc0000b080001000101011100"
    "ffc4001f0000010501010101010100000000000000000102030"
    "405060708090a0bffda0008010100003f00d2cf20ffd9"
)


# ---------------------------------------------------------------------------
# artwork.lookup_release_group
# ---------------------------------------------------------------------------


def _mb_payload(score: int) -> bytes:
    return json.dumps(
        {
            "release-groups": [
                {
                    "id": "9365d16b-1c5a-3b7c-8d2e-aaaaaaaaaaaa",
                    "title": "Frankenchrist",
                    "first-release-date": "1985-10-01",
                    "score": score,
                }
            ]
        }
    ).encode()


def test_lookup_release_group_good_match(monkeypatch):
    monkeypatch.setattr(artwork, "_get", lambda url, timeout: _mb_payload(100))
    match = artwork.lookup_release_group("Dead Kennedys", "Frankenchrist")
    assert match is not None
    assert match.mbid == "9365d16b-1c5a-3b7c-8d2e-aaaaaaaaaaaa"
    assert match.year == 1985


def test_lookup_release_group_low_score_rejected(monkeypatch):
    monkeypatch.setattr(artwork, "_get", lambda url, timeout: _mb_payload(50))
    assert artwork.lookup_release_group("Some", "Album") is None


def test_lookup_release_group_no_results(monkeypatch):
    monkeypatch.setattr(artwork, "_get", lambda url, timeout: b'{"release-groups": []}')
    assert artwork.lookup_release_group("Nobody", "Nothing") is None


def test_lookup_release_group_network_error(monkeypatch):
    def boom(url, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(artwork, "_get", boom)
    try:
        artwork.lookup_release_group("X", "Y")
        raise AssertionError("expected ArtworkLookupError")
    except artwork.ArtworkLookupError:
        pass


# ---------------------------------------------------------------------------
# artwork.fetch_front_cover
# ---------------------------------------------------------------------------


def test_fetch_front_cover_returns_bytes(monkeypatch):
    monkeypatch.setattr(artwork, "_get", lambda url, timeout: _TINY_JPEG)
    assert artwork.fetch_front_cover("some-mbid") == _TINY_JPEG


def test_fetch_front_cover_404_returns_none(monkeypatch):
    def not_found(url, timeout):
        raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    monkeypatch.setattr(artwork, "_get", not_found)
    assert artwork.fetch_front_cover("no-art-mbid") is None


# ---------------------------------------------------------------------------
# library.write_album_metadata
# ---------------------------------------------------------------------------


def test_write_album_metadata_mp3(tmp_path):
    from mutagen.id3 import ID3

    f = tmp_path / "track.mp3"
    f.write_bytes(b"")
    art_done, year_done = write_album_metadata(f, art=_TINY_JPEG, year=1985)
    assert art_done and year_done

    tags = ID3(str(f))
    assert any(k.startswith("APIC") for k in tags)
    assert str(tags["TDRC"].text[0]) == "1985"


def test_write_album_metadata_skips_existing_art(tmp_path):
    f = tmp_path / "track.mp3"
    f.write_bytes(b"")
    write_album_metadata(f, art=_TINY_JPEG, year=1985)
    # Second pass: art already present, so it must not re-embed.
    art_done, year_done = write_album_metadata(f, art=_TINY_JPEG, year=1990)
    assert art_done is False
    assert year_done is True


def test_write_album_metadata_skips_unknown_format(tmp_path):
    f = tmp_path / "track.wav"
    f.write_bytes(b"")
    assert write_album_metadata(f, art=_TINY_JPEG, year=1985) == (False, False)


# ---------------------------------------------------------------------------
# actions.apply_cloud_artwork
# ---------------------------------------------------------------------------


def test_apply_cloud_artwork_orchestration(tmp_path, monkeypatch):
    """Two album folders: one matches MusicBrainz, one doesn't."""
    matched = tmp_path / "Matched Album"
    unmatched = tmp_path / "Unmatched Album"
    matched.mkdir()
    unmatched.mkdir()
    matched_tracks = [matched / "01.mp3", matched / "02.mp3"]
    unmatched_tracks = [unmatched / "01.mp3"]
    for p in [*matched_tracks, *unmatched_tracks]:
        p.write_bytes(b"")

    monkeypatch.setattr(
        "clickwheel.library.find_audio_files",
        lambda target: matched_tracks + unmatched_tracks,
    )

    def fake_scan(path):
        folder = Path(path).parent.name
        return {"artist": "Artist", "album_artist": "Artist", "album": folder}

    monkeypatch.setattr("clickwheel.actions.scan_file", fake_scan)
    monkeypatch.setattr("clickwheel.actions.time.sleep", lambda _s: None)

    def fake_lookup(artist, album, **_kw):
        if album == "Matched Album":
            return artwork.AlbumMatch(mbid="mbid-1", title=album, year=1985)
        return None

    monkeypatch.setattr("clickwheel.artwork.lookup_release_group", fake_lookup)
    monkeypatch.setattr(
        "clickwheel.artwork.fetch_front_cover", lambda mbid, **_kw: _TINY_JPEG
    )

    embedded: list[str] = []

    def fake_write(path, *, art, year):
        embedded.append(str(path))
        return (art is not None, year is not None)

    monkeypatch.setattr("clickwheel.library.write_album_metadata", fake_write)

    result = actions.apply_cloud_artwork(tmp_path)

    assert result.albums_seen == 2
    assert result.albums_matched == 1
    assert result.art_embedded == 2  # two tracks in the matched album
    assert result.years_set == 2
    assert result.unmatched == ["Artist — Unmatched Album"]
