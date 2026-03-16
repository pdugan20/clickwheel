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

To use `clickwheel fix` (metadata cleanup, album art, genre tagging):

```bash
pipx inject clickwheel 'clickwheel[fix]'
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

Commands like `select`, `edit`, `diff`, and `sync` automatically check for library changes before running. To skip this, pass `--no-scan`.

## Commands

| Command               | Description                                                                   |
| --------------------- | ----------------------------------------------------------------------------- |
| `clickwheel scan`     | Index your music library and report on metadata quality                       |
| `clickwheel fix`      | Clean up metadata, fetch album art, fill genres via beets                     |
| `clickwheel select`   | Interactive picker — browse by artist/album/genre                             |
| `clickwheel playlist` | List saved playlists or show details for one                                  |
| `clickwheel edit`     | Add or remove artists from a playlist (interactive or via `--add`/`--remove`) |
| `clickwheel delete`   | Delete a saved playlist                                                       |
| `clickwheel diff`     | Preview what would be added or removed on the iPod                            |
| `clickwheel sync`     | Push your playlist to the iPod                                                |
| `clickwheel ls`       | Show what's on the iPod                                                       |
| `clickwheel eject`    | Safely unmount the iPod                                                       |
| `clickwheel scrobble` | Submit recent iPod listens to Last.fm                                         |

## Configuration

clickwheel reads from `~/.clickwheel/config.yaml`:

```yaml
music_dir: /Volumes/Music/Library
ipod_capacity_gb: 64 # defaults to 64
auto_scan: true # auto-check for library changes (default: true)
auto_scan_staleness_minutes: 30 # how often to re-check (default: 30)
lastfm_api_key: your_key # last.fm/api/account/create
lastfm_api_secret: your_secret
lastfm_username: your_username
```

Environment variables (`MUSIC_DIR`, `AUTO_SCAN`, etc.) override the config file.

### Metadata cleanup (`fix`)

`clickwheel fix` uses [beets](https://beets.io/) to fetch album art, fill genres, and clean up tags. Install the extras first:

```bash
# If installed with pipx:
pipx inject clickwheel 'clickwheel[fix]'

# If installed with pip:
pip install 'clickwheel[fix]'
```

On first run, clickwheel generates a beets config at `~/.clickwheel/beets/config.yaml`. You can edit it to customize sources, matching thresholds, etc. The config is set up to never move or rename your files.

Fix a single artist/album folder:

```bash
clickwheel fix "Artist - Album Name"
```

Or fix the entire library:

```bash
clickwheel fix
```

### Last.fm scrobbling

To submit your iPod listens to Last.fm, add your API credentials to the config (get them at [last.fm/api/account/create](https://www.last.fm/api/account/create)):

```yaml
lastfm_api_key: your_key
lastfm_api_secret: your_secret
lastfm_username: your_username
```

Then authorize clickwheel with your Last.fm account (one-time):

```bash
clickwheel scrobble --auth
```

After that, submit listens any time your iPod is connected:

```bash
clickwheel scrobble
```

Scrobbles are cached locally so duplicates are never submitted, even if you run it multiple times.

## Requirements

- macOS (iPod sync depends on macOS disk utilities)
- Python 3.11+
- iPod Classic with stock firmware, connected via USB
- FLAC files are excluded from sync (stock firmware limitation)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, testing, and commit conventions.
