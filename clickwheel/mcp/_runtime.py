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
from mcp.types import CallToolResult, Icon, TextContent, ToolAnnotations

from clickwheel.config import Config, load_config
from clickwheel.db import Database

logger = logging.getLogger(__name__)


INSTRUCTIONS = """\
Query and manage a clickwheel music library and a connected classic iPod.

WHEN TO USE THIS SERVER:
- Any time the user references "their music", "the iPod", "my library",
  "my playlists" — prefer this over web search or memory.
- Adding music to the iPod (artists, albums, individual tracks).
- Building or editing curated playlists (workout mix, road trip, etc.).
- Inspecting iPod state, listening history, or pending scrobbles.
- Pushing listens to Last.fm.

TWO PLAYLIST CONCEPTS — DON'T CONFLATE THEM:
- "Add tracks to my iPod" / "load up the iPod" / "put more Weezer on
  there": the user wants music on the device, browsable by artist or
  album. NO named playlist needed. Use `add_tracks_to_ipod` or
  `add_artist_to_ipod`. This is the common case.
- "Make me a playlist" / "create a workout mix" / "build a road trip
  playlist": the user wants a named, curated collection that shows up
  under Music → Playlists on the iPod itself. Use `create_playlist` (or
  `add_artist_to_playlist`) to build it, then `sync_playlist_to_ipod`
  to push the playlist to the device. This is the curated case.

TWO DESTINATIONS FOR PLAYLISTS:
- iPod: `sync_playlist_to_ipod` — physical device, the original target.
- Plex / Plexamp: `sync_playlist_to_plex` — optional, only available
  when the user has configured Plex (see `plex_health`). Pushes the
  same playlist to their Plex music library so Plexamp picks it up.
After `create_playlist` or `update_playlist`, ask the user which
destination(s) they want: iPod, Plex, both, or neither. Don't assume.
The two syncs are independent — call both if the user says "both",
each triggers its own Allow/Deny prompt.

PLEX → CLICKWHEEL (recovery direction):
- `list_plex_playlists` shows what's on the Plex side; use it when
  the user wants to know "what playlists do I have on Plex?" or
  before pulling.
- `pull_playlist_from_plex` recovers a Plex playlist into clickwheel's
  local store. Use after a fresh install / Mac wipe when the user's
  Plex still has playlists but clickwheel's SQLite is empty. Smart
  playlists need `include_smart=true` (snapshots the current query).
  Existing local playlists with the same name need `overwrite=true`.

When in doubt, ask the user: do they want it as a playlist they can
browse on the iPod, or just want the songs added to the library? Don't
auto-default to creating throwaway playlists — that pollutes their
device.

REMOVING FROM THE IPOD:
- "Take X off my iPod" / "delete this album from the device" / "free
  up space": use `remove_tracks_from_ipod` (specific paths) or
  `remove_artist_from_ipod` (whole artist). Both physically delete
  the audio files from the iPod; tracks stay in the user's library
  on their Mac and can be re-added later.
- "Remove the workout playlist from my iPod" without deleting its
  songs: use `remove_ipod_playlist`. The playlist artifact under
  Music → Playlists goes away; the tracks themselves stay in the
  library, browsable by artist/album.
- For "remove the playlist AND its tracks", compose the two: collect
  the playlist's tracks (via `get_playlist` if it was synced from
  clickwheel) → `remove_tracks_from_ipod(paths)` → then
  `remove_ipod_playlist(name)`. Tell the user that's what you're
  doing, since it's a multi-step destructive operation.

DISCOVERY (this is how to find tracks — do not improvise):
- "Pick 8 essentials from X" / "build me an X mix" / "find the best X
  tracks" — ALWAYS `list_albums_by_artist <X>` first to see the
  discography, then `list_tracks_by_album <X> <album>` for each album
  you want to cherry-pick from. Collect `path` values from those
  structured results.
- DO NOT call `search_tracks` once per track to resolve paths you
  already chose by name (e.g. nine calls for nine Dylan titles). Each
  call is a fuzzy full-table scan; the album-scoped lookup is one call
  per album and returns the same paths plus useful structure.
- `search_tracks` is for FUZZY DISCOVERY only — the user says "find
  that track about a river" or doesn't remember the artist. Once you
  know the artist, switch to the list-* tools.

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
- BEFORE building a curated playlist destined for the iPod (mood /
  genre / activity mixes — "throw together some grunge", "make me a
  workout mix"), call `get_ipod_contents` so you know what's already
  on the device. If an artist or band you'd include is heavily
  represented (e.g., 50+ tracks), surface that to the user and ask:
  "You've already got 92 Nirvana tracks on there — want me to lean on
  the others for fresh material, or include the essentials anyway?"
  Don't silently ship a playlist where half the tracks dedupe at
  sync time; the user finds out at the very end and it reads as a
  mistake. For pure "add this stuff to my iPod" flows (no playlist
  artifact), skip this — sync is additive and dedups automatically.
- After any destructive iPod operation (`add_tracks_to_ipod`,
  `add_artist_to_ipod`, `sync_playlist_to_ipod`, `submit_scrobbles`)
  succeeds, offer to eject the iPod via `eject_ipod` before the user
  unplugs it.
- After `create_playlist` or `update_playlist`, the user MAY want to
  sync that playlist to the iPod via `sync_playlist_to_ipod`. Ask
  rather than auto-syncing — they might want to keep iterating.
- If a sync/add result reports `library_updated: false`, the music
  copied but the iPod won't see the new tracks yet; surface this in
  plain language and suggest re-running.
- If an iPod tool errors with `IpodNotFoundError` mid-session (after
  you've already used the iPod successfully in the same conversation),
  don't accuse the user of unplugging it. Classic iPods routinely
  auto-dismount during idle conversation lulls: their drive spins
  down after ~30s, macOS Music.app may auto-eject on activity quiet,
  USB selective-suspend on battery does the same. Tell the user
  cheerfully that the iPod stepped offline and ask them to nudge it
  awake (touch the clickwheel, or unplug/replug) before retrying.

SAFETY:
- `delete_playlist`, `add_tracks_to_ipod`, `add_artist_to_ipod`,
  `sync_playlist_to_ipod`, `sync_playlist_to_plex`,
  `pull_playlist_from_plex`, `remove_tracks_from_ipod`,
  `remove_artist_from_ipod`, and `remove_ipod_playlist` are flagged
  destructive. Claude Code (and
  other compliant clients) surface a native Allow/Deny prompt before
  invoking them — that is the user's confirmation moment. Before
  calling, summarize the impact in your reply (track count, size,
  target device / Plex library) so the user has the context to allow
  or deny. For remove operations especially: name the tracks that
  will be deleted, so the user can confirm they meant those.
- The CLI runs alongside this server with richer interactive UI; suggest
  it for complex flows (interactive picker, live sync progress).

LANGUAGE:
- Speak plainly. Don't mention internal jargon ("iTunesDB", "ArtworkDB",
  "scan_meta", "missing_since", etc.) or response field names
  (`library_updated`, `also_on_ipod`, etc.) directly to the user. Say
  "the iPod's library", "your music", "tracks already on the iPod"
  instead. Tool results carry these field names for your own reasoning;
  translate them to natural language before quoting them back.
"""


# Server icon: the clickwheel mark — a white iPod-and-click-wheel glyph
# on a rounded orange tile. Inlined as a base64 SVG data URI so the stdio
# server is self-contained — there's no HTTP endpoint to serve an asset
# file from.
SERVER_ICON = Icon(
    src=(
        "data:image/svg+xml;base64,"
        "PHN2ZyB3aWR0aD0iMTIwIiBoZWlnaHQ9IjEyMCIgdmlld0JveD0iMCAwIDEyMCAx"
        "MjAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2"
        "ZyI+CjxyZWN0IHdpZHRoPSIxMjAiIGhlaWdodD0iMTIwIiByeD0iMTIiIGZpbGw9"
        "IiNGRjlBMDYiLz4KPHBhdGggZD0iTTc3LjAwMSAxOEM4MS40MTkxIDE4LjAwMDEg"
        "ODUuMDAxIDIxLjU4MTggODUuMDAxIDI2Vjk0LjYxNDNDODUuMDAxIDk5LjAzMjQg"
        "ODEuNDE5MSAxMDIuNjE0IDc3LjAwMSAxMDIuNjE0SDQyQzM3LjU4MTcgMTAyLjYx"
        "NCAzNCA5OS4wMzI1IDM0IDk0LjYxNDNWMjZDMzQgMjEuNTgxNyAzNy41ODE3IDE4"
        "IDQyIDE4SDc3LjAwMVpNNTkuNSA2MC44ODY3QzUwLjUzOCA2MC44ODcgNDMuMjcy"
        "NSA2OC4xNTIzIDQzLjI3MjUgNzcuMTE0M0M0My4yNzI2IDg2LjA3NjEgNTAuNTM4"
        "MSA5My4zNDA2IDU5LjUgOTMuMzQwOEM2OC40NjIxIDkzLjM0MDggNzUuNzI3NCA4"
        "Ni4wNzYyIDc1LjcyNzUgNzcuMTE0M0M3NS43Mjc1IDY4LjE1MjEgNjguNDYyMiA2"
        "MC44ODY3IDU5LjUgNjAuODg2N1pNNDcuMTE0MyAyNC45NTMxQzQ0LjM1MyAyNC45"
        "NTMxIDQyLjExNDUgMjcuMTkxOSA0Mi4xMTQzIDI5Ljk1MzFWNDcuNzcxNUM0Mi4x"
        "MTQzIDUwLjUzMjkgNDQuMzUyOCA1Mi43NzE1IDQ3LjExNDMgNTIuNzcxNUg3MS44"
        "ODY3Qzc0LjY0ODEgNTIuNzcxNSA3Ni44ODY3IDUwLjUzMjkgNzYuODg2NyA0Ny43"
        "NzE1VjI5Ljk1MzFDNzYuODg2NSAyNy4xOTE5IDc0LjY0OCAyNC45NTMxIDcxLjg4"
        "NjcgMjQuOTUzMUg0Ny4xMTQzWiIgZmlsbD0id2hpdGUiLz4KPHBhdGggZD0iTTU5"
        "LjU0NSA3MC42ODQ2QzU2LjAyNCA3MC42ODQ2IDUzLjE1ODIgNzMuNTUwNyA1My4x"
        "NTgyIDc3LjA3MDZDNTMuMTU4MiA4MC41OTA1IDU2LjAyNCA4My40NTY2IDU5LjU0"
        "NSA4My40NTY2QzYzLjA2NDUgODMuNDU2NiA2NS45MzAzIDgwLjU5MDUgNjUuOTMw"
        "MyA3Ny4wNzA2QzY1LjkzMDMgNzMuNTUwNyA2My4wNjQ1IDcwLjY4NDYgNTkuNTQ1"
        "IDcwLjY4NDZaIiBmaWxsPSJ3aGl0ZSIvPgo8L3N2Zz4K"
    ),
    mimeType="image/svg+xml",
    sizes=["any"],
)

mcp = FastMCP(name="clickwheel", instructions=INSTRUCTIONS, icons=[SERVER_ICON])


# Advertise the MCP Apps extension in the initialize handshake so hosts
# render `_meta.ui.resourceUri` iframes alongside tool results. Without
# this, Claude Desktop sees the meta but skips iframe rendering.
from clickwheel.mcp.ui import enable_mcp_apps  # noqa: E402

enable_mcp_apps(mcp)


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
def open_session() -> Iterator[tuple[Config, Database]]:
    """Open config + DB for one tool call.

    The MCP server NEVER autoscans. Library scans walk the music directory
    (which can sit on a slow SMB share) — a synchronous scan from a chat
    tool call would block the user for minutes. Instead, MCP tools always
    serve cached data.

    Users refresh by running `clickwheel scan` from the terminal when
    they've added new music. This matches the manual-refresh model used
    by beets, Picard, and Apple Music. The CLI's interactive commands
    (`select`, `edit`) still autoscan with a cheap probe + 24h fallback —
    see clickwheel.autoscan for that strategy.
    """
    cfg = load_config()
    db = Database(cfg.db_path)
    try:
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

    Emits the structured payload BOTH as a JSON string inside `content` AND
    as `structuredContent`. Some clients (Claude Code) surface
    structuredContent to the model directly; others (Claude Desktop) only
    feed text content to the model and treat structuredContent as user-only
    accordion data. Including the JSON in content keeps the LLM functional
    everywhere — the spec endorses this for backwards compatibility.
    """
    import json

    if data is None:
        sc: dict = {}
        content = [TextContent(type="text", text=text)]
    else:
        if isinstance(data, dict):
            sc = data
        else:
            # MCP requires structuredContent to be an object. Wrap lists/scalars
            # under "result", matching FastMCP's own auto-wrap convention.
            sc = {"result": data}
        json_block = json.dumps(sc, default=str, separators=(",", ":"))
        content = [
            TextContent(type="text", text=text),
            TextContent(type="text", text=json_block),
        ]
    return CallToolResult(
        content=content,
        structuredContent=sc,
    )
