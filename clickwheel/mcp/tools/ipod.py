"""iPod tools — read iPod state, sync, and eject."""

from __future__ import annotations

from collections import Counter
from typing import Annotated

from pydantic import Field

from clickwheel import actions
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
        artist_counts = Counter(t.get("artist") or "Unknown" for t in tracks)
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
def sync_playlist_to_ipod(
    playlist: Annotated[str, Field(description="Saved playlist name to sync.")],
) -> dict:
    """Push a saved playlist to the iPod. Copies new tracks and updates the
    iPod's library so it sees them. Tracks already on the iPod that aren't
    in the playlist stay where they are — sync is additive, never deletes.

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
    with open_session() as (cfg, db):
        diff = actions.compute_diff(cfg, db, playlist)

        if not diff.to_add and not diff.to_remove:
            data = {
                "synced": False,
                "reason": "iPod already matches this playlist.",
                "playlist": playlist,
            }
            return render(f"iPod already matches '{playlist}' — nothing to do.", data)

        result = actions.sync_playlist(cfg, db, playlist, diff=diff)

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
