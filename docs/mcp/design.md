# MCP server design

Locked design for the clickwheel MCP server. Source of truth for what the surface looks like; tracker tracks the _progress_ of building it.

## Package layout

- New module: `clickwheel/mcp/` (subpackage)
  - `__init__.py` — exports `main`
  - `server.py` — FastMCP instance + tool definitions
  - `tools_read.py` — read-only tool implementations (Phase 2)
  - `tools_write.py` — mutation tool implementations (Phase 3)
- Console script: `clickwheel-mcp` → `clickwheel.mcp:main`
- Optional dep group in `pyproject.toml`:

  ```toml
  [project.optional-dependencies]
  mcp = ["mcp>=1.2"]
  ```

  Install path: `pipx inject clickwheel 'clickwheel[mcp]'` (matches existing `[fix]` pattern in README).

Why a subpackage and not a separate PyPI project: shared imports with `clickwheel.actions`, `clickwheel.db`, `clickwheel.config`. A separate package would either duplicate those or take a hard dep on `clickwheel`, defeating the point of separation.

## Refactor prerequisite (Phase 1)

Before MCP code lands, extract pure logic from `cli.py` into `clickwheel/actions.py`. Both CLI and MCP consume from there. Without this, MCP would either re-implement scan/sync/edit logic or import from `cli.py`, neither of which is sustainable.

Functions to extract (initial cut — refine in Phase 1):

| Action                                                                            | Source in cli.py         | Notes                                                     |
| --------------------------------------------------------------------------------- | ------------------------ | --------------------------------------------------------- |
| `scan_library(cfg, *, full=False, on_found=None, on_progress=None) -> ScanResult` | `cli.py:61`              | tqdm callback becomes injected `on_progress`.             |
| `library_stats(cfg) -> Stats`                                                     | `cli.py:75`              | Already mostly delegates to `db.get_stats`.               |
| `list_playlist_artists(cfg, name) -> list[dict]`                                  | inside `edit`/`playlist` | Pure DB read.                                             |
| `add_artist_to_playlist(cfg, playlist, artist) -> int`                            | `cli.py:1029`            | Already a `db` method; CLI wrapper handles confirmations. |
| `compute_diff(cfg, playlist) -> Diff`                                             | `cli.py:493`             | Decouple from Rich rendering.                             |
| `sync_playlist(cfg, playlist, *, on_event=None) -> SyncResult`                    | `cli.py:561`             | Live table becomes injected `on_event` callback.          |
| `read_ipod_contents(cfg) -> list[dict]`                                           | `cli.py:709`             | Wraps `_get_ipod_track_list`.                             |
| `read_pending_scrobbles(cfg) -> list[dict]`                                       | inside `scrobble`        | Pure DB read.                                             |
| `submit_pending_scrobbles(cfg, *, batch_size=50) -> SubmitResult`                 | inside `scrobble`        | Already largely in `scrobble.py`.                         |

CLI commands become: parse args → call action → render result. MCP tools become: validate input → call action → return dict.

## Tool surface — Phase 2 (read-only)

Naming: `verb_noun`, `snake_case`. Cluster by prefix where it helps (e.g. `playlist_get`, `playlist_create`, `ipod_contents`, `ipod_sync`).

| Tool                    | Args                          | Returns                                                                         | Description                                          |
| ----------------------- | ----------------------------- | ------------------------------------------------------------------------------- | ---------------------------------------------------- |
| `library_stats`         | —                             | `{total_tracks, total_size_bytes, formats: [{format, count}]}`                  | High-level library stats.                            |
| `list_artists`          | `limit: int = 500`            | `[{artist, track_count, album_count}]`                                          | All indexed artists.                                 |
| `list_albums_by_artist` | `artist: str`                 | `[{album, track_count, year}]`                                                  | Albums for one artist.                               |
| `list_tracks_by_album`  | `artist: str, album: str`     | `[{title, track_number, duration_ms, path}]`                                    | Tracks on one album.                                 |
| `search_tracks`         | `query: str, limit: int = 50` | `[{artist, album, title, path}]`                                                | Substring search across artist/album/title.          |
| `list_playlists`        | —                             | `[{name, track_count, size_bytes}]`                                             | All saved playlists.                                 |
| `get_playlist`          | `name: str`                   | `{name, tracks: [...], artists: [...], size_bytes}`                             | One playlist's contents.                             |
| `get_ipod_contents`     | —                             | `{model, capacity_bytes, used_bytes, tracks: [...]}`                            | What's currently on the iPod. Requires iPod mounted. |
| `get_pending_scrobbles` | —                             | `[{artist, album, title, played_at}]`                                           | Cached scrobbles not yet submitted.                  |
| `library_health`        | —                             | `{missing_tracks: int, last_scan_at, scan_errors_last_run, library_dir_exists}` | Quick "is everything wired up" probe.                |

Total: 10 tools.

## Tool surface — Phase 3 (mutation)

| Tool                          | Args                                   | Returns                                         | Notes                                                                    |
| ----------------------------- | -------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------ |
| `create_playlist`             | `name: str, track_paths: list[str]`    | `{name, track_count}`                           | Errors if name exists; suggest `update_playlist`.                        |
| `update_playlist`             | `name: str, track_paths: list[str]`    | `{name, track_count, replaced: bool}`           | Replace contents.                                                        |
| `delete_playlist`             | `name: str, confirm: bool = False`     | `{deleted: bool}`                               | If `confirm` is false, server elicits confirmation via Elicitation.      |
| `add_artist_to_playlist`      | `playlist: str, artist: str`           | `{added: int}`                                  | Returns count of tracks added.                                           |
| `remove_artist_from_playlist` | `playlist: str, artist: str`           | `{removed: int}`                                | Returns count of tracks removed.                                         |
| `submit_scrobbles`            | `dry_run: bool = false`                | `{submitted: int, failed: int, remaining: int}` | Last.fm credentials must be configured.                                  |
| `sync_playlist_to_ipod`       | `playlist: str, confirm: bool = False` | `{added, removed, kept, errors}`                | Always elicits confirmation if `confirm` is false. iPod must be mounted. |

Total: 7 mutation tools. Combined surface: 17.

## Error model

- **User-facing errors** (config missing, iPod not mounted, playlist not found, Last.fm not configured) → raise `mcp.shared.exceptions.McpError` with `INVALID_PARAMS` and a clear message. The client surfaces it; the LLM gets a chance to ask the user.
- **Server-side errors** (DB corruption, unexpected exceptions) → propagate. Don't swallow.
- **Elicitation refusal** (user declines confirmation) → return `{deleted: false, reason: "user declined"}` rather than raising. Mutation tools should always be safe to "decline."

## Transport, lifecycle, state

- stdio. One process per Claude Code session.
- DB connection: open lazily on first tool call, hold open for the process lifetime, close on shutdown. Tracks autoscan: on every tool call that depends on library data, check `auto_scan_staleness_minutes` (existing config) and trigger a background scan if stale. Re-use `clickwheel.autoscan` so behavior matches the CLI.
- iPod state: re-read iTunesDB on every tool call that touches it. iPod state changes externally (user replugs); caching across calls is wrong.

## Logging

stderr only — stdio transport uses stdout for protocol frames. Log level configurable via `CLICKWHEEL_MCP_LOG_LEVEL` env var (default `WARNING`).

## Open questions for v1

- Do we expose `scan` as a tool, or only as an autoscan trigger? **Lean: autoscan only.** Explicit `scan` would tempt the LLM to invoke it constantly. Revisit if we hit cases where it's actually wanted.
- Do we ship a `prompt`? MCP supports server-defined prompts (templates). Could ship something like "build me a playlist" as a guided template. **Lean: no for v1.** Adds maintenance, low evidence of value yet.

## Out of scope for v1

- Resources (URI-addressable library entities). Revisit in v3 once tool surface is felt-out.
- HTTP/SSE transport.
- Multi-user / hosted deployment.
- Server-defined prompts.
