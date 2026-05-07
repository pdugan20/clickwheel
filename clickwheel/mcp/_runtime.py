"""Shared runtime for the MCP server.

Holds the FastMCP instance, the per-tool session context manager, tool
annotation presets, and small formatting utilities. Tool modules under
`clickwheel.mcp.tools` import from here and never from `server.py`, which
keeps the `server.py → tools/` import direction one-way.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations

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
- Plain text only — no emoji or decorative symbols. The text summaries
  are already concise; resist embellishing with warning glyphs or
  status markers.

WORKFLOWS:
- After `sync_playlist_to_ipod` succeeds, the iTunesDB has just been
  written; offer to call `eject_ipod` before the user unplugs.
- After `submit_scrobbles` finishes, similarly offer `eject_ipod`.
- After `create_playlist` or `update_playlist`, the new playlist is
  ready to sync — offer `sync_playlist_to_ipod`.
- If `sync_playlist_to_ipod` returns `db_write_ok=false`, the music
  copied but the iTunesDB write failed; surface this to the user.

SAFETY:
- `delete_playlist` and `sync_playlist_to_ipod` are flagged destructive.
  Claude Code (and other compliant clients) surface a native Allow/Deny
  prompt before invoking them — that is the user's confirmation moment.
  Before calling either tool, summarize the impact in your reply
  (playlist name, track count, target iPod) so the user has the context
  they need to allow or deny.
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


def format_duration_seconds(seconds: float | int | None) -> str:
    """Format a track-or-playlist duration. >1h shows H:MM:SS, else M:SS."""
    if not seconds:
        return "0:00"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def format_count(n: int, singular: str, plural: str | None = None) -> str:
    """Pluralization helper: '1 track' / '5 tracks'."""
    return f"{n:,} {singular if n == 1 else (plural or singular + 's')}"


def format_timestamp(ts: int | float | None) -> str:
    """Format a unix timestamp as YYYY-MM-DD HH:MM."""
    from datetime import datetime

    if ts is None:
        return "never"
    return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M")


def render(text: str, data: object | None = None) -> CallToolResult:
    """Build a dual-content tool result: a one-line text summary plus the
    structured data the LLM can use for follow-up questions.

    The text block is what an MCP client renders to the user (and what the
    LLM tends to paraphrase from); structuredContent is the precise dict
    available for programmatic access.
    """
    if data is None:
        sc: dict = {}
    elif isinstance(data, dict):
        sc = data
    else:
        # MCP requires structuredContent to be an object. Wrap lists/scalars
        # under "result", matching FastMCP's own auto-wrap convention.
        sc = {"result": data}
    return CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent=sc,
    )
