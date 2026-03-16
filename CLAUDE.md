# clickwheel

A Python CLI for syncing a music library to a classic iPod from a modern Mac.

## Stack

- **Python 3.11+** with Typer, Rich, tqdm, mutagen, pylast
- **SQLite** for library index, playlist storage, and scrobble cache
- **Vendored iOpenPodv2** for iPod database management (iTunesDB + ArtworkDB)
- **beets** for metadata cleanup (called via subprocess)

## Project Layout

- `clickwheel/` — Python CLI package
- `clickwheel/ipod/` — vendored iOpenPodv2 (excluded from ruff)
- `tests/` — pytest test suite
- `scripts/` — bash utilities (audit, fix-metadata, setup)
- `beets/` — beets config template (generated config is gitignored)
- `docs/` — architecture docs

## Commands

- `clickwheel scan` — index library metadata into SQLite (incremental by default)
- `clickwheel fix` — clean up metadata via beets (requires `[fix]` extras)
- `clickwheel select` — interactive iPod subset picker (auto-scans if stale)
- `clickwheel playlist` — list saved playlists
- `clickwheel edit` — add/remove artists from a playlist
- `clickwheel delete` — delete a playlist
- `clickwheel diff` — preview iPod sync changes
- `clickwheel sync` — push playlist to iPod
- `clickwheel ls` — show iPod contents
- `clickwheel eject` — safely unmount iPod
- `clickwheel scrobble` — submit iPod listens to Last.fm (`--auth` for first-time setup)

## Development

```bash
pip install -e '.[dev]'              # install with dev dependencies
pre-commit install --hook-type pre-commit --hook-type commit-msg
python -m pytest tests/ -v           # run tests
ruff check clickwheel/               # lint
ruff format clickwheel/              # format
```

## Configuration

Runtime config is in `~/.clickwheel/config.yaml`. Environment variables override the config file. See README for all settings.

## Key Constraints

- Never move or rename source files (Plex reads from the same library)
- FLAC files are excluded from iPod sync (stock firmware limitation)
- Metadata changes are written in-place to source files
- The `scan` command is read-only (no file modifications)
- `select`, `edit`, `diff`, `sync` auto-scan the library if stale (configurable, `--no-scan` to skip)
- `fix` requires beets + Pillow (`pip install 'clickwheel[fix]'`); auto-generates beets config on first run
- macOS only (iPod sync depends on macOS disk utilities)
