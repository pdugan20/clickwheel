"""iPod tools — read iPod state, sync, and eject."""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from clickwheel import actions
from clickwheel.config import load_config
from clickwheel.db import Database
from clickwheel.mcp._runtime import (
    DESTRUCTIVE,
    MUTATION,
    READ_ONLY,
    format_bytes,
    format_count,
    mcp,
    open_session,
    render,
)
from clickwheel.mcp.ui import ui_tool_meta
from clickwheel.mcp.ui_resources import IPOD_CAPACITY_URI


def _summarize_track(t: dict) -> dict:
    """Project an iPod track record down to chat-friendly fields."""
    return {
        "artist": t.get("artist") or "",
        "title": t.get("title") or "",
        "album": t.get("album") or "",
        "size_bytes": t.get("size") or 0,
    }


@mcp.tool(annotations=READ_ONLY, meta=ui_tool_meta(IPOD_CAPACITY_URI))
def get_ipod_contents() -> dict:
    """High-level snapshot of what's on the iPod: capacity, used/free space,
    track/artist/album counts, and the top 25 artists by track count.
    Does NOT return the full track list — use `list_ipod_tracks` to page
    through tracks (optionally filtered by artist).

    Requires the iPod to be mounted (typically /Volumes/IPOD on macOS).
    Errors if no iPod is detected.

    When to use: the user asks "what's on my iPod?" or "how full is it?".
    Cheap and stays well under the tool-result token cap.

    After this: `list_ipod_tracks` to drill into specific tracks,
    `sync_playlist_to_ipod` to push a saved playlist, `submit_scrobbles`
    to read recent plays, or `eject_ipod` when finished.
    """
    with open_session() as (cfg, _db):
        contents = actions.read_ipod_contents(cfg)
        tracks = contents["tracks"]
        # Fold collabs under their canonical lead artist. primary_artist
        # prefers the album_artist field (which iTunes/Music keeps clean
        # — collabs like "Taylor Swift / HAIM" tag album_artist as
        # "Taylor Swift") and falls back to the per-track artist tag
        # only when album_artist is missing.
        artist_counts = Counter(
            actions.primary_artist(t.get("artist"), t.get("album_artist"))
            for t in tracks
        )
        album_count = len({t.get("album") or "" for t in tracks})
        top_artists = [
            {"artist": a, "track_count": c} for a, c in artist_counts.most_common(25)
        ]
        data = {
            "capacity_bytes": contents["capacity_bytes"],
            "used_bytes": contents["used_bytes"],
            "free_bytes": contents["free_bytes"],
            "track_count": len(tracks),
            "artist_count": len(artist_counts),
            "album_count": album_count,
            "top_artists": top_artists,
        }
        text = (
            f"iPod: {format_count(len(tracks), 'track')} across "
            f"{format_count(len(artist_counts), 'artist')}, "
            f"{format_bytes(contents['used_bytes'])} used / "
            f"{format_bytes(contents['capacity_bytes'])} total "
            f"({format_bytes(contents['free_bytes'])} free)."
        )
        return render(text, data)


@mcp.tool(annotations=READ_ONLY)
def list_ipod_tracks(
    artist: Annotated[
        str | None,
        Field(
            description=(
                "Optional artist filter (exact match). Omit to page through all tracks."
            ),
        ),
    ] = None,
    limit: Annotated[
        int,
        Field(description="Max tracks to return.", ge=1, le=200),
    ] = 50,
    offset: Annotated[
        int,
        Field(description="Pagination offset (0 = first page).", ge=0),
    ] = 0,
) -> list[dict]:
    """Paginated list of tracks on the iPod, optionally filtered by artist.
    Each track is the chat-friendly slice — artist, title, album, size in
    bytes. For the full per-track payload, use the CLI.

    When to use: the user asks for specific iPod tracks — "what Beatles
    songs are on my iPod?", "show me the next batch", etc. Use after
    `get_ipod_contents` to know the total count and top artists.

    Requires the iPod to be mounted.
    """
    with open_session() as (cfg, _db):
        tracks = actions.list_ipod_tracks(
            cfg, artist=artist, limit=limit, offset=offset
        )
        slim = [_summarize_track(t) for t in tracks]
        if not slim:
            text = (
                f"No iPod tracks for '{artist}'."
                if artist
                else f"No iPod tracks at offset {offset}."
            )
            return render(text, slim)
        text = (
            f"{format_count(len(slim), 'track')}"
            + (f" by {artist}" if artist else "")
            + (f" (offset {offset})" if offset else "")
            + "."
        )
        return render(text, slim)


@mcp.tool(annotations=DESTRUCTIVE)
async def sync_playlist_to_ipod(
    playlist: Annotated[str, Field(description="Saved playlist name to sync.")],
    ctx: Context,
) -> dict:
    """Push a saved playlist to the iPod. Copies new tracks and updates the
    iPod's library so it sees them. Tracks already on the iPod that aren't
    in the playlist stay where they are — sync is additive, never deletes.

    Reports progress per track via MCP `notifications/progress` so the host
    can render a live progress bar (Claude Desktop shows the per-track
    artist/title beneath the tool result while files copy).

    Flagged destructive, so MCP clients gate this call with a native
    Allow/Deny prompt. Before invoking, summarize the diff for the user
    (use `get_playlist` and `get_ipod_contents` for context): how many
    tracks will be added, how much space they'll use. The user clicks
    Allow knowing what's about to happen.

    Requires the iPod to be mounted. Errors if the new tracks won't fit.

    Talk to the user in plain language. Don't mention internal terms like
    "iTunesDB" or field names like `library_updated`. Say things like
    "the iPod's library was updated" or "your iPod is ready to unplug."

    When to use: the user says "sync my playlist", "push to the iPod",
    "load up the iPod".

    After a successful sync: offer to eject the iPod (call `eject_ipod`).
    If the result reports `library_updated: false`, the music copied but
    the iPod won't see it yet — tell the user that and suggest re-running
    the sync or using the CLI for retry.
    """
    # actions.sync_playlist is synchronous and blocking (file copies,
    # iPod database write). Running it directly in the async tool would
    # pin the event loop and prevent progress notifications from flushing
    # to the client until the sync finishes. So we hand the work to a
    # worker thread and bridge per-track on_event callbacks back to the
    # main loop via run_coroutine_threadsafe.
    #
    # Each worker reopens its own SQLite connection because the default
    # check_same_thread=True forbids cross-thread reuse.
    cfg = load_config()
    loop = asyncio.get_running_loop()

    def worker() -> tuple[actions.Diff, actions.SyncResult | None]:
        db = Database(cfg.db_path)
        try:
            diff = actions.compute_diff(cfg, db, playlist)
            if not diff.to_add and not diff.to_remove:
                return diff, None

            def on_event(ev: actions.SyncEvent) -> None:
                artist = ev.track.get("artist") or "Unknown"
                title = ev.track.get("title") or "Unknown"
                # Fire-and-forget — progress notifications are best-effort.
                # If the host didn't supply a progressToken, FastMCP's
                # report_progress is a no-op; the future just resolves.
                asyncio.run_coroutine_threadsafe(
                    ctx.report_progress(ev.current, ev.total, f"{artist} — {title}"),
                    loop,
                )

            result = actions.sync_playlist(
                cfg, db, playlist, diff=diff, on_event=on_event
            )
            return diff, result
        finally:
            db.close()

    diff, result = await asyncio.to_thread(worker)

    if result is None:
        data = {
            "synced": False,
            "reason": "iPod already matches this playlist.",
            "playlist": playlist,
        }
        return render(f"iPod already matches '{playlist}' — nothing to do.", data)

    if result.library_updated:
        text = (
            f"Synced '{playlist}': added "
            f"{format_count(len(result.copied), 'track')} "
            f"({format_bytes(diff.add_size_bytes)}). "
            "Offer to eject the iPod when the user is ready to unplug."
        )
    else:
        text = (
            f"Synced '{playlist}', but the iPod's library wasn't "
            f"fully updated. {format_count(len(result.copied), 'track')} "
            "copied to the device, but the iPod may not see them yet. "
            "Suggest the CLI (`clickwheel sync`) for retry support."
        )

    data = {
        "synced": True,
        "playlist": playlist,
        "added": len(result.copied),
        "failed": len(result.failed),
        # Tracks already on the iPod that aren't in this playlist —
        # left alone; sync is additive.
        "also_on_ipod": result.kept_in_place_count,
        "library_updated": result.library_updated,
    }
    return render(text, data)


@mcp.tool(annotations=DESTRUCTIVE)
async def add_tracks_to_ipod(
    paths: Annotated[
        list[str],
        Field(
            description=(
                "Absolute paths (from the indexed library) of tracks to "
                "add. Use list_tracks_by_album / search_tracks to get "
                "paths — never invent them."
            ),
        ),
    ],
    ctx: Context,
) -> dict:
    """Push specific tracks to the iPod's library WITHOUT creating a
    playlist on the device. Tracks land in the main library and are
    browsable by artist/album.

    Use this for the common "add these albums to my iPod" / "put more
    Weezer on the iPod" / "load up the new Olivia Rodrigo record" flow
    where the user doesn't need a named, curated playlist that appears
    under Music → Playlists on the iPod itself.

    For a curated playlist (e.g. "workout mix", "road trip 2026") that
    the user wants to browse on the device, build it with
    `create_playlist` and then call `sync_playlist_to_ipod` — that one
    actually creates the iPod-side playlist.

    Reports per-track progress via MCP `notifications/progress` so the
    host can render a live progress bar (artist — title) beneath the
    tool result while files copy.

    Flagged destructive, so clients gate this call with a native
    Allow/Deny prompt. Summarize the impact in your reply before
    calling (track count, size, target iPod) so the user has context.

    Errors
    ------
    - LibraryNotFoundError: music_dir not mounted.
    - PathsNotFoundError: one or more paths aren't indexed. Suggest
      `clickwheel scan` or double-check the paths.
    - MissingTracksError: one or more paths point to files that no
      longer exist on disk.
    - IpodNotFoundError: no iPod mounted.
    - InsufficientSpaceError: tracks won't fit. Surface the numbers.

    After: offer to eject the iPod via `eject_ipod` when done.
    """
    cfg = load_config()
    loop = asyncio.get_running_loop()

    def worker() -> actions.SyncResult:
        db = Database(cfg.db_path)
        try:

            def on_event(ev: actions.SyncEvent) -> None:
                artist = ev.track.get("artist") or "Unknown"
                title = ev.track.get("title") or "Unknown"
                asyncio.run_coroutine_threadsafe(
                    ctx.report_progress(ev.current, ev.total, f"{artist} — {title}"),
                    loop,
                )

            return actions.add_tracks_to_ipod(cfg, db, paths, on_event=on_event)
        finally:
            db.close()

    result = await asyncio.to_thread(worker)

    if not result.copied and not result.failed:
        if result.kept_in_place_count:
            text = (
                f"All {result.kept_in_place_count} requested tracks were "
                "already on the iPod — nothing to copy."
            )
        else:
            text = "No tracks to copy."
        data = {
            "added": 0,
            "failed": 0,
            "already_present": result.kept_in_place_count,
            "library_updated": result.library_updated,
        }
        return render(text, data)

    if result.library_updated:
        copy_size = sum(t[0].get("file_size") or 0 for t in result.copied)
        suffix = (
            f" ({result.kept_in_place_count} already on the iPod)"
            if result.kept_in_place_count
            else ""
        )
        text = (
            f"Added {format_count(len(result.copied), 'track')} "
            f"({format_bytes(copy_size)}) to the iPod{suffix}. "
            "Offer to eject when the user is ready to unplug."
        )
    else:
        text = (
            f"{format_count(len(result.copied), 'track')} copied to the "
            "iPod, but the library wasn't fully updated. The new tracks "
            "may not be visible on the device yet — suggest the CLI "
            "(`clickwheel sync`) for retry support."
        )

    data = {
        "added": len(result.copied),
        "failed": len(result.failed),
        "already_present": result.kept_in_place_count,
        "library_updated": result.library_updated,
    }
    return render(text, data)


@mcp.tool(annotations=DESTRUCTIVE)
async def add_artist_to_ipod(
    artist: Annotated[
        str,
        Field(description="Artist name (exact match, case-sensitive)."),
    ],
    ctx: Context,
) -> dict:
    """Push every track by an artist to the iPod's library, no playlist
    artifact. Convenience wrapper over `add_tracks_to_ipod` that resolves
    the artist's tracks via the library index.

    Use for "add all the Beatles to my iPod" style requests. Same
    semantics as `add_tracks_to_ipod`: tracks land in the main library,
    browsable by artist/album on the device.

    For a curated playlist of an artist's tracks that shows up under
    Music → Playlists, use `add_artist_to_playlist` + `create_playlist`
    + `sync_playlist_to_ipod`.

    Errors as for `add_tracks_to_ipod`, plus: returns a "no tracks for
    artist" message if the name doesn't match the library index. Names
    are case-sensitive — check via `list_artists` if unsure.
    """
    cfg = load_config()
    loop = asyncio.get_running_loop()

    def worker() -> tuple[list[str], actions.SyncResult | None]:
        db = Database(cfg.db_path)
        try:
            paths = actions.collect_tracks_for_artist(db, artist)
            if not paths:
                return [], None

            def on_event(ev: actions.SyncEvent) -> None:
                a = ev.track.get("artist") or "Unknown"
                t = ev.track.get("title") or "Unknown"
                asyncio.run_coroutine_threadsafe(
                    ctx.report_progress(ev.current, ev.total, f"{a} — {t}"),
                    loop,
                )

            result = actions.add_tracks_to_ipod(cfg, db, paths, on_event=on_event)
            return paths, result
        finally:
            db.close()

    paths, result = await asyncio.to_thread(worker)

    if not paths:
        return render(
            f"No tracks found for '{artist}'. Names are case-sensitive — "
            "check spelling with `list_artists`.",
            {"artist": artist, "added": 0, "found_in_library": 0},
        )

    if result is None:  # unreachable but keep mypy happy
        return render("Internal error: add returned no result.", {})

    if not result.copied and not result.failed:
        text = (
            f"All {len(paths)} tracks by {artist} are already on the iPod "
            "— nothing to copy."
        )
        data = {
            "artist": artist,
            "added": 0,
            "already_present": result.kept_in_place_count,
            "found_in_library": len(paths),
        }
        return render(text, data)

    if result.library_updated:
        copy_size = sum(t[0].get("file_size") or 0 for t in result.copied)
        suffix = (
            f" ({result.kept_in_place_count} already on the iPod)"
            if result.kept_in_place_count
            else ""
        )
        text = (
            f"Added {format_count(len(result.copied), 'track')} by "
            f"{artist} ({format_bytes(copy_size)}) to the iPod{suffix}. "
            "Offer to eject when the user is done."
        )
    else:
        text = (
            f"{format_count(len(result.copied), 'track')} by {artist} "
            "copied to the iPod, but the library wasn't fully updated. "
            "The tracks may not be visible on the device yet — suggest "
            "`clickwheel sync` for retry."
        )

    data = {
        "artist": artist,
        "added": len(result.copied),
        "failed": len(result.failed),
        "already_present": result.kept_in_place_count,
        "found_in_library": len(paths),
        "library_updated": result.library_updated,
    }
    return render(text, data)


@mcp.tool(annotations=MUTATION)
def eject_ipod() -> dict:
    """Safely unmount the iPod via `diskutil eject`. Idempotent in spirit:
    re-running after a successful eject just errors with IpodNotFoundError
    (no iPod mounted), which is fine.

    Errors:
    - IpodNotFoundError if no iPod is mounted (treat as 'already ejected'
      or 'never mounted' — surface gently).
    - EjectFailedError if diskutil exits non-zero (typical cause: a process
      has files open on the iPod). Suggest the user retry after closing
      music apps.

    When to use: after a successful sync or scrobble session, or any time
    the user says "eject", "safely disconnect", "unmount the iPod".
    """
    with open_session() as (cfg, _db):
        data = actions.eject_ipod(cfg)
        return render("iPod ejected — safe to unplug.", data)
