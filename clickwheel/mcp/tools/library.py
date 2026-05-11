"""Library inspection tools — read-only queries against the indexed library."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Annotated

from pydantic import Field

from clickwheel import actions
from clickwheel.mcp._runtime import (
    READ_ONLY,
    format_bytes,
    format_count,
    mcp,
    open_session,
    render,
)
from clickwheel.mcp.ui import ui_tool_meta
from clickwheel.mcp.ui_resources import LIBRARY_STATS_URI


@mcp.tool(annotations=READ_ONLY, meta=ui_tool_meta(LIBRARY_STATS_URI))
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
        data = actions.library_stats(db)
        s = data["stats"]
        if not s["total_tracks"]:
            return render(
                "Library is empty — run `clickwheel scan` to index your music.",
                data,
            )
        size = format_bytes(s["total_bytes"] or 0)
        hours = (s["total_seconds"] or 0) / 3600
        formats = ", ".join(
            f"{f['format'].upper()} {f['count']:,}" for f in data["formats"]
        )
        text = (
            f"Library: {s['total_tracks']:,} tracks, {s['artists']:,} artists, "
            f"{s['albums']:,} albums ({size}, {hours:.0f} hours). "
            f"Formats: {formats}."
        )
        return render(text, data)


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
        all_artists = actions.list_artists(db)
        result = all_artists[:limit]
        if not result:
            return render("No artists indexed — run `clickwheel scan` first.", result)
        truncated = (
            f" (truncated from {len(all_artists):,})"
            if len(all_artists) > limit
            else ""
        )
        text = f"{format_count(len(result), 'artist')}, alphabetical{truncated}."
        return render(text, result)


@mcp.tool(annotations=READ_ONLY)
def list_albums_by_artist(
    artist: Annotated[
        str,
        Field(description="Artist name (exact match, case-sensitive)."),
    ],
) -> list[dict]:
    """Albums for a single artist, ordered by year then album title. Each
    entry includes track count, total size in bytes, and the year (if known).

    When to use: the canonical way to BROWSE an artist's whole catalog —
    "show me everything by Bob Dylan", "what Wilco albums do I have?",
    or any "build me a playlist of X best tracks" flow. Returns the
    complete discography in one call, no result cap, no alphabet
    truncation (unlike `search_tracks` which silently chops at 50–500).

    After this: `list_tracks_by_album` to get individual track paths
    (needed by `create_playlist` / `update_playlist`).
    """
    with open_session() as (_cfg, db):
        result = actions.list_albums_by_artist(db, artist)
        if not result:
            return render(
                f"No albums found for '{artist}'. Names are case-sensitive — "
                "check spelling, or use `search_tracks` for a fuzzy match.",
                result,
            )
        years = [a["year"] for a in result if a.get("year")]
        span = (
            f" ({min(years)}–{max(years)})"
            if years and min(years) != max(years)
            else (f" ({years[0]})" if years else "")
        )
        text = f"{format_count(len(result), 'album')} by {artist}{span}."
        return render(text, result)


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
        result = actions.list_tracks_by_album(db, artist, album)
        if not result:
            return render(
                f"No tracks found for '{artist}' / '{album}'. "
                "Both fields are case-sensitive.",
                result,
            )
        total_seconds = sum(t.get("duration_seconds") or 0 for t in result)
        minutes = total_seconds / 60
        text = (
            f"{format_count(len(result), 'track')} on '{album}' by {artist}, "
            f"{minutes:.0f}m total."
        )
        return render(text, result)


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

    When to use: the user mentions a specific track or theme without
    remembering the exact artist/album. Always start here when the query
    is fuzzy — never guess at what tracks exist.

    DO NOT use this to browse an artist's full catalog. Results are
    alphabetised and capped (default 50, max 500), so a prolific artist
    like Bob Dylan or The Beatles will overflow and you'll silently miss
    everything past the cap. For an artist deep-dive use
    `list_albums_by_artist` (groups the whole discography) then
    `list_tracks_by_album` for the albums you want.

    After this: collect `path` values for `create_playlist` /
    `update_playlist`, or call `list_tracks_by_album` for the full album.
    """
    with open_session() as (_cfg, db):
        result = actions.search_tracks(db, query, limit=limit)
        if not result:
            text = (
                "Empty query — pass a search term."
                if not query.strip()
                else f"No tracks match '{query}'. Try a different word, or "
                "broaden by artist/album."
            )
            return render(text, result)
        if len(result) == limit:
            text = (
                f"Hit the {limit}-result cap on '{query}'. Results are "
                "alphabetical, so anything past the cap is missing. For an "
                "artist deep-dive call `list_albums_by_artist` instead — "
                "it returns the full discography. Or re-call with a higher "
                "`limit` (max 500)."
            )
        else:
            text = f"Found {format_count(len(result), 'track')} matching '{query}'."
        return render(text, result)


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
    with open_session() as (cfg, db):
        health = actions.library_health(cfg, db)
        if health["last_scan_at"] is not None:
            health["last_scan_iso"] = datetime.fromtimestamp(
                health["last_scan_at"]
            ).isoformat()

        problems = []
        if not health["library_dir_exists"]:
            problems.append(f"music_dir '{health['library_dir']}' doesn't exist")
        if health["missing_tracks"]:
            problems.append(
                f"{health['missing_tracks']:,} indexed tracks no longer on disk"
            )
        if health["last_scan_at"] is None:
            problems.append("never scanned — run `clickwheel scan`")

        if problems:
            text = "Library issues: " + "; ".join(problems) + "."
        else:
            age_h = (time.time() - health["last_scan_at"]) / 3600
            text = (
                f"Library OK: {health['total_tracks']:,} tracks, no missing "
                f"files. Last scan {age_h:.1f}h ago."
            )
        return render(text, health)
