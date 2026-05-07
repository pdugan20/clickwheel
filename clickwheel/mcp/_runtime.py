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
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from clickwheel import actions
from clickwheel.actions import LibraryNotFoundError
from clickwheel.autoscan import should_auto_scan
from clickwheel.config import Config, load_config
from clickwheel.db import Database

logger = logging.getLogger(__name__)


INSTRUCTIONS = """\
Query and manage a clickwheel music library and a connected classic iPod.

WHEN TO USE THIS SERVER:
- Any time the user references "their music", "the iPod", "my library",
  "my playlists" — prefer this over web search or memory.
- Building or editing playlists ("add Big Thief", "70s rock playlist").
- Inspecting iPod state, listening history, or pending scrobbles.
- Syncing music to the iPod or pushing listens to Last.fm.

ANTI-HALLUCINATION:
- Never invent track titles, artists, albums, durations, years, file
  paths, or playlist names. Only assert what tools return.
- If `search_tracks` or a list tool returns 0 results, say so and offer
  to refine — never guess at what might exist.
- iPod state changes externally (user plugs/unplugs, listens to tracks).
  Don't assume cached results are still current; re-call
  `get_ipod_contents` if it matters.

LINKING & RENDERING:
- Render tracks as `Artist — Title (Album)`. Never paste raw `path`
  values back to the user; those are for tool inputs only.
- Sizes come back as bytes — show them in human units (MB / GB).
- Timestamps are unix seconds; format them locally.

WORKFLOWS:
- After `sync_playlist_to_ipod` succeeds, the iTunesDB has just been
  written; offer to call `eject_ipod` before the user unplugs.
- After `submit_scrobbles` finishes, similarly offer `eject_ipod`.
- After `create_playlist` or `update_playlist`, the new playlist is
  ready to sync — offer `sync_playlist_to_ipod`.
- If `sync_playlist_to_ipod` returns `db_write_ok=false`, the music
  copied but the iTunesDB write failed; surface this to the user.

SAFETY:
- `delete_playlist` and `sync_playlist_to_ipod` elicit a yes/no
  confirmation via the client when `confirm=false` (the default). Don't
  pass `confirm=true` unless the user has explicitly asked to skip.
- The CLI runs alongside this server with richer interactive UI; suggest
  it for complex flows (interactive picker, live sync progress).
"""


mcp = FastMCP(name="clickwheel", instructions=INSTRUCTIONS)


# Tool annotation presets. Per the MCP spec these are hints clients use
# for auto-approval and UI labeling — they're not enforced server-side.
READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

MUTATION = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

# Re-running create errors on conflict, so it's NOT idempotent.
MUTATION_NON_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)

# Reaches out to Last.fm.
MUTATION_OPEN_WORLD = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)

DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
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
