"""Tests for clickwheel/plex.py — path remap, M3U writer, slug, and the
config-validation guards in actions.py. We do not touch a real Plex
server here; the upload/connect codepaths are exercised manually.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clickwheel import plex as _plex
from clickwheel.actions import (
    PlexNotConfiguredError,
    PlexPathRemapError,
    _require_plex_config,
    _slugify_for_filename,
    plex_doctor,
    sync_playlist_to_plex,
)
from clickwheel.config import Config


@pytest.fixture()
def plex_cfg(tmp_path: Path) -> Config:
    """A Config with Plex enabled and pointed at a fake server."""
    return Config(
        music_dir=tmp_path / "music",
        project_dir=tmp_path,
        plex_enabled=True,
        plex_url="http://example.invalid:32400",
        plex_token="fake-token",
        plex_library_name="Music",
        plex_path_remap_local="/Volumes/Public/",
        plex_path_remap_plex="/share/CACHEDEV1_DATA/Public/",
    )


# ---------------------------------------------------------------------------
# local_to_plex_path
# ---------------------------------------------------------------------------


def test_local_to_plex_path_basic():
    out = _plex.local_to_plex_path(
        "/Volumes/Public/Multimedia/Music/Artist/Album/01.mp3",
        "/Volumes/Public/",
        "/share/CACHEDEV1_DATA/Public/",
    )
    assert out == "/share/CACHEDEV1_DATA/Public/Multimedia/Music/Artist/Album/01.mp3"


def test_local_to_plex_path_identity_when_unset():
    # Empty remap means Plex and clickwheel see identical paths
    # (common when Plex runs on the same host).
    out = _plex.local_to_plex_path("/music/foo.mp3", "", "")
    assert out == "/music/foo.mp3"


def test_local_to_plex_path_partial_config_raises():
    with pytest.raises(_plex.PlexConfigInvalidError):
        _plex.local_to_plex_path("/music/foo.mp3", "/Volumes/", "")
    with pytest.raises(_plex.PlexConfigInvalidError):
        _plex.local_to_plex_path("/music/foo.mp3", "", "/share/")


def test_local_to_plex_path_mismatch_raises():
    with pytest.raises(_plex.PathRemapFailedError):
        _plex.local_to_plex_path(
            "/some/other/path/01.mp3",
            "/Volumes/Public/",
            "/share/CACHEDEV1_DATA/Public/",
        )


# ---------------------------------------------------------------------------
# build_m3u
# ---------------------------------------------------------------------------


def test_build_m3u_writes_header_and_extinf(tmp_path: Path):
    """build_m3u writes an EXTM3U file whose track lines have already been
    remapped to Plex's view of the filesystem. We use an empty remap here
    so we can keep the M3U inside tmp_path; the remap translation itself
    is tested separately in test_local_to_plex_path_*."""
    tracks = [
        {
            "path": "/music/A/Album/01 Song.mp3",
            "artist": "A",
            "title": "Song",
            "duration_seconds": 200.0,
        },
        {
            "path": "/music/B/Album/02 Other.mp3",
            "artist": "B",
            "title": "Other",
            "duration_seconds": None,
        },
    ]
    local = _plex.build_m3u(tracks, tmp_path / "out.m3u", "", "")

    content = local.read_text(encoding="utf-8")
    lines = content.strip().splitlines()
    assert lines[0] == "#EXTM3U"
    assert lines[1] == "#EXTINF:200,A - Song"
    assert lines[2] == "/music/A/Album/01 Song.mp3"
    # Missing duration becomes -1 (standard M3U convention).
    assert lines[3] == "#EXTINF:-1,B - Other"
    assert lines[4] == "/music/B/Album/02 Other.mp3"


def test_build_m3u_remaps_track_paths(tmp_path: Path):
    """When a remap is configured, the track lines in the M3U are the
    Plex-side paths. The M3U's own dest location is independent — it
    can live anywhere writable (callers decide based on where Plex
    will read it from)."""
    tracks = [
        {
            "path": "/Volumes/Public/Music/A/Album/01 Song.mp3",
            "artist": "A",
            "title": "Song",
            "duration_seconds": 200.0,
        }
    ]
    local = _plex.build_m3u(
        tracks,
        tmp_path / "out.m3u",
        "/Volumes/Public/",
        "/share/CACHEDEV1_DATA/Public/",
    )
    lines = local.read_text(encoding="utf-8").strip().splitlines()
    assert "/share/CACHEDEV1_DATA/Public/Music/A/Album/01 Song.mp3" in lines


def test_build_m3u_creates_parent_dir(tmp_path: Path):
    nested = tmp_path / "a" / "b" / "c" / "out.m3u"
    _plex.build_m3u(
        [{"path": "/music/foo.mp3", "artist": "x", "title": "y"}],
        nested,
        "",
        "",
    )
    assert nested.exists()


def test_build_m3u_propagates_path_remap_error(tmp_path: Path):
    tracks = [{"path": "/not/the/right/prefix.mp3", "artist": "x", "title": "y"}]
    with pytest.raises(_plex.PathRemapFailedError):
        _plex.build_m3u(
            tracks,
            tmp_path / "out.m3u",
            "/Volumes/Public/",
            "/share/CACHEDEV1_DATA/Public/",
        )


# ---------------------------------------------------------------------------
# slug
# ---------------------------------------------------------------------------


def test_slugify_strips_unsafe_chars():
    assert _slugify_for_filename("Road Trip 70s") == "Road_Trip_70s"
    assert _slugify_for_filename("70s rock / classics") == "70s_rock___classics"
    assert _slugify_for_filename("simple-name.test_42") == "simple-name.test_42"


def test_slugify_falls_back_for_empty():
    assert _slugify_for_filename("") == "playlist"
    assert _slugify_for_filename("///") == "___"  # not empty after sub


# ---------------------------------------------------------------------------
# find_music_section
# ---------------------------------------------------------------------------


class _StubSection:
    def __init__(self, title: str, kind: str = "artist") -> None:
        self.title = title
        self.type = kind


class _StubLibrary:
    def __init__(self, sections: list[_StubSection]) -> None:
        self._sections = sections

    def sections(self) -> list[_StubSection]:
        return self._sections


class _StubPlex:
    def __init__(self, sections: list[_StubSection]) -> None:
        self.library = _StubLibrary(sections)


def test_find_music_section_picks_by_title():
    """Two artist-type sections exist; pick by exact title to avoid the
    Audiobooks-vs-Music confusion."""
    sections = [
        _StubSection("Audiobooks", "artist"),
        _StubSection("Music", "artist"),
    ]
    s = _plex.find_music_section(_StubPlex(sections), "Music")
    assert s.title == "Music"


def test_find_music_section_raises_on_missing():
    sections = [_StubSection("Movies", "movie"), _StubSection("Music", "artist")]
    with pytest.raises(LookupError):
        _plex.find_music_section(_StubPlex(sections), "Audiobooks")


# ---------------------------------------------------------------------------
# Config + _require_plex_config
# ---------------------------------------------------------------------------


def test_require_plex_config_when_disabled(tmp_path: Path):
    cfg = Config(music_dir=tmp_path / "m", project_dir=tmp_path, plex_enabled=False)
    with pytest.raises(PlexNotConfiguredError):
        _require_plex_config(cfg)


def test_require_plex_config_missing_token(tmp_path: Path):
    cfg = Config(
        music_dir=tmp_path / "m",
        project_dir=tmp_path,
        plex_enabled=True,
        plex_url="http://example.invalid:32400",
        plex_token="",
    )
    with pytest.raises(PlexNotConfiguredError) as exc_info:
        _require_plex_config(cfg)
    assert "plex_token" in str(exc_info.value)


def test_sync_playlist_to_plex_bails_early_when_disabled(tmp_path, populated_db):
    cfg = Config(music_dir=tmp_path / "m", project_dir=tmp_path, plex_enabled=False)
    with pytest.raises(PlexNotConfiguredError):
        sync_playlist_to_plex(cfg, populated_db, "anything")


def test_sync_playlist_to_plex_propagates_path_remap_error(
    plex_cfg: Config, populated_db, monkeypatch
):
    """If the playlist contains a track whose path doesn't match the
    configured remap prefix, surface PlexPathRemapError so the user
    gets a clear pointer at the bad config rather than a Plex-side
    'playlist resolved 0 tracks' mystery."""
    populated_db.save_playlist("mismatched", ["/music/A/Album1/01 T1.mp3"])
    populated_db.commit()

    stub = _StubPlex([_StubSection("Music", "artist")])
    monkeypatch.setattr(_plex, "connect", lambda url, token: stub)

    with pytest.raises(PlexPathRemapError):
        sync_playlist_to_plex(plex_cfg, populated_db, "mismatched")


# ---------------------------------------------------------------------------
# plex_doctor
# ---------------------------------------------------------------------------


class _StubTrackPart:
    def __init__(self, path: str) -> None:
        self.file = path


class _StubTrackMedia:
    def __init__(self, path: str) -> None:
        self.parts = [_StubTrackPart(path)]


class _StubTrack:
    def __init__(self, path: str) -> None:
        self.media = [_StubTrackMedia(path)]


# plexapi's API uses camelCase (searchTracks, friendlyName, leafCount,
# ratingKey, totalSize). The stubs below mirror that surface verbatim
# so the SUT can call them the same way it'd call the real Plex API.
# Per-line N802/N815 silences are deliberate: these names aren't ours.
class _StubSearchSection(_StubSection):
    """Section stub that supports searchTracks() for the doctor's
    sample-track stage."""

    def __init__(self, returned_paths: list[str], *, title: str = "Music") -> None:
        super().__init__(title, "artist")
        self.key = "4"
        self.totalSize = 285  # noqa: N815
        self._paths = returned_paths

    def searchTracks(self, **kwargs):  # noqa: N802
        return [_StubTrack(p) for p in self._paths]


class _StubServer:
    friendlyName = "test-server"  # noqa: N815
    version = "1.0.0"

    def __init__(self, sections: list[_StubSection]) -> None:
        self.library = _StubLibrary(sections)


@pytest.fixture()
def _plexapi_stub(monkeypatch):
    """Tests that stub `_plex.connect` must also bypass the
    plexapi-extra check, otherwise the doctor stops there before the
    stub kicks in. The "plexapi missing" path is the natural state when
    the [plex] extra isn't installed; here we just need it to no-op so
    the rest of the chain reports independently."""
    monkeypatch.setattr(_plex, "_import_plexapi", lambda: None)


def test_plex_doctor_stops_at_disabled_config(tmp_path, populated_db):
    cfg = Config(music_dir=tmp_path / "m", project_dir=tmp_path, plex_enabled=False)
    result = plex_doctor(cfg, populated_db)
    assert result.ok is False
    assert [s.name for s in result.stages] == ["config"]


def test_plex_doctor_all_stages_pass(
    tmp_path, populated_db, monkeypatch, _plexapi_stub
):
    """No remap; sample track resolves at the same path. All five
    stages should report ok=True.

    `plex_doctor` picks the sample via `ORDER BY RANDOM()`, so the stub
    needs to return every indexed path — that way whichever the doctor
    picks, the expected path is in the result set."""
    cfg = Config(
        music_dir=tmp_path / "m",
        project_dir=tmp_path,
        plex_enabled=True,
        plex_url="http://example.invalid:32400",
        plex_token="t",
        plex_library_name="Music",
    )
    all_paths = [
        r["path"]
        for r in populated_db.conn.execute("SELECT path FROM tracks").fetchall()
    ]
    monkeypatch.setattr(
        _plex,
        "connect",
        lambda url, token: _StubServer([_StubSearchSection(all_paths)]),
    )

    result = plex_doctor(cfg, populated_db)
    assert result.ok is True, [(s.name, s.detail) for s in result.stages if not s.ok]
    assert [s.name for s in result.stages] == [
        "config",
        "plexapi extra",
        "connect",
        "music section",
        "sample track",
    ]


def test_plex_doctor_flags_path_remap_mismatch(
    plex_cfg: Config, populated_db, monkeypatch, _plexapi_stub
):
    """The sample-track stage should fail clearly when the configured
    remap can't translate the clickwheel-side path."""
    monkeypatch.setattr(
        _plex,
        "connect",
        lambda url, token: _StubServer([_StubSearchSection(["/anywhere/01.mp3"])]),
    )
    result = plex_doctor(plex_cfg, populated_db)
    sample_stage = next(s for s in result.stages if s.name == "sample track")
    assert sample_stage.ok is False
    assert "remap" in sample_stage.detail.lower()


def test_plex_doctor_handles_empty_library(
    tmp_path, monkeypatch, tmp_db, _plexapi_stub
):
    """If the DB has no mp3 tracks to sample, sample-track stage fails
    with an instructive message (run scan) rather than a stack trace."""
    cfg = Config(
        music_dir=tmp_path / "m",
        project_dir=tmp_path,
        plex_enabled=True,
        plex_url="http://example.invalid:32400",
        plex_token="t",
    )
    monkeypatch.setattr(
        _plex,
        "connect",
        lambda url, token: _StubServer([_StubSearchSection([])]),
    )
    result = plex_doctor(cfg, tmp_db)
    sample_stage = next(s for s in result.stages if s.name == "sample track")
    assert sample_stage.ok is False
    assert "scan" in sample_stage.detail.lower()


# ---------------------------------------------------------------------------
# set_playlist_summary
# ---------------------------------------------------------------------------


def test_set_playlist_summary_calls_edit_summary():
    """set_playlist_summary mirrors a clickwheel description onto a Plex
    playlist via plexapi's editSummary()."""
    from clickwheel.plex import set_playlist_summary

    class _StubPlaylist:
        def __init__(self) -> None:
            self.summary: str | None = None

        def editSummary(self, value: str) -> None:  # noqa: N802
            self.summary = value

    pl = _StubPlaylist()
    set_playlist_summary(pl, "a tidy description")
    assert pl.summary == "a tidy description"
