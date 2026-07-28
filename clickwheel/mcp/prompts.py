"""Server-defined prompts. Importing this module registers them on the
MCPServer instance held in `clickwheel.mcp._runtime`.

Prompts are user-invokable via the client (typically a slash command).
They seed the conversation with anti-hallucination rules and explicit
tool-chaining instructions so the LLM uses clickwheel tools the way the
server intends.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from clickwheel.mcp._runtime import mcp


@mcp.prompt(
    title="Build a clickwheel playlist by vibe",
    description=(
        "Walks the LLM through building a playlist that matches a vibe or "
        "theme, using only tracks the clickwheel library actually has. "
        "Encodes the canonical search → list → create_playlist → sync flow "
        "and the anti-hallucination rule that no track may be named unless "
        "a tool returned it. Best invoked conversationally (e.g. 'build me "
        "a 45-minute late-night indie folk playlist named chill') — "
        "Claude Code's slash-command parser splits args on whitespace "
        "without honoring quotes, so multi-word values fail there."
    ),
)
def build_playlist(
    vibe: Annotated[
        str,
        Field(
            description=(
                "Free-text description of the playlist. e.g. 'late-night "
                "headphone listening, mostly indie folk'."
            ),
        ),
    ],
    target_minutes: Annotated[
        int,
        Field(
            description="Target total duration in minutes.",
            ge=10,
            le=600,
        ),
    ] = 60,
    name: Annotated[
        str,
        Field(
            description=(
                "Playlist name to save as. Will error if it already exists "
                "— use update_playlist or pick a new name."
            ),
        ),
    ] = "from-claude",
) -> list[dict]:
    """Generate the build-playlist prompt body."""
    body = f"""\
Build a clickwheel playlist using ONLY tracks from the user's library.

Vibe: {vibe}
Target length: ~{target_minutes} minutes
Save as: {name!r}

Steps:

1. Start by calling `library_stats` to confirm the library is indexed and
   roughly how many tracks are available.

2. Use `search_tracks` with multiple terms drawn from the vibe (artists,
   genres, mood words, era cues). Try 3-6 different searches. For each
   query, prefer tracks that strongly match — don't bulk-add weak hits.

3. For artists that show up repeatedly, drill in with
   `list_albums_by_artist` and `list_tracks_by_album` so you can pick
   specific tracks rather than every track they've ever recorded.

4. Build a list of `path` values from the tool results. NEVER invent a
   path — every entry must come from the structured output of a tool.

5. Estimate total duration as you go (each track returns
   `duration_seconds`). Stop when you're within ~10 minutes of the target.

6. Call `create_playlist(name={name!r}, track_paths=[...])` to save.

7. Show the user the final track list as `Artist — Title (Album)` lines
   with a running duration. Offer to:
   - call `sync_playlist_to_ipod` to push it to the iPod
   - call `update_playlist` to swap tracks they don't like
   - call `delete_playlist` if they want to start over

If at any point a search returns 0 results, say so plainly and suggest
broader terms — never fall back to making up tracks. If the library is
empty (`library_stats` shows 0 tracks), stop and tell the user to run
`clickwheel scan`.
"""
    return [{"role": "user", "content": body}]
