"""Playlist tools — read and mutation."""

from __future__ import annotations

from typing import Annotated

from mcp.server.fastmcp import Context
from pydantic import Field

from clickwheel import actions
from clickwheel.mcp._runtime import (
    DESTRUCTIVE,
    MUTATION,
    MUTATION_NON_IDEMPOTENT,
    READ_ONLY,
    elicit_confirm,
    mcp,
    open_session,
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
        return actions.list_playlists(db)


@mcp.tool(annotations=READ_ONLY)
def get_playlist(
    name: Annotated[str, Field(description="Playlist name.")],
) -> dict:
    """One playlist's full contents: track list, artist breakdown, and
    total size in bytes. Errors if the playlist doesn't exist.

    When to use: showing the user what's in a saved playlist, or before
    editing it.

    After this: `update_playlist` to replace contents,
    `add_artist_to_playlist` / `remove_artist_from_playlist` to adjust by
    artist, or `sync_playlist_to_ipod` to push to the device.
    """
    with open_session() as (_cfg, db):
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
        return {"name": name, "track_count": count}


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
        return {"name": name, "track_count": count, "replaced": replaced}


@mcp.tool(annotations=DESTRUCTIVE)
async def delete_playlist(
    ctx: Context,
    name: Annotated[str, Field(description="Playlist name.")],
    confirm: Annotated[
        bool,
        Field(
            description=(
                "Pass true to skip the user confirmation prompt. Default "
                "false — server elicits a yes/no via the client."
            ),
        ),
    ] = False,
) -> dict:
    """Delete a saved playlist. Destructive — cannot be undone (the playlist
    record is removed; the underlying music files are untouched).

    By default, asks the user to confirm via the client. Pass `confirm=true`
    only when the user explicitly says to skip prompts.

    When to use: the user says "delete" or "remove" a playlist by name.
    """
    with open_session(autoscan=False) as (_cfg, db):
        if not actions.playlist_exists(db, name):
            return {"deleted": False, "reason": f"Playlist '{name}' not found."}

        if not confirm:
            track_count = len(db.get_playlist(name))
            ok = await elicit_confirm(
                ctx,
                f"Delete playlist '{name}'? It contains {track_count} track(s). "
                "This cannot be undone.",
            )
            if not ok:
                return {"deleted": False, "reason": "user declined"}

        actions.delete_playlist(db, name)
        return {"deleted": True, "name": name}


@mcp.tool(annotations=MUTATION)
def add_artist_to_playlist(
    playlist: Annotated[str, Field(description="Playlist name (created if missing).")],
    artist: Annotated[str, Field(description="Artist name (exact match).")],
) -> dict:
    """Add every track by `artist` to `playlist` (skipping duplicates).
    Creates the playlist if it doesn't already exist. Returns the number of
    tracks actually added (0 if all tracks were already present).

    When to use: the user says "add Big Thief to my road-trip playlist" or
    similar.

    After this: `sync_playlist_to_ipod` to push the change.
    """
    with open_session() as (_cfg, db):
        added = actions.add_artist_to_playlist(db, playlist, artist)
        return {"added": added, "playlist": playlist, "artist": artist}


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
        return {"removed": removed, "playlist": playlist, "artist": artist}
