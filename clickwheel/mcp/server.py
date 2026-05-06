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

from mcp.server.fastmcp import FastMCP

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
