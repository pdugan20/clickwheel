# clickwheel

A Python CLI for syncing a music library to a classic iPod from a modern Mac.

## Stack

- **Python 3.11+** with Typer, Rich, questionary, tqdm, mutagen, pylast
- **SQLite** for library index, playlist storage, and scrobble cache
- **Vendored iOpenPodv2** for iPod database management (iTunesDB + ArtworkDB)
- **beets** for metadata cleanup (called via subprocess)

## Project Layout

- `clickwheel/cli.py` — Typer command definitions (entry point)
- `clickwheel/actions.py` — pure-logic functions consumed by both the CLI and the MCP server (no Rich/tqdm/typer/questionary). Errors raised as a typed `ClickwheelError` hierarchy.
- `clickwheel/output.py` — Rich console helpers (tables, spinners, panels, errors)
- `clickwheel/config.py` — config loading (~/.clickwheel/config.yaml, env vars)
- `clickwheel/db.py` — SQLite database (tracks, playlists, scrobble cache)
- `clickwheel/library.py` — music file scanning (mutagen)
- `clickwheel/autoscan.py` — staleness check + CLI-friendly auto-scan wrapper around `actions.scan_library`
- `clickwheel/scrobble.py` — Last.fm scrobbling (pylast)
- `clickwheel/mcp/` — optional MCP server (gated by `[mcp]` extra). `clickwheel-mcp` console script and `python -m clickwheel.mcp` both work.
- `clickwheel/ipod/` — vendored iOpenPodv2 (excluded from ruff)
- `tests/` — pytest test suite
- `scripts/` — bash utilities (audit, fix-metadata, setup, pre-push)
- `docs/` — architecture, releasing, and testing docs (`docs/mcp/` covers the MCP project)

## Commands

- `clickwheel scan` — index library metadata into SQLite (incremental by default)
- `clickwheel fix` — clean up metadata via beets (requires `[fix]` extras)
- `clickwheel select` — interactive iPod subset picker (questionary checkbox, auto-scans if stale)
- `clickwheel playlist` — list saved playlists
- `clickwheel edit` — add/remove artists (interactive questionary menus or `--add`/`--remove` flags)
- `clickwheel delete` — delete a playlist (with confirmation)
- `clickwheel diff` — preview iPod sync changes (panel + colored tables)
- `clickwheel sync` — push playlist to iPod (Rich Live table, confirmation)
- `clickwheel ls` — show iPod contents
- `clickwheel eject` — safely unmount iPod
- `clickwheel scrobble` — submit iPod listens to Last.fm (`--auth` for first-time setup)

## Development

```bash
make dev                             # install with dev dependencies
make test                            # run tests with coverage
make lint                            # ruff check + format check
make format                          # auto-format code
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

## Critical Rules

1. **All CLI output goes through `output.py`** — never call `console.print()` directly. A pre-commit pygrep hook enforces this. Use the semantic helpers: `error()`, `warn()`, `success()`, `info()`, `status()`, `dim()`, `confirm()`, `spinner()`.

2. **Never move or rename source files** — Plex reads from the same music library. Metadata changes are written in-place.

3. **The `scan` command is read-only** — it only reads metadata and writes to SQLite. No file modifications.

4. **FLAC files are excluded from iPod sync** — stock iPod firmware doesn't support FLAC. Don't add transcoding.

5. **`clickwheel/ipod/` is vendored code** — excluded from ruff linting. Don't refactor it unless fixing a bug in the iPod database writer.

6. **Interactive prompts use questionary** — not raw `typer.prompt()` or `input()`. Arrow-key selection with `questionary.select()` and `questionary.checkbox()`. Non-interactive flags (`--add`/`--remove`) are kept for scripting.

7. **Long operations use `spinner()` context manager** — beets phases, iPod reads, Last.fm calls, eject. Never leave the user staring at a frozen terminal.

8. **Destructive operations require confirmation** — delete, sync. Use `typer.confirm()` with sensible defaults.

9. **`select`, `edit`, `diff`, `sync` auto-scan** the library via a two-tier strategy: cheap probe (stat music_dir + first-level dirs, ~5s on SMB) catches new artist/album folders; full incremental scan runs only when probe detects change OR the 24h fallback timer (default `auto_scan_staleness_minutes=1440`) expires. `--no-scan` skips both. The MCP server NEVER autoscans — chat tool calls always serve cached data. See `clickwheel/autoscan.py` for the detailed contract.

10. **`fix` requires beets extras** — `pip install 'clickwheel[fix]'`. Auto-generates beets config on first run.

11. **MCP tools wrap `actions.py`, never `cli.py`** — CLI commands are display adapters, MCP tools are RPC adapters. Both consume the same pure functions. New library/iPod features should land in `actions.py` first, then get a thin wrapper in each surface.

12. **MCP destructive tools elicit confirmation** — `delete_playlist` and `sync_playlist_to_ipod` use `Context.elicit()` to ask the user via the client when `confirm=False`. Don't bypass this on the server side; if a caller really needs no prompt they pass `confirm=True`.

13. **MCP server logs to stderr only** — stdout is the wire protocol. Use `logger` from `clickwheel.mcp.server`, controlled by `CLICKWHEEL_MCP_LOG_LEVEL`.

## Code Style

- **Naming**: snake_case for functions/variables, UPPER_CASE for constants
- **Error handling**: use `error()` + `raise typer.Exit(1)` for fatal errors. Offer retry for recoverable failures (sync DB write, scrobble submission).
- **Imports**: lazy imports for heavy modules (questionary, subprocess, pylast) — import inside the function that uses them
- **Output colors**: red=errors, yellow=warnings, green=success/confirm, bold=status, dim=hints, cyan=panels
- **Progress**: `tqdm` for scan (many small items), Rich `Live` table for sync (fewer items, show detail), `spinner()` for async waits

## Configuration

Runtime config is in `~/.clickwheel/config.yaml`. Environment variables override the config file. See README for all settings.

## Testing

- pytest with coverage threshold (30% minimum, excluding vendored ipod/)
- Coverage runs in CI and uploads to Codecov
- Test matrix: Python 3.11-3.13 on Ubuntu and macOS
