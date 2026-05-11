"""Regression tests for the iPod sync layer.

The big one is `test_write_ipod_db_preserves_existing_tracks` — guards
against the Phase 5 bug where `write_ipod_db` orphaned every previously-
synced track because `write_itunesdb` is "replace everything" semantics
and we passed only the newly-copied tracks. Discovered when a Weezer
test sync silently nuked 335 Taylor-Swift tracks from the iTunesDB.

If anyone ever changes `write_ipod_db` to skip merging by default again,
this test screams.
"""

from __future__ import annotations

from clickwheel.ipod import sync as sync_module


def test_existing_track_to_trackinfo_round_trips_state(monkeypatch):
    """Helper preserves play counts, dates, dbid — fields users care about."""
    src = {
        "title": "My Name Is Jonas",
        "location": ":iPod_Control:Music:F00/01.m4a",
        "size": 5_000_000,
        "length": 200_000,
        "filetype": "m4a",
        "bitrate": 256,
        "sampleRate": 44100,
        "artist": "Weezer",
        "album": "Weezer (Blue Album)",
        "album_artist": "Weezer",
        "genre": "Rock",
        "year": 1994,
        "trackNumber": 1,
        "totalTracks": 10,
        "discNumber": 1,
        "totalDiscs": 1,
        "playCount": 7,
        "lastPlayed": 1700000000,
        "rating": 80,
        "dateAdded": 1690000000,
        "dbid": 0x12345678ABCDEF00,
        "trackID": 42,
        "mhiiLink": 0x999,
        "artworkCount": 1,
        "artworkSize": 50000,
    }
    ti = sync_module._existing_track_to_trackinfo(src)
    assert ti.title == "My Name Is Jonas"
    assert ti.location == ":iPod_Control:Music:F00/01.m4a"
    assert ti.play_count == 7  # state preserved
    assert ti.last_played == 1700000000
    assert ti.rating == 80
    assert ti.date_added == 1690000000
    assert ti.dbid == 0x12345678ABCDEF00
    assert ti.track_id == 42
    assert ti.artist == "Weezer"
    assert ti.year == 1994
    assert ti.track_number == 1
    assert ti.total_tracks == 10
    # Artwork fields must round-trip — without them, the next
    # merged-write nukes existing tracks' album art via the ArtworkDB
    # preserve-existing path missing its lookup key.
    assert ti.mhii_link == 0x999
    assert ti.artwork_count == 1
    assert ti.artwork_size == 50000


def test_write_ipod_db_preserves_existing_tracks(tmp_path, monkeypatch):
    """REGRESSION: write_ipod_db must merge new tracks with existing ones,
    not clobber. Phase 5 bug: a 10-track sync orphaned 335 prior tracks
    because write_itunesdb is "replace everything" and we passed only the
    new ones.

    This test stands in for the integration scenario by mocking the
    read/write boundary and asserting the call to write_itunesdb gets
    BOTH the existing AND new tracks.
    """
    captured_calls: list[list] = []

    def fake_read_ipod(mount):
        # Two existing tracks already on the iPod.
        return {
            "mhlt": [
                {
                    "title": "Old Track 1",
                    "location": ":iPod_Control:Music:F00:old1.mp3",
                    "artist": "OldArtist",
                    "size": 1000,
                    "length": 1000,
                    "filetype": "mp3",
                    "playCount": 5,  # play count we want to preserve
                    "dbid": 0x1111,
                },
                {
                    "title": "Old Track 2",
                    "location": ":iPod_Control:Music:F00:old2.mp3",
                    "artist": "OldArtist",
                    "size": 2000,
                    "length": 2000,
                    "filetype": "mp3",
                    "dbid": 0x2222,
                },
            ]
        }

    def fake_write_itunesdb(ipod_path, tracks, **kwargs):
        captured_calls.append(list(tracks))
        return True

    monkeypatch.setattr("clickwheel.ipod.read_ipod", fake_read_ipod, raising=True)
    monkeypatch.setattr(sync_module, "write_itunesdb", fake_write_itunesdb)

    # One newly-copied track.
    new_tracks = [
        (
            {
                "path": "/music/foo.mp3",
                "title": "New Track",
                "artist": "NewArtist",
                "format": "mp3",
                "file_size": 3000,
                "duration_seconds": 3.0,
            },
            "F00/new.mp3",
        )
    ]

    ok = sync_module.write_ipod_db(tmp_path, new_tracks)
    assert ok is True

    assert len(captured_calls) == 1
    written = captured_calls[0]
    # Must have ALL THREE tracks: 2 existing + 1 new.
    assert len(written) == 3
    titles = {t.title for t in written}
    assert titles == {"New Track", "Old Track 1", "Old Track 2"}
    # Play count from the existing track must round-trip — sync isn't
    # supposed to wipe user history.
    old1 = next(t for t in written if t.title == "Old Track 1")
    assert old1.play_count == 5
    assert old1.dbid == 0x1111


def test_write_ipod_db_full_replace_skips_merge(tmp_path, monkeypatch):
    """The escape hatch: full_replace=True writes only new tracks. Used
    for deliberate wipe-and-fill, e.g. an explicit `clickwheel reset`."""
    captured_calls: list[list] = []

    def fake_read_ipod(mount):
        # Even if existing tracks are present, full_replace ignores them.
        return {
            "mhlt": [{"title": "Old", "location": ":iPod_Control:Music:F00/old.mp3"}]
        }

    def fake_write_itunesdb(ipod_path, tracks, **kwargs):
        captured_calls.append(list(tracks))
        return True

    monkeypatch.setattr("clickwheel.ipod.read_ipod", fake_read_ipod, raising=True)
    monkeypatch.setattr(sync_module, "write_itunesdb", fake_write_itunesdb)

    new_tracks = [
        (
            {
                "path": "/music/foo.mp3",
                "title": "New",
                "format": "mp3",
            },
            "F00/new.mp3",
        )
    ]

    sync_module.write_ipod_db(tmp_path, new_tracks, full_replace=True)
    assert len(captured_calls) == 1
    assert [t.title for t in captured_calls[0]] == ["New"]


def test_write_ipod_db_path_collision_new_wins(tmp_path, monkeypatch):
    """If a newly-copied track has the same iPod-relative path as an
    existing track, the new copy wins (existing entry is dropped).

    iPod track locations use a mixed format — `:iPod_Control:Music:` as
    the prefix (colons), then `F00/filename.ext` (slash for the file
    inside the bucket dir). track_to_trackinfo builds the same shape, so
    location-equality dedup works.
    """
    captured_calls: list[list] = []

    def fake_read_ipod(mount):
        return {
            "mhlt": [
                {
                    "title": "Stale Metadata",
                    # Real iPod format: colons up to F00, then slash.
                    "location": ":iPod_Control:Music:F00/duplicate.mp3",
                    "filetype": "mp3",
                }
            ]
        }

    def fake_write_itunesdb(ipod_path, tracks, **kwargs):
        captured_calls.append(list(tracks))
        return True

    monkeypatch.setattr("clickwheel.ipod.read_ipod", fake_read_ipod, raising=True)
    monkeypatch.setattr(sync_module, "write_itunesdb", fake_write_itunesdb)

    new_tracks = [
        (
            {
                "path": "/music/foo.mp3",
                "title": "Fresh Metadata",
                "format": "mp3",
            },
            "F00/duplicate.mp3",
        )
    ]
    sync_module.write_ipod_db(tmp_path, new_tracks)

    written = captured_calls[0]
    assert len(written) == 1  # not 2 — collision deduped
    assert written[0].title == "Fresh Metadata"


def test_write_ipod_db_continues_when_existing_unreadable(tmp_path, monkeypatch):
    """If reading the existing iTunesDB fails (corrupt db, share unmounted
    mid-call), still write the new tracks — degraded but doesn't crash.
    The fail-soft is intentional: a merge failure shouldn't lose the new
    tracks the user just copied."""
    captured_calls: list[list] = []

    def fake_read_ipod(mount):
        raise OSError("simulated read failure")

    def fake_write_itunesdb(ipod_path, tracks, **kwargs):
        captured_calls.append(list(tracks))
        return True

    monkeypatch.setattr("clickwheel.ipod.read_ipod", fake_read_ipod, raising=True)
    monkeypatch.setattr(sync_module, "write_itunesdb", fake_write_itunesdb)

    new_tracks = [({"path": "/x.mp3", "title": "Only", "format": "mp3"}, "F00/x.mp3")]
    ok = sync_module.write_ipod_db(tmp_path, new_tracks)
    assert ok is True
    assert len(captured_calls[0]) == 1


def test_write_ipod_db_no_tracks_at_all(tmp_path, monkeypatch):
    """No new tracks AND nothing existing → nothing to write, returns False."""
    monkeypatch.setattr(
        "clickwheel.ipod.read_ipod", lambda m: {"mhlt": []}, raising=True
    )
    called = []
    monkeypatch.setattr(
        sync_module,
        "write_itunesdb",
        lambda *a, **kw: called.append(True) or True,
    )
    ok = sync_module.write_ipod_db(tmp_path, [])
    assert ok is False
    assert not called  # didn't bother calling write_itunesdb


def test_action_sync_playlist_passes_existing_through(tmp_path, monkeypatch):
    """Integration: actions.sync_playlist's call into write_ipod_db hits
    the merge path (write_ipod_db default behavior). This is the exact
    Phase 5 path; if we ever pass full_replace=True here by mistake,
    the regression returns."""
    from clickwheel import actions
    from clickwheel.actions import Diff
    from clickwheel.config import Config
    from clickwheel.db import Database

    music = tmp_path / "music"
    music.mkdir()
    cfg = Config(
        music_dir=music,
        project_dir=tmp_path,
        ipod_mount=tmp_path / "ipod",
        auto_scan=False,
    )
    (cfg.ipod_mount).mkdir()

    db = Database(cfg.db_path)
    db.save_playlist("p", [])

    # Stub the iPod-level operations so we don't need a real device.
    monkeypatch.setattr(
        actions, "compute_diff", lambda *a, **kw: Diff(playlist="p", to_add=[])
    )
    # sync_playlist now reads existing iPod playlists for conflict
    # detection — fake those out too.
    monkeypatch.setattr(actions, "require_ipod", lambda _cfg: {"fake": "db"})
    monkeypatch.setattr("clickwheel.ipod.get_ipod_playlists", lambda _db: [])
    full_replace_flags: list[bool] = []

    def fake_write_ipod_db(
        mount,
        copied,
        *,
        full_replace=False,
        playlist_specs=None,
        overwrite_playlist_names=None,
    ):
        full_replace_flags.append(full_replace)
        return True

    def fake_copy(*a, **kw):
        return ([], [])

    import shutil as _shutil

    monkeypatch.setattr(
        _shutil, "disk_usage", lambda p: type("DU", (), {"free": 10**12})()
    )
    monkeypatch.setattr("clickwheel.ipod.sync.copy_tracks_to_ipod", fake_copy)
    monkeypatch.setattr("clickwheel.ipod.sync.write_ipod_db", fake_write_ipod_db)

    actions.sync_playlist(cfg, db, "p", diff=Diff(playlist="p", to_add=[]))
    db.close()

    # The default merge behavior must be in effect — full_replace must NOT
    # be True. If anyone changes the default they'll trip this.
    assert full_replace_flags == [False]
