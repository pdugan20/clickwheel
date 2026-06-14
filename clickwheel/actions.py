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


class LibraryStorageOfflineError(LibraryNotFoundError):
    """The music library's network share is unreachable and couldn't be
    automatically remounted (the NAS is likely asleep or off the network).

    Subclasses LibraryNotFoundError so existing handlers still catch it."""


class PlaylistNotFoundError(ClickwheelError):
    """Named playlist doesn't exist."""


class IpodNotFoundError(ClickwheelError):
    """iPod not mounted or not detected."""


class FfmpegNotFoundError(ClickwheelError):
    """ffmpeg is required for FLAC conversion but isn't installed."""


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


class AppleMusicNotConfiguredError(ClickwheelError):
    """Raised when apple_music_enabled is off, or required keys are missing."""


class AppleMusicExtraNotInstalledError(ClickwheelError):
    """Raised when the `[applemusic]` extra (pyjwt[crypto]) isn't installed."""


class AppleMusicKeyFileError(ClickwheelError):
    """Raised when the .p8 path is missing/unreadable or not a PEM key."""


class AppleMusicAuthError(ClickwheelError):
    """Raised when the user-token auth dance failed or was cancelled."""


class AppleMusicUnreachableError(ClickwheelError):
    """Raised when Apple Music's REST API is unreachable or rejects auth."""


class AppleMusicNoMatchesError(ClickwheelError):
    """Raised when a playlist push has zero usable matches.

    Carries `matched_low_confidence` so the CLI can offer to lower the
    threshold instead of giving up.
    """

    def __init__(self, message: str, *, matched_low_confidence: int = 0) -> None:
        super().__init__(message)
        self.matched_low_confidence = matched_low_confidence


class AppleMusicPlaylistNotFoundError(ClickwheelError):
    """Raised when a named Apple Music library playlist isn't found."""


class AppleMusicAppleScriptError(ClickwheelError):
    """Raised when the AppleScript-based delete fails — osascript
    error, Music.app missing, or non-macOS platform.
    """


class PlexPlaylistNotFoundError(ClickwheelError):
    """Raised when a named Plex playlist doesn't exist on the server."""


class PlexSmartPlaylistError(ClickwheelError):
    """Raised when pull is asked for a smart Plex playlist without
    `include_smart=True`. Smart playlists are dynamically computed by
    Plex; materializing them produces a stale snapshot, so we require
    an explicit opt-in."""


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
class ConvertResult:
    """Outcome of a convert_tracks run."""

    converted: list[str] = field(default_factory=list)  # output mp3 paths
    skipped: list[str] = field(default_factory=list)  # source paths (cache hit)
    failed: list[dict] = field(default_factory=list)  # {"path": str, "reason": str}
    output_dir: str = ""


def _safe_path_component(name: str) -> str:
    """Make a tag value safe to use as a single path segment."""
    cleaned = re.sub(r"[/\\:]", "_", name).strip()
    return cleaned or "Unknown"


def resolve_flac_sources(
    db: Database,
    *,
    scopes: list[dict] | None = None,
    all_flac: bool = False,
) -> list[dict]:
    """Resolve the set of source FLAC track dicts to convert.

    `all_flac=True` returns every FLAC in the library. Otherwise each scope is
    `{"artist": str, "album": str | None}`; album=None converts all of that
    artist's FLAC. Duplicates across scopes are removed (first occurrence wins).
    """
    if all_flac:
        return db.get_flac_tracks()
    seen: set[str] = set()
    out: list[dict] = []
    for sc in scopes or []:
        for t in db.get_flac_tracks(sc.get("artist"), sc.get("album")):
            if t["path"] not in seen:
                seen.add(t["path"])
                out.append(t)
    return out


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
    # copied holds (track_dict, ipod_relative_path) tuples — the first
    # element of copy_tracks_to_ipod()'s return. failed holds the track
    # dicts that couldn't be copied.
    copied: list[tuple[dict, str]] = field(default_factory=list)
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


@dataclass
class ArtworkResult:
    """Outcome of a cloud-artwork pass over a set of album folders."""

    albums_seen: int = 0
    albums_matched: int = 0
    art_embedded: int = 0  # track count
    years_set: int = 0  # track count
    unmatched: list[str] = field(default_factory=list)
    art_fetch_failed: list[str] = field(default_factory=list)
    albums_skipped_complete: int = 0  # already had art + year, no MB call
    cache_hits: int = 0  # served from mb_matches, no MB call
    cache_misses: int = 0  # actually hit MusicBrainz


@dataclass
class AlbumArtistRepairResult:
    """Outcome of an albumartist repair pass."""

    scanned: int = 0
    repaired: int = 0
    failed: list[str] = field(default_factory=list)


@dataclass
class GenreResult:
    """Outcome of a Last.fm genre lookup pass."""

    albums_seen: int = 0
    albums_matched: int = 0
    tracks_tagged: int = 0  # tracks where a genre was newly written
    unmatched: list[str] = field(default_factory=list)
    albums_skipped_complete: int = 0  # every track already had a genre
    cache_hits: int = 0
    cache_misses: int = 0
    skipped_no_credentials: bool = False


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
        # Only sweep tracks that live under music_dir. Tracks indexed from
        # outside it (e.g. `clickwheel convert` MP3s in cfg.transcode_dir) are
        # owned by their producer, not scan, and must not be flagged missing.
        missing_paths = {
            p for p in (db_paths - disk_paths) if Path(p).is_relative_to(cfg.music_dir)
        }
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


def list_convertible_albums(db: Database) -> list[dict]:
    """FLAC albums available to convert, with per-album conversion status."""
    return db.get_flac_albums()


def convert_tracks(
    cfg: Config,
    db: Database,
    *,
    scopes: list[dict] | None = None,
    all_flac: bool = False,
    bitrate: int | None = None,
    force: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
) -> ConvertResult:
    """Transcode the selected FLAC sources to MP3 under cfg.transcode_dir.

    Skips sources whose mtime is unchanged and whose output still exists
    (unless force=True), records each conversion in the transcodes cache, and
    indexes every produced MP3 into the tracks table so it flows through the
    normal sync pipeline. Raises FfmpegNotFoundError if ffmpeg is absent.
    """
    from clickwheel import transcode

    ffmpeg = transcode.find_ffmpeg()
    if ffmpeg is None:
        raise FfmpegNotFoundError(
            "ffmpeg not found. Install it with: brew install ffmpeg"
        )

    use_bitrate = bitrate or cfg.transcode_bitrate
    sources = resolve_flac_sources(db, scopes=scopes, all_flac=all_flac)
    result = ConvertResult(output_dir=str(cfg.transcode_dir))
    total = len(sources)

    for i, track in enumerate(sources, 1):
        src = Path(track["path"])
        try:
            # Mirror the source's path under music_dir: source paths are
            # unique, so this is collision-free and deterministic (multi-disc
            # albums with same-named tracks no longer overwrite each other).
            dest = (cfg.transcode_dir / src.relative_to(cfg.music_dir)).with_suffix(
                ".mp3"
            )
        except ValueError:
            # Source lives outside music_dir — fall back to a tag-based layout.
            label = primary_artist(track.get("artist"), track.get("album_artist"))
            album = track.get("album") or "Unknown Album"
            dest = (
                cfg.transcode_dir
                / _safe_path_component(label)
                / _safe_path_component(album)
                / (src.stem + ".mp3")
            )

        try:
            cur_mtime = src.stat().st_mtime
        except OSError:
            result.failed.append({"path": str(src), "reason": "source missing on disk"})
            if progress_callback:
                progress_callback(i, total)
            continue

        if not force:
            cached = db.get_transcode(str(src))
            if (
                cached
                and cached["source_mtime"] == cur_mtime
                and Path(cached["output_path"]).exists()
            ):
                result.skipped.append(str(src))
                if progress_callback:
                    progress_callback(i, total)
                continue

        try:
            transcode.transcode_to_mp3(src, dest, use_bitrate, ffmpeg)
        except transcode.TranscodeError as e:
            result.failed.append(
                {"path": str(src), "reason": e.detail or "ffmpeg error"}
            )
            if progress_callback:
                progress_callback(i, total)
            continue

        scanned = scan_file(dest)
        if scanned:
            db.upsert_track(scanned)
        # record_transcode commits internally, flushing the upsert above and
        # this cache row together — so an interrupted run never leaves a
        # transcode-cache hit whose track row was rolled back.
        db.record_transcode(str(src), cur_mtime, str(dest), use_bitrate)
        result.converted.append(str(dest))
        if progress_callback:
            progress_callback(i, total)

    db.commit()
    return result


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

    # Bounded probe rather than a bare is_dir(): a stale network mount makes
    # is_dir() block in the kernel, which would hang this (remote-callable)
    # health tool. probe_live() decides within a timeout and never hangs.
    from clickwheel.mount import probe_live

    return {
        "library_dir": str(cfg.music_dir),
        "library_dir_exists": probe_live(cfg.music_dir),
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


def repair_albumartist(
    db: Database,
    target: Path,
    *,
    on_track: Callable[[Path], None] | None = None,
) -> AlbumArtistRepairResult:
    """Rewrite `albumartist` tags that wrongly contain the album title.

    Legacy taggers (notably old Windows Media Player / Zune, which
    leave AlbumArt_*.jpg and ZuneAlbumArt.jpg crumbs in album folders)
    sometimes wrote the album name into the `albumartist` slot, leaving
    the real artist only in the per-track `artist` field. That breaks
    artist aggregation in clickwheel, Plex, and anything else that
    keys on albumartist.

    Uses the SQLite index to find the broken files under `target` and
    only opens those — a full-library fix that used to walk every file
    over SMB now skips ~90% of the library, since the index already
    knows which files are affected. Each candidate is re-validated
    against the file on disk before writing, so a stale DB row (a file
    that was fixed externally since the last scan) is silently skipped.

    Failures (e.g. an unreadable file) are collected in `failed` rather
    than raised so a single bad file doesn't abort the whole pass.
    """
    from mutagen import File as MutagenFile

    result = AlbumArtistRepairResult()
    for row in db.find_corrupt_albumartists(str(target)):
        path = Path(row["path"])
        result.scanned += 1
        try:
            audio = MutagenFile(str(path), easy=True)
        except Exception:
            result.failed.append(str(path))
            continue
        if audio is None or audio.tags is None:
            continue

        def _first(key: str) -> str | None:
            # Called synchronously within this iteration, so the closure over
            # `audio` never outlives the loop — B023 is a false positive here.
            vals = audio.tags.get(key)  # noqa: B023
            return str(vals[0]) if vals else None

        albumartist = _first("albumartist")
        album = _first("album")
        artist = _first("artist")
        # Re-check against the live file: the DB may be stale if
        # something fixed this tag externally since the last scan.
        if not (
            albumartist
            and album
            and artist
            and albumartist == album
            and albumartist != artist
        ):
            continue

        try:
            audio["albumartist"] = artist
            audio.save()
        except Exception:
            result.failed.append(str(path))
            continue
        result.repaired += 1
        if on_track:
            on_track(path)

    return result


def apply_cloud_artwork(
    db: Database,
    target: Path,
    *,
    refresh: bool = False,
    on_album: Callable[[str], None] | None = None,
) -> ArtworkResult:
    """Embed cloud cover art and canonical release years under `target`.

    Walks `target` for audio files, groups them into albums by folder,
    then for each album:

    1. Skips entirely if the index says every track already has art AND
       a year — nothing to do, no network call.
    2. Else consults the `mb_matches` cache. A cached `matched` row
       reuses the mbid/year; a cached `unmatched` row reports the
       no-match without re-querying MusicBrainz. The 1-req/s rate
       limit applies only to cache misses.
    3. Else performs the MusicBrainz lookup and caches the result
       (positive or negative) so the next `fix` run skips it.

    Pass `refresh=True` to bypass the cache and force a re-lookup —
    used by `clickwheel fix --refresh-mb`.

    Albums MusicBrainz can't confidently match are reported in
    `unmatched`; albums that match but whose Cover Art Archive fetch
    fails (a transient network issue) are reported in
    `art_fetch_failed`. `on_album` is called with "Artist — Album" as
    each album is processed.
    """
    from collections import defaultdict

    from clickwheel import artwork
    from clickwheel.library import find_audio_files, write_album_metadata

    groups: dict[Path, list[Path]] = defaultdict(list)
    for f in find_audio_files(target):
        groups[f.parent].append(f)

    result = ArtworkResult()
    network_calls = 0
    for _folder, paths in sorted(groups.items()):
        meta = None
        for p in paths:
            meta = scan_file(p)
            if meta and meta.get("album"):
                break
        album = (meta or {}).get("album")
        artist = (meta or {}).get("album_artist") or (meta or {}).get("artist")
        if not album or not artist:
            continue

        result.albums_seen += 1
        if on_album:
            on_album(f"{artist} — {album}")

        # Cheapest skip: the index says every track is already complete.
        if db.album_metadata_complete([str(p) for p in paths]):
            result.albums_skipped_complete += 1
            continue

        # Cache lookup. A cached `unmatched` row is authoritative
        # until the user passes --refresh-mb.
        cached = None if refresh else db.get_mb_match(artist, album)
        if cached:
            result.cache_hits += 1
            if cached["status"] == "unmatched":
                result.unmatched.append(f"{artist} — {album}")
                continue
            match_mbid = cached["mbid"]
            match_year = cached["year"]
        else:
            result.cache_misses += 1
            # MusicBrainz asks for <=1 req/s. Rate-limit only the
            # actual network calls, not cache hits.
            if network_calls > 0:
                time.sleep(1.1)
            network_calls += 1
            try:
                match = artwork.lookup_release_group(artist, album)
            except artwork.ArtworkLookupError:
                match = None
            if match is None:
                db.save_mb_match(artist, album, mbid=None, year=None)
                result.unmatched.append(f"{artist} — {album}")
                continue
            match_mbid = match.mbid
            match_year = match.year
            db.save_mb_match(artist, album, mbid=match_mbid, year=match_year)

        result.albums_matched += 1

        art: bytes | None = None
        try:
            art = artwork.fetch_front_cover(match_mbid)
        except artwork.ArtworkLookupError:
            result.art_fetch_failed.append(f"{artist} — {album}")

        for p in paths:
            # A file indexed at scan time may have vanished by now
            # (download tools that move/delete temp files, manual
            # library reorganization, SMB hiccups). Skip the write
            # rather than aborting the whole pass. `OSError` covers
            # `FileNotFoundError` and any SMB/network filesystem error.
            try:
                art_done, year_done = write_album_metadata(p, art=art, year=match_year)
            except OSError:
                continue
            result.art_embedded += int(art_done)
            result.years_set += int(year_done)

    return result


# Last.fm tags that look like genres but aren't useful. The lookup
# walks the top tags and picks the first one that isn't in this list
# and isn't a bare year. Kept short on purpose — beets' lastgenre has
# a huge curated list, but we just need to dodge the obvious junk.
_JUNK_GENRE_TAGS = frozenset(
    {
        "favorites",
        "favourite",
        "favourites",
        "favorite albums",
        "favourite albums",
        "seen live",
        "owned",
        "albums i own",
        "spotify",
        "vinyl",
        "mp3",
        "want to listen",
        "missing tags",
        "albums",
    }
)


def _is_junk_genre_tag(tag: str) -> bool:
    t = tag.lower().strip()
    if not t:
        return True
    if re.fullmatch(r"\d{4}", t):
        return True
    return t in _JUNK_GENRE_TAGS


def _write_genre_tag(path: Path, genre: str) -> bool:
    """Embed `genre` only if the file currently lacks one. Returns True
    if a write happened."""
    from mutagen import File as MutagenFile

    try:
        audio = MutagenFile(str(path), easy=True)
    except Exception:
        return False
    if audio is None or audio.tags is None:
        return False
    existing = audio.tags.get("genre")
    if existing and str(existing[0]).strip():
        return False
    try:
        audio["genre"] = genre
        audio.save()
    except Exception:
        return False
    return True


def apply_cloud_genres(
    db: Database,
    target: Path,
    *,
    api_key: str,
    refresh: bool = False,
    on_album: Callable[[str], None] | None = None,
) -> GenreResult:
    """Fill in missing genres from Last.fm's album top tags.

    Replaces the old `beet lastgenre` pipeline. Same shape as
    `apply_cloud_artwork`:

    1. Skip if every track in the album already has a `genre` tag —
       no Last.fm call.
    2. Else consult the `genre_matches` cache. `matched` reuses the
       cached genre; `unmatched` records the miss without re-querying.
    3. Else query Last.fm via pylast, take the top non-junk tag, cache
       the outcome.

    Tags get a light filter: bare years and obvious meta-tags like
    "favorites" / "seen live" are skipped. Rate limit is 0.25s between
    actual network calls (Last.fm tolerates 5/sec). Pass `refresh=True`
    to bypass the cache.

    If `api_key` is empty, the pass returns immediately with
    `skipped_no_credentials=True` and no work done; the caller is
    expected to surface that as a warning.
    """
    result = GenreResult()
    if not api_key:
        result.skipped_no_credentials = True
        return result

    from collections import defaultdict

    import pylast

    from clickwheel.library import find_audio_files

    network = pylast.LastFMNetwork(api_key=api_key)

    groups: dict[Path, list[Path]] = defaultdict(list)
    for f in find_audio_files(target):
        groups[f.parent].append(f)

    network_calls = 0
    for _folder, paths in sorted(groups.items()):
        meta = None
        for p in paths:
            meta = scan_file(p)
            if meta and meta.get("album"):
                break
        album = (meta or {}).get("album")
        artist = (meta or {}).get("album_artist") or (meta or {}).get("artist")
        if not album or not artist:
            continue

        result.albums_seen += 1
        if on_album:
            on_album(f"{artist} — {album}")

        if db.album_genres_complete([str(p) for p in paths]):
            result.albums_skipped_complete += 1
            continue

        cached = None if refresh else db.get_genre_match(artist, album)
        if cached:
            result.cache_hits += 1
            if cached["status"] == "unmatched":
                result.unmatched.append(f"{artist} — {album}")
                continue
            genre = cached["genre"]
        else:
            result.cache_misses += 1
            if network_calls > 0:
                time.sleep(0.25)
            network_calls += 1
            try:
                album_obj = network.get_album(artist, album)
                top_tags = album_obj.get_top_tags(limit=5)
            except (pylast.PyLastError, OSError):
                # Last.fm API errors and low-level network failures
                # both surface here. Programming errors (KeyError,
                # AttributeError, etc.) deliberately bubble up so a
                # broken integration doesn't silently no-op every album.
                top_tags = []

            genre = None
            for item in top_tags:
                name = getattr(item.item, "name", str(item.item)).strip()
                if name and not _is_junk_genre_tag(name):
                    genre = name.title()
                    break

            if genre is None:
                db.save_genre_match(artist, album, genre=None)
                result.unmatched.append(f"{artist} — {album}")
                continue
            db.save_genre_match(artist, album, genre=genre)

        result.albums_matched += 1
        for p in paths:
            if _write_genre_tag(p, genre):
                result.tracks_tagged += 1

    return result


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


def save_playlist(
    db: Database, name: str, track_paths: list[str], description: str | None = None
) -> None:
    db.save_playlist(name, track_paths, description)


def create_playlist(
    db: Database,
    name: str,
    track_paths: list[str],
    description: str | None = None,
) -> int:
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
    db.save_playlist(name, track_paths, description)
    return len(db.get_playlist(name))


def update_playlist(
    db: Database,
    name: str,
    track_paths: list[str],
    description: str | None = None,
) -> tuple[int, bool]:
    """Replace a playlist's contents (or create it if it doesn't exist).

    `description=None` leaves any existing description untouched.

    Returns (track_count, replaced) — `replaced` is True if a playlist by
    this name already existed.
    """
    replaced = playlist_exists(db, name)
    db.save_playlist(name, track_paths, description)
    return len(db.get_playlist(name)), replaced


def set_playlist_description(db: Database, name: str, description: str) -> None:
    """Set a playlist's description without touching its tracks. Raises
    PlaylistNotFoundError if the playlist doesn't exist."""
    if not db.set_playlist_description(name, description):
        raise PlaylistNotFoundError(f"Playlist '{name}' not found.")


def get_playlist_description(db: Database, name: str) -> str | None:
    """Return a playlist's description, or None if unset / no such playlist."""
    return db.get_playlist_description(name)


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


def _assert_paths_indexed(db: Database, paths: list[str]) -> None:
    """Raise PathsNotFoundError if any path isn't in the library index.

    Mirrors the validation `add_tracks_to_ipod` does so callers (CLI,
    MCP) get the same "run a scan / check for typos" guidance when a
    path doesn't resolve. FLAC and missing-on-disk tracks are *in* the
    index, so they pass here — the DB layer skips them on insert.
    """
    unknown = [
        p
        for p in paths
        if db.conn.execute("SELECT 1 FROM tracks WHERE path = ?", (p,)).fetchone()
        is None
    ]
    if unknown:
        raise PathsNotFoundError(
            f"{len(unknown)} of {len(paths)} paths aren't in the library "
            "index. Run `clickwheel scan` if you've added music since the "
            "last scan, or check the paths for typos.",
            unknown,
        )


def add_tracks_to_playlist(db: Database, playlist: str, track_paths: list[str]) -> int:
    """Append specific tracks to a saved playlist, preserving order.

    Creates the playlist if it doesn't exist. Duplicates already in the
    playlist, FLAC files, and tracks flagged missing on disk are silently
    skipped. Returns the number of tracks actually added.

    Raises PathsNotFoundError if any path isn't in the library index.
    """
    _assert_paths_indexed(db, track_paths)
    return db.add_tracks_to_playlist(playlist, track_paths)


def remove_tracks_from_playlist(
    db: Database, playlist: str, track_paths: list[str]
) -> int:
    """Remove specific tracks from a saved playlist.

    Returns the number of references removed (0 if the playlist doesn't
    exist or none of the paths were in it). The playlist record stays even
    if it ends up empty.

    Raises PathsNotFoundError if any path isn't in the library index.
    """
    _assert_paths_indexed(db, track_paths)
    return db.remove_tracks_from_playlist(playlist, track_paths)


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


def ensure_library_available(cfg: Config) -> None:
    """Make sure the music library's network share is mounted and responsive,
    remounting a stale/dropped SMB share when possible.

    Use this instead of a bare ``cfg.music_dir.is_dir()`` check before any
    operation that reads or writes library files: ``is_dir()`` blocks in the
    kernel on a stale mount, so a tool call fired remotely (e.g. from the
    Claude app while away) would hang instead of recovering. This probes with
    a timeout and, on macOS, force-remounts a dropped network share so the
    operation can proceed. Raises LibraryStorageOfflineError if the share
    can't be reached at all (the NAS is asleep / off the network).
    """
    from clickwheel.mount import MountStatus, ensure_mounted

    res = ensure_mounted(
        cfg.music_dir,
        mount_url=cfg.library_mount_url,
        auto_remount=cfg.library_auto_remount,
    )
    if res.status is MountStatus.OFFLINE:
        raise LibraryStorageOfflineError(
            f"Music library at {cfg.music_dir} isn't mounted and couldn't be "
            f"reconnected — the NAS may be asleep or off the network. "
            f"({res.detail})"
        )


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

    ensure_library_available(cfg)

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

    ensure_library_available(cfg)

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
        rec = by_triple.get(triple)
        if rec is None:
            unmatched.append(triple)
        else:
            matched.append(rec)
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


def retry_ipod_db_write(cfg: Config, copied: list[tuple[dict, str]]) -> bool:
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
    except _plex.PlexExtraMissingError as exc:
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

    # Plex sync writes the import M3U onto the NAS share, so the share must be
    # mounted and live — remount it if it dropped (this is the one realistic
    # "away" op that depends on the library storage).
    ensure_library_available(cfg)

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

    # Carry the clickwheel-side description over to the Plex playlist's
    # summary. M3U import can't convey a description, so this is a
    # separate edit call after the playlist exists.
    description = db.get_playlist_description(playlist_name)
    if description:
        _plex.set_playlist_summary(playlist, description)

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
# Plex pull (read-back)
# ---------------------------------------------------------------------------


@dataclass
class PlexPlaylistSummary:
    """One entry in `list_plex_playlists`."""

    name: str
    smart: bool
    track_count: int
    summary: str = ""


@dataclass
class PlexPullResult:
    """Outcome of `pull_playlist_from_plex`.

    `matched` is the number of Plex tracks whose remapped path was
    found in clickwheel's SQLite index — only those get written to the
    new local playlist. `unmatched` typically means the file lives on
    Plex but not in clickwheel's scanned tree (or vice versa), or the
    path remap can't translate the Plex-side path.
    """

    playlist_name: str
    smart: bool
    total_plex_tracks: int
    matched: int
    unmatched: int
    skipped_no_path: int
    description: str
    replaced: bool
    unmatched_details: list[dict] = field(default_factory=list)


def list_plex_playlists(cfg: Config) -> list[PlexPlaylistSummary]:
    """Return every audio playlist on the user's Plex server.

    Each entry includes `smart` so callers can distinguish smart
    (Plex-managed, dynamic) from manual (hand-curated) playlists.
    Manual ones are the safe targets for `pull_playlist_from_plex`;
    smart ones materialize a snapshot.

    Raises: PlexNotConfiguredError, PlexExtraNotInstalledError,
    PlexUnreachableError.
    """
    from clickwheel import plex as _plex

    _require_plex_config(cfg)
    plex = _connect_plex(cfg)
    out: list[PlexPlaylistSummary] = []
    for pl in _plex.list_audio_playlists(plex):
        out.append(
            PlexPlaylistSummary(
                name=pl.title,
                smart=bool(getattr(pl, "smart", False)),
                track_count=int(getattr(pl, "leafCount", 0) or len(pl.items())),
                summary=getattr(pl, "summary", "") or "",
            )
        )
    return out


def pull_playlist_from_plex(
    cfg: Config,
    db: Database,
    name: str,
    *,
    include_smart: bool = False,
    overwrite: bool = False,
) -> PlexPullResult:
    """Recover a Plex playlist into clickwheel's local SQLite store.

    For each track in the Plex playlist we translate the Plex-side
    file path back to clickwheel's view (via the configured remap) and
    look it up in the tracks index. Matched paths become the new
    playlist's contents, in Plex's order. Unmatched tracks are
    reported in `unmatched_details` so the caller can show the user
    which ones to chase down — typical causes are FLAC originals that
    Plex has indexed but clickwheel's scanner skipped, or files added
    to Plex after the last `clickwheel scan`.

    The Plex playlist's `summary` field is carried over as the
    clickwheel playlist's description, mirroring the push direction
    (`sync_playlist_to_plex` does the reverse).

    Smart playlists are refused by default (PlexSmartPlaylistError);
    pass `include_smart=True` to materialize a snapshot. If a
    clickwheel playlist with this name already exists, refuses with
    PlaylistAlreadyExistsError unless `overwrite=True`.

    Raises: PlexNotConfiguredError, PlexExtraNotInstalledError,
    PlexUnreachableError, PlexPlaylistNotFoundError,
    PlexSmartPlaylistError, PlaylistAlreadyExistsError.
    """
    from clickwheel import plex as _plex

    _require_plex_config(cfg)
    plex = _connect_plex(cfg)

    target = _plex.find_audio_playlist(plex, name)
    if target is None:
        raise PlexPlaylistNotFoundError(f"No audio playlist named {name!r} on Plex.")

    is_smart = bool(getattr(target, "smart", False))
    if is_smart and not include_smart:
        raise PlexSmartPlaylistError(
            f"Playlist {name!r} is a smart playlist (dynamically computed by "
            "Plex). Pulling it would freeze a snapshot. Re-run with "
            "include_smart=True if that's what you want."
        )

    already_exists = playlist_exists(db, name)
    if already_exists and not overwrite:
        raise PlaylistAlreadyExistsError(
            f"Playlist '{name}' already exists locally. "
            "Pass overwrite=True to replace its contents."
        )

    plex_tracks = _plex.read_playlist_tracks(target)
    skipped_no_path = int(getattr(target, "leafCount", 0) or 0) - len(plex_tracks)
    if skipped_no_path < 0:
        skipped_no_path = 0

    matched_paths: list[str] = []
    unmatched: list[dict] = []
    for pt in plex_tracks:
        plex_path = pt["plex_path"]
        try:
            local_path = _plex.plex_to_local_path(
                plex_path, cfg.plex_path_remap_local, cfg.plex_path_remap_plex
            )
        except _plex.PathRemapFailedError:
            unmatched.append({**pt, "reason": "path_remap_failed"})
            continue
        except _plex.PlexConfigInvalidError as exc:
            raise PlexNotConfiguredError(str(exc)) from exc

        row = db.conn.execute(
            "SELECT 1 FROM tracks WHERE path = ?", (local_path,)
        ).fetchone()
        if row is None:
            unmatched.append(
                {**pt, "local_path": local_path, "reason": "not_in_clickwheel_index"}
            )
            continue
        matched_paths.append(local_path)

    description = getattr(target, "summary", "") or ""
    db.save_playlist(name, matched_paths, description or None)

    return PlexPullResult(
        playlist_name=name,
        smart=is_smart,
        total_plex_tracks=len(plex_tracks) + skipped_no_path,
        matched=len(matched_paths),
        unmatched=len(unmatched),
        skipped_no_path=skipped_no_path,
        description=description,
        replaced=already_exists,
        unmatched_details=unmatched,
    )


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


# ---------------------------------------------------------------------------
# Apple Music
# ---------------------------------------------------------------------------


@dataclass
class AppleMusicDoctorStage:
    """One step of `apple_music_doctor`'s probe chain."""

    name: str
    ok: bool
    detail: str


@dataclass
class AppleMusicDoctorResult:
    """Ordered list of stages + a roll-up `ok`. Mirrors PlexDoctorResult."""

    stages: list[AppleMusicDoctorStage] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.stages) and all(s.ok for s in self.stages)

    def _add(self, name: str, ok: bool, detail: str) -> None:
        self.stages.append(AppleMusicDoctorStage(name=name, ok=ok, detail=detail))


def _require_apple_music_config(cfg: Config) -> None:
    """Validate that apple_music is enabled and the minimum keys are set."""
    if not cfg.apple_music_enabled:
        raise AppleMusicNotConfiguredError(
            "Apple Music is disabled. Set `apple_music_enabled: true` in "
            "~/.clickwheel/config.yaml or CLICKWHEEL_APPLE_MUSIC_ENABLED=true."
        )
    missing = []
    if not cfg.apple_music_team_id:
        missing.append("apple_music_team_id")
    if not cfg.apple_music_key_id and not cfg.apple_music_developer_token:
        # Need either a key id (to sign tokens) or a pre-signed dev token.
        missing.append("apple_music_key_id (or APPLE_MUSIC_DEVELOPER_TOKEN)")
    if not cfg.apple_music_key_file and not cfg.apple_music_developer_token:
        missing.append("apple_music_key_file (or APPLE_MUSIC_DEVELOPER_TOKEN)")
    if missing:
        raise AppleMusicNotConfiguredError(
            f"Apple Music is enabled but {', '.join(missing)} is not set."
        )


def _resolve_developer_token(cfg: Config) -> str:
    """Return a usable developer token.

    Priority: if `APPLE_MUSIC_DEVELOPER_TOKEN` is set in env, use it
    verbatim (caller-supplied; we don't validate signature). Otherwise
    sign one on demand from the configured .p8 + key id + team id.

    Translates pyjwt/file errors into typed ClickwheelError variants.
    """
    if cfg.apple_music_developer_token:
        return cfg.apple_music_developer_token

    from clickwheel import applemusic as _am

    try:
        key_pem = _am.read_private_key(cfg.apple_music_key_file)
    except FileNotFoundError as exc:
        raise AppleMusicKeyFileError(str(exc)) from exc
    except _am.AppleMusicConfigInvalidError as exc:
        raise AppleMusicKeyFileError(str(exc)) from exc

    try:
        return _am.generate_developer_token(
            key_pem, cfg.apple_music_key_id, cfg.apple_music_team_id
        )
    except _am.AppleMusicExtraMissingError as exc:
        raise AppleMusicExtraNotInstalledError(str(exc)) from exc


def _save_apple_music_user_token(user_token: str) -> None:
    """Persist the Music User Token to ~/.clickwheel/.env.

    Updates the line if present, appends it otherwise. Keeps the file
    at mode 600 (we created it that way; chmod is idempotent).
    """
    from clickwheel.config import CONFIG_DIR

    env_path = CONFIG_DIR / ".env"
    line = f"APPLE_MUSIC_USER_TOKEN={user_token}\n"

    if env_path.exists():
        existing = env_path.read_text().splitlines(keepends=True)
        out: list[str] = []
        replaced = False
        for ln in existing:
            if ln.startswith("APPLE_MUSIC_USER_TOKEN="):
                out.append(line)
                replaced = True
            else:
                out.append(ln)
        if not replaced:
            if out and not out[-1].endswith("\n"):
                out[-1] = out[-1] + "\n"
            out.append(line)
        env_path.write_text("".join(out))
    else:
        env_path.write_text(line)

    try:
        env_path.chmod(0o600)
    except OSError:
        # Best-effort — if chmod fails, the file is still written.
        pass


def apple_music_auth(cfg: Config, *, build: str | None = None) -> str:
    """Run the Music User Token auth dance.

    Opens the user's browser to a local MusicKit-JS page, captures the
    token they get from Apple's auth popup, persists it to
    ~/.clickwheel/.env as APPLE_MUSIC_USER_TOKEN. Returns the token.

    Raises: AppleMusicNotConfiguredError, AppleMusicExtraNotInstalledError,
    AppleMusicKeyFileError, AppleMusicAuthError.
    """
    from clickwheel import __version__
    from clickwheel import applemusic as _am

    _require_apple_music_config(cfg)
    dev_token = _resolve_developer_token(cfg)

    try:
        result = _am.run_user_token_auth(dev_token, build=build or __version__)
    except _am.AppleMusicAuthFailedError as exc:
        raise AppleMusicAuthError(str(exc)) from exc

    if result.error or not result.user_token:
        raise AppleMusicAuthError(result.error or "Auth dance ended without a token.")

    _save_apple_music_user_token(result.user_token)
    return result.user_token


def apple_music_doctor(cfg: Config) -> AppleMusicDoctorResult:
    """Probe the Apple Music integration end-to-end.

    Stages run in order; a failing stage halts the chain but earlier
    successes are still reported so the user sees how far they got.
    Mirrors plex_doctor's shape.
    """
    from clickwheel import applemusic as _am

    result = AppleMusicDoctorResult()

    # 1. config
    try:
        _require_apple_music_config(cfg)
    except AppleMusicNotConfiguredError as exc:
        result._add("config", False, str(exc))
        return result
    result._add(
        "config",
        True,
        f"enabled, storefront={cfg.apple_music_storefront}, "
        f"team_id={cfg.apple_music_team_id}",
    )

    # 2. applemusic extra (pyjwt + cryptography)
    try:
        _am._import_jwt()
    except _am.AppleMusicExtraMissingError as exc:
        result._add("applemusic extra", False, str(exc))
        return result
    result._add("applemusic extra", True, "installed")

    # 3. .p8 readable (only relevant if signing locally)
    if cfg.apple_music_developer_token:
        result._add(
            "p8 readable",
            True,
            "skipped — APPLE_MUSIC_DEVELOPER_TOKEN provided directly.",
        )
    else:
        try:
            _am.read_private_key(cfg.apple_music_key_file)
        except FileNotFoundError as exc:
            result._add("p8 readable", False, str(exc))
            return result
        except _am.AppleMusicConfigInvalidError as exc:
            result._add("p8 readable", False, str(exc))
            return result
        result._add(
            "p8 readable",
            True,
            f"{cfg.apple_music_key_file} parses as a PEM private key.",
        )

    # 4. developer token signs
    try:
        dev_token = _resolve_developer_token(cfg)
    except (
        AppleMusicKeyFileError,
        AppleMusicExtraNotInstalledError,
    ) as exc:
        result._add("developer token", False, str(exc))
        return result
    result._add(
        "developer token",
        True,
        f"signed ({len(dev_token)} chars) with kid={cfg.apple_music_key_id or '?'}.",
    )

    # 5. developer token verifies against catalog
    try:
        hit = _am.verify_developer_token(dev_token, cfg.apple_music_storefront)
    except _am.AppleMusicHTTPError as exc:
        result._add(
            "catalog reachable",
            False,
            (
                f"HTTP {exc.status} from Apple Music. Token may be signed "
                "by a revoked key, or the key isn't authorized for MusicKit. "
                f"Body: {exc.body[:200] or '(empty)'}"
            ),
        )
        return result
    label = (
        f"{hit['attributes']['artistName']} — {hit['attributes']['name']}"
        if hit
        else "(no songs returned)"
    )
    result._add(
        "catalog reachable",
        True,
        f"search returned {label}.",
    )

    # 6. user token present
    if not cfg.apple_music_user_token:
        result._add(
            "user token",
            False,
            "no APPLE_MUSIC_USER_TOKEN in ~/.clickwheel/.env yet. "
            "Run `clickwheel apple auth` to mint one.",
        )
        return result
    result._add(
        "user token",
        True,
        f"present ({len(cfg.apple_music_user_token)} chars).",
    )

    # 7. user token verified
    try:
        storefront_resp = _am.verify_user_token(
            dev_token, cfg.apple_music_user_token, cfg.apple_music_storefront
        )
    except _am.AppleMusicHTTPError as exc:
        result._add(
            "user token verified",
            False,
            (
                f"HTTP {exc.status} for /v1/me/storefront. User token may have "
                "expired or been revoked. Re-run `clickwheel apple auth`."
            ),
        )
        return result
    sf_data = storefront_resp.get("data", [])
    storefront_id = sf_data[0]["id"] if sf_data else "?"
    result._add(
        "user token verified",
        True,
        f"user's storefront resolves to {storefront_id!r}.",
    )

    # 8. iCloud Music Library state
    try:
        icml = _am.detect_icloud_music_library(
            dev_token, cfg.apple_music_user_token, cfg.apple_music_storefront
        )
    except _am.AppleMusicHTTPError as exc:
        result._add(
            "iCloud Music Library",
            False,
            f"HTTP {exc.status} probing /v1/me/library/songs: {exc.body[:200]}",
        )
        return result
    if icml:
        result._add(
            "iCloud Music Library",
            True,
            "ON — user library is accessible (uploaded tracks become "
            "playlist-eligible).",
        )
    else:
        result._add(
            "iCloud Music Library",
            True,
            (
                "OFF — only Apple Music catalog tracks can be added to "
                "playlists. Enable in Music.app or iPhone Settings → Music "
                "to broaden the matching pool."
            ),
        )

    # 9. storefront matches config
    if storefront_id and storefront_id != cfg.apple_music_storefront:
        result._add(
            "storefront match",
            False,
            (
                f"Config says storefront={cfg.apple_music_storefront!r} but "
                f"the user is in {storefront_id!r}. Catalog lookups will use "
                "the configured value; matching may miss region-locked tracks."
            ),
        )
    else:
        result._add(
            "storefront match",
            True,
            f"config and user agree on storefront={storefront_id!r}.",
        )

    return result


# ---------------------------------------------------------------------------
# Apple Music: catalog matching + playlist push
# ---------------------------------------------------------------------------


@dataclass
class AppleMusicTrackMatch:
    """Outcome for one clickwheel track in a match/push operation."""

    track_path: str
    title: str
    artist: str
    album: str
    isrc: str | None = None
    # Filled when a usable match was found:
    song_id: str | None = None
    kind: str | None = None  # 'catalog' | 'library'
    confidence: float = 0.0
    matched_artist: str = ""
    matched_title: str = ""
    matched_album: str = ""
    # Why this row landed where it did:
    cached: bool = False
    reason: str = ""  # 'isrc' | 'fuzzy' | 'library' | 'cache' | 'unmatched'


@dataclass
class AppleMusicMatchResult:
    """Outcome of `match_playlist_to_apple_music` (a dry-run preview).

    `low_confidence` is the count of tracks whose best match scored
    below the configured threshold — they're surfaced for triage but
    not used by `sync_playlist_to_apple_music` unless the caller
    lowers the threshold.
    """

    playlist_name: str
    total: int
    matched: int  # at or above the confidence threshold
    low_confidence: int
    unmatched: int
    storefront: str
    icml: bool
    tracks: list[AppleMusicTrackMatch] = field(default_factory=list)


@dataclass
class AppleMusicPushResult:
    """Outcome of a successful `sync_playlist_to_apple_music` call."""

    playlist_name: str
    apple_music_playlist_id: str
    pushed: int
    unmatched: int
    low_confidence_skipped: int
    storefront: str


def _read_track_metadata(db: Database, name: str) -> list[dict]:
    """Pull artist/title/album/path/isrc tuples for every track in a
    clickwheel playlist. ISRC isn't in the SQLite index yet (we don't
    re-scan to backfill old rows), so we read it from disk on demand.
    """
    rows = db.get_playlist(name)
    if not rows:
        raise PlaylistNotFoundError(f"Playlist '{name}' not found.")

    from clickwheel import applemusic as _am

    out: list[dict] = []
    for r in rows:
        path = r["path"]
        try:
            isrc = _am.read_isrc(path) if Path(path).exists() else None
        except Exception:
            isrc = None
        out.append(
            {
                "path": path,
                "artist": r.get("artist") or "",
                "title": r.get("title") or "",
                "album": r.get("album") or "",
                "isrc": isrc,
            }
        )
    return out


def _detect_icml(cfg: Config, dev_token: str) -> bool:
    """Best-effort iCloud Music Library probe. Returns False on any
    failure (matching still works against the public catalog)."""
    from clickwheel import applemusic as _am

    if not cfg.apple_music_user_token:
        return False
    try:
        return _am.detect_icloud_music_library(
            dev_token, cfg.apple_music_user_token, cfg.apple_music_storefront
        )
    except Exception:
        return False


def match_playlist_to_apple_music(
    cfg: Config,
    db: Database,
    name: str,
    *,
    refresh: bool = False,
    min_confidence: float = 0.85,
) -> AppleMusicMatchResult:
    """Match every track in a clickwheel playlist against Apple Music.

    Read-only: doesn't create or modify the user's Apple Music library.
    Populates the `apple_music_song_map` cache as a side effect so
    subsequent calls (and `sync_playlist_to_apple_music`) skip the
    network for already-matched paths. Pass `refresh=True` to ignore
    the cache and re-match every track.

    `min_confidence` controls the threshold between `matched` and
    `low_confidence` in the result — the matcher itself surfaces every
    candidate it finds; this just bucketizes them.

    Raises: AppleMusicNotConfiguredError, AppleMusicExtraNotInstalledError,
    AppleMusicKeyFileError, AppleMusicUnreachableError,
    PlaylistNotFoundError.
    """
    from clickwheel import applemusic as _am

    _require_apple_music_config(cfg)
    dev_token = _resolve_developer_token(cfg)
    icml = _detect_icml(cfg, dev_token)

    tracks = _read_track_metadata(db, name)

    results: list[AppleMusicTrackMatch] = []
    matched = low_confidence = unmatched = 0

    for t in tracks:
        row = AppleMusicTrackMatch(
            track_path=t["path"],
            title=t["title"],
            artist=t["artist"],
            album=t["album"],
            isrc=t["isrc"],
        )

        cached = None if refresh else db.get_apple_music_song(t["path"])
        if cached and cached.get("storefront") == cfg.apple_music_storefront:
            row.song_id = cached["song_id"]
            row.kind = cached["kind"]
            row.confidence = cached["confidence"]
            row.cached = True
            row.reason = "cache"
        else:
            try:
                hit = _am.match_track(
                    dev_token=dev_token,
                    user_token=cfg.apple_music_user_token or None,
                    storefront=cfg.apple_music_storefront,
                    artist=t["artist"],
                    title=t["title"],
                    album=t["album"],
                    isrc=t["isrc"],
                    icml=icml,
                )
            except _am.AppleMusicHTTPError as exc:
                raise AppleMusicUnreachableError(str(exc)) from exc

            if hit is not None:
                row.song_id = hit.song_id
                row.kind = hit.kind
                row.confidence = hit.confidence
                row.matched_artist = hit.matched_artist
                row.matched_title = hit.matched_title
                row.matched_album = hit.matched_album
                row.reason = (
                    "isrc"
                    if hit.confidence == 1.0 and hit.kind == "catalog"
                    else hit.kind
                )
                db.upsert_apple_music_song(
                    t["path"],
                    hit.song_id,
                    hit.kind,
                    hit.confidence,
                    cfg.apple_music_storefront,
                )

        if row.song_id is None:
            row.reason = row.reason or "unmatched"
            unmatched += 1
        elif row.confidence >= min_confidence:
            matched += 1
        else:
            low_confidence += 1

        results.append(row)

    return AppleMusicMatchResult(
        playlist_name=name,
        total=len(tracks),
        matched=matched,
        low_confidence=low_confidence,
        unmatched=unmatched,
        storefront=cfg.apple_music_storefront,
        icml=icml,
        tracks=results,
    )


def sync_playlist_to_apple_music(
    cfg: Config,
    db: Database,
    name: str,
    *,
    refresh: bool = False,
    min_confidence: float = 0.85,
    include_low_confidence: bool = False,
) -> AppleMusicPushResult:
    """Create a playlist in the user's Apple Music account from a
    clickwheel playlist.

    Calls `match_playlist_to_apple_music` first to bucket every track
    into matched / low-confidence / unmatched. Only `matched` tracks
    (and optionally `low_confidence` if the caller passes
    `include_low_confidence=True`) are pushed. The playlist's name and
    description come from the clickwheel-side playlist.

    Raises: AppleMusicNotConfiguredError, AppleMusicExtraNotInstalledError,
    AppleMusicKeyFileError, AppleMusicUnreachableError,
    AppleMusicNoMatchesError, PlaylistNotFoundError. The user token
    must be present and valid — `apple_music_doctor` is the way to
    confirm before calling this.
    """
    from clickwheel import applemusic as _am

    _require_apple_music_config(cfg)
    if not cfg.apple_music_user_token:
        raise AppleMusicNotConfiguredError(
            "No APPLE_MUSIC_USER_TOKEN. Run `clickwheel apple auth` first."
        )

    match = match_playlist_to_apple_music(
        cfg, db, name, refresh=refresh, min_confidence=min_confidence
    )

    pushable = [
        t
        for t in match.tracks
        if t.song_id is not None
        and (t.confidence >= min_confidence or include_low_confidence)
    ]
    if not pushable:
        raise AppleMusicNoMatchesError(
            (
                f"No tracks in '{name}' matched Apple Music at confidence "
                f">= {min_confidence:.2f}. {match.low_confidence} low-"
                "confidence and {match.unmatched} unmatched."
            ).format(match=match),
            matched_low_confidence=match.low_confidence,
        )

    song_refs = [
        {
            "id": t.song_id,
            "type": "library-songs" if t.kind == "library" else "songs",
        }
        for t in pushable
    ]
    description = db.get_playlist_description(name) or ""
    dev_token = _resolve_developer_token(cfg)

    try:
        body = _am.create_library_playlist(
            dev_token, cfg.apple_music_user_token, name, description, song_refs
        )
    except _am.AppleMusicHTTPError as exc:
        raise AppleMusicUnreachableError(str(exc)) from exc

    playlist_data = body.get("data", [{}])[0]
    return AppleMusicPushResult(
        playlist_name=name,
        apple_music_playlist_id=playlist_data.get("id", ""),
        pushed=len(pushable),
        unmatched=match.unmatched,
        low_confidence_skipped=(0 if include_low_confidence else match.low_confidence),
        storefront=cfg.apple_music_storefront,
    )


# ---------------------------------------------------------------------------
# Apple Music: read-back (list + pull)
# ---------------------------------------------------------------------------


@dataclass
class AppleMusicPlaylistEntry:
    """One playlist in `list_apple_music_playlists` output.

    `track_count` is None when Apple's listing endpoint didn't populate
    the field — that's the typical case for `/v1/me/library/playlists`.
    """

    playlist_id: str
    name: str
    description: str = ""
    track_count: int | None = None
    can_edit: bool = True


@dataclass
class AppleMusicPullTrack:
    """One track row in an Apple Music pull preview/result."""

    apple_song_id: str
    kind: str  # 'catalog' | 'library'
    artist: str
    title: str
    album: str
    # Filled when a usable local match was found:
    local_path: str | None = None
    reason: str = ""  # 'cache' | 'exact' | 'fuzzy' | 'unmatched'
    confidence: float = 0.0


@dataclass
class AppleMusicPullResult:
    """Outcome of `pull_playlist_from_apple_music`."""

    playlist_name: str
    apple_music_playlist_id: str
    total: int
    matched: int
    unmatched: int
    replaced: bool
    description: str
    tracks: list[AppleMusicPullTrack] = field(default_factory=list)


def list_apple_music_playlists(cfg: Config) -> list[AppleMusicPlaylistEntry]:
    """Return every library playlist in the user's Apple Music account.

    Read-only. Requires a user token (run `clickwheel apple auth`
    first).

    Raises: AppleMusicNotConfiguredError, AppleMusicExtraNotInstalledError,
    AppleMusicKeyFileError, AppleMusicUnreachableError.
    """
    from clickwheel import applemusic as _am

    _require_apple_music_config(cfg)
    if not cfg.apple_music_user_token:
        raise AppleMusicNotConfiguredError(
            "No APPLE_MUSIC_USER_TOKEN. Run `clickwheel apple auth` first."
        )
    dev_token = _resolve_developer_token(cfg)
    try:
        playlists = _am.list_user_playlists(dev_token, cfg.apple_music_user_token)
    except _am.AppleMusicHTTPError as exc:
        raise AppleMusicUnreachableError(str(exc)) from exc
    return [
        AppleMusicPlaylistEntry(
            playlist_id=p.playlist_id,
            name=p.name,
            description=p.description,
            track_count=p.track_count,
            can_edit=p.can_edit,
        )
        for p in playlists
    ]


def _resolve_apple_track_to_local(
    db: Database,
    apple_song_id: str,
    artist: str,
    title: str,
    album: str,
    storefront: str,
    min_fuzzy_confidence: float,
) -> tuple[str | None, str, float]:
    """Map one Apple Music track to a local clickwheel track path.

    Strategy ladder: cache (highest fidelity) → exact artist+title
    (very high) → fuzzy composite (best-effort). Returns
    `(local_path, reason, confidence)` where `local_path` is None
    when no acceptable match was found.
    """
    cached = db.get_track_path_by_apple_song_id(apple_song_id, storefront)
    if cached:
        return (cached, "cache", 1.0)
    exact = db.find_track_by_artist_title(artist, title, album)
    if exact:
        return (exact, "exact", 0.99)
    fuzzy_path, fuzzy_score = db.fuzzy_find_track(
        artist, title, album, min_confidence=min_fuzzy_confidence
    )
    if fuzzy_path:
        return (fuzzy_path, "fuzzy", fuzzy_score)
    return (None, "unmatched", 0.0)


def pull_playlist_from_apple_music(
    cfg: Config,
    db: Database,
    name: str,
    *,
    overwrite: bool = False,
    min_fuzzy_confidence: float = 0.85,
) -> AppleMusicPullResult:
    """Import an Apple Music library playlist into clickwheel's local store.

    Each Apple track is mapped to a local file path via the song_map
    cache, then an exact metadata match, then a fuzzy composite score.
    Tracks Apple has but clickwheel doesn't are reported in
    `unmatched_details`.

    Raises: AppleMusicNotConfiguredError, AppleMusicExtraNotInstalledError,
    AppleMusicKeyFileError, AppleMusicUnreachableError,
    AppleMusicPlaylistNotFoundError, PlaylistAlreadyExistsError.
    """
    from clickwheel import applemusic as _am

    _require_apple_music_config(cfg)
    if not cfg.apple_music_user_token:
        raise AppleMusicNotConfiguredError(
            "No APPLE_MUSIC_USER_TOKEN. Run `clickwheel apple auth` first."
        )
    dev_token = _resolve_developer_token(cfg)

    try:
        playlists = _am.list_user_playlists(dev_token, cfg.apple_music_user_token)
    except _am.AppleMusicHTTPError as exc:
        raise AppleMusicUnreachableError(str(exc)) from exc

    target = next((p for p in playlists if p.name == name), None)
    if target is None:
        raise AppleMusicPlaylistNotFoundError(
            f"No Apple Music library playlist named {name!r}. "
            "Use `list_apple_music_playlists` to see what's available."
        )

    already_exists = playlist_exists(db, name)
    if already_exists and not overwrite:
        raise PlaylistAlreadyExistsError(
            f"Playlist '{name}' already exists locally. "
            "Pass overwrite=True to replace its contents."
        )

    try:
        apple_tracks = _am.read_user_playlist_tracks(
            dev_token, cfg.apple_music_user_token, target.playlist_id
        )
    except _am.AppleMusicHTTPError as exc:
        raise AppleMusicUnreachableError(str(exc)) from exc

    results: list[AppleMusicPullTrack] = []
    matched_paths: list[str] = []
    matched = unmatched = 0
    for t in apple_tracks:
        path, reason, conf = _resolve_apple_track_to_local(
            db,
            t["song_id"],
            t["artist"],
            t["title"],
            t["album"],
            cfg.apple_music_storefront,
            min_fuzzy_confidence,
        )
        row = AppleMusicPullTrack(
            apple_song_id=t["song_id"],
            kind=t["kind"],
            artist=t["artist"],
            title=t["title"],
            album=t["album"],
            local_path=path,
            reason=reason,
            confidence=conf,
        )
        if path is not None:
            matched_paths.append(path)
            matched += 1
            # Backfill the song_map cache so subsequent push round-trips
            # for the same track don't re-do the work.
            if reason != "cache":
                db.upsert_apple_music_song(
                    path, t["song_id"], t["kind"], conf, cfg.apple_music_storefront
                )
        else:
            unmatched += 1
        results.append(row)

    db.save_playlist(name, matched_paths, target.description or None)

    return AppleMusicPullResult(
        playlist_name=name,
        apple_music_playlist_id=target.playlist_id,
        total=len(apple_tracks),
        matched=matched,
        unmatched=unmatched,
        replaced=already_exists,
        description=target.description,
        tracks=results,
    )


# ---------------------------------------------------------------------------
# Apple Music: AppleScript-driven delete (works around Apple's REST API gap)
# ---------------------------------------------------------------------------


@dataclass
class AppleMusicDeleteResult:
    """Result of `delete_apple_music_playlist`. `deleted` is the count
    of playlists Music.app removed (0 when nothing matched the name).
    """

    name: str
    deleted: int


def delete_apple_music_playlist(name: str) -> AppleMusicDeleteResult:
    """Delete every Music.app playlist matching `name` via AppleScript.

    Apple's REST API doesn't expose DELETE on library playlists
    (confirmed via 401 with empty body — see Apple Developer Forums).
    This drives Music.app via osascript instead; the deletion
    propagates through iCloud Music Library to all signed-in devices.

    Raises: AppleMusicAppleScriptError on any osascript failure,
    Music.app missing, or non-macOS platform. No Apple Music config
    is required (it's a purely local operation).
    """
    from clickwheel import applemusic as _am

    try:
        deleted = _am.delete_local_music_playlist(name)
    except (
        _am.AppleScriptUnavailableError,
        _am.AppleScriptError,
    ) as exc:
        raise AppleMusicAppleScriptError(str(exc)) from exc
    return AppleMusicDeleteResult(name=name, deleted=deleted)
