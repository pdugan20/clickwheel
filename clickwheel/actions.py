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


class PlaylistConflictError(ClickwheelError):
    """A playlist with the same name already exists on the iPod.

    Raised by `sync_playlist` when called without an `on_conflict`
    decision and a same-name iPod-side playlist exists. The MCP tool
    surface catches this and turns it into a structured "please pick
    an option" response so the LLM can ask the user how to proceed.
    """

    def __init__(
        self,
        message: str,
        existing_name: str,
        existing_track_count: int,
    ) -> None:
        super().__init__(message)
        self.existing_name = existing_name
        self.existing_track_count = existing_track_count


class PlexNotConfiguredError(ClickwheelError):
    """Plex integration is disabled or missing credentials."""


class PlexExtraNotInstalledError(ClickwheelError):
    """The `clickwheel[plex]` extra (plexapi) isn't installed."""


class PlexUnreachableError(ClickwheelError):
    """Couldn't connect to the Plex server (network error or bad token)."""


class PlexSectionNotFoundError(ClickwheelError):
    """The configured Plex music section name doesn't exist on the server."""


class PlexPathRemapError(ClickwheelError):
    """A track path didn't match the configured plex path remap prefix."""


@dataclass
class IpodPlaylistSpec:
    """Internal: a playlist destined for the iPod's iTunesDB.

    Used to ferry "write this playlist" intent through `write_ipod_db`.
    `tracks` is a list of clickwheel-side track dicts (from the library
    DB or from compute_diff) — `write_ipod_db` matches them to
    TrackInfo dbids via (artist, album, title) so the resulting
    iPod-side playlist references the right tracks.
    """

    name: str
    tracks: list[dict] = field(default_factory=list)


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
class RemoveEvent:
    """Emitted per track as remove_tracks_from_ipod unlinks files."""

    current: int
    total: int
    track: dict
    ok: bool


@dataclass
class RemoveResult:
    """Outcome of a remove_*_from_ipod call.

    `removed` is the iPod-side track records (artist/album/title/location)
    that were dropped from the iTunesDB AND whose physical files were
    unlinked. `not_matched` is the inputs that didn't correspond to any
    iPod track. `bytes_freed` is the sum of file sizes for `removed`.
    """

    removed: list[dict] = field(default_factory=list)
    not_matched: list[str] = field(default_factory=list)
    bytes_freed: int = 0
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


def list_ipod_playlists(cfg: Config) -> list[dict]:
    """Read user-visible playlists currently on the iPod.

    Returns one dict per playlist (excluding the auto-generated master
    playlist) with: name, track_count, total_bytes, is_smart.
    `total_bytes` is best-effort, computed by summing the matching
    tracks' size fields; if the playlist references a track ID that
    isn't in the current track list, that track contributes 0.

    Raises IpodNotFoundError if no iPod is mounted.
    """
    from clickwheel.ipod import get_ipod_playlists, get_ipod_tracks

    ipod_db = require_ipod(cfg)
    raw_playlists = get_ipod_playlists(ipod_db)
    tracks_by_id = {t.get("trackID"): t for t in get_ipod_tracks(ipod_db)}

    result: list[dict] = []
    for p in raw_playlists:
        total = 0
        for tid in p.get("item_track_ids", []):
            t = tracks_by_id.get(tid)
            if t:
                total += t.get("size") or 0
        result.append(
            {
                "name": p["name"],
                "track_count": p["track_count"],
                "total_bytes": total,
                "is_smart": p["is_smart"],
            }
        )
    return result


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
    on_conflict: str | None = None,
    target_name: str | None = None,
) -> SyncResult:
    """Copy a playlist to the iPod and create/update the matching
    iPod-side playlist under Music → Playlists on the device.

    Confirmation is the caller's job. This function actually performs
    the sync. Pass a pre-computed `diff` (e.g. from a preview) to avoid
    re-reading the iPod.

    Same-name iPod playlist handling
    --------------------------------
    If a playlist with `target_name or playlist_name` already exists on
    the iPod, behavior depends on `on_conflict`:
      - None         → raise PlaylistConflictError so callers can ask
                        the user what to do.
      - "merge"      → union the existing iPod playlist's tracks with
                        the new track list (dedup by dbid). Existing
                        track order is preserved; new tracks append.
      - "replace"    → drop the iPod playlist's previous contents and
                        write the new track list as-is.
      - "rename"     → write the new playlist under `target_name`
                        (required). The original iPod playlist with the
                        clashing name is left untouched.

    Pre-flight checks
    -----------------
    - LibraryNotFoundError if cfg.music_dir isn't reachable.
    - MissingTracksError if any playlist tracks are flagged missing on
      disk. Carries the offending tracks so callers can suggest
      `heal_playlist`.

    Raises PlaylistNotFoundError, IpodNotFoundError,
    InsufficientSpaceError, PlaylistConflictError.
    """
    from clickwheel.ipod import get_ipod_playlists
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

    # Determine the target iPod playlist name and check for conflict
    # before touching anything destructive.
    ipod_db = require_ipod(cfg)
    existing_ipod_playlists = get_ipod_playlists(ipod_db)
    existing_by_name = {p["name"]: p for p in existing_ipod_playlists}

    if on_conflict == "rename":
        if not target_name:
            raise ClickwheelError("on_conflict='rename' requires a target_name.")
        ipod_playlist_name = target_name
        # Rename also can't itself collide — check.
        if target_name in existing_by_name:
            raise PlaylistConflictError(
                f"An iPod playlist named '{target_name}' already exists. "
                "Pick a different name.",
                existing_name=target_name,
                existing_track_count=existing_by_name[target_name]["track_count"],
            )
    else:
        ipod_playlist_name = playlist_name

    conflicting = existing_by_name.get(ipod_playlist_name)
    if conflicting and on_conflict not in {"merge", "replace", "rename"}:
        raise PlaylistConflictError(
            f"An iPod playlist named '{ipod_playlist_name}' already "
            f"exists with {conflicting['track_count']} track(s). Re-call "
            "with on_conflict='merge' (combine), 'replace' (overwrite), "
            "or 'rename' (use target_name=...).",
            existing_name=ipod_playlist_name,
            existing_track_count=conflicting["track_count"],
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

    # Build the playlist spec for write_ipod_db. The full playlist (not
    # just to_add) is what we want as the iPod-side playlist contents.
    playlist_tracks = db.get_playlist(playlist_name)
    spec = IpodPlaylistSpec(name=ipod_playlist_name, tracks=playlist_tracks)

    # For merge: union with existing iPod tracks (preserve order, append
    # new ones not already there). Match by (artist, album, title).
    overwrite_names = {ipod_playlist_name}
    if on_conflict == "merge" and conflicting is not None:
        existing_tracks = read_ipod_track_list(ipod_db)
        # Map existing iPod trackIDs in the conflicting playlist back to
        # track records so we can build a (artist, album, title) list.
        track_id_to_record = {t.get("trackID"): t for t in existing_tracks}
        seen: set[tuple[str, str, str]] = set()
        merged: list[dict] = []
        for tid in conflicting["item_track_ids"]:
            t = track_id_to_record.get(tid)
            if not t:
                continue
            triple = (t.get("artist") or "", t.get("album") or "", t.get("title") or "")
            if triple in seen:
                continue
            seen.add(triple)
            merged.append(
                {
                    "artist": t.get("artist"),
                    "album": t.get("album"),
                    "title": t.get("title"),
                }
            )
        for t in playlist_tracks:
            triple = (t.get("artist") or "", t.get("album") or "", t.get("title") or "")
            if triple in seen:
                continue
            seen.add(triple)
            merged.append(t)
        spec = IpodPlaylistSpec(name=ipod_playlist_name, tracks=merged)

    db_ok = write_ipod_db(
        cfg.ipod_mount,
        copied,
        playlist_specs=[spec],
        overwrite_playlist_names=overwrite_names,
    )

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


def _match_ipod_tracks_by_triples(
    ipod_tracks: list[dict],
    triples: list[tuple[str, str, str]],
) -> tuple[list[dict], list[tuple[str, str, str]]]:
    """Return (matched_ipod_tracks, unmatched_triples).

    Matches by (artist, album, title) — the same identity key sync uses.
    """
    by_triple: dict[tuple[str, str, str], dict] = {}
    for t in ipod_tracks:
        key = (
            (t.get("artist") or ""),
            (t.get("album") or ""),
            (t.get("title") or ""),
        )
        by_triple[key] = t
    matched: list[dict] = []
    unmatched: list[tuple[str, str, str]] = []
    for triple in triples:
        t = by_triple.get(triple)
        if t is None:
            unmatched.append(triple)
        else:
            matched.append(t)
    return matched, unmatched


def remove_tracks_from_ipod(
    cfg: Config,
    db: Database,
    paths: list[str],
    *,
    on_event: Callable[[RemoveEvent], None] | None = None,
) -> RemoveResult:
    """Remove specific tracks from the iPod's library.

    Resolves each `path` to its (artist, album, title) via the library
    DB, then matches against the iPod's current track list to find the
    iPod-side records to drop. Rewrites the iTunesDB without those
    tracks, then unlinks the physical files from iPod_Control/Music/Fxx/
    to actually free space.

    Sync is NORMALLY additive — this is the explicit "delete" door, and
    DOES delete the music files from the device. Caller (UI/MCP tool)
    must gate with destructive confirmation.

    Paths that aren't in the library index are reported as unmatched.
    Paths that ARE in the library but whose triple isn't on the iPod
    are also reported as unmatched (the user asked to remove something
    that's already not there).

    Pre-flight raises LibraryNotFoundError, IpodNotFoundError. Track
    deletion is best-effort: if a physical file fails to unlink, the
    iTunesDB rewrite still succeeds (the track becomes invisible on the
    device, the file just lingers as orphan bytes — won't crash).
    """
    from clickwheel.ipod import get_ipod_tracks
    from clickwheel.ipod.sync import unlink_ipod_track_files, write_ipod_db

    if not cfg.music_dir.is_dir():
        raise LibraryNotFoundError(
            f"Music library at {cfg.music_dir} isn't mounted. "
            "Mount the share before removing tracks."
        )

    # Resolve clickwheel paths → (artist, album, title) triples via the
    # library DB. We don't error on unknown paths here — they're added
    # to `not_matched` so the caller can surface them and decide.
    triples: list[tuple[str, str, str]] = []
    not_matched: list[str] = []
    for path in paths:
        row = db.conn.execute(
            "SELECT artist, album, title FROM tracks WHERE path = ?", (path,)
        ).fetchone()
        if row is None:
            not_matched.append(path)
            continue
        triples.append((row["artist"] or "", row["album"] or "", row["title"] or ""))

    ipod_db = require_ipod(cfg)
    ipod_tracks = get_ipod_tracks(ipod_db)
    matched, unmatched_triples = _match_ipod_tracks_by_triples(ipod_tracks, triples)
    # Report triples-not-on-iPod back as path-shaped strings so the
    # caller can list them. We don't have the original path for these
    # (we did already resolve to triples), so format the triple instead.
    for at, al, ti in unmatched_triples:
        not_matched.append(f"{at} — {ti} ({al})")

    total = len(matched)
    locations: list[str] = []
    for i, t in enumerate(matched, start=1):
        loc = t.get("location") or ""
        if loc:
            locations.append(loc)
        if on_event:
            on_event(RemoveEvent(current=i, total=total, track=t, ok=True))

    bytes_freed = sum(t.get("size") or 0 for t in matched)

    # Rewrite iTunesDB without the removed tracks.
    library_updated = write_ipod_db(
        cfg.ipod_mount,
        copied_tracks=[],
        remove_track_locations=set(locations),
    )

    # Unlink the physical files. Best-effort.
    if library_updated and locations:
        unlink_ipod_track_files(cfg.ipod_mount, locations)

    return RemoveResult(
        removed=[
            {
                "artist": t.get("artist"),
                "album": t.get("album"),
                "title": t.get("title"),
                "size_bytes": t.get("size") or 0,
            }
            for t in matched
        ],
        not_matched=not_matched,
        bytes_freed=bytes_freed,
        library_updated=library_updated,
    )


def remove_artist_from_ipod(
    cfg: Config,
    artist: str,
    *,
    on_event: Callable[[RemoveEvent], None] | None = None,
) -> RemoveResult:
    """Drop every iPod track whose canonical lead artist matches.

    Matches via `primary_artist` (album_artist-first), same rollup logic
    the capacity-bar legend uses. So "Taylor Swift / HAIM" tracks would
    be removed when you ask to remove "Taylor Swift" — that's the
    expected behavior given those tracks ARE Taylor Swift tracks.

    Doesn't require the tracks to be in the library DB. Reads the iPod
    directly, filters by primary_artist, then drops the matches.

    Errors: IpodNotFoundError.
    """
    from clickwheel.ipod import get_ipod_tracks
    from clickwheel.ipod.sync import unlink_ipod_track_files, write_ipod_db

    ipod_db = require_ipod(cfg)
    ipod_tracks = get_ipod_tracks(ipod_db)

    matched = [
        t
        for t in ipod_tracks
        if primary_artist(t.get("artist"), t.get("album_artist")) == artist
    ]
    total = len(matched)
    if total == 0:
        return RemoveResult(
            removed=[], not_matched=[], bytes_freed=0, library_updated=True
        )

    locations: list[str] = []
    for i, t in enumerate(matched, start=1):
        loc = t.get("location") or ""
        if loc:
            locations.append(loc)
        if on_event:
            on_event(RemoveEvent(current=i, total=total, track=t, ok=True))

    bytes_freed = sum(t.get("size") or 0 for t in matched)
    library_updated = write_ipod_db(
        cfg.ipod_mount,
        copied_tracks=[],
        remove_track_locations=set(locations),
    )
    if library_updated and locations:
        unlink_ipod_track_files(cfg.ipod_mount, locations)

    return RemoveResult(
        removed=[
            {
                "artist": t.get("artist"),
                "album": t.get("album"),
                "title": t.get("title"),
                "size_bytes": t.get("size") or 0,
            }
            for t in matched
        ],
        not_matched=[],
        bytes_freed=bytes_freed,
        library_updated=library_updated,
    )


def remove_ipod_playlist(cfg: Config, name: str) -> RemoveResult:
    """Drop a playlist from the iPod's iTunesDB.

    The playlist's TRACKS are NOT deleted from the library — they stay
    accessible via the Music → Artists / Albums browsing. Only the
    playlist artifact under Music → Playlists goes away.

    For "delete the playlist AND its tracks" the caller composes:
    list iPod tracks for that playlist via the playlist's items,
    `remove_tracks_from_ipod(paths)`, then `remove_ipod_playlist(name)`.

    Errors: IpodNotFoundError, PlaylistNotFoundError.
    """
    from clickwheel.ipod import get_ipod_playlists
    from clickwheel.ipod.sync import write_ipod_db

    ipod_db = require_ipod(cfg)
    existing = {p["name"] for p in get_ipod_playlists(ipod_db)}
    if name not in existing:
        raise PlaylistNotFoundError(
            f"No iPod playlist named '{name}'. "
            f"Use list_ipod_playlists to see what's there."
        )

    library_updated = write_ipod_db(
        cfg.ipod_mount,
        copied_tracks=[],
        remove_playlist_names={name},
    )
    return RemoveResult(
        removed=[],
        not_matched=[],
        bytes_freed=0,
        library_updated=library_updated,
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


# ---------------------------------------------------------------------------
# Plex sync
# ---------------------------------------------------------------------------


@dataclass
class PlexSyncResult:
    """Outcome of a `sync_playlist_to_plex` call.

    `pushed` is the number of tracks we put into the M3U; `resolved` is
    how many Plex actually matched against its index. A gap between the
    two means some clickwheel files aren't visible to Plex — typically
    because Plex hasn't scanned them yet, or they live outside Plex's
    music section.
    """

    pushed: int = 0
    resolved: int = 0
    playlist_rating_key: int | None = None
    m3u_local_path: str = ""
    m3u_plex_path: str = ""


def _default_plex_playlist_dir(cfg: Config) -> Path:
    """Default location for clickwheel-written M3U files.

    Lives inside the music library so Plex can read it without extra
    share configuration — Plex already needs read access to the music
    dir, so a hidden subdir there is the safe universal default.
    """
    return cfg.music_dir / ".clickwheel-playlists"


def _plex_playlist_dir(cfg: Config) -> Path:
    if cfg.plex_playlist_dir:
        return Path(cfg.plex_playlist_dir)
    return _default_plex_playlist_dir(cfg)


def _slugify_for_filename(name: str) -> str:
    """Sanitize a playlist name into a filesystem-safe slug.

    Replaces anything outside [A-Za-z0-9._-] with `_`. Doesn't try to
    handle case-folding or unicode normalization — Plex stores the
    playlist title as given; the slug only governs the M3U filename.
    """
    safe = []
    for ch in name:
        if ch.isalnum() or ch in "._-":
            safe.append(ch)
        else:
            safe.append("_")
    return "".join(safe) or "playlist"


def _require_plex_config(cfg: Config) -> None:
    if not cfg.plex_enabled:
        raise PlexNotConfiguredError(
            "Plex sync is disabled. Set `plex_enabled: true` in "
            "~/.clickwheel/config.yaml or CLICKWHEEL_PLEX_ENABLED=true."
        )
    missing = []
    if not cfg.plex_url:
        missing.append("plex_url")
    if not cfg.plex_token:
        missing.append("plex_token (CLICKWHEEL_PLEX_TOKEN)")
    if missing:
        raise PlexNotConfiguredError(
            f"Plex sync is enabled but {', '.join(missing)} is not set."
        )


def _connect_plex(cfg: Config):
    """Connect with all the plexapi-flavored exceptions translated to
    our ClickwheelError hierarchy."""
    from clickwheel import plex as _plex

    try:
        return _plex.connect(cfg.plex_url, cfg.plex_token)
    except _plex.PlexExtraMissing as exc:
        raise PlexExtraNotInstalledError(str(exc)) from exc
    except Exception as exc:
        # plexapi raises Unauthorized for bad tokens and various
        # requests.exceptions for connection issues. Both surface to the
        # user with the same advice: check the URL/token/network.
        raise PlexUnreachableError(
            f"Couldn't reach Plex at {cfg.plex_url}: {exc}"
        ) from exc


def sync_playlist_to_plex(
    cfg: Config,
    db: Database,
    playlist_name: str,
) -> PlexSyncResult:
    """Push a clickwheel playlist into the user's Plex music library.

    Writes an EXTM3U file inside `cfg.plex_playlist_dir` (default:
    `{music_dir}/.clickwheel-playlists/`) containing the Plex-side
    paths to each track, then asks Plex to import it. Plex resolves
    each path against its own indexed library — paths Plex doesn't
    recognize are silently skipped, which is why the result reports
    both `pushed` and `resolved`.

    Re-uploading the same playlist (same name -> same M3U path)
    overwrites the prior playlist; that's plexapi's documented
    behavior and is what makes the operation idempotent.

    Raises: PlexNotConfiguredError, PlexExtraNotInstalledError, PlexUnreachableError,
    PlexSectionNotFoundError, PlexPathRemapError, PlaylistNotFoundError.
    """
    from clickwheel import plex as _plex

    _require_plex_config(cfg)

    tracks = get_playlist(db, playlist_name)  # raises PlaylistNotFoundError

    plex = _connect_plex(cfg)
    try:
        section = _plex.find_music_section(plex, cfg.plex_library_name)
    except LookupError as exc:
        raise PlexSectionNotFoundError(str(exc)) from exc

    m3u_local = _plex_playlist_dir(cfg) / f"{_slugify_for_filename(playlist_name)}.m3u"
    try:
        m3u_local = _plex.build_m3u(
            tracks,
            m3u_local,
            cfg.plex_path_remap_local,
            cfg.plex_path_remap_plex,
        )
        m3u_plex = _plex.local_to_plex_path(
            m3u_local.as_posix(),
            cfg.plex_path_remap_local,
            cfg.plex_path_remap_plex,
        )
    except _plex.PathRemapFailedError as exc:
        raise PlexPathRemapError(str(exc)) from exc
    except _plex.PlexConfigInvalidError as exc:
        raise PlexNotConfiguredError(str(exc)) from exc

    playlist = _plex.upload_playlist(plex, section, playlist_name, m3u_plex)

    return PlexSyncResult(
        pushed=len(tracks),
        resolved=int(getattr(playlist, "leafCount", 0) or 0),
        playlist_rating_key=getattr(playlist, "ratingKey", None),
        m3u_local_path=str(m3u_local),
        m3u_plex_path=m3u_plex,
    )


def delete_plex_playlist(cfg: Config, name: str) -> int:
    """Delete every audio playlist on Plex matching `name`. Returns the
    count actually deleted (0 if none existed). Does NOT touch the
    clickwheel-side playlist."""
    from clickwheel import plex as _plex

    _require_plex_config(cfg)
    plex = _connect_plex(cfg)
    return _plex.delete_audio_playlist(plex, name)


# ---------------------------------------------------------------------------
# Plex diagnostic
# ---------------------------------------------------------------------------


@dataclass
class PlexDoctorStage:
    """One step of `plex_doctor`'s probe chain."""

    name: str
    ok: bool
    detail: str


@dataclass
class PlexDoctorResult:
    """Outcome of `plex_doctor` — an ordered list of stages and a roll-up
    `ok` flag. The first failing stage halts the chain, but earlier
    successful stages are still reported so the user sees how far they
    got."""

    stages: list[PlexDoctorStage] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.stages) and all(s.ok for s in self.stages)

    def _add(self, name: str, ok: bool, detail: str) -> None:
        self.stages.append(PlexDoctorStage(name=name, ok=ok, detail=detail))


def plex_doctor(cfg: Config, db: Database) -> PlexDoctorResult:
    """Probe the user's Plex setup end-to-end without mutating anything.

    Stages: config check → plexapi extra installed → connect → find music
    section → pick a clickwheel-side mp3 and confirm Plex resolves the
    same physical file via the configured path remap. Each stage is
    reported even if a later one fails; the first failure stops the
    chain so we don't pile cascading errors.

    Returns a `PlexDoctorResult`; never raises (errors become stages
    with `ok=False`). Callers render it however they like.
    """
    from clickwheel import plex as _plex

    result = PlexDoctorResult()

    # 1. config
    try:
        _require_plex_config(cfg)
    except PlexNotConfiguredError as exc:
        result._add("config", False, str(exc))
        return result
    result._add(
        "config",
        True,
        f"enabled, url={cfg.plex_url}, library={cfg.plex_library_name!r}",
    )

    # 2. extra
    try:
        _plex._import_plexapi()
    except _plex.PlexExtraMissingError as exc:
        result._add("plexapi extra", False, str(exc))
        return result
    result._add("plexapi extra", True, "installed")

    # 3. connect
    try:
        plex = _plex.connect(cfg.plex_url, cfg.plex_token)
    except Exception as exc:
        result._add("connect", False, f"{cfg.plex_url}: {exc}")
        return result
    server_name = getattr(plex, "friendlyName", "(unknown)")
    server_version = getattr(plex, "version", "(unknown)")
    result._add(
        "connect",
        True,
        f"server={server_name!r} version={server_version}",
    )

    # 4. section
    try:
        section = _plex.find_music_section(plex, cfg.plex_library_name)
    except LookupError as exc:
        result._add("music section", False, str(exc))
        return result
    total = getattr(section, "totalSize", "?")
    result._add(
        "music section",
        True,
        f"section [{section.key}] {section.title!r}, ~{total} artists",
    )

    # 5. sample track resolution
    sample_row = db.conn.execute(
        """
        SELECT title, artist, album, path
        FROM tracks
        WHERE format = 'mp3'
          AND title IS NOT NULL AND title != ''
          AND artist IS NOT NULL AND artist != ''
          AND album IS NOT NULL AND album != ''
        ORDER BY RANDOM()
        LIMIT 1
        """
    ).fetchone()
    if not sample_row:
        result._add(
            "sample track",
            False,
            "library has no mp3 tracks to sample. Run `clickwheel scan`.",
        )
        return result
    sample = dict(sample_row)
    try:
        matches = section.searchTracks(
            title=sample["title"],
            **{"artist.title": sample["artist"]},
        )
    except Exception as exc:
        result._add("sample track", False, f"Plex search failed: {exc}")
        return result

    expected_plex_path: str | None
    try:
        expected_plex_path = _plex.local_to_plex_path(
            sample["path"],
            cfg.plex_path_remap_local,
            cfg.plex_path_remap_plex,
        )
    except (_plex.PathRemapFailedError, _plex.PlexConfigInvalidError) as exc:
        result._add("sample track", False, f"path remap config: {exc}")
        return result

    label = f"{sample['artist']} / {sample['album']} / {sample['title']}"
    if not matches:
        # Soft signal — not a real failure. M3U upload uses Plex's
        # path-based indexer, not the metadata search this probe uses.
        # The only way this branch fires AND sync also fails is if
        # Plex hasn't scanned the file at all — which is the user's
        # next thing to check, but most of the time everything works.
        result._add(
            "sample track",
            True,
            (
                f"soft signal: Plex's metadata search didn't find "
                f"{label}, but path-based sync may still work. If a "
                "subsequent sync_playlist_to_plex reports low "
                "resolved counts, trigger a Plex library scan."
            ),
        )
        return result

    plex_paths = [
        part.file for m in matches[:5] for media in m.media for part in media.parts
    ]
    if expected_plex_path in plex_paths:
        result._add(
            "sample track",
            True,
            f"{label} found in Plex at the expected path",
        )
    else:
        result._add(
            "sample track",
            False,
            (
                f"{label} found in Plex, but not at the expected path "
                f"({expected_plex_path!r}). Plex returned: {plex_paths[:3]}. "
                "Check plex_path_remap_local / plex_path_remap_plex."
            ),
        )
    return result
