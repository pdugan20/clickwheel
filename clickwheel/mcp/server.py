"""FastMCP server exposing clickwheel library and iPod queries.

Read-only in this revision (Phase 2). Mutation tools land in Phase 3.

The server runs over stdio and is intended to be registered with Claude Code
(or another MCP client) via `claude mcp add` or a `.mcp.json` entry pointing
at the `clickwheel-mcp` console script.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, Field

from clickwheel import actions
from clickwheel.actions import (
    ClickwheelError,
    LibraryNotFoundError,
)
from clickwheel.autoscan import should_auto_scan
from clickwheel.config import Config, load_config
from clickwheel.db import Database

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure stderr logging. stdout is reserved for the MCP wire protocol."""
    level_name = os.environ.get("CLICKWHEEL_MCP_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )


@contextmanager
def _open_session(*, autoscan: bool = True) -> Iterator[tuple[Config, Database]]:
    """Open config + DB for one tool call.

    SQLite is fast to open; per-call lifecycle keeps the server stateless and
    handles config edits made mid-session. If `autoscan` is True (default),
    runs an incremental scan when the DB is older than the configured
    staleness threshold.
    """
    cfg = load_config()
    db = Database(cfg.db_path)
    try:
        if autoscan:
            run, _reason = should_auto_scan(cfg, db)
            if run:
                try:
                    actions.scan_library(cfg, db, full=False)
                except LibraryNotFoundError:
                    # Music share unreachable — fall back to cached data.
                    logger.warning(
                        "Music dir not reachable during autoscan; serving cached data"
                    )
        yield cfg, db
    finally:
        db.close()


mcp = FastMCP(
    name="clickwheel",
    instructions=(
        "Query a clickwheel music library and iPod. Use list_artists, "
        "list_playlists, search_tracks, and similar tools for read-only "
        "browsing. get_ipod_contents requires the iPod to be mounted. "
        "library_health is a quick probe to confirm setup is working."
    ),
)


# ---------------------------------------------------------------------------
# Tools — read-only (Phase 2)
# ---------------------------------------------------------------------------


@mcp.tool()
def library_stats() -> dict:
    """High-level library stats: track/artist/album counts, total size and
    duration, format breakdown, and missing-metadata counts.

    Use this to give the user a quick overview of their library."""
    with _open_session() as (_cfg, db):
        return actions.library_stats(db)


@mcp.tool()
def list_artists(limit: int = 500) -> list[dict]:
    """All artists in the indexed library, with track count, album count,
    and total size in bytes per artist. Excludes FLAC tracks (iPod-incompatible).

    Returns at most `limit` artists. Sorted alphabetically."""
    with _open_session() as (_cfg, db):
        return actions.list_artists(db)[:limit]


@mcp.tool()
def list_albums_by_artist(artist: str) -> list[dict]:
    """Albums for a single artist, with track count, total size, and year.
    Sorted by year then album title."""
    with _open_session() as (_cfg, db):
        return actions.list_albums_by_artist(db, artist)


@mcp.tool()
def list_tracks_by_album(artist: str, album: str) -> list[dict]:
    """Tracks on a single album, ordered by disc/track number. Returns full
    track records including path, duration, and file size."""
    with _open_session() as (_cfg, db):
        return actions.list_tracks_by_album(db, artist, album)


@mcp.tool()
def search_tracks(query: str, limit: int = 50) -> list[dict]:
    """Case-insensitive substring search across artist, album, and title.
    Returns at most `limit` matching tracks. Use this when the user asks
    about a song without remembering the exact artist or album."""
    with _open_session() as (_cfg, db):
        return actions.search_tracks(db, query, limit=limit)


@mcp.tool()
def list_playlists() -> list[dict]:
    """All saved clickwheel playlists with track counts, total size in bytes,
    and last-updated timestamps."""
    with _open_session() as (_cfg, db):
        return actions.list_playlists(db)


@mcp.tool()
def get_playlist(name: str) -> dict:
    """One playlist's full contents: track list, artist breakdown, and total
    size. Raises an error if the playlist doesn't exist."""
    with _open_session() as (_cfg, db):
        tracks = actions.get_playlist(db, name)
        artists = actions.get_playlist_artists(db, name)
        size = actions.get_playlist_size(db, name)
        return {
            "name": name,
            "track_count": len(tracks),
            "size_bytes": size,
            "tracks": tracks,
            "artists": artists,
        }


@mcp.tool()
def get_ipod_contents() -> dict:
    """What's currently on the iPod: track list, capacity, and used/free space.
    Requires the iPod to be mounted (typically /Volumes/IPOD on macOS).
    Errors if no iPod is detected."""
    with _open_session(autoscan=False) as (cfg, _db):
        return actions.read_ipod_contents(cfg)


@mcp.tool()
def get_pending_scrobbles() -> list[dict]:
    """Cached iPod plays that haven't yet been submitted to Last.fm.
    Each entry has artist, title, album, timestamp, and duration."""
    with _open_session(autoscan=False) as (_cfg, db):
        return actions.read_pending_scrobbles(db)


@mcp.tool()
def library_health() -> dict:
    """Quick health probe: does the library directory exist, when was the
    last scan, how many tracks are missing from disk, etc. Use this when
    the user reports "something's not working"."""
    with _open_session(autoscan=False) as (cfg, db):
        health = actions.library_health(cfg, db)
        if health["last_scan_at"] is not None:
            health["last_scan_iso"] = datetime.fromtimestamp(
                health["last_scan_at"]
            ).isoformat()
        return health


# ---------------------------------------------------------------------------
# Tools — mutation (Phase 3)
#
# Tools that change state. Destructive ones (delete_playlist,
# sync_playlist_to_ipod) elicit a confirmation from the user via MCP's
# elicitation feature when the caller didn't pass `confirm=True`.
# ---------------------------------------------------------------------------


class _Confirm(BaseModel):
    """Schema for a yes/no elicitation prompt."""

    confirm: bool = Field(
        description="Confirm the action. Set false to cancel.",
    )


async def _elicit_confirm(ctx: Context, message: str) -> bool:
    """Ask the client to confirm. Returns True only on explicit accept+confirm."""
    result = await ctx.elicit(message=message, schema=_Confirm)
    if result.action != "accept" or result.data is None:
        return False
    return bool(result.data.confirm)


@mcp.tool()
def create_playlist(name: str, track_paths: list[str]) -> dict:
    """Create a new playlist with the given track paths. Errors if a playlist
    with the same name already exists — use update_playlist to replace.

    `track_paths` should be the absolute paths returned by list_tracks_by_album,
    search_tracks, etc."""
    with _open_session() as (_cfg, db):
        count = actions.create_playlist(db, name, track_paths)
        return {"name": name, "track_count": count}


@mcp.tool()
def update_playlist(name: str, track_paths: list[str]) -> dict:
    """Replace a playlist's contents (or create it if it doesn't exist).
    Returns track_count and `replaced` (True if a playlist by this name
    already existed)."""
    with _open_session() as (_cfg, db):
        count, replaced = actions.update_playlist(db, name, track_paths)
        return {"name": name, "track_count": count, "replaced": replaced}


@mcp.tool()
async def delete_playlist(ctx: Context, name: str, confirm: bool = False) -> dict:
    """Delete a saved playlist by name. If `confirm` is False (default),
    asks the user to confirm via the client. Pass `confirm=True` to skip
    the prompt."""
    with _open_session(autoscan=False) as (_cfg, db):
        if not actions.playlist_exists(db, name):
            return {"deleted": False, "reason": f"Playlist '{name}' not found."}

        if not confirm:
            track_count = len(db.get_playlist(name))
            ok = await _elicit_confirm(
                ctx,
                f"Delete playlist '{name}'? It contains {track_count} track(s). "
                "This cannot be undone.",
            )
            if not ok:
                return {"deleted": False, "reason": "user declined"}

        actions.delete_playlist(db, name)
        return {"deleted": True, "name": name}


@mcp.tool()
def add_artist_to_playlist(playlist: str, artist: str) -> dict:
    """Add every track by `artist` to `playlist` (skipping duplicates).
    Creates the playlist if it doesn't already exist. Returns the number
    of tracks actually added."""
    with _open_session() as (_cfg, db):
        added = actions.add_artist_to_playlist(db, playlist, artist)
        return {"added": added, "playlist": playlist, "artist": artist}


@mcp.tool()
def remove_artist_from_playlist(playlist: str, artist: str) -> dict:
    """Remove every track by `artist` from `playlist`. Returns the number
    of tracks removed (0 if the artist wasn't in the playlist)."""
    with _open_session(autoscan=False) as (_cfg, db):
        removed = actions.remove_artist_from_playlist(db, playlist, artist)
        return {"removed": removed, "playlist": playlist, "artist": artist}


@mcp.tool()
def submit_scrobbles(dry_run: bool = False) -> dict:
    """Submit pending iPod plays to Last.fm.

    First reads the iPod for any new plays (caching them in the local DB),
    then submits all unsent scrobbles. Pass `dry_run=True` to see what
    would be sent without actually submitting.

    Requires Last.fm to be configured (api key, secret, session key).
    Requires the iPod to be mounted to pick up new plays."""
    with _open_session(autoscan=False) as (cfg, db):
        plays_status = actions.collect_ipod_plays(cfg, db)

        if dry_run:
            pending = actions.read_pending_scrobbles(db)
            return {
                "dry_run": True,
                "plays_found_on_ipod": plays_status["plays_found"],
                "newly_cached": plays_status["new_cached"],
                "pending_total": len(pending),
                "oldest_age_days": plays_status["oldest_age_days"],
            }

        result = actions.submit_pending_scrobbles(cfg, db)
        return {
            "submitted": result.submitted,
            "failed": result.failed,
            "remaining_pending": result.remaining_pending,
            "newly_cached": plays_status["new_cached"],
            "plays_found_on_ipod": plays_status["plays_found"],
        }


@mcp.tool()
async def sync_playlist_to_ipod(
    ctx: Context, playlist: str, confirm: bool = False
) -> dict:
    """Sync a saved playlist to the iPod: copy new tracks, leave existing
    matches in place, and rewrite the iTunesDB.

    By default, computes the diff first and asks the user to confirm before
    doing anything destructive. Pass `confirm=True` to skip the prompt
    (use sparingly — this writes to the iPod).

    Requires the iPod to be mounted. Errors with InsufficientSpaceError
    if the new tracks won't fit."""
    with _open_session() as (cfg, db):
        diff = actions.compute_diff(cfg, db, playlist)

        if not diff.to_add and not diff.to_remove:
            return {
                "synced": False,
                "reason": "iPod already matches this playlist.",
                "playlist": playlist,
            }

        if not confirm:
            ok = await _elicit_confirm(
                ctx,
                f"Sync '{playlist}' to iPod? "
                f"Will add {len(diff.to_add)} track(s) "
                f"({_format_bytes(diff.add_size_bytes)}) "
                f"and {len(diff.to_remove)} track(s) currently on iPod "
                "won't be in this playlist (they stay on the iPod for now).",
            )
            if not ok:
                return {"synced": False, "reason": "user declined"}

        result = actions.sync_playlist(cfg, db, playlist, diff=diff)
        return {
            "synced": True,
            "playlist": playlist,
            "copied": len(result.copied),
            "failed": len(result.failed),
            "removed_count": result.removed_count,
            "db_write_ok": result.db_write_ok,
        }


def _format_bytes(n: int) -> str:
    if n >= 1024**3:
        return f"{n / 1024**3:.1f} GB"
    if n >= 1024**2:
        return f"{n / 1024**2:.1f} MB"
    return f"{n / 1024:.1f} KB"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Console-script entry point. Runs the server over stdio."""
    _setup_logging()
    logger.info("Starting clickwheel MCP server (stdio)")
    try:
        mcp.run(transport="stdio")
    except ClickwheelError as exc:
        logger.error("Server error: %s", exc)
        sys.exit(1)
