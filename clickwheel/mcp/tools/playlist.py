"""Playlist tools — read and mutation."""

from __future__ import annotations

from mcp.server.fastmcp import Context

from clickwheel import actions
from clickwheel.mcp._runtime import elicit_confirm, mcp, open_session


@mcp.tool()
def list_playlists() -> list[dict]:
    """All saved clickwheel playlists with track counts, total size in bytes,
    and last-updated timestamps."""
    with open_session() as (_cfg, db):
        return actions.list_playlists(db)


@mcp.tool()
def get_playlist(name: str) -> dict:
    """One playlist's full contents: track list, artist breakdown, and total
    size. Raises an error if the playlist doesn't exist."""
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


@mcp.tool()
def create_playlist(name: str, track_paths: list[str]) -> dict:
    """Create a new playlist with the given track paths. Errors if a playlist
    with the same name already exists — use update_playlist to replace.

    `track_paths` should be the absolute paths returned by list_tracks_by_album,
    search_tracks, etc."""
    with open_session() as (_cfg, db):
        count = actions.create_playlist(db, name, track_paths)
        return {"name": name, "track_count": count}


@mcp.tool()
def update_playlist(name: str, track_paths: list[str]) -> dict:
    """Replace a playlist's contents (or create it if it doesn't exist).
    Returns track_count and `replaced` (True if a playlist by this name
    already existed)."""
    with open_session() as (_cfg, db):
        count, replaced = actions.update_playlist(db, name, track_paths)
        return {"name": name, "track_count": count, "replaced": replaced}


@mcp.tool()
async def delete_playlist(ctx: Context, name: str, confirm: bool = False) -> dict:
    """Delete a saved playlist by name. If `confirm` is False (default),
    asks the user to confirm via the client. Pass `confirm=True` to skip
    the prompt."""
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


@mcp.tool()
def add_artist_to_playlist(playlist: str, artist: str) -> dict:
    """Add every track by `artist` to `playlist` (skipping duplicates).
    Creates the playlist if it doesn't already exist. Returns the number
    of tracks actually added."""
    with open_session() as (_cfg, db):
        added = actions.add_artist_to_playlist(db, playlist, artist)
        return {"added": added, "playlist": playlist, "artist": artist}


@mcp.tool()
def remove_artist_from_playlist(playlist: str, artist: str) -> dict:
    """Remove every track by `artist` from `playlist`. Returns the number
    of tracks removed (0 if the artist wasn't in the playlist)."""
    with open_session(autoscan=False) as (_cfg, db):
        removed = actions.remove_artist_from_playlist(db, playlist, artist)
        return {"removed": removed, "playlist": playlist, "artist": artist}
