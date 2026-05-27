"""Tests for cloud artwork: MusicBrainz lookup, Cover Art Archive fetch,
the mutagen embed helper, and the apply_cloud_artwork orchestration."""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path

from clickwheel import actions, artwork
from clickwheel.db import Database
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
# artwork._get — transient-failure retry
# ---------------------------------------------------------------------------


class _FakeResp:
    """Minimal stand-in for the object urllib.request.urlopen returns."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


def test_get_retries_transient_failure_then_succeeds(monkeypatch):
    """A connection error is retried; a later success is still returned."""
    calls: list[int] = []

    def flaky(req, timeout):
        calls.append(1)
        if len(calls) < 3:
            raise urllib.error.URLError("connection reset")
        return _FakeResp(b"ok")

    monkeypatch.setattr("urllib.request.urlopen", flaky)
    monkeypatch.setattr("clickwheel.artwork.time.sleep", lambda _s: None)

    assert artwork._get("https://example/x", timeout=5) == b"ok"
    assert len(calls) == 3


def test_get_does_not_retry_404(monkeypatch):
    """A 4xx is a definitive answer — raised at once, never retried."""
    calls: list[int] = []

    def not_found(req, timeout):
        calls.append(1)
        raise urllib.error.HTTPError("https://example/x", 404, "Not Found", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", not_found)
    monkeypatch.setattr("clickwheel.artwork.time.sleep", lambda _s: None)

    try:
        artwork._get("https://example/x", timeout=5)
        raise AssertionError("expected HTTPError")
    except urllib.error.HTTPError as exc:
        assert exc.code == 404
    assert len(calls) == 1


def test_get_retries_5xx_then_raises_after_exhaustion(monkeypatch):
    """A 5xx is retried, then surfaced once the attempt budget is spent."""
    calls: list[int] = []

    def server_error(req, timeout):
        calls.append(1)
        raise urllib.error.HTTPError("https://example/x", 503, "Down", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", server_error)
    monkeypatch.setattr("clickwheel.artwork.time.sleep", lambda _s: None)

    try:
        artwork._get("https://example/x", timeout=5)
        raise AssertionError("expected HTTPError")
    except urllib.error.HTTPError as exc:
        assert exc.code == 503
    assert len(calls) == artwork._MAX_ATTEMPTS


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


def test_apply_cloud_artwork_orchestration(tmp_path, tmp_db: Database, monkeypatch):
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

    result = actions.apply_cloud_artwork(tmp_db, tmp_path)

    assert result.albums_seen == 2
    assert result.albums_matched == 1
    assert result.art_embedded == 2  # two tracks in the matched album
    assert result.years_set == 2
    assert result.unmatched == ["Artist — Unmatched Album"]
    assert result.art_fetch_failed == []
    # Both outcomes — positive and negative — should be cached now.
    assert tmp_db.get_mb_match("Artist", "Matched Album")["status"] == "matched"
    assert tmp_db.get_mb_match("Artist", "Unmatched Album")["status"] == "unmatched"


def test_apply_cloud_artwork_records_fetch_failure(
    tmp_path, tmp_db: Database, monkeypatch
):
    """An album that matches MusicBrainz but whose art fetch fails lands in
    art_fetch_failed — distinct from a genuine no-art result — and its
    release year is still written."""
    album = tmp_path / "Matched Album"
    album.mkdir()
    tracks = [album / "01.mp3", album / "02.mp3"]
    for p in tracks:
        p.write_bytes(b"")

    monkeypatch.setattr("clickwheel.library.find_audio_files", lambda target: tracks)
    monkeypatch.setattr("clickwheel.actions.time.sleep", lambda _s: None)

    def fake_scan(path):
        return {"artist": "Artist", "album_artist": "Artist", "album": "Matched Album"}

    monkeypatch.setattr("clickwheel.actions.scan_file", fake_scan)

    def fake_lookup(artist, album, **_kw):
        return artwork.AlbumMatch(mbid="mbid-1", title=album, year=1985)

    monkeypatch.setattr("clickwheel.artwork.lookup_release_group", fake_lookup)

    def boom(mbid, **_kw):
        raise artwork.ArtworkLookupError("Cover Art Archive error: HTTP 503")

    monkeypatch.setattr("clickwheel.artwork.fetch_front_cover", boom)

    def fake_write(path, *, art, year):
        return (art is not None, year is not None)

    monkeypatch.setattr("clickwheel.library.write_album_metadata", fake_write)

    result = actions.apply_cloud_artwork(tmp_db, tmp_path)

    assert result.albums_matched == 1
    assert result.art_embedded == 0
    assert result.years_set == 2  # year still written despite the art failure
    assert result.art_fetch_failed == ["Artist — Matched Album"]
    assert result.unmatched == []
    # MB match still gets cached even when the art fetch failed.
    assert tmp_db.get_mb_match("Artist", "Matched Album")["status"] == "matched"


def test_apply_cloud_artwork_survives_vanished_file(
    tmp_path, tmp_db: Database, monkeypatch
):
    """A track indexed by an earlier scan but gone from disk by the time
    we try to write to it must not abort the whole pass — the other
    files in the same album still get their tags written."""
    album = tmp_path / "Matched Album"
    album.mkdir()
    vanished = album / "01.mp3"
    real = album / "02.mp3"
    for p in (vanished, real):
        p.write_bytes(b"")

    monkeypatch.setattr(
        "clickwheel.library.find_audio_files", lambda target: [vanished, real]
    )
    monkeypatch.setattr(
        "clickwheel.actions.scan_file",
        lambda path: {
            "artist": "Artist",
            "album_artist": "Artist",
            "album": "Matched Album",
        },
    )
    monkeypatch.setattr("clickwheel.actions.time.sleep", lambda _s: None)
    monkeypatch.setattr(
        "clickwheel.artwork.lookup_release_group",
        lambda artist, album, **_kw: artwork.AlbumMatch(
            mbid="mbid-1", title=album, year=1990
        ),
    )
    monkeypatch.setattr(
        "clickwheel.artwork.fetch_front_cover", lambda mbid, **_kw: _TINY_JPEG
    )

    def fake_write(path, *, art, year):
        if path == vanished:
            raise FileNotFoundError(2, "No such file or directory", str(path))
        return (art is not None, year is not None)

    monkeypatch.setattr("clickwheel.library.write_album_metadata", fake_write)

    # Must not raise; result reflects only the surviving file.
    result = actions.apply_cloud_artwork(tmp_db, tmp_path)

    assert result.albums_matched == 1
    assert result.art_embedded == 1
    assert result.years_set == 1


def test_apply_cloud_artwork_uses_mb_cache(tmp_path, tmp_db: Database, monkeypatch):
    """A cached match is reused without hitting MusicBrainz."""
    album = tmp_path / "Cached Album"
    album.mkdir()
    track = album / "01.mp3"
    track.write_bytes(b"")

    tmp_db.save_mb_match("Artist", "Cached Album", mbid="mb-cached", year=1999)

    monkeypatch.setattr("clickwheel.library.find_audio_files", lambda target: [track])
    monkeypatch.setattr(
        "clickwheel.actions.scan_file",
        lambda path: {
            "artist": "Artist",
            "album_artist": "Artist",
            "album": "Cached Album",
        },
    )
    monkeypatch.setattr("clickwheel.actions.time.sleep", lambda _s: None)

    network_calls: list[tuple[str, str]] = []

    def boom(artist, album, **_kw):
        network_calls.append((artist, album))
        raise AssertionError("MB should not be queried on a cache hit")

    monkeypatch.setattr("clickwheel.artwork.lookup_release_group", boom)
    monkeypatch.setattr(
        "clickwheel.artwork.fetch_front_cover", lambda mbid, **_kw: _TINY_JPEG
    )
    monkeypatch.setattr(
        "clickwheel.library.write_album_metadata",
        lambda path, *, art, year: (art is not None, year is not None),
    )

    result = actions.apply_cloud_artwork(tmp_db, tmp_path)

    assert network_calls == []
    assert result.cache_hits == 1
    assert result.cache_misses == 0
    assert result.albums_matched == 1
    assert result.years_set == 1


def test_apply_cloud_artwork_negative_cache(tmp_path, tmp_db: Database, monkeypatch):
    """A cached `unmatched` row blocks re-querying MB for known no-matches."""
    album = tmp_path / "Obscure Album"
    album.mkdir()
    track = album / "01.mp3"
    track.write_bytes(b"")

    tmp_db.save_mb_match("Obscure Artist", "Obscure Album", mbid=None, year=None)

    monkeypatch.setattr("clickwheel.library.find_audio_files", lambda target: [track])
    monkeypatch.setattr(
        "clickwheel.actions.scan_file",
        lambda path: {
            "artist": "Obscure Artist",
            "album_artist": "Obscure Artist",
            "album": "Obscure Album",
        },
    )
    monkeypatch.setattr("clickwheel.actions.time.sleep", lambda _s: None)

    def boom(artist, album, **_kw):
        raise AssertionError("MB should not be queried on a cached unmatched")

    monkeypatch.setattr("clickwheel.artwork.lookup_release_group", boom)

    result = actions.apply_cloud_artwork(tmp_db, tmp_path)

    assert result.cache_hits == 1
    assert result.cache_misses == 0
    assert result.unmatched == ["Obscure Artist — Obscure Album"]
    assert result.albums_matched == 0


def test_apply_cloud_artwork_per_album_skip(tmp_path, tmp_db: Database, monkeypatch):
    """If every track already has art + year per the index, no MB call
    happens and the album is recorded as skipped-complete."""
    from tests.test_repair_albumartist import _track_row

    album = tmp_path / "Complete Album"
    album.mkdir()
    track = album / "01.mp3"
    track.write_bytes(b"")
    row = _track_row(
        track, artist="Artist", album="Complete Album", albumartist="Artist"
    )
    row["has_art"] = 1
    row["year"] = 2005
    tmp_db.upsert_track(row)
    tmp_db.commit()

    monkeypatch.setattr("clickwheel.library.find_audio_files", lambda target: [track])
    monkeypatch.setattr(
        "clickwheel.actions.scan_file",
        lambda path: {
            "artist": "Artist",
            "album_artist": "Artist",
            "album": "Complete Album",
        },
    )

    def boom(*_a, **_kw):
        raise AssertionError("Complete albums shouldn't trigger MB or art fetch")

    monkeypatch.setattr("clickwheel.artwork.lookup_release_group", boom)
    monkeypatch.setattr("clickwheel.artwork.fetch_front_cover", boom)
    monkeypatch.setattr(
        "clickwheel.library.write_album_metadata", lambda *_a, **_kw: (False, False)
    )

    result = actions.apply_cloud_artwork(tmp_db, tmp_path)

    assert result.albums_skipped_complete == 1
    assert result.cache_hits == 0
    assert result.cache_misses == 0
    assert result.albums_matched == 0


def test_apply_cloud_artwork_refresh_bypasses_cache(
    tmp_path, tmp_db: Database, monkeypatch
):
    """`refresh=True` ignores the cache and re-queries MB."""
    album = tmp_path / "Stale Album"
    album.mkdir()
    track = album / "01.mp3"
    track.write_bytes(b"")

    # Wrong year in the cache — the refresh should overwrite it.
    tmp_db.save_mb_match("Artist", "Stale Album", mbid="mb-old", year=1900)

    monkeypatch.setattr("clickwheel.library.find_audio_files", lambda target: [track])
    monkeypatch.setattr(
        "clickwheel.actions.scan_file",
        lambda path: {
            "artist": "Artist",
            "album_artist": "Artist",
            "album": "Stale Album",
        },
    )
    monkeypatch.setattr("clickwheel.actions.time.sleep", lambda _s: None)

    monkeypatch.setattr(
        "clickwheel.artwork.lookup_release_group",
        lambda artist, album, **_kw: artwork.AlbumMatch(
            mbid="mb-fresh", title=album, year=2024
        ),
    )
    monkeypatch.setattr(
        "clickwheel.artwork.fetch_front_cover", lambda mbid, **_kw: _TINY_JPEG
    )
    monkeypatch.setattr(
        "clickwheel.library.write_album_metadata",
        lambda path, *, art, year: (art is not None, year is not None),
    )

    result = actions.apply_cloud_artwork(tmp_db, tmp_path, refresh=True)

    assert result.cache_misses == 1
    assert result.cache_hits == 0
    cached = tmp_db.get_mb_match("Artist", "Stale Album")
    assert cached["mbid"] == "mb-fresh"
    assert cached["year"] == 2024
