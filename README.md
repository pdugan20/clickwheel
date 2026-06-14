# clickwheel

[![PyPI](https://img.shields.io/pypi/v/clickwheel?logo=pypi&logoColor=white)](https://pypi.org/project/clickwheel/)
[![CI](https://github.com/pdugan20/clickwheel/actions/workflows/ci.yml/badge.svg)](https://github.com/pdugan20/clickwheel/actions/workflows/ci.yml)
[![docs](https://img.shields.io/badge/docs-docs.clickwheel.fm-blue)](https://docs.clickwheel.fm)
[![Python](https://img.shields.io/badge/Python-%3E%3D3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?logo=opensourceinitiative&logoColor=white)](https://opensource.org/licenses/MIT)

Sync a music library to a classic iPod from a modern Mac, no iTunes required. Scan, clean up metadata, pick what goes on the iPod, and sync, all from the terminal. Optional MCP server lets Claude or other AI clients drive it conversationally.

Full documentation: [docs.clickwheel.fm](https://docs.clickwheel.fm).

## Install

```bash
pipx install clickwheel
```

Optional extras:

```bash
pipx inject clickwheel 'clickwheel[mcp]'   # MCP server for Claude / AI clients
```

`clickwheel fix` (metadata cleanup) runs entirely on the base install, no extras required.

## Quick Start

Point clickwheel at your music:

```bash
mkdir -p ~/.clickwheel
echo "music_dir: /path/to/your/music" > ~/.clickwheel/config.yaml
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
| `clickwheel convert`  | Transcode FLAC albums to iPod-playable MP3     |
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

`clickwheel convert` transcodes selected FLAC albums to iPod-playable MP3 (interactive picker, or `--artist`/`--album`/`--all-flac`; `--bitrate`, `--force`). Output goes to `transcode_dir` and is indexed into the library, so the resulting MP3s flow through `select`/`sync` like any other track. It requires `ffmpeg` on your PATH (`brew install ffmpeg`).

Each optional integration has its own doc:

- **Plex / Plexamp**: push/pull playlists between clickwheel and a Plex music library. See the [Plex guide](https://docs.clickwheel.fm/guides/plex).
- **Apple Music**: push/pull/delete playlists in your Apple Music account; syncs across Apple devices via iCloud Music Library. See the [Apple Music guide](https://docs.clickwheel.fm/guides/apple-music).
- **Last.fm**: submit iPod listens. See the [scrobbling guide](https://docs.clickwheel.fm/guides/scrobbling).

## Configuration

```yaml
# ~/.clickwheel/config.yaml
music_dir: /Volumes/Music/Library
ipod_capacity_gb: 64
auto_scan: true
transcode_dir: ~/.clickwheel/transcoded
transcode_bitrate: 320
```

- `transcode_dir` — where `clickwheel convert` writes converted MP3s (default `~/.clickwheel/transcoded`). Kept outside your music library so Plex and the scanner don't pick them up.
- `transcode_bitrate` — MP3 CBR bitrate in kbps for conversion (default `320`).

Environment variables (`MUSIC_DIR`, `AUTO_SCAN`, etc.) override config values. See the [configuration reference](https://docs.clickwheel.fm/reference/configuration) for the full schema and `fix` walkthrough. Integrations (Plex, Apple Music, Last.fm) are all off by default; opt in via the per-integration guides linked above.

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

The server exposes tools across library, playlist, iPod, Plex, Apple Music, and Last.fm domains, plus a `build_playlist` prompt with anti-hallucination rules. Destructive operations (`delete_playlist`, `sync_playlist_to_ipod`) are gated by client confirmation.

For client setup (Claude Code, Claude Desktop, mobile) and the full tool reference, see the [MCP server docs](https://docs.clickwheel.fm/concepts/mcp-server).

## Requirements

- macOS (iPod sync depends on macOS disk utilities)
- Python 3.11+
- iPod Classic with stock firmware, connected via USB
- FLAC files are excluded from sync (stock firmware limitation); use `clickwheel convert` to transcode them to MP3
- `ffmpeg` on your PATH for `clickwheel convert` (`brew install ffmpeg`)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, testing, and commit conventions.
