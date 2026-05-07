"""Library inspection tools — read-only queries against the indexed library."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import Field

from clickwheel import actions
from clickwheel.mcp._runtime import READ_ONLY, mcp, open_session


@mcp.tool(annotations=READ_ONLY)
def library_stats() -> dict:
    """High-level stats for the indexed music library.

    Returns total tracks/artists/albums, total size in bytes, total duration
    in seconds, format breakdown (mp3/m4a/flac counts), and counts of tracks
    missing common metadata fields.

    When to use: the user wants an overview ("how big is my library?", "how
    many albums do I have?"). Run this first before suggesting next steps.

    After this: `library_health` to verify scan freshness, or `list_artists`
    to drill in.
    """
    with open_session() as (_cfg, db):
        return actions.library_stats(db)


@mcp.tool(annotations=READ_ONLY)
def list_artists(
    limit: Annotated[
        int,
        Field(description="Max artists to return.", ge=1, le=5000),
    ] = 500,
) -> list[dict]:
    """All artists in the indexed library, alphabetical, with track count,
    album count, and total size in bytes per artist. FLAC tracks are excluded
    (the iPod doesn't play FLAC).

    When to use: the user asks "what artists do I have?", or you need to
    pick names for `list_albums_by_artist` / `add_artist_to_playlist`.

    After this: `list_albums_by_artist` to drill into one, or
    `add_artist_to_playlist` to bulk-add an artist's whole catalog.
    """
    with open_session() as (_cfg, db):
        return actions.list_artists(db)[:limit]


@mcp.tool(annotations=READ_ONLY)
def list_albums_by_artist(
    artist: Annotated[
        str,
        Field(description="Artist name (exact match, case-sensitive)."),
    ],
) -> list[dict]:
    """Albums for a single artist, ordered by year then album title. Each
    entry includes track count, total size in bytes, and the year (if known).

    When to use: drilling into an artist's discography after `list_artists`,
    or before calling `list_tracks_by_album` for a specific album.

    After this: `list_tracks_by_album` to get individual track paths
    (needed by `create_playlist` / `update_playlist`).
    """
    with open_session() as (_cfg, db):
        return actions.list_albums_by_artist(db, artist)


@mcp.tool(annotations=READ_ONLY)
def list_tracks_by_album(
    artist: Annotated[
        str,
        Field(description="Artist name (exact match)."),
    ],
    album: Annotated[
        str,
        Field(description="Album title (exact match)."),
    ],
) -> list[dict]:
    """All tracks on one album, ordered by disc/track number. Returns full
    track records: title, path, duration, file size, format, year, etc.

    When to use: building a playlist that includes a specific album, or
    answering questions about album contents.

    After this: collect the `path` values and pass them to `create_playlist`
    or `update_playlist`.
    """
    with open_session() as (_cfg, db):
        return actions.list_tracks_by_album(db, artist, album)


@mcp.tool(annotations=READ_ONLY)
def search_tracks(
    query: Annotated[
        str,
        Field(description="Substring to match. Empty/whitespace returns []."),
    ],
    limit: Annotated[
        int,
        Field(description="Max results.", ge=1, le=500),
    ] = 50,
) -> list[dict]:
    """Case-insensitive substring search across artist, album, and title.

    When to use: the user mentions a track or theme without remembering the
    exact artist/album. Always start here when the query is fuzzy — never
    guess at what tracks exist.

    After this: collect `path` values for `create_playlist` /
    `update_playlist`, or call `list_tracks_by_album` for the full album.
    """
    with open_session() as (_cfg, db):
        return actions.search_tracks(db, query, limit=limit)


@mcp.tool(annotations=READ_ONLY)
def library_health() -> dict:
    """Setup probe: does the library directory exist, when was the last
    scan, how many indexed tracks are now missing from disk, is auto-scan
    enabled, etc.

    When to use: the user reports "something's broken" or you suspect the
    library index is out of date. Cheap to call.

    After this: nothing automatic. If `last_scan_at` is old or
    `library_dir_exists` is false, surface that to the user.
    """
    with open_session(autoscan=False) as (cfg, db):
        health = actions.library_health(cfg, db)
        if health["last_scan_at"] is not None:
            health["last_scan_iso"] = datetime.fromtimestamp(
                health["last_scan_at"]
            ).isoformat()
        return health
