"""Playlist tools — read and mutation."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from clickwheel import actions
from clickwheel.mcp._runtime import (
    DESTRUCTIVE,
    MUTATION,
    MUTATION_NON_IDEMPOTENT,
    READ_ONLY,
    format_bytes,
    format_count,
    mcp,
    open_session,
    render,
)


@mcp.tool(annotations=READ_ONLY)
def list_playlists() -> list[dict]:
    """All saved clickwheel playlists with track counts, total size in
    bytes, and last-updated timestamps.

    When to use: the user asks what playlists exist, or before
    `get_playlist` / `delete_playlist` / `sync_playlist_to_ipod`.

    After this: `get_playlist` for one playlist's contents, or
    `sync_playlist_to_ipod` to push it.
    """
    with open_session() as (_cfg, db):
        result = actions.list_playlists(db)
        if not result:
            return render(
                "No playlists yet — use `create_playlist` to build one, or "
                "the `clickwheel select` CLI for an interactive picker.",
                result,
            )
        names = ", ".join(f"'{p['name']}' ({p['tracks']})" for p in result)
        text = f"{format_count(len(result), 'playlist')}: {names}."
        return render(text, result)


@mcp.tool(annotations=READ_ONLY)
def get_playlist(
    name: Annotated[str, Field(description="Playlist name.")],
) -> dict:
    """Summary of one playlist: total track count, total size, and the
    artist breakdown (with track count + size per artist). Does NOT return
    the full track list — use `list_playlist_tracks` to page through tracks.

    Errors if the playlist doesn't exist.

    When to use: showing the user a quick playlist overview, or before
    deciding to edit/sync.

    After this: `list_playlist_tracks` to drill into specific tracks,
    `update_playlist` to replace contents, `add_artist_to_playlist` /
    `remove_artist_from_playlist` to adjust by artist, or
    `sync_playlist_to_ipod` to push to the device.
    """
    with open_session() as (_cfg, db):
        tracks = actions.get_playlist(db, name)
        artists = actions.get_playlist_artists(db, name)
        size = actions.get_playlist_size(db, name)
        data = {
            "name": name,
            "track_count": len(tracks),
            "size_bytes": size,
            "artists": artists,
        }
        text = (
            f"'{name}': {format_count(len(tracks), 'track')} across "
            f"{format_count(len(artists), 'artist')}, {format_bytes(size)}."
        )
        return render(text, data)


@mcp.tool(annotations=READ_ONLY)
def list_playlist_tracks(
    name: Annotated[str, Field(description="Playlist name.")],
    limit: Annotated[
        int,
        Field(description="Max tracks to return.", ge=1, le=200),
    ] = 50,
    offset: Annotated[
        int,
        Field(description="Pagination offset (0 = first page).", ge=0),
    ] = 0,
) -> list[dict]:
    """Paginated list of tracks in a saved playlist, in playlist order.
    Returns full track records (artist, title, album, path, duration,
    file_size, format) — the `path` values are needed if you're going to
    pass them to `update_playlist`.

    When to use: showing the user specific tracks in a playlist, or
    collecting `path` values before an `update_playlist` call.

    Errors if the playlist doesn't exist.
    """
    with open_session() as (_cfg, db):
        tracks = actions.list_playlist_tracks(db, name, limit=limit, offset=offset)
        if not tracks:
            return render(
                f"No tracks at offset {offset} for '{name}'.",
                tracks,
            )
        text = (
            f"{format_count(len(tracks), 'track')} from '{name}'"
            + (f" (offset {offset})" if offset else "")
            + "."
        )
        return render(text, tracks)


@mcp.tool(annotations=MUTATION_NON_IDEMPOTENT)
def create_playlist(
    name: Annotated[str, Field(description="New playlist name (must not exist).")],
    track_paths: Annotated[
        list[str],
        Field(
            description=(
                "Absolute file paths from the library. Get these from "
                "list_tracks_by_album or search_tracks — never invent paths."
            ),
        ),
    ],
) -> dict:
    """Create a new playlist with the given track paths. Errors if a
    playlist with the same name already exists — use `update_playlist`
    to replace contents instead.

    When to use: the user asks to "make" or "create" a playlist with
    specific tracks already identified.

    After this: `sync_playlist_to_ipod` to push it to the device, or
    `add_artist_to_playlist` to bulk-add an entire artist on top.
    """
    with open_session() as (_cfg, db):
        count = actions.create_playlist(db, name, track_paths)
        data = {"name": name, "track_count": count}
        text = (
            f"Created '{name}' with {format_count(count, 'track')}. "
            "Sync to iPod with `sync_playlist_to_ipod`."
        )
        return render(text, data)


@mcp.tool(annotations=MUTATION)
def update_playlist(
    name: Annotated[str, Field(description="Playlist name (created if missing).")],
    track_paths: Annotated[
        list[str],
        Field(description="Absolute file paths from the library."),
    ],
) -> dict:
    """Replace a playlist's contents wholesale (or create it if it doesn't
    exist). Returns the new track count and `replaced` (True if a playlist
    by this name already existed).

    When to use: rebuilding a playlist from scratch, or the user explicitly
    says "replace" / "set the playlist to ...".

    After this: `sync_playlist_to_ipod` to push the new contents.
    """
    with open_session() as (_cfg, db):
        count, replaced = actions.update_playlist(db, name, track_paths)
        data = {"name": name, "track_count": count, "replaced": replaced}
        verb = "Replaced" if replaced else "Created"
        text = (
            f"{verb} '{name}' (now {format_count(count, 'track')}). "
            "Sync to iPod with `sync_playlist_to_ipod`."
        )
        return render(text, data)


@mcp.tool(annotations=DESTRUCTIVE)
def delete_playlist(
    name: Annotated[str, Field(description="Playlist name.")],
) -> dict:
    """Permanently delete a saved playlist. Cannot be undone — the playlist
    record is removed; the underlying music files are untouched.

    Flagged `destructiveHint=true`, so MCP clients (Claude Code etc.) gate
    this call with a native Allow/Deny prompt. Before invoking, summarize
    the impact (playlist name + track count from a prior `get_playlist`
    or `list_playlists` call) so the user has context for the decision.

    When to use: the user explicitly says "delete" or "remove" a playlist
    by name.
    """
    with open_session(autoscan=False) as (_cfg, db):
        if not actions.playlist_exists(db, name):
            data = {"deleted": False, "reason": f"Playlist '{name}' not found."}
            return render(f"Playlist '{name}' not found — nothing to delete.", data)
        actions.delete_playlist(db, name)
        return render(f"Deleted '{name}'.", {"deleted": True, "name": name})


@mcp.tool(annotations=MUTATION)
def add_artist_to_playlist(
    playlist: Annotated[str, Field(description="Playlist name (created if missing).")],
    artist: Annotated[str, Field(description="Artist name (exact match).")],
) -> dict:
    """Add every track by `artist` to `playlist` (skipping duplicates).
    Creates the playlist if it doesn't already exist. Returns the number
    of tracks actually added.

    When to use: the user says "add Big Thief to my road-trip playlist" or
    similar.

    After this: `sync_playlist_to_ipod` to push the change.
    """
    with open_session() as (_cfg, db):
        added = actions.add_artist_to_playlist(db, playlist, artist)
        data = {"added": added, "playlist": playlist, "artist": artist}
        if added == 0:
            text = (
                f"No tracks added — '{artist}' is either already in "
                f"'{playlist}' or has no library tracks."
            )
        else:
            text = (
                f"Added {format_count(added, 'track')} by {artist} "
                f"to '{playlist}'. Sync with `sync_playlist_to_ipod`."
            )
        return render(text, data)


@mcp.tool(annotations=MUTATION)
def heal_playlist(
    name: Annotated[str, Field(description="Playlist name.")],
) -> dict:
    """Drop references in a playlist to tracks whose files are no longer on
    disk (flagged missing by `clickwheel scan`). Returns the number dropped,
    the number remaining, and the list of removed track records.

    Why this exists: `sync_playlist_to_ipod` errors with `MissingTracksError`
    if a playlist references files that have been moved or deleted. Heal
    drops the dead refs so sync can proceed. After healing, the user
    typically wants to re-add the artist (`add_artist_to_playlist`) to
    pick up replacement files at their new paths.

    Uses the DB's missing flag — accuracy depends on scan freshness. If
    the user just renamed/replaced files, suggest `clickwheel scan` first.

    When to use: when sync errored with `MissingTracksError`, or when the
    user explicitly says "remove dead links from my playlist" / "clean up
    my playlist".
    """
    with open_session(autoscan=False) as (_cfg, db):
        result = actions.heal_playlist(db, name)
        if result["dropped"] == 0:
            text = (
                f"'{name}' is clean — no dead references "
                f"({result['remaining']} tracks intact)."
            )
            return render(text, result)
        text = (
            f"Dropped {result['dropped']} dead reference(s) from '{name}'. "
            f"{result['remaining']} tracks remain. "
            f"Re-add the artist with `add_artist_to_playlist` if you want "
            "replacement files (which now sit at different paths)."
        )
        return render(text, result)


@mcp.tool(annotations=MUTATION)
def remove_artist_from_playlist(
    playlist: Annotated[str, Field(description="Playlist name.")],
    artist: Annotated[str, Field(description="Artist name (exact match).")],
) -> dict:
    """Remove every track by `artist` from `playlist`. Returns the number
    of tracks removed (0 if the artist wasn't in the playlist).

    When to use: the user says "drop Big Thief from my road-trip playlist".
    The playlist record stays even if it ends up empty.
    """
    with open_session(autoscan=False) as (_cfg, db):
        removed = actions.remove_artist_from_playlist(db, playlist, artist)
        data = {"removed": removed, "playlist": playlist, "artist": artist}
        if removed == 0:
            text = f"'{artist}' wasn't in '{playlist}' — nothing removed."
        else:
            text = (
                f"Removed {format_count(removed, 'track')} by {artist} "
                f"from '{playlist}'."
            )
        return render(text, data)
