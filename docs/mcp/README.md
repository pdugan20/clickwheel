# MCP server

clickwheel ships an optional MCP (Model Context Protocol) server so AI clients like Claude Code or Claude Desktop can read and modify your library conversationally — "what artists are on my iPod?", "add Big Thief to the ipod playlist", "sync the playlist".

This page covers per-client install/config, the full tool reference, and behavior notes. For the high-level pitch and one-liner install, see the [main README](../../README.md#mcp-server).

## Install

```bash
pipx inject clickwheel 'clickwheel[mcp]'
```

That puts the `clickwheel-mcp` binary in `~/.local/bin/` (with `pipx`) or your active venv's `bin/` (with `pip`).

## Client configuration

### Claude Code

```bash
claude mcp add clickwheel clickwheel-mcp --scope user
```

Or add to a project's `.mcp.json`:

```json
{ "mcpServers": { "clickwheel": { "command": "clickwheel-mcp" } } }
```

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "clickwheel": {
      "command": "/Users/YOU/.local/bin/clickwheel-mcp"
    }
  }
}
```

Use the absolute path `pipx` printed during install — Desktop doesn't always inherit your shell's `PATH`. Quit (⌘Q) and relaunch Desktop after editing.

### Other clients (Cursor, Continue, Cline, Zed, etc.)

Any MCP-aware client works — point it at the `clickwheel-mcp` binary as a stdio server. Most clients use a similar JSON config schema.

## Usage

Once configured, drive it conversationally:

> Build me a 45-minute late-night indie folk playlist using only tracks I actually own.
>
> What's on my iPod, and how full is it?
>
> Sync the 'ipod' playlist to my iPod and then eject it.

The server includes a built-in `build_playlist` prompt that walks the model through a vibe-based playlist build with anti-hallucination rules (never invent track names; only assert what tools return). Claude Code surfaces it in the slash-command picker; Claude Desktop currently doesn't expose stdio prompts in its UI, so use natural language.

## Tool reference

25 tools + 1 prompt, grouped by domain.

### Library (read)

| Tool                    | What it does                                                                          |
| ----------------------- | ------------------------------------------------------------------------------------- |
| `library_stats`         | Track/artist/album counts, total size, format breakdown                               |
| `library_health`        | Setup probe — does the music dir exist, when was the last scan, how many missing refs |
| `list_artists`          | All artists alphabetically with track/album counts                                    |
| `list_albums_by_artist` | Albums for one artist, ordered by year                                                |
| `list_tracks_by_album`  | Tracks on one album, ordered by disc/track number                                     |
| `search_tracks`         | Substring search across artist, album, title                                          |

### Playlist (read + mutation)

| Tool                          | What it does                                                          |
| ----------------------------- | --------------------------------------------------------------------- |
| `list_playlists`              | All saved playlists with track counts and total size                  |
| `get_playlist`                | One playlist's summary (use `list_playlist_tracks` for the full list) |
| `list_playlist_tracks`        | Paginated tracks in a playlist, in order                              |
| `create_playlist`             | New playlist from a list of track paths                               |
| `update_playlist`             | Replace a playlist's contents wholesale                               |
| `add_artist_to_playlist`      | Add every track by an artist (skips duplicates)                       |
| `remove_artist_from_playlist` | Remove every track by an artist                                       |
| `heal_playlist`               | Drop references to tracks no longer on disk                           |
| `delete_playlist`             | Permanently delete a playlist (destructive)                           |

### iPod (read + mutation)

| Tool                      | What it does                                                                            |
| ------------------------- | --------------------------------------------------------------------------------------- |
| `get_ipod_contents`       | iPod summary — capacity, used/free space, top artists                                   |
| `list_ipod_tracks`        | Paginated track list, optionally filtered by artist                                     |
| `list_ipod_playlists`     | iPod-side playlists (the ones visible under Music → Playlists on the device)            |
| `sync_playlist_to_ipod`   | Push a saved playlist to the iPod (destructive, additive). Handles same-name conflicts. |
| `add_tracks_to_ipod`      | Push specific tracks to the iPod library without creating a playlist (destructive)      |
| `add_artist_to_ipod`      | Push every track by an artist to the iPod library (destructive)                         |
| `remove_tracks_from_ipod` | Drop specific tracks from the iPod (destructive; tracks stay in the library)            |
| `remove_artist_from_ipod` | Drop every track by an artist from the iPod (destructive; tracks stay in the library)   |
| `remove_ipod_playlist`    | Delete a playlist artifact from the iPod without touching its tracks (destructive)      |
| `eject_ipod`              | Safely unmount via `diskutil eject`                                                     |

### Last.fm scrobbling

| Tool                    | What it does                                  |
| ----------------------- | --------------------------------------------- |
| `get_pending_scrobbles` | Cached iPod plays not yet sent to Last.fm     |
| `submit_scrobbles`      | Pull recent plays and submit (`dry_run` flag) |

## Destructive-tool gating

Seven tools carry the MCP `destructiveHint=true` annotation: `delete_playlist`, `sync_playlist_to_ipod`, `add_tracks_to_ipod`, `add_artist_to_ipod`, `remove_tracks_from_ipod`, `remove_artist_from_ipod`, `remove_ipod_playlist`. Different clients honor the flag differently:

- **Claude Code** shows a per-call Allow/Deny prompt before each invocation.
- **Claude Desktop** asks once when the tool is first used in a conversation, then runs freely thereafter.
- The server-side `instructions` block tells the model to summarize the impact in chat before invoking any destructive tool, so users get a chance to back out regardless of the client's gating model.

`sync_playlist_to_ipod` and the `add_*` tools are additive — tracks already on the iPod that aren't in the playlist/request stay where they are. They never silently delete from the iPod. The explicit `remove_*` tools are the only way to drop tracks.

## Behavior notes

- **Logging** goes to stderr (stdout is reserved for the MCP wire protocol). Set `CLICKWHEEL_MCP_LOG_LEVEL=DEBUG` for verbose output.
- **No auto-scan.** Chat tool calls always serve cached data. Run `clickwheel scan` from the terminal when you've added music; the next chat session sees it.
- **FLAC tracks are excluded** from sync (stock iPod firmware doesn't play FLAC).

## Inline UI bundles (MCP Apps)

Clickwheel ships an MCP Apps extension that lets compatible hosts (Claude Desktop, Claude.ai, VS Code Copilot, Goose) render an interactive iframe inline beneath certain tool results.

| Tool                                                                                                                                              | Bundle           | What it shows                                                                                                                                                                                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `get_ipod_contents`                                                                                                                               | iPod capacity    | Used/free bar segmented by top artists (8 named + "Other"), inline pill legend capped at 4 + "Other"; click a pill to ask a follow-up                                                                                      |
| `library_stats`                                                                                                                                   | Library overview | Track / artist / album counts + hours inline next to the title, mono-blue stacked format bar with single-line hover tooltips                                                                                               |
| `sync_playlist_to_ipod`, `add_tracks_to_ipod`, `add_artist_to_ipod`, `remove_tracks_from_ipod`, `remove_artist_from_ipod`, `remove_ipod_playlist` | Sync result      | Live progress while the tool runs (polls `state://clickwheel/sync-progress` for the static "X MB · N albums" subtitle + counter), switches to a completion card with `Ready to eject` / `Library not fully updated` / etc. |

`library_health` is text-only now — no bundle, returns a structured payload + summary that hosts render however they like.

Hosts without MCP Apps support fall back to the same text + structured-content payload the Python tools have always returned — nothing breaks, the iframe just doesn't appear.

The bundles live under [`web/`](../../web/) (React 19 + Vite). They're built into a single inlined HTML each via `vite-plugin-singlefile`, then concatenated into [`clickwheel/mcp/_ui_bundles.py`](../../clickwheel/mcp/_ui_bundles.py) by `web/scripts/inline_bundles.mjs`. That generated module is checked in so `pip install clickwheel[mcp]` works without a Node toolchain.

### Editing a bundle

```bash
make dev-web        # http://localhost:5174/workbench/ — live preview with fixtures
# edit web/<bundle>.tsx, components/, lib/...
make build-web      # rebuild bundles + regenerate the Python module
make lint-web       # eslint + tsc
```

CI rebuilds the bundles and fails if the checked-in `_ui_bundles.py` drifts from `web/` — so don't forget `make build-web` before committing.

### Adding a new bundle

1. Drop `web/<name>.html`, `web/<name>.tsx`, `web/<name>.fixtures.ts`. Use an existing bundle as a template.
2. Register it in `web/workbench/registry.ts` so the workbench sidebar lists it.
3. Run `make build-web`.
4. In `clickwheel/mcp/ui_resources.py`, add a `register_ui_resource(...)` call pointing at the new bundle's `*_HTML` constant.
5. In the matching tool, add `meta=ui_tool_meta(URI)` to the `@mcp.tool` decorator.
6. Test with `npm run dev` (workbench) and a real Claude Desktop call.

## Dev install (clone-based)

If you're hacking on clickwheel from a clone in `~/Documents/`, Claude Desktop's sandbox will refuse to read the in-tree venv's `pyvenv.cfg` (macOS applies a `com.apple.provenance` xattr to files in `Documents`). Either:

- Install with `pipx install --editable .` so the venv lives in `~/.local/pipx/`, or
- Grant Claude Desktop access to your Documents folder under System Settings → Privacy & Security → Files & Folders.

Claude Code is unaffected.

## Internal docs

- [`test-plan.md`](test-plan.md) — manual iPod test runbook plus the findings log from Phase 5 (sync merge bug, autoscan rework, dual-emit fix, Round 6 Desktop quirks). Reusable for future regression testing.

For high-level architecture, see [`docs/architecture.md`](../architecture.md).
