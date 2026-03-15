# clickwheel

[![PyPI](https://img.shields.io/pypi/v/clickwheel?logo=pypi&logoColor=white)](https://pypi.org/project/clickwheel/)
[![CI](https://github.com/pdugan20/clickwheel/actions/workflows/ci.yml/badge.svg)](https://github.com/pdugan20/clickwheel/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-%3E%3D3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?logo=opensourceinitiative&logoColor=white)](https://opensource.org/licenses/MIT)

A CLI for syncing a music library to a classic iPod from a modern Mac — no iTunes required.

Handles the full workflow: scan and clean up your library's metadata, interactively pick what goes on the iPod, and sync with a progress bar.

## Install

```bash
pipx install clickwheel
```

Or with album art embedding support:

```bash
pipx install 'clickwheel[artwork]'
```

## Quick Start

Create a config file pointing to your music library:

```bash
mkdir -p ~/.clickwheel
cat > ~/.clickwheel/config.yaml << 'EOF'
music_dir: /path/to/your/music
EOF
```

Then run `clickwheel scan` to index your library and `clickwheel select` to start picking music for your iPod.

## Commands

| Command               | Description                                               |
| --------------------- | --------------------------------------------------------- |
| `clickwheel scan`     | Index your music library and report on metadata quality   |
| `clickwheel fix`      | Clean up metadata, fetch album art, fill genres via beets |
| `clickwheel select`   | Interactive picker — browse by artist/album/genre         |
| `clickwheel playlist` | List saved playlists or show details for one              |
| `clickwheel edit`     | Add or remove artists from a playlist                     |
| `clickwheel delete`   | Delete a saved playlist                                   |
| `clickwheel diff`     | Preview what would be added or removed on the iPod        |
| `clickwheel sync`     | Push your playlist to the iPod                            |
| `clickwheel ls`       | Show what's on the iPod                                   |
| `clickwheel eject`    | Safely unmount the iPod                                   |
| `clickwheel scrobble` | Submit recent iPod listens to Last.fm                     |

## Configuration

clickwheel reads from `~/.clickwheel/config.yaml`:

```yaml
music_dir: /Volumes/Music/Library
ipod_capacity_gb: 64 # defaults to 64
lastfm_api_key: your_key # last.fm/api/account/create
lastfm_api_secret: your_secret
lastfm_username: your_username
```

Environment variables (`MUSIC_DIR`, `ACOUSTID_API_KEY`, etc.) override the config file.

## Requirements

- macOS (iPod sync depends on macOS disk utilities)
- Python 3.11+
- iPod Classic with stock firmware, connected via USB
- FLAC files are excluded from sync (stock firmware limitation)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, testing, and commit conventions.
