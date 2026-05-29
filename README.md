# clickwheel

[![PyPI](https://img.shields.io/pypi/v/clickwheel?logo=pypi&logoColor=white)](https://pypi.org/project/clickwheel/)
[![CI](https://github.com/pdugan20/clickwheel/actions/workflows/ci.yml/badge.svg)](https://github.com/pdugan20/clickwheel/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-%3E%3D3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?logo=opensourceinitiative&logoColor=white)](https://opensource.org/licenses/MIT)

Sync a music library to a classic iPod from a modern Mac — no iTunes required. Scan, clean up metadata, pick what goes on the iPod, and sync, all from the terminal. Optional MCP server lets Claude or other AI clients drive it conversationally.

## Install

```bash
pipx install clickwheel
```

Optional extras:

```bash
pipx inject clickwheel 'clickwheel[mcp]'   # MCP server for Claude / AI clients
```

`clickwheel fix` (metadata cleanup) runs entirely on the base install — no extras required.

## Quick Start

Point clickwheel at your music:

```bash
mkdir -p ~/.clickwheel
cat > ~/.clickwheel/config.yaml << 'EOF'
music_dir: /path/to/your/music
EOF
```

Then index it and pick what goes on the iPod:

```bash
clickwheel scan      # build the library index
clickwheel select    # interactive checkbox picker
clickwheel sync      # push to the iPod
```

## Commands

The iPod workflow:

| Command               | Description                                   |
| --------------------- | --------------------------------------------- |
| `clickwheel scan`     | Index your library; report metadata gaps      |
| `clickwheel fix`      | Fill in album art, years, genres; repair tags |
| `clickwheel select`   | Interactive checkbox picker for the iPod      |
| `clickwheel playlist` | List saved playlists or show one's tracks     |
| `clickwheel edit`     | Add/remove artists or set a description       |
| `clickwheel heal`     | Drop playlist refs to files no longer on disk |
| `clickwheel delete`   | Delete a saved playlist                       |
| `clickwheel diff`     | Preview what would change on the iPod         |
| `clickwheel sync`     | Push your playlist to the iPod                |
| `clickwheel ls`       | Show what's on the iPod                       |
| `clickwheel eject`    | Safely unmount the iPod                       |

Each optional integration has its own doc:

- **Plex / Plexamp** — push/pull playlists between clickwheel and a Plex music library. See [`docs/plex.md`](docs/plex.md).
- **Apple Music** — push/pull/delete playlists in your Apple Music account; syncs across Apple devices via iCloud Music Library. See [`docs/applemusic.md`](docs/applemusic.md).
- **Last.fm** — submit iPod listens. See [`docs/lastfm.md`](docs/lastfm.md).

## Configuration

```yaml
# ~/.clickwheel/config.yaml
music_dir: /Volumes/Music/Library
ipod_capacity_gb: 64
auto_scan: true
```

Environment variables (`MUSIC_DIR`, `AUTO_SCAN`, etc.) override config values. See [`docs/configuration.md`](docs/configuration.md) for the full schema and `fix` walkthrough. Integrations (Plex, Apple Music, Last.fm) are all off by default — opt in via the per-integration docs linked above.

## MCP server

clickwheel ships an optional MCP server so Claude Code, Claude Desktop, and other MCP-aware clients can drive your library conversationally:

> What's on my iPod, and how full is it?
>
> Build me a 45-minute late-night indie folk playlist using only tracks I actually own.
>
> Sync the 'ipod' playlist to my iPod and then eject it.

Quick start with Claude Code:

```bash
pipx inject clickwheel 'clickwheel[mcp]'
claude mcp add clickwheel clickwheel-mcp --scope user
```

The server exposes 37 tools across library, playlist, iPod, Plex, Apple Music, and Last.fm domains, plus a `build_playlist` prompt with anti-hallucination rules. Destructive operations (`delete_playlist`, `sync_playlist_to_ipod`) are gated by client confirmation.

For Claude Desktop config, the full tool reference, and other clients (Cursor, Continue, Cline, Zed), see [`docs/mcp/`](docs/mcp/).

## Requirements

- macOS (iPod sync depends on macOS disk utilities)
- Python 3.11+
- iPod Classic with stock firmware, connected via USB
- FLAC files are excluded from sync (stock firmware limitation)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, testing, and commit conventions.
