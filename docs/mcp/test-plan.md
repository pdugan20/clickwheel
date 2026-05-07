# MCP manual test plan

End-to-end manual tests run from a chat client (Claude Code primarily; Claude Desktop as a secondary pass) against the user's real iPod and library. Walk this top-to-bottom in Phase 5; record findings under "Findings" at the bottom.

The MCP surface today is **18 tools + 1 prompt**:

- Read (10): `library_stats`, `library_health`, `list_artists`, `list_albums_by_artist`, `list_tracks_by_album`, `search_tracks`, `list_playlists`, `get_playlist`, `get_ipod_contents`, `get_pending_scrobbles`
- Mutation (8): `create_playlist`, `update_playlist`, `delete_playlist`, `add_artist_to_playlist`, `remove_artist_from_playlist`, `submit_scrobbles`, `sync_playlist_to_ipod`, `eject_ipod`
- Prompt (1): `build_playlist`

## 0. Setup

- [ ] `pip install -e '.[mcp]'` (dev) **or** `pipx inject clickwheel 'clickwheel[mcp]'` (installed) succeeds
- [ ] `clickwheel-mcp` (or `python -m clickwheel.mcp`) starts without errors
- [ ] `claude mcp add --scope user clickwheel <abs path or 'clickwheel-mcp'>` registers the server
- [ ] `claude mcp list` shows `clickwheel: ... ✓ Connected`
- [ ] In a fresh Claude Code session: ask "what tools does the clickwheel MCP expose?" — all 18 tools + the `build_playlist` prompt appear

## 1. Read-only tools

### Library inspection

- [ ] "What's in my library?" → `library_stats` returns track/artist/album counts; **text summary** reads naturally (e.g. "Library: 12,049 tracks, 734 artists, 803 albums (88.9 GB, 759 hours)")
- [ ] "Show me my artists" → `list_artists` returns alphabetical list
- [ ] "Cap at 50" → `list_artists(limit=50)` honors the limit; text says "(truncated from 734)"
- [ ] "What albums do I have by Big Thief?" → `list_albums_by_artist` returns the discography with year span in the text
- [ ] "What's on the album Two Hands?" → `list_tracks_by_album` returns ordered tracks; text shows total runtime
- [ ] "Search for tracks with 'love'" → `search_tracks` returns matches
- [ ] **Negative result test**: search for a guaranteed-no-match query like "zzzqqq" → tool returns `[]` AND text says "No tracks match …"
- [ ] **Case-sensitivity guard**: ask for albums by an artist with the wrong capitalization → tool returns `[]` AND text says "Names are case-sensitive — use search_tracks for a fuzzy match"

### Playlist inspection

- [ ] "List my saved playlists" → `list_playlists` matches `clickwheel playlist` output
- [ ] "Show me what's in the 'ipod' playlist" → `get_playlist` returns track list, artist breakdown, total size
- [ ] "Which artists are in 'ipod'?" → derived from `get_playlist.artists`
- [ ] **Empty case**: ask about a playlist that doesn't exist → `PlaylistNotFoundError` surfaced clearly

### iPod inspection (iPod mounted)

- [ ] "What's on my iPod right now?" → `get_ipod_contents` returns the existing content correctly
- [ ] "How full is the iPod?" → capacity / used / free in the text summary
- [ ] **Disconnected case**: unplug the iPod, repeat → `IpodNotFoundError` with clear message

### Scrobble inspection

- [ ] "Any pending scrobbles?" → `get_pending_scrobbles` returns cached plays (or empty + helpful text)
- [ ] iPod disconnected and scrobble cache empty → empty list, no error

### Library health

- [ ] "Is my clickwheel library OK?" → `library_health` reports `library_dir_exists`, `total_tracks`, `missing_tracks`, last scan age
- [ ] **Stale library**: rename the music directory, ask again → text flags "music_dir … doesn't exist"

## 2. Mutation tools

### Playlist mutations (no iPod required)

- [ ] "Create a playlist called 'test-mcp' with all tracks by [artist X]" → Claude likely chains `list_albums_by_artist` → `list_tracks_by_album` → `create_playlist`. End state: new playlist exists.
- [ ] **Duplicate guard**: re-run same create → `PlaylistAlreadyExistsError`; LLM offers `update_playlist`
- [ ] "Replace 'test-mcp' with [artist Y]'s catalog" → `update_playlist`, `replaced: true`
- [ ] "Add [artist Z] to 'test-mcp'" → `add_artist_to_playlist`, count > 0
- [ ] "Remove [artist Y] from 'test-mcp'" → `remove_artist_from_playlist`, count > 0
- [ ] "Delete 'test-mcp'" — Claude triggers elicitation. Decline once → playlist still exists. Accept → playlist gone, `list_playlists` confirms.

### Scrobble submission

- [ ] Pending scrobbles present, Last.fm configured → `submit_scrobbles` submits; **`next_step_hint` field** in the result tells Claude to offer `eject_ipod`
- [ ] `dry_run=true` → preview counts only, nothing submitted
- [ ] Last.fm NOT configured → `LastfmNotConfiguredError` pointing to `clickwheel scrobble --auth`

### Sync (the scary one — iPod connected)

- [ ] Pre-flight: `clickwheel ls` and `get_ipod_contents` report identical contents (sanity check)
- [ ] "Sync 'ipod' to my iPod" → Claude calls `sync_playlist_to_ipod(playlist='ipod')`, server elicits confirmation showing "+N tracks (X MB), N tracks won't be removed"
- [ ] **Decline path**: decline the elicitation → `synced: false, reason: "user declined"`; iPod state unchanged
- [ ] **Accept path**: accept → tool runs; result includes `next_step_hint` ≈ "Offer to call eject_ipod"
- [ ] Existing iPod tracks NOT in the playlist are preserved (additive semantics — sanity check after the sync)
- [ ] After sync, `get_ipod_contents` reflects the new state; `clickwheel ls` matches
- [ ] **Disconnected case**: pull the iPod cable, retry → clear `IpodNotFoundError`, no partial state
- [ ] **Already-in-sync case**: re-run sync immediately → "iPod already matches 'ipod' — nothing to do"

### Eject

- [ ] After a successful sync, Claude proactively offers `eject_ipod` (driven by the `next_step_hint`)
- [ ] "Yes, eject" → `eject_ipod` succeeds; iPod is unmounted; `get_ipod_contents` would now error
- [ ] **Already-ejected case**: re-run `eject_ipod` → `IpodNotFoundError` (the gentle "no iPod mounted" message)

## 3. Build-playlist prompt

This is a slash-command in the client (`/build_playlist` in Claude Code; available in the Desktop prompt menu).

- [ ] Prompt is discoverable in the client's slash-command picker
- [ ] Invoking with `vibe="late-night jazz"`, `target_minutes=45`, `name="quiet"` seeds the conversation with the templated body
- [ ] Claude follows the steps: starts with `library_stats`, runs multiple `search_tracks`, drills in with `list_albums_by_artist`/`list_tracks_by_album`, ends with `create_playlist`
- [ ] **Anti-hallucination check**: Claude does NOT invent any track titles. Every track in the final playlist appears in a tool result earlier in the chat.
- [ ] Final output renders tracks as `Artist — Title (Album)` (per server `instructions`), never as raw paths
- [ ] Claude offers `sync_playlist_to_ipod` as the natural next step

## 4. Cross-cutting

- [ ] Server logs to stderr only — `~/.clickwheel/clickwheel-mcp.log` (if you redirect) or `claude mcp inspect clickwheel` shows clean output, no MCP protocol stream corruption
- [ ] Tools handle a missing config file gracefully (clear error, not stack trace) — to test, temporarily rename `~/.clickwheel/config.yaml`
- [ ] Tools handle an empty DB gracefully (fresh install, never scanned) — `library_stats` returns "Library is empty — run `clickwheel scan`"
- [ ] Concurrent CLI use (`clickwheel scan` running while a chat session is calling MCP tools) doesn't deadlock SQLite (WAL mode should make this fine but worth verifying once)
- [ ] Killing Claude Code mid-tool-call doesn't leave the DB in a corrupt state

## 5. Claude Desktop pass (Mac)

The same `clickwheel-mcp` binary runs in Claude Desktop. Register by editing
`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "clickwheel": {
      "command": "/Users/patrickdugan/Documents/Github/clickwheel/.venv/bin/clickwheel-mcp"
    }
  }
}
```

Quit and relaunch Claude Desktop. Then a smaller pass to confirm UX:

- [ ] Tools and the `build_playlist` prompt show up in the Desktop UI
- [ ] Read tools work (`library_stats`, `list_playlists`)
- [ ] Tool descriptions render in Desktop's tool inspector
- [ ] Text summaries (the bit we built in 4.5c) display naturally in Desktop's tool-result UI rather than just JSON
- [ ] Elicitation prompts surface as a Desktop dialog (not a bare API error) for `delete_playlist` and `sync_playlist_to_ipod`
- [ ] One end-to-end sync from Desktop → eject

Desktop and Claude Code share the protocol, so failures here usually mean a UX issue, not a server bug. Note any rendering quirks for follow-up.

## 6. Tool annotations

These don't have user-visible behavior yet, but worth confirming the metadata is correct so future client UI features (auto-approval lists, "destructive action" badges) work.

- [ ] `claude mcp inspect clickwheel` (or equivalent) shows annotations
- [ ] Read tools: `readOnlyHint=true`
- [ ] `delete_playlist` and `sync_playlist_to_ipod`: `destructiveHint=true`
- [ ] `submit_scrobbles`: `openWorldHint=true`
- [ ] `create_playlist`: `idempotentHint=false`

## Findings

(Populate during the run. Format: `<scenario>` — `<observed>` — `<follow-up>`.)
