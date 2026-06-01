"""Curated CLI examples, keyed by full command path.

Consumed by gen-cli-reference.py to render an "Examples" block under each
command. Hand-maintained: add the realistic invocations worth showing, skip
trivial ones. Each entry is a list of (command, comment) pairs; comment may be
None. Keep comments short and em-dash-free.
"""

from __future__ import annotations

EXAMPLES: dict[str, list[tuple[str, str | None]]] = {
    # Library
    "scan": [
        ("clickwheel scan", "Incremental index of new or changed files"),
        ("clickwheel scan --full", "Rescan the whole library from scratch"),
    ],
    "fix": [
        ("clickwheel fix", "Repair the whole library: album art, year, genres"),
        ('clickwheel fix "Nirvana"', "Just one artist folder"),
        ("clickwheel fix --refresh-genres", "Re-fetch genres, ignoring the cache"),
    ],
    # Playlists
    "playlist": [
        ("clickwheel playlist", "List saved playlists"),
        ("clickwheel playlist road-trip", "Show one playlist's tracks"),
    ],
    "edit": [
        ('clickwheel edit road-trip --add "Nirvana"', "Add an artist"),
        ('clickwheel edit road-trip --remove "Beastie Boys"', "Remove an artist"),
        ('clickwheel edit road-trip -d "Windows down"', "Set the description"),
    ],
    "delete": [
        ("clickwheel delete road-trip", "Delete a playlist (asks to confirm)"),
    ],
    "heal": [
        ("clickwheel heal road-trip", "Drop references to files no longer on disk"),
    ],
    # iPod
    "select": [
        ("clickwheel select", "Interactive picker; saved as the 'ipod' playlist"),
        ('clickwheel select --name "road-trip"', "Build a named selection"),
    ],
    "diff": [
        ("clickwheel diff", "Preview changes for the 'ipod' playlist"),
    ],
    "sync": [
        ("clickwheel sync", "Push the 'ipod' playlist to the device"),
        ("clickwheel sync --dry-run", "Show what would change without writing"),
        ("clickwheel sync road-trip", "Sync a specific playlist"),
    ],
    "ls": [
        ("clickwheel ls", "Show what's on the iPod"),
    ],
    "eject": [
        ("clickwheel eject", "Safely unmount before unplugging"),
    ],
    # Plex
    "plex doctor": [
        ("clickwheel plex doctor", "Diagnose the Plex connection (five stages)"),
    ],
    "plex list": [
        ("clickwheel plex list", "List Plex audio playlists"),
    ],
    "plex pull": [
        ("clickwheel plex pull road-trip", "Import a Plex playlist into clickwheel"),
    ],
    "sync-plex": [
        ("clickwheel sync-plex road-trip", "Push one playlist to Plex"),
        ("clickwheel sync-plex --all", "Push every clickwheel playlist"),
    ],
    # Apple Music
    "apple auth": [
        ("clickwheel apple auth", "One-time browser authorization"),
    ],
    "apple doctor": [
        ("clickwheel apple doctor", "End-to-end Apple Music probe"),
    ],
    "apple match": [
        ("clickwheel apple match road-trip", "Preview how tracks resolve (no writes)"),
    ],
    "apple push": [
        ("clickwheel apple push road-trip", "Create the playlist in Apple Music"),
        (
            "clickwheel apple push road-trip --include-low",
            "Include low-confidence matches",
        ),
    ],
    "apple pull": [
        ("clickwheel apple pull road-trip", "Import an Apple Music playlist"),
    ],
    # Last.fm
    "scrobble": [
        ("clickwheel scrobble --auth", "First-time Last.fm authorization"),
        ("clickwheel scrobble", "Submit new iPod listens"),
        ("clickwheel scrobble --status", "Show pending scrobbles without sending"),
    ],
}
