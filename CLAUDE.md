# clickwheel

A Python CLI for syncing a music library to a classic iPod from a modern Mac.

## Stack

- **Python 3.11+** with Typer, Rich, tqdm, mutagen
- **Bash scripts** for beets-based metadata cleanup
- **SQLite** for library index and playlist storage
- **libgpod** for iPod database management (Phase 5)

## Project Layout

- `clickwheel/` — Python CLI package (installed via `pipx install -e .`)
- `beets/` — beets config template, generated config is gitignored
- `scripts/` — bash utilities (audit, fix-metadata, setup)
- `playlists/` — saved iPod selections
- `reports/` — audit output (gitignored)
- `docs/` — architecture docs and project tracker

## Commands

- `clickwheel scan` — index library metadata into SQLite
- `clickwheel fix` — run beets metadata cleanup
- `clickwheel select` — interactive iPod subset picker
- `clickwheel playlist` — manage saved selections
- `clickwheel diff/sync/ls/eject` — iPod sync (Phase 5)

## Development

```bash
pipx install -e .                    # install CLI in editable mode
ruff check clickwheel/               # lint Python
ruff format clickwheel/              # format Python
shellcheck scripts/*.sh              # lint bash
shfmt -d scripts/*.sh                # check bash formatting
```

## Configuration

All runtime config is in `.env` (gitignored). Copy `.env.example` to get started. The `setup.sh` script generates `beets/config.yaml` from the template.

## Key Constraints

- Never move or rename source files (Plex reads from the same library)
- FLAC files are excluded from iPod sync (stock firmware limitation)
- Metadata changes are written in-place to source files
- The `scan` command is read-only (no file modifications)
