# Architecture

## Overview

clickwheel is a Python CLI that manages the full iPod sync workflow:

1. **Scan** — read metadata from a music library into a local SQLite index
2. **Fix** — repair `albumartist` tags, fetch art/year from MusicBrainz, fetch genres from Last.fm. All native, all cached in SQLite.
3. **Select** — interactively pick artists/albums that fit on the iPod
4. **Sync** — write files and the iTunesDB to the iPod

It also ships an optional MCP (Model Context Protocol) server so AI clients can drive the same workflows conversationally.

## Data flow

```text
Music Library (NAS/local)
        |
        v
   clickwheel scan --> SQLite index (~/.clickwheel/library.db)
        |
        +-----> CLI commands (select, edit, diff, sync, ...)
        |
        +-----> MCP server (clickwheel-mcp) <----- AI clients (Claude Code/Desktop, ...)
        |
        v
   clickwheel sync --> iPod (via vendored iOpenPodv2)
```

## Module layout

```text
clickwheel/
  cli.py          # Typer command definitions (entry point)
  actions.py      # pure-logic functions consumed by both CLI and MCP
  config.py       # config loading (~/.clickwheel/config.yaml, env vars)
  db.py           # SQLite database (tracks, playlists, scrobble cache)
  library.py      # music file scanning (mutagen)
  autoscan.py     # two-tier library staleness check
  output.py       # Rich console helpers (tables, spinners, panels, errors)
  scrobble.py     # Last.fm scrobbling + web auth (pylast)
  mcp/            # optional MCP server (gated by [mcp] extra)
  ipod/           # vendored iOpenPodv2 (iTunesDB + ArtworkDB writers)
```

## Key design decisions

### Files stay in place

clickwheel never moves, copies, or renames source files. The music library is the single source of truth. Other apps (Plex, music players) read from the same files; tag rewrites (e.g. `clickwheel fix`) are applied in place.

### Local SQLite index

`clickwheel scan` reads metadata from the library and stores it in a local SQLite database (WAL mode, so the CLI and MCP server can read concurrently). This avoids re-reading thousands of files over SMB every time you want to browse or select music. Scans are incremental by default — only files whose mtime or size changed are re-read.

### Two-tier auto-scan

`select`, `edit`, `diff`, and `sync` check whether the index is stale before running. The check is two-tier: a cheap probe of top-level music folders catches new artist/album folders (~5s on SMB); a full re-scan runs at most once per `auto_scan_staleness_minutes` (default: 1440 = 24h). The cheap probe is ~40× faster than a full SMB walk, so the practical cost of running auto-scan on every command is minimal.

### Selections are playlists

When you `clickwheel select`, the result is a playlist stored in SQLite with full track paths. Playlists track size so you can see capacity usage before syncing.

### No FLAC on iPod

Stock iPod firmware doesn't support FLAC. Rather than building a transcoding pipeline, FLAC files are excluded from selection. Convert them separately if needed.

### iPod database via vendored iOpenPodv2

The iPod's stock firmware requires a proprietary database (`iTunesDB`). We vendor iOpenPodv2 (MIT-licensed, ~2,000 lines) to write it directly — no libgpod dependency, no C extensions, pure Python.

### Sync merges, never clobbers

`sync_playlist` reads the existing iTunesDB and merges the playlist's tracks into it, preserving play counts, artwork links, and tracks that aren't in the current playlist. Earlier versions wrote only the new tracks, which silently dropped everything else on the iPod (recovered via the `.backup` file once; now prevented in code with regression tests).

### numpy is optional

numpy is only used for RGB565 artwork conversion in the ArtworkDB writer. At ~30MB installed, it's behind an `artwork` extra: `pipx install clickwheel[artwork]`.

### Last.fm auth via web flow

Scrobbling requires a Last.fm session key, obtained through a one-time browser auth flow (`clickwheel scrobble --auth`). The session key is saved to `~/.clickwheel/config.yaml` and never expires unless the user revokes it. No passwords are stored.

## CLI / MCP separation

The CLI and MCP server share pure-logic functions in `clickwheel/actions.py`. CLI commands handle args + Rich rendering and call into actions; MCP tools validate input + call into actions and return dicts. Both surfaces stay thin display adapters over the same logic.

A typed error hierarchy (`ClickwheelError` subclasses) lives in `actions.py`. CLI translates them to `output.error()` + `typer.Exit(1)`; MCP translates them to `McpError` with appropriate codes.

### MCP server specifics

- **Transport:** stdio. One process per client session.
- **No auto-scan.** Library scans walk the music directory (potentially over slow SMB); a synchronous scan from a chat tool call would block the user for minutes. MCP tools always serve cached data. Users refresh by running `clickwheel scan` from the terminal.
- **iPod state** is re-read on every tool call that touches it. iPod state changes externally (user plugs/unplugs); caching across calls would be wrong.
- **Logging** goes to stderr only — stdout is reserved for protocol frames. Configurable via `CLICKWHEEL_MCP_LOG_LEVEL`.
- **Destructive tools** (`delete_playlist`, `sync_playlist_to_ipod`) carry the MCP `destructiveHint=true` annotation. Server-side `instructions` ask the model to summarize impact in chat before invoking, so users get context regardless of how the client gates the call.

See [`docs/mcp/README.md`](mcp/README.md) for client install/config and the full tool reference.

## Dependencies

| Dependency  | Purpose                   | Install             |
| ----------- | ------------------------- | ------------------- |
| Typer       | CLI framework             | pip (auto)          |
| Rich        | Terminal formatting       | pip (auto)          |
| questionary | Interactive prompts       | pip (auto)          |
| tqdm        | Progress bars             | pip (auto)          |
| mutagen     | Audio metadata            | pip (auto)          |
| pylast      | Last.fm API               | pip (auto)          |
| mcp         | Model Context Protocol    | pip (mcp extra)     |
| numpy       | RGB565 artwork conversion | pip (artwork extra) |
