# clickwheel

[![CI](https://github.com/pdugan20/clickwheel/actions/workflows/ci.yml/badge.svg)](https://github.com/pdugan20/clickwheel/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-%3E%3D3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Bash](https://img.shields.io/badge/scripts-bash-blue?logo=gnubash&logoColor=white)](https://www.gnu.org/software/bash/)
[![ShellCheck](https://img.shields.io/badge/linting-shellcheck-brightgreen?logo=gnu&logoColor=white)](https://www.shellcheck.net/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow?logo=opensourceinitiative&logoColor=white)](https://opensource.org/licenses/MIT)

A CLI for syncing a music library to a classic iPod from a modern Mac.

Handles the full workflow: audit and clean up your library's metadata and album art, interactively select what goes on the iPod, and sync with a progress bar — all without iTunes.

## Prerequisites

- macOS with [Homebrew](https://brew.sh)
- Python 3.11+
- Music library accessible via local or network mount
- iPod Classic (stock firmware, connected via USB)

## Quick Start

```bash
git clone https://github.com/pdugan20/clickwheel.git
cd clickwheel
cp .env.example .env        # edit with your music path + API key
./scripts/setup.sh          # install all dependencies

# metadata cleanup (one-time)
clickwheel scan              # audit library quality
clickwheel fix               # fix tags, art, genres via beets

# iPod workflow (ongoing)
clickwheel select            # pick artists/albums for iPod
clickwheel diff              # preview changes
clickwheel sync              # push to iPod
```

## Commands

| Command | Description |
| --- | --- |
| `clickwheel scan` | Index the music library, report on metadata/art quality |
| `clickwheel fix` | Clean up metadata, fetch album art, fill genres (beets) |
| `clickwheel select` | Interactive picker — browse by artist/album/genre, track size vs. capacity |
| `clickwheel playlist` | List, save, and load selections |
| `clickwheel diff` | Preview what would be added/removed on the iPod |
| `clickwheel sync` | Push current selection to iPod with progress bar |
| `clickwheel ls` | Show what's currently on the iPod |
| `clickwheel eject` | Safely unmount the iPod |

## Configuration

All config lives in `.env` in the project root:

```bash
MUSIC_DIR=/path/to/your/music       # local path or network mount
ACOUSTID_API_KEY=your_key_here      # from acoustid.org (free)
IPOD_MOUNT=/Volumes/IPOD            # iPod mount point (auto-detected if omitted)
```

## Project Structure

```text
clickwheel/         # Python CLI package
  __main__.py       # entry point
  cli.py            # Typer command definitions
  library.py        # music library indexing
  selector.py       # interactive subset picker
  ipod.py           # iPod sync via libgpod
  db.py             # local SQLite for library index + selections
beets/              # beets configuration
  config.yaml.template
scripts/            # bash utilities
  setup.sh          # install all dependencies
  audit.sh          # standalone metadata audit (ffprobe-based)
  fix-metadata.sh   # standalone beets cleanup
playlists/          # saved selections
reports/            # audit output and logs (gitignored)
```

## Stack

- **[Typer](https://typer.tiangolo.com/)** — CLI framework
- **[Rich](https://rich.readthedocs.io/)** — terminal UI (tables, progress bars, trees)
- **[beets](https://beets.io)** — metadata cleanup engine
- **[libgpod](https://github.com/fadingred/libgpod)** — iPod database management
- **[tqdm](https://tqdm.github.io/)** — progress bars for sync
- **[ffprobe](https://ffmpeg.org)** — audio file inspection

## Notes

- Metadata changes are written in-place. If your library is shared with Plex or other apps, changes will be picked up on their next scan.
- beets is configured to never move or rename files.
- FLAC files are not synced to the iPod (stock firmware doesn't support FLAC). Convert them separately if needed.
- The `scan` and `audit.sh` commands are fully non-destructive (read-only).
