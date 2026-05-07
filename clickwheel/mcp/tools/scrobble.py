"""Scrobble tools — pending plays and Last.fm submission."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from clickwheel import actions
from clickwheel.mcp._runtime import (
    MUTATION_OPEN_WORLD,
    READ_ONLY,
    format_count,
    mcp,
    open_session,
    render,
)


@mcp.tool(annotations=READ_ONLY)
def get_pending_scrobbles() -> list[dict]:
    """Cached iPod plays that haven't yet been submitted to Last.fm. Each
    entry has `artist`, `title`, `album`, `timestamp` (unix seconds), and
    `duration_seconds`.

    When to use: the user asks what's pending, or before deciding whether
    to call `submit_scrobbles`.

    After this: `submit_scrobbles` to push them, optionally with
    `dry_run=true` first to preview.
    """
    with open_session() as (_cfg, db):
        result = actions.read_pending_scrobbles(db)
        if not result:
            return render(
                "No pending scrobbles. Connect the iPod and call "
                "`submit_scrobbles` to pull recent plays.",
                result,
            )
        text = (
            f"{format_count(len(result), 'scrobble')} pending. "
            "Call `submit_scrobbles` to push to Last.fm."
        )
        return render(text, result)


@mcp.tool(annotations=MUTATION_OPEN_WORLD)
def submit_scrobbles(
    dry_run: Annotated[
        bool,
        Field(
            description=(
                "If true, just count what would be sent without actually "
                "submitting to Last.fm."
            ),
        ),
    ] = False,
) -> dict:
    """Pull recent plays from the iPod and submit them to Last.fm.

    Workflow inside this one tool:
    1. Reads the iPod for any new plays (caching them in the local DB).
    2. Submits all unsent scrobbles to Last.fm in batches of 50.
    3. Returns counts.

    Requires both the iPod to be mounted (to pick up new plays) and Last.fm
    to be configured (api key, secret, session key in
    ~/.clickwheel/config.yaml). The CLI's `clickwheel scrobble --auth` runs
    one-time setup.

    Returns include a `next_step_hint` — when submission succeeds, hints
    that the iPod can be ejected.

    When to use: the user wants to update Last.fm with their iPod listening
    history. Don't run repeatedly in a session — once submitted, scrobbles
    are flagged and won't re-send.
    """
    with open_session() as (cfg, db):
        plays_status = actions.collect_ipod_plays(cfg, db)

        if dry_run:
            pending = actions.read_pending_scrobbles(db)
            data = {
                "dry_run": True,
                "plays_found_on_ipod": plays_status["plays_found"],
                "newly_cached": plays_status["new_cached"],
                "pending_total": len(pending),
                "oldest_age_days": plays_status["oldest_age_days"],
                "next_step_hint": None,
            }
            text = (
                f"Dry run: {format_count(len(pending), 'scrobble')} ready, "
                f"{plays_status['new_cached']} newly cached from iPod. "
                "Re-run without dry_run to actually send."
            )
            return render(text, data)

        result = actions.submit_pending_scrobbles(cfg, db)

        if result.submitted > 0 and result.failed == 0:
            next_hint = (
                "Scrobbles sent successfully. Offer to call eject_ipod "
                "before the user unplugs the device."
            )
            text = (
                f"Submitted {format_count(result.submitted, 'scrobble')} "
                "to Last.fm. Call `eject_ipod` when ready to unplug."
            )
        elif result.submitted == 0 and result.failed == 0:
            next_hint = None
            text = "No scrobbles to submit."
        else:
            next_hint = None
            text = (
                f"Sent {result.submitted}, but {result.failed} failed. "
                f"{result.remaining_pending} still pending — try again later."
            )

        data = {
            "submitted": result.submitted,
            "failed": result.failed,
            "remaining_pending": result.remaining_pending,
            "newly_cached": plays_status["new_cached"],
            "plays_found_on_ipod": plays_status["plays_found"],
            "next_step_hint": next_hint,
        }
        return render(text, data)
