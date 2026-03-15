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
    errors = 0

    for i, track in enumerate(tracks):
        src = Path(track["path"])
        if not src.exists():
            logger.warning("Source file not found: %s", src)
            errors += 1
            continue

        subdir = f"F{i % 50:02d}"
        dest = music_dir / subdir / src.name

        try:
            shutil.copy2(str(src), str(dest))
            ipod_rel = f"{subdir}/{src.name}"
            copied.append((track, ipod_rel))
        except OSError as exc:
            logger.warning("Failed to copy %s: %s", src, exc)
            errors += 1

        if progress_callback:
            progress_callback(i + 1, len(tracks))

    return copied


def write_ipod_db(
    ipod_mount: Path,
    copied_tracks: list[tuple[dict, str]],
) -> bool:
    """Write the iTunesDB and ArtworkDB for all tracks on the iPod.

    Args:
        ipod_mount: iPod mount point
        copied_tracks: list of (track_dict, ipod_relative_path) tuples

    Returns True on success.
    """
    track_infos = []
    pc_file_paths = {}

    for track, ipod_rel in copied_tracks:
        ti = track_to_trackinfo(track, ipod_rel)
        track_infos.append(ti)
        # Map source file path by dbid for artwork extraction
        if track.get("path"):
            pc_file_paths[ti.track_id] = track["path"]

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
