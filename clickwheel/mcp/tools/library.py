"""Library inspection tools — read-only queries against the indexed library."""

from __future__ import annotations

from datetime import datetime

from clickwheel import actions
from clickwheel.mcp._runtime import mcp, open_session


@mcp.tool()
def library_stats() -> dict:
    """High-level library stats: track/artist/album counts, total size and
    duration, format breakdown, and missing-metadata counts.

    Use this to give the user a quick overview of their library."""
    with open_session() as (_cfg, db):
        return actions.library_stats(db)


@mcp.tool()
def list_artists(limit: int = 500) -> list[dict]:
    """All artists in the indexed library, with track count, album count,
    and total size in bytes per artist. Excludes FLAC tracks (iPod-incompatible).

    Returns at most `limit` artists. Sorted alphabetically."""
    with open_session() as (_cfg, db):
        return actions.list_artists(db)[:limit]


@mcp.tool()
def list_albums_by_artist(artist: str) -> list[dict]:
    """Albums for a single artist, with track count, total size, and year.
    Sorted by year then album title."""
    with open_session() as (_cfg, db):
        return actions.list_albums_by_artist(db, artist)


@mcp.tool()
def list_tracks_by_album(artist: str, album: str) -> list[dict]:
    """Tracks on a single album, ordered by disc/track number. Returns full
    track records including path, duration, and file size."""
    with open_session() as (_cfg, db):
        return actions.list_tracks_by_album(db, artist, album)


@mcp.tool()
def search_tracks(query: str, limit: int = 50) -> list[dict]:
    """Case-insensitive substring search across artist, album, and title.
    Returns at most `limit` matching tracks. Use this when the user asks
    about a song without remembering the exact artist or album."""
    with open_session() as (_cfg, db):
        return actions.search_tracks(db, query, limit=limit)


@mcp.tool()
def library_health() -> dict:
    """Quick health probe: does the library directory exist, when was the
    last scan, how many tracks are missing from disk, etc. Use this when
    the user reports "something's not working"."""
    with open_session(autoscan=False) as (cfg, db):
        health = actions.library_health(cfg, db)
        if health["last_scan_at"] is not None:
            health["last_scan_iso"] = datetime.fromtimestamp(
                health["last_scan_at"]
            ).isoformat()
        return health
