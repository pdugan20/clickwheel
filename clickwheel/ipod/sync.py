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

    Returns True on success. If reading the existing iTunesDB fails (corrupt
    db, share unmounted mid-call), the merge step is skipped with a logged
    warning and only `copied_tracks` are written — degraded but doesn't
    crash. The fail-soft is intentional: a merge failure shouldn't lose
    the new tracks the user just copied.
    """
    from clickwheel.ipod import get_ipod_tracks, read_ipod

    new_track_infos: list[TrackInfo] = []
    pc_file_paths: dict[int, str] = {}
    new_locations: set[str] = set()

    for track, ipod_rel in copied_tracks:
        ti = track_to_trackinfo(track, ipod_rel)
        new_track_infos.append(ti)
        new_locations.add(ti.location)
        if track.get("path"):
            pc_file_paths[ti.track_id] = track["path"]

    track_infos: list[TrackInfo] = list(new_track_infos)

    if not full_replace:
        try:
            existing = get_ipod_tracks(read_ipod(ipod_mount))
            for t in existing:
                loc = t.get("location") or ""
                if loc in new_locations:
                    continue  # new copy wins for matching paths
                track_infos.append(_existing_track_to_trackinfo(t))
        except Exception:
            logger.exception(
                "Could not read existing iTunesDB for merge; writing only "
                "newly-copied tracks (existing tracks would be orphaned)"
            )

    if not track_infos:
        logger.warning("No tracks to write to iTunesDB")
        return False

    try:
        return write_itunesdb(
            ipod_path=str(ipod_mount),
            tracks=track_infos,
            pc_file_paths=pc_file_paths if pc_file_paths else None,
        )
    except Exception:
        logger.exception("Failed to write iTunesDB")
        return False
