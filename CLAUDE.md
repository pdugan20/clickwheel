# clickwheel

A Python CLI for syncing a music library to a classic iPod from a modern Mac.

## Stack

- **Python 3.11+** with Typer, Rich, questionary, tqdm, mutagen, pylast
- **SQLite** for library index, playlist storage, scrobble cache, MusicBrainz cache, Last.fm genre cache
- **Vendored iOpenPodv2** for iPod database management (iTunesDB + ArtworkDB)

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
- `clickwheel convert` — transcode selected FLAC albums to MP3 (interactive picker or `--artist`/`--album`/`--all-flac`); writes to `transcode_dir` and indexes the results
- `clickwheel fix` — repair albumartist, fetch art/year from MusicBrainz, fetch genres from Last.fm (native — no extras required)
- `clickwheel select` — interactive iPod subset picker (questionary checkbox, auto-scans if stale)
- `clickwheel playlist` — list saved playlists
- `clickwheel edit` — add/remove artists, set a description (interactive questionary menus or `--add`/`--remove`/`--description` flags)
- `clickwheel delete` — delete a playlist (with confirmation)
- `clickwheel diff` — preview iPod sync changes (panel + colored tables)
- `clickwheel sync` — push playlist to iPod (Rich Live table, confirmation)
- `clickwheel ls` — show iPod contents
- `clickwheel eject` — safely unmount iPod
- `clickwheel scrobble` — submit iPod listens to Last.fm (`--auth` for first-time setup)

## Development

Dev tooling uses [uv](https://docs.astral.sh/uv/) (env + dependency management;
`uv.lock` is committed, tools run via `uv run`). uv is **dev-only** — end users
still install the published package with `pipx`.

```bash
make dev        # uv sync (dev + mcp extras) + install pre-commit hooks
make test       # run tests with coverage
make lint       # ruff check + format check
make typecheck  # mypy
make format     # auto-format code
```

## Critical Rules

1. **All CLI output goes through `output.py`** — never call `console.print()` directly. A pre-commit pygrep hook enforces this. Use the semantic helpers: `error()`, `warn()`, `success()`, `info()`, `status()`, `dim()`, `confirm()`, `spinner()`.

2. **Never move or rename source files** — Plex reads from the same music library. Metadata changes are written in-place.

3. **The `scan` command is read-only** — it only reads metadata and writes to SQLite. No file modifications.

4. **FLAC is excluded from the iPod _sync_ path** — stock iPod firmware can't decode FLAC, so sync/select/add-to-ipod never copy FLAC directly. There is NO transparent/automatic transcoding in the sync path. The explicit `clickwheel convert` command (FLAC→MP3 into `transcode_dir`, outside `music_dir`) is the sanctioned way to get FLAC onto the iPod; it indexes its MP3 outputs so they then flow through the normal pipeline. See `docs/superpowers/specs/2026-06-14-flac-to-mp3-conversion-design.md`.

5. **`clickwheel/ipod/` is vendored code** — excluded from ruff linting. Don't refactor it unless fixing a bug in the iPod database writer.

6. **Interactive prompts use questionary** — not raw `typer.prompt()` or `input()`. Arrow-key selection with `questionary.select()` and `questionary.checkbox()`. Non-interactive flags (`--add`/`--remove`) are kept for scripting.

7. **Long operations use `spinner()` context manager** — iPod reads, Last.fm calls, eject. Never leave the user staring at a frozen terminal.

8. **Destructive operations require confirmation** — delete, sync. Use `typer.confirm()` with sensible defaults.

9. **`select`, `edit`, `diff`, `sync` auto-scan** the library via a two-tier strategy: cheap probe (stat music_dir + first-level dirs, ~5s on SMB) catches new artist/album folders; full incremental scan runs only when probe detects change OR the 24h fallback timer (default `auto_scan_staleness_minutes=1440`) expires. `--no-scan` skips both. The MCP server NEVER autoscans — chat tool calls always serve cached data. See `clickwheel/autoscan.py` for the detailed contract.

10. **`fix` runs a 3-step native pipeline** — repair albumartist → MusicBrainz art+year → Last.fm genres. All three steps are index-driven (no FS walks for known-clean state), cache positive _and_ negative outcomes in SQLite (`mb_matches`, `genre_matches`), and skip albums the index already says are complete. Re-runs on an unchanged library do zero network work. No external dependencies beyond the base install — beets was removed in favor of native `pylast`-driven genre lookups. CLI flags `--refresh-mb` / `--refresh-genres` invalidate the respective cache.

11. **MCP tools wrap `actions.py`, never `cli.py`** — CLI commands are display adapters, MCP tools are RPC adapters. Both consume the same pure functions. New library/iPod features should land in `actions.py` first, then get a thin wrapper in each surface.

12. **MCP destructive tools are gated by the client, not the server** — mutation tools (`delete_playlist`, `sync_playlist_to_ipod`, the `add_*`/`remove_*` family, etc.) carry the `destructiveHint=true` annotation (the `DESTRUCTIVE` preset in `_runtime.py`); compliant clients (Claude Code, Claude Desktop, claude.ai) surface a native Allow/Deny prompt before invoking. The server does **not** call `Context.elicit()` and there is no `confirm` parameter — gating lives entirely in the annotation plus the `instructions` block, which tells the model to summarize the impact (track count, target, names) in chat before calling. Keep the `destructiveHint` annotation on every mutating tool; that flag _is_ the confirmation contract. (`ctx: Context` is used only for `report_progress`.)

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

- pytest with coverage threshold (60% minimum, excluding vendored ipod/)
- Coverage runs in CI and uploads to Codecov
- Test matrix: Python 3.11-3.14 on Ubuntu and macOS
