"""Sync engine — copy tracks to iPod and write iTunesDB + ArtworkDB."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from clickwheel.ipod.itunesdb_writer import TrackInfo, write_itunesdb

logger = logging.getLogger(__name__)


def track_to_trackinfo(track: dict, ipod_filename: str) -> TrackInfo:
    """Convert a clickwheel DB track dict to an iTunesDB TrackInfo."""
    fmt = (track.get("format") or "mp3").lower()
    # iPod paths use colon separators
    ipod_path = f":iPod_Control:Music:{ipod_filename}"

    return TrackInfo(
        title=track.get("title") or "Unknown",
        location=ipod_path,
        size=track.get("file_size") or 0,
        length=int((track.get("duration_seconds") or 0) * 1000),
        filetype=fmt,
        bitrate=track.get("bitrate") or 0,
        sample_rate=track.get("sample_rate") or 44100,
        artist=track.get("artist"),
        album=track.get("album"),
        album_artist=track.get("album_artist"),
        genre=track.get("genre"),
        year=track.get("year") or 0,
        track_number=track.get("track_number") or 0,
        disc_number=track.get("disc_number") or 1,
    )


def copy_tracks_to_ipod(
    tracks: list[dict],
    ipod_mount: Path,
    progress_callback=None,
) -> list[tuple[dict, str]]:
    """Copy track files to iPod Music directory.

    Returns list of (track_dict, ipod_relative_path) tuples for tracks
    that were successfully copied.
    """
    music_dir = ipod_mount / "iPod_Control" / "Music"
    music_dir.mkdir(parents=True, exist_ok=True)

    # Create F00..F49 subdirectories
    for i in range(50):
        (music_dir / f"F{i:02d}").mkdir(exist_ok=True)

    copied: list[tuple[dict, str]] = []
    failed: list[dict] = []

    for i, track in enumerate(tracks):
        src = Path(track["path"])
        if not src.exists():
            failed.append(track)
            if progress_callback:
                progress_callback(i + 1, len(tracks))
            continue

        subdir = f"F{i % 50:02d}"
        dest = music_dir / subdir / src.name

        try:
            shutil.copy(str(src), str(dest))
            ipod_rel = f"{subdir}/{src.name}"
            copied.append((track, ipod_rel))
        except OSError:
            failed.append(track)

        if progress_callback:
            progress_callback(i + 1, len(tracks))

    return copied, failed


def unlink_ipod_track_files(
    ipod_mount: Path,
    locations: list[str],
) -> int:
    """Delete the physical track files for the given iTunesDB locations.

    iTunesDB locations are colon-prefixed paths like
    `:iPod_Control:Music:F00/foo.mp3`. We rewrite to filesystem paths
    relative to `ipod_mount` and unlink. Failures are logged but don't
    raise — partial cleanup is preferable to refusing the operation
    entirely. The iTunesDB has already been rewritten by the caller, so
    even if a file remains on disk it's no longer reachable through the
    iPod UI; it just wastes space.

    Returns the count of files successfully removed.
    """
    removed = 0
    for loc in locations:
        if not loc:
            continue
        # ":iPod_Control:Music:F00/foo.mp3" → "iPod_Control/Music/F00/foo.mp3"
        rel = loc.lstrip(":").replace(":", "/")
        target = ipod_mount / rel
        try:
            target.unlink()
            removed += 1
        except FileNotFoundError:
            # Already gone — count it as removed for the caller's
            # purposes, the user wanted it not on the iPod.
            removed += 1
        except OSError:
            logger.warning("Could not unlink %s", target, exc_info=True)
    return removed


def _existing_track_to_trackinfo(t: dict) -> TrackInfo:
    """Convert an existing iTunesDB track dict (read via
    `clickwheel.ipod.get_ipod_tracks`) back to a `TrackInfo` for re-writing.

    Preserves play counts, dates, ratings, dbid, etc. so re-writing the
    iTunesDB doesn't lose user-meaningful state. Without this round-trip
    helper, a sync would clobber every previously-written track.
    """
    played_mark = t.get("playedMark")
    return TrackInfo(
        title=t.get("title") or "Unknown",
        location=t.get("location") or "",
        size=t.get("size") or 0,
        length=t.get("length") or 0,
        filetype=t.get("filetype") or "mp3",
        bitrate=t.get("bitrate") or 0,
        sample_rate=t.get("sampleRate") or 44100,
        vbr=bool(t.get("vbr")),
        artist=t.get("artist"),
        album=t.get("album"),
        album_artist=t.get("album_artist"),
        genre=t.get("genre"),
        year=t.get("year") or 0,
        track_number=t.get("trackNumber") or 0,
        total_tracks=t.get("totalTracks") or 0,
        disc_number=t.get("discNumber") or 1,
        total_discs=t.get("totalDiscs") or 1,
        bpm=t.get("bpm") or 0,
        compilation=bool(t.get("compilation")),
        rating=t.get("rating") or 0,
        play_count=t.get("playCount") or 0,
        skip_count=t.get("skipCount") or 0,
        volume=t.get("volume") or 0,
        start_time=t.get("startTime") or 0,
        stop_time=t.get("stopTime") or 0,
        sound_check=t.get("soundCheck") or 0,
        bookmark_time=t.get("bookmarkTime") or 0,
        checked=t.get("checked") or 0,
        gapless_data=t.get("gaplessData") or 0,
        gapless_track_flag=t.get("gaplessTrackFlag") or 0,
        gapless_album_flag=t.get("gaplessAlbumFlag") or 0,
        pregap=t.get("pregap") or 0,
        postgap=t.get("postgap") or 0,
        sample_count=t.get("sampleCount") or 0,
        encoder_flag=t.get("encoderFlag") or 0,
        skip_when_shuffling=bool(t.get("skipWhenShuffling")),
        remember_position=bool(t.get("rememberPosition")),
        podcast_flag=t.get("podcastFlag") or 0,
        movie_file_flag=t.get("movieFileFlag") or 0,
        played_mark=played_mark if played_mark is not None else -1,
        explicit_flag=t.get("explicitFlag") or 0,
        date_added=t.get("dateAdded") or 0,
        date_released=t.get("dateReleased") or 0,
        last_modified=t.get("lastModified") or 0,
        last_played=t.get("lastPlayed") or 0,
        last_skipped=t.get("lastSkipped") or 0,
        track_id=t.get("trackID") or 0,
        dbid=t.get("dbid") or 0,
        # Artwork link — needed so write_artworkdb's preserve-existing
        # path recognizes this track and copies the existing image into
        # the rewritten ArtworkDB. Without these, merged tracks lose
        # their album art the next time we sync new tracks.
        mhii_link=t.get("mhiiLink") or 0,
        artwork_count=t.get("artworkCount") or 0,
        artwork_size=t.get("artworkSize") or 0,
    )


def write_ipod_db(
    ipod_mount: Path,
    copied_tracks: list[tuple[dict, str]],
    *,
    full_replace: bool = False,
    playlist_specs: "list[IpodPlaylistSpec] | None" = None,
    overwrite_playlist_names: set[str] | None = None,
    remove_track_locations: set[str] | None = None,
    remove_playlist_names: set[str] | None = None,
) -> bool:
    """Write the iTunesDB. By default MERGES with the existing iTunesDB on
    the iPod, preserving previously-synced tracks (and their play counts /
    dates / dbid / etc.). This is the only safe default — sync is supposed
    to be additive, and the underlying `write_itunesdb` is "replace
    everything" semantics, so without merging we orphan every previous
    track on the device.

    Args:
        ipod_mount: iPod mount point.
        copied_tracks: list of (clickwheel_track_dict, ipod_relative_path)
                       tuples for tracks just copied to the iPod.
        full_replace: if True, write ONLY `copied_tracks` and clobber
                      existing tracks. Use only for deliberate
                      wipe-and-fill operations. **DEFAULT FALSE** — every
                      common caller wants merge semantics.
        playlist_specs: optional list of IpodPlaylistSpec entries to
                        write as user-visible playlists under
                        Music → Playlists on the device. Each spec's
                        tracks are matched to TrackInfo dbids via the
                        merged track list and emitted as a PlaylistInfo
                        with the right references.
        overwrite_playlist_names: names of existing iPod-side playlists
                        that should NOT be preserved during merge. Used
                        when the caller is replacing/renaming a same-
                        name playlist. Defaults to the names in
                        `playlist_specs` (replace-on-write semantics).
        remove_track_locations: iTunesDB `location` strings (with colon
                        prefix) for tracks to drop from the rewritten
                        iTunesDB. Used by `remove_tracks_from_ipod`.
                        The caller is responsible for unlinking the
                        physical files separately — this function only
                        rewrites the database.
        remove_playlist_names: names of iPod-side playlists to drop
                        from the rewritten iTunesDB. Used by
                        `remove_ipod_playlist`. Tracks referenced by
                        the removed playlist are NOT deleted from the
                        library — only the playlist artifact goes away.

    Returns True on success. If reading the existing iTunesDB fails (corrupt
    db, share unmounted mid-call), the merge step is skipped with a logged
    warning and only `copied_tracks` are written — degraded but doesn't
    crash. The fail-soft is intentional: a merge failure shouldn't lose
    the new tracks the user just copied.
    """
    from clickwheel.ipod import get_ipod_playlists, get_ipod_tracks, read_ipod
    from clickwheel.ipod.itunesdb_writer.mhit_writer import generate_dbid
    from clickwheel.ipod.itunesdb_writer.mhyp_writer import PlaylistInfo

    # Local import to avoid circular dep (actions imports sync).
    from clickwheel.actions import IpodPlaylistSpec  # noqa: F401

    new_track_infos: list[TrackInfo] = []
    pc_file_paths: dict[int, str] = {}
    new_locations: set[str] = set()
    new_triple_to_dbid: dict[tuple[str, str, str], int] = {}

    for track, ipod_rel in copied_tracks:
        ti = track_to_trackinfo(track, ipod_rel)
        if ti.dbid == 0:
            # Pre-assign so playlist_specs can reference newly-copied
            # tracks. write_itunesdb would otherwise lazy-assign during
            # write — too late for our matching pass below.
            ti.dbid = generate_dbid()
        new_track_infos.append(ti)
        new_locations.add(ti.location)
        if track.get("path"):
            pc_file_paths[ti.track_id] = track["path"]
        triple = (
            (track.get("artist") or ""),
            (track.get("album") or ""),
            (track.get("title") or ""),
        )
        new_triple_to_dbid[triple] = ti.dbid

    track_infos: list[TrackInfo] = list(new_track_infos)
    existing_triple_to_dbid: dict[tuple[str, str, str], int] = {}
    existing_playlists: list[dict] = []

    remove_locs = remove_track_locations or set()

    if not full_replace:
        try:
            ipod_db = read_ipod(ipod_mount)
            existing_tracks = get_ipod_tracks(ipod_db)
            existing_playlists = get_ipod_playlists(ipod_db)
            # Build trackID → dbid for preserved playlists.
            track_id_to_dbid: dict[int, int] = {}
            for t in existing_tracks:
                loc = t.get("location") or ""
                if loc in new_locations:
                    continue  # new copy wins for matching paths
                if loc in remove_locs:
                    continue  # caller asked us to drop this track
                ti = _existing_track_to_trackinfo(t)
                track_infos.append(ti)
                triple = (
                    (ti.artist or ""),
                    (ti.album or ""),
                    (ti.title or ""),
                )
                existing_triple_to_dbid[triple] = ti.dbid
                tid = t.get("trackID")
                if tid is not None and ti.dbid:
                    track_id_to_dbid[tid] = ti.dbid
        except Exception:
            logger.exception(
                "Could not read existing iTunesDB for merge; writing only "
                "newly-copied tracks (existing tracks would be orphaned)"
            )
            track_id_to_dbid = {}
    else:
        track_id_to_dbid = {}

    if not track_infos:
        logger.warning("No tracks to write to iTunesDB")
        return False

    # Build PlaylistInfo list: new specs + preserved existing.
    triple_to_dbid = {**existing_triple_to_dbid, **new_triple_to_dbid}
    # new_* wins on conflict because the new copy supersedes the old.

    new_playlist_infos: list[PlaylistInfo] = []
    if playlist_specs:
        for spec in playlist_specs:
            ids: list[int] = []
            for ct in spec.tracks:
                triple = (
                    (ct.get("artist") or ""),
                    (ct.get("album") or ""),
                    (ct.get("title") or ""),
                )
                dbid = triple_to_dbid.get(triple)
                if dbid:
                    ids.append(dbid)
            new_playlist_infos.append(
                PlaylistInfo(name=spec.name, track_ids=ids)
            )

    # Preserve existing iPod playlists not being replaced. Smart
    # playlists pass through too — they aren't user-managed via
    # clickwheel today, but we don't want to lose them on rewrite.
    new_names = (
        overwrite_playlist_names
        if overwrite_playlist_names is not None
        else {spec.name for spec in (playlist_specs or [])}
    )
    drop_names = remove_playlist_names or set()
    preserved_playlist_infos: list[PlaylistInfo] = []
    for raw in existing_playlists:
        name = raw.get("name") or ""
        if name in new_names:
            continue  # explicitly being replaced
        if name in drop_names:
            continue  # explicitly being removed
        if raw.get("is_smart"):
            # Smart playlists need their preferences/rules preserved to
            # remain functional. Punt on that for now — drop them rather
            # than write a broken stub. (Pre-existing user-created smart
            # playlists are rare on the kinds of devices clickwheel
            # targets; this is a known limitation worth revisiting.)
            continue
        dbids = []
        for tid in raw.get("item_track_ids", []):
            dbid = track_id_to_dbid.get(tid)
            if dbid:
                dbids.append(dbid)
        preserved_playlist_infos.append(
            PlaylistInfo(name=name, track_ids=dbids)
        )

    all_playlists = new_playlist_infos + preserved_playlist_infos

    try:
        return write_itunesdb(
            ipod_path=str(ipod_mount),
            tracks=track_infos,
            pc_file_paths=pc_file_paths if pc_file_paths else None,
            playlists=all_playlists if all_playlists else None,
        )
    except Exception:
        logger.exception("Failed to write iTunesDB")
        return False
