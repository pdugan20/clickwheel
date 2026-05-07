"""iPod tools — read iPod state, sync, and eject."""

from __future__ import annotations

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


@mcp.tool(annotations=READ_ONLY)
def get_ipod_contents() -> dict:
    """What's currently on the iPod: full track list, total capacity, used,
    and free space (all in bytes). Requires the iPod to be mounted (typically
    /Volumes/IPOD on macOS). Errors if no iPod is detected.

    When to use: the user asks "what's on my iPod?", or before a sync to
    show what's already there.

    After this: `sync_playlist_to_ipod` to push a saved playlist, or
    `submit_scrobbles` to read recent plays. Eject when finished via
    `eject_ipod`.
    """
    with open_session(autoscan=False) as (cfg, _db):
        data = actions.read_ipod_contents(cfg)
        tracks = data["tracks"]
        text = (
            f"iPod: {format_count(len(tracks), 'track')}, "
            f"{format_bytes(data['used_bytes'])} used / "
            f"{format_bytes(data['capacity_bytes'])} total "
            f"({format_bytes(data['free_bytes'])} free)."
        )
        return render(text, data)


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
    with open_session(autoscan=False) as (cfg, _db):
        data = actions.eject_ipod(cfg)
        return render("iPod ejected — safe to unplug.", data)
