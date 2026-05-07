"""Scrobble tools — pending plays and Last.fm submission."""

from __future__ import annotations

from clickwheel import actions
from clickwheel.mcp._runtime import mcp, open_session


@mcp.tool()
def get_pending_scrobbles() -> list[dict]:
    """Cached iPod plays that haven't yet been submitted to Last.fm.
    Each entry has artist, title, album, timestamp, and duration."""
    with open_session(autoscan=False) as (_cfg, db):
        return actions.read_pending_scrobbles(db)


@mcp.tool()
def submit_scrobbles(dry_run: bool = False) -> dict:
    """Submit pending iPod plays to Last.fm.

    First reads the iPod for any new plays (caching them in the local DB),
    then submits all unsent scrobbles. Pass `dry_run=True` to see what
    would be sent without actually submitting.

    Requires Last.fm to be configured (api key, secret, session key).
    Requires the iPod to be mounted to pick up new plays."""
    with open_session(autoscan=False) as (cfg, db):
        plays_status = actions.collect_ipod_plays(cfg, db)

        if dry_run:
            pending = actions.read_pending_scrobbles(db)
            return {
                "dry_run": True,
                "plays_found_on_ipod": plays_status["plays_found"],
                "newly_cached": plays_status["new_cached"],
                "pending_total": len(pending),
                "oldest_age_days": plays_status["oldest_age_days"],
            }

        result = actions.submit_pending_scrobbles(cfg, db)
        return {
            "submitted": result.submitted,
            "failed": result.failed,
            "remaining_pending": result.remaining_pending,
            "newly_cached": plays_status["new_cached"],
            "plays_found_on_ipod": plays_status["plays_found"],
        }
