# MCP project tracker

Live tracker for the MCP integration. Update statuses as we go. See `design.md` for the locked design and `research.md` for SDK/spec findings.

**Status legend:** ☐ pending · ◐ in progress · ☒ done · ⊘ skipped/deferred

## Phase 0 — Research and design

- ☒ Web research on Python MCP SDK status (`mcp` vs `fastmcp`)
- ☒ Web research on MCP spec features (elicitation, structured output, resources)
- ☒ Web research on Claude Code `.mcp.json` scope precedence
- ☒ Web research on tool naming/description conventions
- ☒ Write `docs/mcp/research.md`
- ☒ Write `docs/mcp/design.md`
- ☒ Write `docs/mcp/tracker.md` (this file)
- ☒ Write `docs/mcp/test-plan.md`
- ☒ **User reviews `design.md`, gives go-ahead** (approved 2026-05-06)

## Phase 1 — `actions.py` refactor (ships standalone, `refactor:` commit)

- ☒ Create `clickwheel/actions.py` skeleton with the function signatures from `design.md`
- ☒ Move `scan_library` logic out of `cli.py:scan` — replace tqdm with `on_progress` callback. CLI command becomes thin wrapper that adapts the callback to tqdm.
- ☒ Move `compute_diff` logic out of `cli.py:diff` — return structured `Diff`; CLI adapts to Rich tables.
- ☒ Move `sync_playlist` logic out of `cli.py:sync` — return `SyncResult`; CLI adapts to Live table via `on_event` callback.
- ☒ Move pure read helpers (`library_stats`, `list_playlist_artists`, `read_ipod_contents`, `read_pending_scrobbles`) to `actions.py`.
- ☒ Move `submit_pending_scrobbles` orchestration out of `cli.py:scrobble`.
- ☒ Consolidate `autoscan.incremental_scan` into `actions.scan_library` — autoscan now decides _whether_ to scan, actions does the actual work.
- ☒ Run full test suite — 92 passed, 41.6% coverage.
- ☒ Manual smoke: `clickwheel scan --stats` and `clickwheel playlist` behave identically against real library.
- ☒ Conventional commit: `refactor: extract action logic from cli.py into actions.py` (commit `741cdb0`).

## Phase 2 — Read-only MCP server (`feat:` commit)

- ☒ Add `[mcp]` extra to `pyproject.toml` (`mcp>=1.2`)
- ☒ Add `[project.scripts]` entry: `clickwheel-mcp = "clickwheel.mcp:main"`
- ☒ Create `clickwheel/mcp/__init__.py` exporting `main`
- ☒ Create `clickwheel/mcp/__main__.py` so `python -m clickwheel.mcp` works
- ☒ Create `clickwheel/mcp/server.py` — FastMCP instance, per-call DB lifecycle, stderr-only logging, env-driven log level (`CLICKWHEEL_MCP_LOG_LEVEL`)
- ☒ Implement the 10 read tools inline in `server.py` (kept as one file for now; split if it grows past ~500 lines)
- ☒ Each tool: type hints + docstring (FastMCP picks up the schema), wraps an `actions.py` call, returns structured dict/list
- ☒ Add `library_health` and `search_tracks` to `actions.py` (newly required by MCP surface)
- ☒ Wire autoscan into library-data tools via `_open_session(autoscan=True)` — `IPod`/scrobble tools opt out
- ☒ Add `tests/test_mcp_server.py` — 14 direct unit tests of tool functions
- ☒ Add `tests/test_mcp_smoke.py` — spawns `python -m clickwheel.mcp` over stdio, runs a real `initialize` + `tools/list` round trip
- ☒ Lint passes; tests pass — 107 passing, 45.5% coverage
- ☐ Manual: register with Claude Code via `claude mcp add` (verify the 2.1.122 user-scope bug status; fall back to project scope or hand-edit if needed), invoke from a chat session
- ☒ Conventional commit: `feat: add read-only mcp server` (commit `74ba924`).

## Phase 3 — Mutation tools (`feat:` commit)

- ☒ Add the 7 mutation tools to `mcp/server.py` (kept inline; split if file grows past ~500 lines): `create_playlist`, `update_playlist`, `delete_playlist`, `add_artist_to_playlist`, `remove_artist_from_playlist`, `submit_scrobbles`, `sync_playlist_to_ipod`
- ☒ Add `playlist_exists`, `create_playlist`, `update_playlist`, `PlaylistAlreadyExistsError` to `actions.py`
- ☒ Implement elicitation pattern for `delete_playlist` and `sync_playlist_to_ipod` — server requests yes/no confirmation when `confirm=False` via `Context.elicit()`
- ☒ Tests for each mutation tool (12 new cases, including elicitation accept/decline paths via a fake Context)
- ☒ Live protocol smoke: 17 tools register and respond to `tools/list`
- ☐ Manual: invoke each mutation tool from a chat session against the real library (but not the iPod yet)
- ☐ Conventional commit: `feat: add mcp mutation tools` (minor bump)

## Phase 4 — Docs and packaging

- ☒ Add `## MCP server` section to `README.md`: install, register with Claude Code, tool table with read/mutation grouping, link to `docs/mcp/`
- ☒ Update `CLAUDE.md`: `actions.py` and `clickwheel/mcp/` in project layout, three new Critical Rules (MCP tools wrap actions, destructive tools elicit, stderr logging only)
- ☒ `pyproject.toml` description unchanged — MCP is an add-on, not the headline feature
- ☐ Conventional commit: `docs: document mcp server install and usage`

## Phase 5 — Manual iPod testing

- ☐ Walk `docs/mcp/test-plan.md` against the real iPod
- ☐ Capture findings, file follow-ups as new tracker rows or issues
- ☐ Decide on release: tag and let release-please publish, or sit on it for a week

## Post-ship follow-ups (parking lot)

- ☐ Resources (`clickwheel://artists/<name>`, `clickwheel://playlists/<name>`)
- ☐ Server-defined prompts ("build me a playlist of X")
- ☐ Reconsider whether `scan` should be an explicit tool
- ☐ HTTP transport if ever needed for remote/Desktop integration
