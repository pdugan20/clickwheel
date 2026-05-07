"""iPod tools — read iPod state and sync to it."""

from __future__ import annotations

from mcp.server.fastmcp import Context

from clickwheel import actions
from clickwheel.mcp._runtime import elicit_confirm, format_bytes, mcp, open_session


@mcp.tool()
def get_ipod_contents() -> dict:
    """What's currently on the iPod: track list, capacity, and used/free space.
    Requires the iPod to be mounted (typically /Volumes/IPOD on macOS).
    Errors if no iPod is detected."""
    with open_session(autoscan=False) as (cfg, _db):
        return actions.read_ipod_contents(cfg)


@mcp.tool()
async def sync_playlist_to_ipod(
    ctx: Context, playlist: str, confirm: bool = False
) -> dict:
    """Sync a saved playlist to the iPod: copy new tracks, leave existing
    matches in place, and rewrite the iTunesDB.

    By default, computes the diff first and asks the user to confirm before
    doing anything destructive. Pass `confirm=True` to skip the prompt
    (use sparingly — this writes to the iPod).

    Requires the iPod to be mounted. Errors with InsufficientSpaceError
    if the new tracks won't fit."""
    with open_session() as (cfg, db):
        diff = actions.compute_diff(cfg, db, playlist)

        if not diff.to_add and not diff.to_remove:
            return {
                "synced": False,
                "reason": "iPod already matches this playlist.",
                "playlist": playlist,
            }

        if not confirm:
            ok = await elicit_confirm(
                ctx,
                f"Sync '{playlist}' to iPod? "
                f"Will add {len(diff.to_add)} track(s) "
                f"({format_bytes(diff.add_size_bytes)}) "
                f"and {len(diff.to_remove)} track(s) currently on iPod "
                "won't be in this playlist (they stay on the iPod for now).",
            )
            if not ok:
                return {"synced": False, "reason": "user declined"}

        result = actions.sync_playlist(cfg, db, playlist, diff=diff)
        return {
            "synced": True,
            "playlist": playlist,
            "copied": len(result.copied),
            "failed": len(result.failed),
            "removed_count": result.removed_count,
            "db_write_ok": result.db_write_ok,
        }
