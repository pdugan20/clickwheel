"""Shared runtime for the MCP server.

Holds the FastMCP instance, the per-tool session context manager, and small
utilities (formatters, the elicitation helper). Tool modules under
`clickwheel.mcp.tools` import from here and never from `server.py`, which
keeps the `server.py → tools/` import direction one-way.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from mcp.server.fastmcp import Context, FastMCP
from pydantic import BaseModel, Field

from clickwheel import actions
from clickwheel.actions import LibraryNotFoundError
from clickwheel.autoscan import should_auto_scan
from clickwheel.config import Config, load_config
from clickwheel.db import Database

logger = logging.getLogger(__name__)


mcp = FastMCP(
    name="clickwheel",
    instructions=(
        "Query a clickwheel music library and iPod. Use list_artists, "
        "list_playlists, search_tracks, and similar tools for read-only "
        "browsing. get_ipod_contents requires the iPod to be mounted. "
        "library_health is a quick probe to confirm setup is working."
    ),
)


@contextmanager
def open_session(*, autoscan: bool = True) -> Iterator[tuple[Config, Database]]:
    """Open config + DB for one tool call.

    SQLite is fast to open; per-call lifecycle keeps the server stateless and
    handles config edits made mid-session. If `autoscan` is True (default),
    runs an incremental scan when the DB is older than the configured
    staleness threshold.
    """
    cfg = load_config()
    db = Database(cfg.db_path)
    try:
        if autoscan:
            run, _reason = should_auto_scan(cfg, db)
            if run:
                try:
                    actions.scan_library(cfg, db, full=False)
                except LibraryNotFoundError:
                    logger.warning(
                        "Music dir not reachable during autoscan; serving cached data"
                    )
        yield cfg, db
    finally:
        db.close()


def format_bytes(n: int) -> str:
    if n >= 1024**3:
        return f"{n / 1024**3:.1f} GB"
    if n >= 1024**2:
        return f"{n / 1024**2:.1f} MB"
    return f"{n / 1024:.1f} KB"


class Confirm(BaseModel):
    """Schema for a yes/no elicitation prompt."""

    confirm: bool = Field(
        description="Confirm the action. Set false to cancel.",
    )


async def elicit_confirm(ctx: Context, message: str) -> bool:
    """Ask the client to confirm. Returns True only on explicit accept+confirm."""
    result = await ctx.elicit(message=message, schema=Confirm)
    if result.action != "accept" or result.data is None:
        return False
    return bool(result.data.confirm)
