# MCP manual test plan

End-to-end manual test scenarios run against the user's real iPod (which already has content on it). Run this in Phase 5 after Phase 4 is shipped.

Update this list before testing — Pat to mark up missing scenarios or unrealistic assumptions.

## Setup

- [ ] `pipx inject clickwheel 'clickwheel[mcp]'` succeeds
- [ ] `clickwheel-mcp --help` (or equivalent) confirms binary on PATH
- [ ] Register with Claude Code via `claude mcp add` (use whichever scope works — see research.md re: 2.1.122 bug)
- [ ] In a fresh Claude Code session, ask "what tools does the clickwheel MCP expose?" — all 10 (or 17 in Phase 3) tools appear

## Read-only scenarios (Phase 2)

### Library inspection

- [ ] "What's in my library?" → `library_stats` returns track count and format breakdown
- [ ] "Show me my top 20 artists by track count" → `list_artists` returns sorted list
- [ ] "What albums do I have by [artist]?" → `list_albums_by_artist`
- [ ] "Search for tracks with 'love' in the title" → `search_tracks`
- [ ] "Are there any missing files in my library?" → `library_health` reports `missing_tracks`

### Playlist inspection

- [ ] "List my saved playlists" → `list_playlists` matches output of `clickwheel playlist`
- [ ] "What's in my [playlist name] playlist?" → `get_playlist` returns full track list
- [ ] "Which artists are in [playlist]?" → derived from `get_playlist`

### iPod inspection (requires iPod mounted)

- [ ] iPod connected → "What's on my iPod right now?" → `get_ipod_contents` returns existing content correctly
- [ ] iPod connected → "How full is the iPod?" → capacity/used reflected accurately
- [ ] iPod disconnected → tool returns clear error ("iPod not mounted") rather than crashing

### Scrobble inspection

- [ ] "Any pending scrobbles?" → `get_pending_scrobbles` returns cached plays
- [ ] No pending scrobbles → returns empty list, no error

### Autoscan

- [ ] After modifying a file in the library, a tool call triggers autoscan (configurable via `auto_scan_staleness_minutes`)
- [ ] `--no-scan` equivalent: tool calls don't autoscan if config disables it (or env var override)

## Mutation scenarios (Phase 3)

### Playlist mutations

- [ ] "Create a playlist called 'test-mcp' with all tracks by [artist]" → `create_playlist` succeeds
- [ ] Re-running same create → returns clear error suggesting `update_playlist`
- [ ] "Add [artist 2] to test-mcp" → `add_artist_to_playlist` returns correct add count
- [ ] "Remove [artist] from test-mcp" → `remove_artist_from_playlist` returns correct remove count
- [ ] "Delete test-mcp" without confirmation → server elicits confirmation, LLM relays to user
- [ ] User declines confirmation → tool returns `{deleted: false, reason: "user declined"}`, no DB change
- [ ] User accepts → playlist is deleted; `list_playlists` no longer shows it

### Scrobble submission

- [ ] Pending scrobbles present, Last.fm configured → `submit_scrobbles` submits, count matches what was pending
- [ ] Pending scrobbles, Last.fm NOT configured → clear error pointing to `clickwheel scrobble --auth`
- [ ] `dry_run=true` → no submission, count of what _would_ submit returned

### Sync (the scary one)

- [ ] iPod connected, target playlist exists → `sync_playlist_to_ipod` elicits confirmation, then runs
- [ ] Diff is shown to user before sync (via elicitation payload or LLM-formatted summary)
- [ ] Existing iPod content is preserved correctly (i.e. tracks not in target playlist that were already on iPod — confirm sync semantics match `clickwheel sync`)
- [ ] iPod disconnected → clear error, no partial state
- [ ] After sync, `get_ipod_contents` reflects new state
- [ ] `clickwheel ls` (CLI) and `get_ipod_contents` (MCP) report identical contents post-sync — sanity check that we didn't fork the read paths

## Cross-cutting

- [ ] All tools handle a missing config file gracefully (clear error, not stack trace)
- [ ] All tools handle an empty DB (fresh install, never scanned) gracefully
- [ ] Server logs to stderr, never stdout (would corrupt MCP protocol stream)
- [ ] Killing Claude Code mid-tool-call doesn't leave the DB in a corrupt state
- [ ] Concurrent CLI use (`clickwheel scan` running while MCP server is also up) doesn't deadlock SQLite

## Findings

(Populate during Phase 5.)
