"""Pure-logic actions consumed by both the CLI and the MCP server.

Functions here return data (and accept progress callbacks) without touching
Rich, tqdm, typer, or questionary. The CLI adapts these calls to interactive
output; the MCP server adapts them to structured tool responses.

Errors are raised as typed exceptions so callers can map them to their own
error surface (typer.Exit, McpError, etc.).
"""

from __future__ import annotations

import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from clickwheel.config import Config
from clickwheel.db import Database
from clickwheel.library import AUDIO_EXTENSIONS, scan_file

# Strips trailing "feat./featuring/with X" annotations. Anchored to a
# word boundary on the keyword so band names that happen to contain
# "feat" survive. Optional opening paren handles "(feat. X)" too.
_FEAT_SUFFIX_RE = re.compile(
    r"\s+\(?(?:feat\.?|featuring|with)\s+.*$",
    re.IGNORECASE,
)


def primary_artist(
    artist: str | None,
    album_artist: str | None = None,
) -> str:
    """Pick a canonical lead-artist label for rollup/grouping purposes.

    Strategy mirrors iTunes/Music itself: trust `album_artist` as the
    authoritative field, fall back to `artist` only when album_artist
    is empty or a compilation marker. We do NOT try to parse multi-
    artist strings — every plausible separator (",", "/", "&", "and")
    appears in legitimate band names ("Crosby, Stills and Nash",
    "AC/DC", "Belle & Sebastian", "Sly and the Family Stone"), so any
    regex-based split will misclassify real artists as collabs.

    The single piece of normalization we apply is stripping trailing
    "feat. X" / "featuring X" / "with X" annotations, which are
    unambiguous. Useful as a safety net for tags that leak those
    annotations into the album_artist field.

    For users whose tags don't disambiguate well, the right fix is
    re-tagging with beets or Picard (which link to MusicBrainz IDs and
    write a clean album_artist), not smarter parsing here.
    """
    chosen: str | None = None
    if album_artist:
        aa = album_artist.strip()
        if aa and aa.casefold() != "various artists":
            chosen = aa
    if not chosen and artist:
        chosen = artist.strip()
    if not chosen:
        return "Unknown"
    cleaned = _FEAT_SUFFIX_RE.sub("", chosen).strip()
    return cleaned or "Unknown"


class ClickwheelError(Exception):
    """Base class for user-facing clickwheel errors."""


class LibraryNotFoundError(ClickwheelError):
    """Music library directory doesn't exist."""


class PlaylistNotFoundError(ClickwheelError):
    """Named playlist doesn't exist."""


class IpodNotFoundError(ClickwheelError):
    """iPod not mounted or not detected."""


class LastfmNotConfiguredError(ClickwheelError):
    """Last.fm API key, secret, or session key is missing."""


class InsufficientSpaceError(ClickwheelError):
    """iPod doesn't have enough free space for the requested operation."""


class EjectFailedError(ClickwheelError):
    """`diskutil eject` returned a non-zero exit code."""


class MissingTracksError(ClickwheelError):
    """A playlist references tracks whose files are no longer on disk.

    Carries a list of the offending tracks so callers can surface them
    or hand them to `heal_playlist`. The text message is a short summary;
    consult `.missing_tracks` for details.
    """

    def __init__(self, message: str, missing_tracks: list[dict]) -> None:
        super().__init__(message)
        self.missing_tracks = missing_tracks


class PathsNotFoundError(ClickwheelError):
    """One or more requested paths aren't in the indexed library.

    Caller should usually surface the offending paths and suggest a
    `clickwheel scan`. Most commonly raised by `add_tracks_to_ipod`
    when the LLM passes a path that doesn't exist in the SQLite index.
    """

    def __init__(self, message: str, unknown_paths: list[str]) -> None:
        super().__init__(message)
        self.unknown_paths = unknown_paths


@dataclass
class ScanResult:
    total: int = 0
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    missing: int = 0
    errors: int = 0


@dataclass
class ScanProgress:
    current: int
    total: int
    added: int
    updated: int
    unchanged: int
    errors: int


@dataclass
class Diff:
    """Add/remove/unchanged sets between a playlist and the iPod.

    `to_add` carries full track dicts (in playlist order) because sync needs
    file paths and sizes. `to_remove` and `unchanged` are (artist, album, title)
    tuples — those tracks live on the iPod, not in our DB.
    """

    playlist: str
    to_add: list[dict] = field(default_factory=list)
    to_remove: list[tuple[str, str, str]] = field(default_factory=list)
    unchanged: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def add_size_bytes(self) -> int:
        return sum(t.get("file_size") or 0 for t in self.to_add)

    def to_add_display(self) -> list[tuple[str, str, str]]:
        return sorted(
            (t["artist"] or "", t["album"] or "", t["title"] or "") for t in self.to_add
        )


@dataclass
class SyncEvent:
    """Emitted during sync_playlist for each track copy attempt."""

    current: int
    total: int
    track: dict
    ok: bool


@dataclass
class SyncResult:
    copied: list[dict] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    # Tracks that exist on the iPod but aren't in the playlist being synced.
    # NOT removed — sync is additive. Renamed from `removed_count` (which
    # lied) after a Phase 5 finding where the LLM correctly flagged the
    # contradiction with the "additive only" docstring.
    kept_in_place_count: int = 0
    # Whether the iPod's library was successfully updated to reference the
    # newly-copied tracks. False means the music files made it to the
    # device but the iPod won't see them yet. Renamed from `db_write_ok`
    # to keep user-facing copy free of the iTunesDB acronym.
    library_updated: bool = True


@dataclass
class ScrobbleSubmitResult:
    plays_found: int = 0
    new_cached: int = 0
    submitted: int = 0
    failed: int = 0
    remaining_pending: int = 0
    oldest_age_days: float | None = None


# ---------------------------------------------------------------------------
# Library scanning
# ---------------------------------------------------------------------------


def scan_library(
    cfg: Config,
    db: Database,
    *,
    full: bool = False,
    on_found: Callable[[int], None] | None = None,
    on_progress: Callable[[ScanProgress], None] | None = None,
) -> ScanResult:
    """Walk the music library and update the index.

    full=True clears the DB and re-scans every file. full=False (default) is
    incremental: skip files whose mtime+size match the DB, mark vanished files
    as missing.

    Raises LibraryNotFoundError if cfg.music_dir doesn't exist.
    """
    if not cfg.music_dir.is_dir():
        raise LibraryNotFoundError(f"Music folder not found: {cfg.music_dir}")

    if full:
        db.clear_tracks()

    # Phase 1: discover audio files on disk
    disk_files: list[Path] = []
    for entry in cfg.music_dir.rglob("*"):
        if entry.suffix.lower() in AUDIO_EXTENSIONS:
            disk_files.append(entry)
            if on_found is not None:
                on_found(len(disk_files))
    disk_files.sort()

    result = ScanResult(total=len(disk_files))
    db_paths = db.get_all_tracked_paths() if not full else set()

    # Phase 2: per-file scan, comparing against DB unless full
    for i, path in enumerate(disk_files, 1):
        try:
            stat = path.stat()
        except OSError:
            result.errors += 1
            _emit_scan_progress(on_progress, i, result)
            continue

        if not full:
            db_mtime, db_size = db.get_track_mtime(str(path))
            if (
                db_mtime is not None
                and db_size is not None
                and stat.st_mtime == db_mtime
                and stat.st_size == db_size
            ):
                result.unchanged += 1
                if str(path) not in db_paths:
                    db.clear_missing(str(path))
                _emit_scan_progress(on_progress, i, result)
                continue

            track = scan_file(path)
            if track:
                db.upsert_track(track)
                if str(path) in db_paths:
                    result.updated += 1
                else:
                    result.added += 1
            else:
                result.errors += 1
        else:
            track = scan_file(path)
            if track:
                db.upsert_track(track)
                result.added += 1
            else:
                result.errors += 1

        if (result.added + result.updated) % 500 == 0:
            db.commit()
        _emit_scan_progress(on_progress, i, result)

    db.commit()

    # Phase 3: detect deleted files (incremental only)
    if not full:
        disk_paths = {str(p) for p in disk_files}
        missing_paths = db_paths - disk_paths
        if missing_paths:
            result.missing = db.mark_missing(missing_paths)

    db.set_scan_meta("last_scan_completed", str(time.time()))

    # Write the cheap-probe baseline so future autoscan checks can skip
    # full walks when nothing's changed at the top level.
    from clickwheel.autoscan import _max_child_mtime

    current_max = _max_child_mtime(cfg.music_dir)
    if current_max is not None:
        db.set_scan_meta("last_probe_max_child_mtime", str(current_max))

    return result


def _emit_scan_progress(
    cb: Callable[[ScanProgress], None] | None,
    current: int,
    result: ScanResult,
) -> None:
    if cb is None:
        return
    cb(
        ScanProgress(
            current=current,
            total=result.total,
            added=result.added,
            updated=result.updated,
            unchanged=result.unchanged,
            errors=result.errors,
        )
    )


def library_stats(db: Database) -> dict:
    """Return combined library stats and format breakdown."""
    return {
        "stats": db.get_stats(),
        "formats": db.get_format_breakdown(),
    }


def library_health(cfg: Config, db: Database) -> dict:
    """Return a quick health probe of the library setup.

    Useful as a "is everything wired up?" check from an MCP client.
    """
    last_scan = db.get_scan_meta("last_scan_completed")
    last_scan_ts = float(last_scan) if last_scan else None

    missing_count = db.conn.execute(
        "SELECT COUNT(*) FROM tracks WHERE missing_since IS NOT NULL"
    ).fetchone()[0]

    total_count = db.conn.execute(
        "SELECT COUNT(*) FROM tracks WHERE missing_since IS NULL"
    ).fetchone()[0]

    return {
        "library_dir": str(cfg.music_dir),
        "library_dir_exists": cfg.music_dir.is_dir(),
        "total_tracks": total_count,
        "missing_tracks": missing_count,
        "last_scan_at": last_scan_ts,
        "auto_scan_enabled": cfg.auto_scan,
    }


def search_tracks(db: Database, query: str, limit: int = 50) -> list[dict]:
    """Substring search across artist, album, and title.

    Case-insensitive. Returns at most `limit` results, newest scans first.
    """
    if not query.strip():
        return []
    pattern = f"%{query.strip()}%"
    rows = db.conn.execute(
        """
        SELECT path, artist, album, title, duration_seconds, file_size, format
        FROM tracks
        WHERE missing_since IS NULL
          AND (
            artist LIKE ? COLLATE NOCASE
            OR album LIKE ? COLLATE NOCASE
            OR title LIKE ? COLLATE NOCASE
          )
        ORDER BY artist COLLATE NOCASE, album COLLATE NOCASE, track_number
        LIMIT ?
        """,
        (pattern, pattern, pattern, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Library and playlist queries (thin wrappers, here so callers don't need to
# touch the Database API directly)
# ---------------------------------------------------------------------------


def list_artists(db: Database) -> list[dict]:
    return db.get_artists()


def list_albums_by_artist(db: Database, artist: str) -> list[dict]:
    return db.get_albums_by_artist(artist)


def list_tracks_by_album(db: Database, artist: str, album: str) -> list[dict]:
    return db.get_tracks_by_album(artist, album)


def list_playlists(db: Database) -> list[dict]:
    return db.list_playlists()


def get_playlist(db: Database, name: str) -> list[dict]:
    """Return tracks in a playlist. Raises PlaylistNotFoundError if missing."""
    tracks = db.get_playlist(name)
    if not tracks:
        raise PlaylistNotFoundError(f"Playlist '{name}' not found.")
    return tracks


def get_playlist_artists(db: Database, name: str) -> list[dict]:
    return db.get_playlist_artists(name)


def get_playlist_size(db: Database, name: str) -> int:
    return db.get_playlist_size(name)


# ---------------------------------------------------------------------------
# Playlist mutations
# ---------------------------------------------------------------------------


class PlaylistAlreadyExistsError(ClickwheelError):
    """A playlist with the given name already exists."""


def playlist_exists(db: Database, name: str) -> bool:
    row = db.conn.execute("SELECT 1 FROM playlists WHERE name = ?", (name,)).fetchone()
    return row is not None


def save_playlist(db: Database, name: str, track_paths: list[str]) -> None:
    db.save_playlist(name, track_paths)


def create_playlist(db: Database, name: str, track_paths: list[str]) -> int:
    """Create a new playlist. Raises PlaylistAlreadyExistsError if `name`
    is taken — callers should use `update_playlist` to overwrite.

    Returns the number of tracks actually persisted (paths not in the index
    are silently skipped by the DB layer).
    """
    if playlist_exists(db, name):
        raise PlaylistAlreadyExistsError(
            f"Playlist '{name}' already exists. "
            "Use update_playlist to replace its contents."
        )
    db.save_playlist(name, track_paths)
    return len(db.get_playlist(name))


def update_playlist(
    db: Database, name: str, track_paths: list[str]
) -> tuple[int, bool]:
    """Replace a playlist's contents (or create it if it doesn't exist).

    Returns (track_count, replaced) — `replaced` is True if a playlist by
    this name already existed.
    """
    replaced = playlist_exists(db, name)
    db.save_playlist(name, track_paths)
    return len(db.get_playlist(name)), replaced


def delete_playlist(db: Database, name: str) -> bool:
    """Delete a playlist by name. Raises PlaylistNotFoundError if it doesn't
    exist (callers that prefer no-op-on-missing can catch and ignore)."""
    if not playlist_exists(db, name):
        raise PlaylistNotFoundError(f"Playlist '{name}' not found.")
    return db.delete_playlist(name)


def heal_playlist(db: Database, name: str) -> dict:
    """Drop playlist references to tracks flagged missing on disk.

    Uses the DB's `missing_since` flag (set by `clickwheel scan`), so the
    accuracy depends on scan freshness. For real-time accuracy, run a
    scan first.

    Returns a dict with:
      - dropped: number of references removed
      - remaining: number of tracks still in the playlist
      - dropped_tracks: list of removed track records (artist, album, title,
        path) so callers can show the user what was dropped

    Raises PlaylistNotFoundError if the playlist doesn't exist.
    """
    if not playlist_exists(db, name):
        raise PlaylistNotFoundError(f"Playlist '{name}' not found.")

    dropped_tracks = db.get_missing_tracks_in_playlist(name)
    dropped = db.remove_missing_tracks_from_playlist(name)
    remaining = len(db.get_playlist(name))
    return {
        "dropped": dropped,
        "remaining": remaining,
        "dropped_tracks": dropped_tracks,
    }


def add_artist_to_playlist(db: Database, playlist: str, artist: str) -> int:
    return db.add_artist_to_playlist(playlist, artist)


def remove_artist_from_playlist(db: Database, playlist: str, artist: str) -> int:
    return db.remove_artist_from_playlist(playlist, artist)


def collect_tracks_for_artist(db: Database, artist: str) -> list[str]:
    """All track paths for a single artist, ordered by album/track.

    Caller is responsible for dedup across multiple artists.
    """
    paths: list[str] = []
    seen: set[str] = set()
    for album in db.get_albums_by_artist(artist):
        for track in db.get_tracks_by_album(artist, album["album"]):
            p = track["path"]
            if p not in seen:
                seen.add(p)
                paths.append(p)
    return paths


def calc_size_of_paths(db: Database, paths: list[str]) -> int:
    if not paths:
        return 0
    placeholders = ",".join("?" * len(paths))
    row = db.conn.execute(
        f"SELECT COALESCE(SUM(file_size), 0) AS total "
        f"FROM tracks WHERE path IN ({placeholders})",
        paths,
    ).fetchone()
    return row["total"] if row else 0


# ---------------------------------------------------------------------------
# iPod inspection
# ---------------------------------------------------------------------------


def require_ipod(cfg: Config) -> dict:
    """Find and read the iPod database. Raises IpodNotFoundError if missing."""
    from clickwheel.ipod import find_ipod, read_ipod

    if not find_ipod(cfg.ipod_mount):
        raise IpodNotFoundError(
            "No iPod found. Make sure it's plugged in and shows up in Finder."
        )
    return read_ipod(cfg.ipod_mount)


def read_ipod_track_list(ipod_db: dict) -> list[dict]:
    from clickwheel.ipod import get_ipod_tracks

    return get_ipod_tracks(ipod_db)


def read_ipod_contents(cfg: Config) -> dict:
    """Return iPod track list plus capacity/usage. Raises IpodNotFoundError."""
    ipod_db = require_ipod(cfg)
    tracks = read_ipod_track_list(ipod_db)
    total_size = sum(t.get("size", 0) for t in tracks)
    try:
        usage = shutil.disk_usage(str(cfg.ipod_mount))
        capacity = usage.total
        used = usage.used
        free = usage.free
    except OSError:
        capacity = cfg.ipod_capacity_bytes
        used = total_size
        free = max(0, capacity - used)
    return {
        "capacity_bytes": capacity,
        "used_bytes": used,
        "free_bytes": free,
        "tracks": tracks,
    }


def list_ipod_tracks(
    cfg: Config,
    *,
    artist: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Paginated list of iPod tracks, optionally filtered by artist.

    Caller passes an absolute offset/limit window. Use this to drill into
    the iPod's contents without paying for the whole track manifest in one
    response. Raises IpodNotFoundError.
    """
    ipod_db = require_ipod(cfg)
    tracks = read_ipod_track_list(ipod_db)
    if artist:
        tracks = [t for t in tracks if t.get("artist") == artist]
    return tracks[offset : offset + limit]


def list_playlist_tracks(
    db: Database,
    name: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Paginated list of tracks in a saved playlist.

    Raises PlaylistNotFoundError.
    """
    if not playlist_exists(db, name):
        raise PlaylistNotFoundError(f"Playlist '{name}' not found.")
    tracks = db.get_playlist(name)
    return tracks[offset : offset + limit]


# ---------------------------------------------------------------------------
# Sync (diff + copy)
# ---------------------------------------------------------------------------


def compute_diff(cfg: Config, db: Database, playlist_name: str) -> Diff:
    """Compute add/remove/unchanged sets between a playlist and the iPod.

    Raises PlaylistNotFoundError, IpodNotFoundError.
    """
    ipod_db = require_ipod(cfg)
    ipod_tracks = read_ipod_track_list(ipod_db)
    ipod_set = {
        (t.get("artist", ""), t.get("album", ""), t.get("title", ""))
        for t in ipod_tracks
    }

    playlist_tracks = db.get_playlist(playlist_name)
    if not playlist_tracks:
        raise PlaylistNotFoundError(f"Playlist '{playlist_name}' not found.")

    playlist_set = {
        (t["artist"] or "", t["album"] or "", t["title"] or "") for t in playlist_tracks
    }

    to_add = [
        t
        for t in playlist_tracks
        if (t["artist"] or "", t["album"] or "", t["title"] or "") not in ipod_set
    ]

    return Diff(
        playlist=playlist_name,
        to_add=to_add,
        to_remove=sorted(ipod_set - playlist_set),
        unchanged=sorted(playlist_set & ipod_set),
    )


def sync_playlist(
    cfg: Config,
    db: Database,
    playlist_name: str,
    *,
    diff: Diff | None = None,
    on_event: Callable[[SyncEvent], None] | None = None,
) -> SyncResult:
    """Copy tracks from a playlist to the iPod and update the iPod's library.

    Confirmation is the caller's job. This function actually performs the sync.
    Pass a pre-computed `diff` (e.g. from a preview) to avoid re-reading the
    iPod.

    Pre-flight checks:
    - LibraryNotFoundError if cfg.music_dir isn't reachable (catches
      unmounted-share cases before we hang on per-file timeouts).
    - MissingTracksError if any playlist tracks are flagged missing on
      disk (catches stale-playlist cases — files were moved/deleted since
      the playlist was built). The error carries the missing tracks so
      callers can suggest `heal_playlist`.

    Raises PlaylistNotFoundError, IpodNotFoundError, InsufficientSpaceError.
    """
    from clickwheel.ipod.sync import copy_tracks_to_ipod, write_ipod_db

    if not cfg.music_dir.is_dir():
        raise LibraryNotFoundError(
            f"Music library at {cfg.music_dir} isn't mounted. "
            "Mount the share before syncing."
        )

    if diff is None:
        diff = compute_diff(cfg, db, playlist_name)

    missing = db.get_missing_tracks_in_playlist(playlist_name)
    if missing:
        # Only block on missing tracks that are actually in the to-add set —
        # tracks already on the iPod are safe even if their source files are
        # gone (we're not re-copying them).
        to_add_paths = {t["path"] for t in diff.to_add}
        blocking = [t for t in missing if t["path"] in to_add_paths]
        if blocking:
            raise MissingTracksError(
                f"{len(blocking)} track(s) in '{playlist_name}' reference "
                "files that no longer exist on disk. Run `clickwheel heal "
                f"{playlist_name}` (or the heal_playlist MCP tool) to drop "
                "the dead references, then re-add via `clickwheel edit "
                "--add` or `add_artist_to_playlist`.",
                blocking,
            )

    to_add = diff.to_add
    add_size = diff.add_size_bytes

    ipod_stat = shutil.disk_usage(str(cfg.ipod_mount))
    if add_size > ipod_stat.free:
        raise InsufficientSpaceError(
            f"Not enough space on iPod. "
            f"Need {add_size} bytes but only {ipod_stat.free} free."
        )

    total_count = len(to_add)

    def _on_progress(current: int, total: int) -> None:
        if on_event is None or current < 1 or current > total_count:
            return
        track = to_add[current - 1]
        on_event(SyncEvent(current=current, total=total_count, track=track, ok=True))

    copied, failed = copy_tracks_to_ipod(to_add, cfg.ipod_mount, _on_progress)
    db_ok = write_ipod_db(cfg.ipod_mount, copied)

    return SyncResult(
        copied=copied,
        failed=failed,
        kept_in_place_count=len(diff.to_remove),
        library_updated=db_ok,
    )


def add_tracks_to_ipod(
    cfg: Config,
    db: Database,
    paths: list[str],
    *,
    on_event: Callable[[SyncEvent], None] | None = None,
) -> SyncResult:
    """Push specific tracks to the iPod's library without creating a playlist.

    Use this for the common "add this artist / these albums to my iPod"
    flow where the user doesn't need a curated, named playlist on the
    device. The tracks land in the master library and are browsable by
    artist/album. For a curated playlist that shows up under Music →
    Playlists on the iPod itself, use sync_playlist_to_ipod instead.

    Behavior mirrors `sync_playlist`: dedupes against what's already on
    the iPod (sync is additive — never deletes), space-checks before
    copying, streams per-track progress via `on_event`.

    Raises
    ------
    LibraryNotFoundError
        cfg.music_dir isn't reachable.
    PathsNotFoundError
        One or more paths aren't in the indexed library.
    MissingTracksError
        One or more paths point to files that no longer exist on disk.
    IpodNotFoundError
        No iPod mounted.
    InsufficientSpaceError
        New tracks won't fit.
    """
    from clickwheel.ipod import get_ipod_tracks
    from clickwheel.ipod.sync import copy_tracks_to_ipod, write_ipod_db

    if not cfg.music_dir.is_dir():
        raise LibraryNotFoundError(
            f"Music library at {cfg.music_dir} isn't mounted. "
            "Mount the share before adding tracks."
        )

    # Resolve paths → full track records via the library DB.
    tracks: list[dict] = []
    unknown: list[str] = []
    missing: list[dict] = []
    for path in paths:
        row = db.conn.execute("SELECT * FROM tracks WHERE path = ?", (path,)).fetchone()
        if row is None:
            unknown.append(path)
            continue
        track = dict(row)
        if track.get("missing_since") is not None:
            missing.append(track)
            continue
        tracks.append(track)

    if unknown:
        raise PathsNotFoundError(
            f"{len(unknown)} of {len(paths)} paths aren't in the library "
            "index. Run `clickwheel scan` if you've added music since the "
            "last scan, or check the paths for typos.",
            unknown,
        )
    if missing:
        raise MissingTracksError(
            f"{len(missing)} of {len(paths)} tracks reference files that no "
            "longer exist on disk. Run `clickwheel scan` to refresh the "
            "index, then retry.",
            missing,
        )

    # Diff against the iPod so we don't re-copy tracks that are already there.
    ipod_db = require_ipod(cfg)
    ipod_tracks = get_ipod_tracks(ipod_db)
    ipod_set = {
        (t.get("artist") or "", t.get("album") or "", t.get("title") or "")
        for t in ipod_tracks
    }
    to_add = [
        t
        for t in tracks
        if (t["artist"] or "", t["album"] or "", t["title"] or "") not in ipod_set
    ]

    add_size = sum(t.get("file_size") or 0 for t in to_add)
    ipod_stat = shutil.disk_usage(str(cfg.ipod_mount))
    if add_size > ipod_stat.free:
        raise InsufficientSpaceError(
            f"Not enough space on iPod. "
            f"Need {add_size} bytes but only {ipod_stat.free} free."
        )

    total_count = len(to_add)

    def _on_progress(current: int, total: int) -> None:
        if on_event is None or current < 1 or current > total_count:
            return
        track = to_add[current - 1]
        on_event(SyncEvent(current=current, total=total_count, track=track, ok=True))

    copied, failed = copy_tracks_to_ipod(to_add, cfg.ipod_mount, _on_progress)
    db_ok = write_ipod_db(cfg.ipod_mount, copied)

    # kept_in_place_count: how many requested tracks were already there.
    already_present = len(tracks) - len(to_add)
    return SyncResult(
        copied=copied,
        failed=failed,
        kept_in_place_count=already_present,
        library_updated=db_ok,
    )


def retry_ipod_db_write(cfg: Config, copied: list[dict]) -> bool:
    from clickwheel.ipod.sync import write_ipod_db

    return write_ipod_db(cfg.ipod_mount, copied)


def eject_ipod(cfg: Config) -> dict:
    """Safely unmount the iPod via `diskutil eject`.

    Verifies the iPod is mounted first. Returns a status dict with the mount
    path. Raises IpodNotFoundError if the iPod isn't mounted, or
    EjectFailedError if diskutil exits non-zero.
    """
    import subprocess

    require_ipod(cfg)

    result = subprocess.run(
        ["diskutil", "eject", str(cfg.ipod_mount)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise EjectFailedError(result.stderr.strip() or "diskutil eject failed")
    return {"ejected": True, "mount": str(cfg.ipod_mount)}


# ---------------------------------------------------------------------------
# Scrobbling
# ---------------------------------------------------------------------------


def read_pending_scrobbles(db: Database) -> list[dict]:
    from clickwheel.scrobble import get_pending_scrobbles

    return get_pending_scrobbles(db.conn)


def collect_ipod_plays(cfg: Config, db: Database) -> dict:
    """Read recent plays from iPod and cache them. Returns a status dict.

    Useful as a step before submitting — separates the "read iPod" from the
    "submit to Last.fm" flow.

    Raises IpodNotFoundError.
    """
    from clickwheel.scrobble import cache_scrobbles, read_ipod_plays

    require_ipod(cfg)  # validate mount only
    plays = read_ipod_plays(cfg.ipod_mount)

    oldest_age_days: float | None = None
    if plays:
        now = int(time.time())
        oldest = min(p.timestamp for p in plays)
        oldest_age_days = (now - oldest) / 86400

    new_cached = cache_scrobbles(db.conn, plays) if plays else 0
    return {
        "plays_found": len(plays),
        "new_cached": new_cached,
        "oldest_age_days": oldest_age_days,
    }


def submit_pending_scrobbles(
    cfg: Config,
    db: Database,
    pending: list[dict] | None = None,
) -> ScrobbleSubmitResult:
    """Submit pending scrobbles to Last.fm.

    If `pending` is None, reads pending from the cache. Caller should verify
    cfg.lastfm_session_key beforehand or accept the LastfmNotConfiguredError.

    Raises LastfmNotConfiguredError.
    """
    from clickwheel.scrobble import get_pending_scrobbles, submit_scrobbles

    if not cfg.lastfm_api_key or not cfg.lastfm_api_secret:
        raise LastfmNotConfiguredError(
            "Last.fm API key/secret missing. "
            "Add them to ~/.clickwheel/config.yaml or .env."
        )
    if not cfg.lastfm_session_key:
        raise LastfmNotConfiguredError(
            "Last.fm not authorized. "
            "Run `clickwheel scrobble --auth` to connect your account."
        )

    if pending is None:
        pending = get_pending_scrobbles(db.conn)

    if not pending:
        return ScrobbleSubmitResult()

    submitted, failed = submit_scrobbles(
        cfg.lastfm_api_key,
        cfg.lastfm_api_secret,
        cfg.lastfm_username,
        pending,
        db.conn,
        session_key=cfg.lastfm_session_key,
    )
    remaining = len(get_pending_scrobbles(db.conn))
    return ScrobbleSubmitResult(
        submitted=submitted,
        failed=failed,
        remaining_pending=remaining,
    )
