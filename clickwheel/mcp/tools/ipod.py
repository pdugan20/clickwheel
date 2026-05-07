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


def _summarize_track(t: dict) -> dict:
    """Project an iPod track record down to chat-friendly fields."""
    return {
        "artist": t.get("artist") or "",
        "title": t.get("title") or "",
        "album": t.get("album") or "",
        "size_bytes": t.get("size") or 0,
    }


@mcp.tool(annotations=READ_ONLY)
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
    """Permanently push a saved playlist to the iPod. Copies new tracks and
    rewrites the iTunesDB. Tracks already on the iPod that aren't in the
    playlist STAY on the iPod — this is an additive operation, never deletes.

    Flagged `destructiveHint=true`, so MCP clients (Claude Code etc.) gate
    this call with a native Allow/Deny prompt. Before invoking, summarize
    the diff for the user — call `compute_diff`-equivalent context (e.g.
    use `get_playlist` and `get_ipod_contents`) and tell them how many
    tracks will be copied and how much space they'll use, so they can
    Allow/Deny knowingly.

    Requires the iPod to be mounted. Errors with InsufficientSpaceError if
    the new tracks won't fit.

    Returns a result dict including a `next_step_hint` field — when the
    sync succeeds, that hint will tell you to call `eject_ipod`.

    When to use: the user says "sync my playlist", "push to the iPod",
    "load up the iPod".

    After this: if `next_step_hint` is set, call `eject_ipod` (do confirm
    with the user first since they may want to do something else with the
    iPod before unplugging). If `db_write_ok=false`, the music copied but
    the iTunesDB write failed — surface this to the user.
    """
    with open_session() as (cfg, db):
        diff = actions.compute_diff(cfg, db, playlist)

        if not diff.to_add and not diff.to_remove:
            data = {
                "synced": False,
                "reason": "iPod already matches this playlist.",
                "playlist": playlist,
                "next_step_hint": None,
            }
            return render(f"iPod already matches '{playlist}' — nothing to do.", data)

        result = actions.sync_playlist(cfg, db, playlist, diff=diff)

        if result.db_write_ok:
            next_hint = (
                "Sync succeeded. Offer to call eject_ipod before the user "
                "unplugs the device."
            )
            text = (
                f"Synced '{playlist}': copied "
                f"{format_count(len(result.copied), 'track')} "
                f"({format_bytes(diff.add_size_bytes)}). "
                "Call `eject_ipod` when ready to unplug."
            )
        else:
            next_hint = (
                "Music copied but iTunesDB write failed. Surface this to "
                "the user — the iPod may not see the new tracks."
            )
            text = (
                f"Synced '{playlist}' but the iTunesDB write FAILED. "
                f"Copied {format_count(len(result.copied), 'track')}, but "
                "the iPod may not see them. Try the CLI's `clickwheel sync` "
                "for retry support."
            )

        data = {
            "synced": True,
            "playlist": playlist,
            "copied": len(result.copied),
            "failed": len(result.failed),
            "removed_count": result.removed_count,
            "db_write_ok": result.db_write_ok,
            "next_step_hint": next_hint,
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
