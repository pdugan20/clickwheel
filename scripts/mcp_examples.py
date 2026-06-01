"""Curated example prompts per MCP domain.

Consumed by gen-mcp-reference.py to render a "Try asking Claude" block at the top
of each domain page. MCP examples are natural-language prompts (not shell
commands), since that's how users drive the tools through Claude. Hand-maintained,
em-dash-free.
"""

from __future__ import annotations

PROMPTS: dict[str, list[str]] = {
    "Library": [
        "What's in my library?",
        "Do I have any Beastie Boys albums?",
        "Search my library for acoustic versions.",
    ],
    "Playlists": [
        "What playlists do I have?",
        "Build a 45-minute late-night indie folk playlist.",
        "Add Nirvana to my road-trip playlist.",
    ],
    "iPod": [
        "What's on my iPod, and how full is it?",
        "Put all my Weezer on the iPod.",
        "Sync my road-trip playlist to the iPod, then eject it.",
    ],
    "Plex": [
        "Is my Plex connection working?",
        "Push my road-trip playlist to Plexamp.",
        "What playlists are on Plex?",
    ],
    "Apple Music": [
        "Push my road-trip playlist to Apple Music.",
        "Pull my Heavy Rotation playlist from Apple Music.",
    ],
    "Last.fm": [
        "What listens am I waiting to scrobble?",
        "Submit my recent iPod plays to Last.fm.",
    ],
}
