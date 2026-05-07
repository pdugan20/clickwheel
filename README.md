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
pipx inject clickwheel 'clickwheel[fix]'   # metadata cleanup via beets
pipx inject clickwheel 'clickwheel[mcp]'   # MCP server for Claude / AI clients
```

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

| Command               | Description                                                             |
| --------------------- | ----------------------------------------------------------------------- |
| `clickwheel scan`     | Index your music library and report on metadata quality                 |
| `clickwheel fix`      | Clean up metadata, fetch album art, fill genres via beets               |
| `clickwheel select`   | Interactive picker — checkbox artist selection                          |
| `clickwheel playlist` | List saved playlists or show details for one                            |
| `clickwheel edit`     | Add or remove artists via interactive menus or `--add`/`--remove` flags |
| `clickwheel heal`     | Drop playlist references to tracks no longer on disk                    |
| `clickwheel delete`   | Delete a saved playlist (with confirmation)                             |
| `clickwheel diff`     | Preview what would be added or removed on the iPod                      |
| `clickwheel sync`     | Push your playlist to the iPod (with live progress table)               |
| `clickwheel ls`       | Show what's on the iPod                                                 |
| `clickwheel eject`    | Safely unmount the iPod                                                 |
| `clickwheel scrobble` | Submit recent iPod listens to Last.fm                                   |

## Configuration

```yaml
# ~/.clickwheel/config.yaml
music_dir: /Volumes/Music/Library
ipod_capacity_gb: 64
auto_scan: true
auto_scan_staleness_minutes: 1440 # default: 24h
lastfm_api_key: your_key
lastfm_api_secret: your_secret
lastfm_username: your_username
```

Environment variables (`MUSIC_DIR`, `AUTO_SCAN`, etc.) override config values. See [`docs/configuration.md`](docs/configuration.md) for the full schema, auto-scan internals, and `fix` / Last.fm walkthroughs.

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

The server exposes 21 tools across library, playlist, iPod, and Last.fm domains, plus a `build_playlist` prompt with anti-hallucination rules. Destructive operations (`delete_playlist`, `sync_playlist_to_ipod`) are gated by client confirmation.

For Claude Desktop config, the full tool reference, and other clients (Cursor, Continue, Cline, Zed), see [`docs/mcp/`](docs/mcp/).

## Requirements

- macOS (iPod sync depends on macOS disk utilities)
- Python 3.11+
- iPod Classic with stock firmware, connected via USB
- FLAC files are excluded from sync (stock firmware limitation)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, testing, and commit conventions.
