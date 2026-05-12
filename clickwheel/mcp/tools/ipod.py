"""iPod tools — read iPod state, sync, and eject."""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from clickwheel import actions
from clickwheel._sync_detail import detail_for_paths, detail_for_tracks
from clickwheel.config import load_config
from clickwheel.db import Database
from clickwheel.mcp import _sync_state
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
from clickwheel.mcp.ui_resources import IPOD_CAPACITY_URI, SYNC_RESULT_URI


def _push_progress(
    loop: asyncio.AbstractEventLoop,
    ctx: Context,
    ev: actions.SyncEvent | actions.RemoveEvent,
) -> None:
    """Common progress sink: updates the global sync-state resource AND
    fires Context.report_progress for hosts that surface it natively.

    The state update is what powers the live sync-result iframe (it
    polls state://clickwheel/sync-progress). The report_progress call
    is a belt-and-suspenders fallback for clients that DO render
    notifications/progress visibly (Claude Desktop currently doesn't,
    but the spec says they should).
    """
    artist = ev.track.get("artist") or "Unknown"
    title = ev.track.get("title") or "Unknown"
    message = f"{artist} — {title}"
    _sync_state.update(ev.current, ev.total, message)
    asyncio.run_coroutine_threadsafe(
        ctx.report_progress(ev.current, ev.total, message),
        loop,
    )


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
def list_ipod_playlists() -> list[dict]:
    """List the playlists currently on the iPod (the ones visible under
    Music → Playlists on the device).

    Returns the user-visible playlists only — the auto-generated master
    "iPod" library playlist is filtered out since that's not a thing the
    user thinks of as a playlist. Each entry carries: name, track_count,
    total_bytes, is_smart (smart playlists are iTunes-created auto-filter
    playlists like the "Music" or "Recently Added" defaults).

    Use this to:
      - Answer "what playlists are on my iPod?"
      - Check for a name conflict before `sync_playlist_to_ipod` (though
        the sync tool will also detect conflicts and ask you to resolve).
      - Help the user decide if a sync should merge, replace, or rename.

    Note: this lists IPOD-side playlists. For draft playlists you've
    built in clickwheel but haven't synced yet, use `list_playlists`.

    Requires the iPod to be mounted.
    """
    with open_session() as (cfg, _db):
        result = actions.list_ipod_playlists(cfg)
        if not result:
            return render(
                "No user playlists on the iPod (the main library is "
                "always there, but no curated collections).",
                result,
            )
        names = ", ".join(f"'{p['name']}' ({p['track_count']})" for p in result)
        text = f"{format_count(len(result), 'playlist')} on the iPod: {names}."
        return render(text, result)


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


@mcp.tool(
    annotations=DESTRUCTIVE,
    meta=ui_tool_meta(SYNC_RESULT_URI),
)
async def sync_playlist_to_ipod(
    playlist: Annotated[str, Field(description="Saved playlist name to sync.")],
    ctx: Context,
    on_conflict: Annotated[
        str | None,
        Field(
            description=(
                "How to resolve a same-name playlist already on the iPod. "
                "Omit on the first call; if a conflict exists, this tool "
                "returns a structured error so you can ask the user to "
                "pick one of: 'merge' (combine tracks), 'replace' "
                "(overwrite contents), 'rename' (use target_name for a "
                "new playlist name)."
            ),
        ),
    ] = None,
    target_name: Annotated[
        str | None,
        Field(
            description=(
                "Required when on_conflict='rename'. The new iPod-side "
                "playlist name to use instead of the clickwheel name."
            ),
        ),
    ] = None,
) -> dict:
    """Push a saved playlist (the clickwheel-side draft) to the iPod
    AND create/update the corresponding playlist on the device under
    Music → Playlists. Copies any missing tracks first.

    Two effects on the iPod:
      1. The playlist's tracks land in the iPod's main library (additive
         — sync never deletes tracks from the device).
      2. A playlist with the same name appears under Music → Playlists,
         containing those tracks. This is the curated-collection thing
         the user can browse on the device.

    For "just put music on the iPod without a playlist artifact" use
    `add_tracks_to_ipod` or `add_artist_to_ipod` — DO NOT create
    throwaway playlists just to push tracks.

    Reports progress per track via MCP `notifications/progress` so the
    host can render a live progress bar while files copy.

    Same-name handling
    ------------------
    If a playlist with the same name already exists on the iPod (e.g.
    leftover from a previous sync or iTunes), the first call returns
    a structured error describing the conflict. Present the options to
    the user in plain language:

      • merge   — combine the existing iPod playlist's tracks with the
                  new tracks (dedup; existing track order is preserved).
      • replace — overwrite the existing playlist's contents with the
                  new tracks. Doesn't delete tracks from the library.
      • rename  — keep the existing playlist as-is, write the new one
                  under a different name (set target_name).

    Then re-call with the chosen `on_conflict` (+ `target_name` for
    rename).

    Flagged destructive — clients gate with native Allow/Deny prompts.
    Summarize the impact before calling so the user has context.

    Errors
    ------
    - LibraryNotFoundError: music_dir not mounted.
    - PlaylistNotFoundError: clickwheel-side playlist doesn't exist.
    - MissingTracksError: tracks in the playlist reference files no
      longer on disk. Surface the count, suggest `heal_playlist`.
    - IpodNotFoundError: no iPod mounted.
    - InsufficientSpaceError: new tracks won't fit.
    - PlaylistConflictError: same-name iPod playlist exists; ask the
      user which on_conflict mode to use.

    After success: offer to eject the iPod (`eject_ipod`).
    """
    cfg = load_config()
    loop = asyncio.get_running_loop()

    def worker() -> tuple[actions.Diff | None, actions.SyncResult | None, dict | None]:
        db = Database(cfg.db_path)
        try:
            diff = actions.compute_diff(cfg, db, playlist)
            if not diff.to_add and not diff.to_remove and not on_conflict:
                # No tracks to copy AND no explicit conflict resolution
                # requested — if the iPod playlist already exists with
                # the right contents, this is a no-op. But if the
                # iPod-side playlist is missing entirely (sync was done
                # by an older version that only copied tracks), we
                # still want to write it. Let sync_playlist sort it out
                # below; it'll just no-op the copy step.
                pass

            _sync_state.start(
                kind="sync",
                total=len(diff.to_add),
                operation=f"playlist '{playlist}'",
                detail=detail_for_tracks(diff.to_add),
            )

            def on_event(ev: actions.SyncEvent) -> None:
                _push_progress(loop, ctx, ev)

            try:
                result = actions.sync_playlist(
                    cfg,
                    db,
                    playlist,
                    diff=diff,
                    on_event=on_event,
                    on_conflict=on_conflict,
                    target_name=target_name,
                )
            except actions.PlaylistConflictError as exc:
                return (
                    diff,
                    None,
                    {
                        "kind": "conflict",
                        "existing_name": exc.existing_name,
                        "existing_track_count": exc.existing_track_count,
                        "message": str(exc),
                    },
                )
            return diff, result, None
        finally:
            db.close()
            _sync_state.finish()

    diff, result, conflict = await asyncio.to_thread(worker)

    if conflict is not None:
        text = (
            f"The iPod already has a playlist called "
            f"'{conflict['existing_name']}' with "
            f"{format_count(conflict['existing_track_count'], 'track')}. "
            "Ask the user how to proceed: merge (combine tracks), "
            "replace (overwrite the iPod's version with your '"
            f"{playlist}'), or rename (write to a different name). "
            "Re-call this tool with the chosen on_conflict (and "
            "target_name for rename)."
        )
        data = {
            "synced": False,
            "conflict": conflict,
            "playlist": playlist,
        }
        return render(text, data)

    if result is None:
        # Defensive: shouldn't happen on a non-conflict path.
        return render(
            f"iPod already matches '{playlist}' — nothing to do.",
            {"synced": False, "playlist": playlist},
        )

    final_name = target_name if on_conflict == "rename" else playlist
    if result.library_updated:
        if result.copied:
            text = (
                f"Synced '{playlist}' to the iPod as '{final_name}': "
                f"added {format_count(len(result.copied), 'track')} "
                f"({format_bytes(diff.add_size_bytes) if diff else '?'}). "
                "Offer to eject the iPod when ready."
            )
        else:
            text = (
                f"Updated the iPod's '{final_name}' playlist — all "
                "tracks were already on the device. Offer to eject when "
                "ready."
            )
    else:
        text = (
            f"Synced '{playlist}', but the iPod's library wasn't fully "
            "updated. The music copied but may not be visible yet — "
            "suggest re-running the sync or using `clickwheel sync` "
            "for retry support."
        )

    data = {
        "synced": True,
        "playlist": playlist,
        "ipod_playlist": final_name,
        "on_conflict": on_conflict,
        "added": len(result.copied),
        "failed": len(result.failed),
        # Tracks already on the iPod that aren't in this playlist —
        # left alone; sync is additive.
        "also_on_ipod": result.kept_in_place_count,
        "library_updated": result.library_updated,
    }
    return render(text, data)


@mcp.tool(
    annotations=DESTRUCTIVE,
    meta=ui_tool_meta(SYNC_RESULT_URI),
)
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
            _sync_state.start(
                kind="add",
                total=len(paths),
                operation=f"{len(paths)} tracks",
                detail=detail_for_paths(db, paths),
            )

            def on_event(ev: actions.SyncEvent) -> None:
                _push_progress(loop, ctx, ev)

            return actions.add_tracks_to_ipod(cfg, db, paths, on_event=on_event)
        finally:
            db.close()
            _sync_state.finish()

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


@mcp.tool(
    annotations=DESTRUCTIVE,
    meta=ui_tool_meta(SYNC_RESULT_URI),
)
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

            _sync_state.start(
                kind="add",
                total=len(paths),
                operation=f"all tracks by {artist}",
                detail=detail_for_paths(db, paths),
            )

            def on_event(ev: actions.SyncEvent) -> None:
                _push_progress(loop, ctx, ev)

            result = actions.add_tracks_to_ipod(cfg, db, paths, on_event=on_event)
            return paths, result
        finally:
            db.close()
            _sync_state.finish()

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


@mcp.tool(
    annotations=DESTRUCTIVE,
    meta=ui_tool_meta(SYNC_RESULT_URI),
)
async def remove_tracks_from_ipod(
    paths: Annotated[
        list[str],
        Field(
            description=(
                "Absolute paths (from the indexed library) of tracks to "
                "remove from the iPod. Get these via list_tracks_by_album "
                "or search_tracks. Paths that aren't on the iPod are "
                "reported back as unmatched — not an error."
            ),
        ),
    ],
    ctx: Context,
) -> dict:
    """Remove specific tracks from the iPod — drops them from the
    iTunesDB AND deletes the underlying audio files from the device.

    Use for "take Pinkerton off my iPod" / "remove these test tracks" /
    "free up space, delete this album." Tracks come off the device
    entirely — they remain in your library (clickwheel's index of your
    Mac's music folder is untouched) and can be re-added later via
    `add_tracks_to_ipod`.

    Reports progress per track via MCP `notifications/progress`.

    Flagged destructive — clients gate with native Allow/Deny prompts.
    Summarize the impact in your reply BEFORE calling: how many tracks,
    estimated space freed (look up file sizes via the library), and the
    confirmation that this deletes from the iPod (not from the library).

    For removing every track by an artist, prefer `remove_artist_from_ipod`
    — it doesn't need path resolution and handles primary-artist
    rollup naturally (e.g., removing "Taylor Swift" also drops
    "Taylor Swift / HAIM" tracks).

    Errors
    ------
    - LibraryNotFoundError: music_dir not mounted.
    - IpodNotFoundError: no iPod mounted.
    - Paths not in the library OR triples not on the iPod are reported
      as `not_matched` in the result — not raised.

    After success: offer to eject the iPod via `eject_ipod`. Used space
    will reflect the freed bytes immediately.
    """
    cfg = load_config()
    loop = asyncio.get_running_loop()

    def worker() -> actions.RemoveResult:
        db = Database(cfg.db_path)
        try:
            _sync_state.start(
                kind="remove",
                total=len(paths),
                operation=f"{len(paths)} tracks",
                detail=detail_for_paths(db, paths),
            )

            def on_event(ev: actions.RemoveEvent) -> None:
                _push_progress(loop, ctx, ev)

            return actions.remove_tracks_from_ipod(cfg, db, paths, on_event=on_event)
        finally:
            db.close()
            _sync_state.finish()

    result = await asyncio.to_thread(worker)

    n_removed = len(result.removed)
    n_not_matched = len(result.not_matched)
    if n_removed == 0:
        if n_not_matched == 0:
            text = "No tracks specified."
        else:
            text = (
                f"None of the {n_not_matched} requested tracks are on the "
                "iPod. Nothing to remove."
            )
    elif result.library_updated:
        text = (
            f"Removed {format_count(n_removed, 'track')} "
            f"({format_bytes(result.bytes_freed)} freed). "
            "Offer to eject the iPod when ready."
        )
    else:
        text = (
            f"{format_count(n_removed, 'track')} removed from the iPod's "
            "library, but the database write didn't fully complete. "
            "Suggest the CLI for retry."
        )

    data = {
        "removed": n_removed,
        "not_matched": n_not_matched,
        "bytes_freed": result.bytes_freed,
        "library_updated": result.library_updated,
    }
    return render(text, data)


@mcp.tool(
    annotations=DESTRUCTIVE,
    meta=ui_tool_meta(SYNC_RESULT_URI),
)
async def remove_artist_from_ipod(
    artist: Annotated[
        str,
        Field(
            description=(
                "Artist name to drop from the iPod. Matched via canonical "
                "lead-artist rollup (album_artist-first), so e.g. removing "
                "'Taylor Swift' also drops 'Taylor Swift / HAIM' tracks."
            ),
        ),
    ],
    ctx: Context,
) -> dict:
    """Drop every track by an artist from the iPod, in one shot.

    Mirrors `add_artist_to_ipod`. Use for "delete all Weezer from my
    iPod" / "I'm done with this artist." The artist's tracks are
    physically removed from the device; they stay in your library
    (your Mac's music folder is untouched).

    Matching uses `primary_artist` (album_artist preferred), so
    collab variants like "Taylor Swift / HAIM" with
    album_artist='Taylor Swift' are correctly grouped under their
    canonical lead.

    No library lookup required — reads the iPod's track list directly
    and filters. So even iTunes-only artists (not in your clickwheel
    library) can be removed.

    Flagged destructive — Allow/Deny gates the call. Before invoking,
    summarize: artist name + how many tracks will go (call
    `list_ipod_tracks` first if you want the exact count) + that this
    deletes from the iPod, not the library.

    After: offer to eject.
    """
    cfg = load_config()
    loop = asyncio.get_running_loop()

    def worker() -> actions.RemoveResult:
        # We don't know the count until we read the iPod, so start with
        # an estimated total of 0; update() will reset to the real total
        # on the first tick.
        _sync_state.start(
            kind="remove",
            total=0,
            operation=f"all tracks by {artist}",
        )

        def on_event(ev: actions.RemoveEvent) -> None:
            _push_progress(loop, ctx, ev)

        try:
            return actions.remove_artist_from_ipod(cfg, artist, on_event=on_event)
        finally:
            _sync_state.finish()

    result = await asyncio.to_thread(worker)

    n_removed = len(result.removed)
    if n_removed == 0:
        text = (
            f"No tracks by '{artist}' on the iPod. Nothing to remove. "
            "Names are matched via the canonical lead-artist rollup — "
            "check spelling, or use `list_ipod_tracks` to see what's there."
        )
    elif result.library_updated:
        text = (
            f"Removed {format_count(n_removed, 'track')} by {artist} "
            f"({format_bytes(result.bytes_freed)} freed). "
            "Offer to eject when done."
        )
    else:
        text = (
            f"{format_count(n_removed, 'track')} by {artist} removed but "
            "the iPod's library wasn't fully updated. Suggest re-running."
        )

    data = {
        "artist": artist,
        "removed": n_removed,
        "bytes_freed": result.bytes_freed,
        "library_updated": result.library_updated,
    }
    return render(text, data)


@mcp.tool(
    annotations=DESTRUCTIVE,
    meta=ui_tool_meta(SYNC_RESULT_URI),
)
def remove_ipod_playlist(
    name: Annotated[
        str,
        Field(description="Name of the iPod playlist to remove."),
    ],
) -> dict:
    """Remove a playlist from the iPod (Music → Playlists). The
    playlist's tracks are NOT deleted — they stay in the iPod's main
    library, browsable by artist/album. Only the playlist artifact
    goes away.

    Use for "delete the workout playlist from my iPod" / "I don't want
    this playlist on the device anymore but keep the songs."

    For "remove the playlist AND its tracks", call this AFTER
    `remove_tracks_from_ipod` with the playlist's track paths
    (you can collect those via the clickwheel-side `get_playlist` if
    the playlist was synced from clickwheel).

    Errors
    ------
    - IpodNotFoundError: no iPod mounted.
    - PlaylistNotFoundError: no iPod-side playlist with this name.
      Use `list_ipod_playlists` to see what exists.

    Flagged destructive. After success: offer to eject.
    """
    with open_session() as (cfg, _db):
        result = actions.remove_ipod_playlist(cfg, name)
        if result.library_updated:
            text = (
                f"Removed playlist '{name}' from the iPod. The tracks "
                "themselves are still in the library. Offer to eject."
            )
        else:
            text = (
                f"Tried to remove '{name}' but the iPod's library "
                "wasn't fully updated. Suggest re-running."
            )
        data = {
            "ipod_playlist": name,
            "removed_playlist": True,
            "library_updated": result.library_updated,
        }
        return render(text, data)


@mcp.tool(annotations=MUTATION)
def eject_ipod() -> dict:
    """Safely unmount the iPod via `diskutil eject`. Idempotent: if no
    iPod is currently mounted, returns `{"ejected": False,
    "already_unmounted": True}` rather than raising. This handles the
    classic iPod's normal post-sync auto-disconnect — after the device
    finishes writing its iTunesDB, its firmware flips the screen back
    to the menu and tells macOS it's safe to remove, at which point
    the volume dismounts automatically. So by the time the user asks
    you to eject, the iPod may already be gone. That's expected; tell
    the user the iPod auto-disconnected and they're safe to unplug.
    Other things that can cause an idle disconnect: macOS Music.app
    auto-eject after activity, USB selective-suspend on battery, the
    iPod's own drive-spindown power-saving.

    Errors:
    - EjectFailedError if diskutil exits non-zero (typical cause: a
      process has files open on the iPod). Suggest the user retry
      after closing music apps.

    When to use: after a successful sync or scrobble session, or any
    time the user says "eject", "safely disconnect", "unmount the iPod".
    """
    with open_session() as (cfg, _db):
        try:
            data = actions.eject_ipod(cfg)
            return render("iPod ejected — safe to unplug.", data)
        except actions.IpodNotFoundError:
            return render(
                "iPod is already disconnected — likely auto-ejected after "
                "the database write finished (that's normal classic-iPod "
                "behaviour). Safe to unplug.",
                {"ejected": False, "already_unmounted": True},
            )
