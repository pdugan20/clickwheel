# MCP manual test walkthrough

Round-by-round guide for verifying the clickwheel MCP server end-to-end. Tick items as you go; record anything surprising under [Findings](#findings) at the bottom.

**Surface under test:** 18 tools + 1 prompt.

- Read (10): `library_stats`, `library_health`, `list_artists`, `list_albums_by_artist`, `list_tracks_by_album`, `search_tracks`, `list_playlists`, `get_playlist`, `get_ipod_contents`, `get_pending_scrobbles`
- Mutation (8): `create_playlist`, `update_playlist`, `delete_playlist`, `add_artist_to_playlist`, `remove_artist_from_playlist`, `submit_scrobbles`, `sync_playlist_to_ipod`, `eject_ipod`
- Prompt (1): `build_playlist`

How to use this doc: each round is run from a **fresh Claude Code session** (or Claude Desktop in Round 6). Paste the literal prompts and check the expectation. Items marked **(needs iPod)** require the device plugged in; **(needs music share)** requires `/Volumes/Public/Multimedia/Music` mounted.

---

## Round 0 — Setup

- [ ] `pip install -e '.[mcp]'` (dev) **or** `pipx inject clickwheel 'clickwheel[mcp]'` succeeds
- [ ] `clickwheel-mcp` is on PATH or reachable at an absolute path
- [ ] `claude mcp add --scope user clickwheel <path-to-clickwheel-mcp>` returns "Added stdio MCP server"
- [ ] `claude mcp list` shows `clickwheel: ... ✓ Connected`
- [ ] In a fresh Claude Code session, "What tools does the clickwheel MCP expose?" lists all 20 tools and mentions the `build_playlist` prompt

## Round 1 — Read tools, no iPod, no mutation

Goal: confirm dual-content (text summary + structuredContent), negative-result text, anti-hallucination, and tool chaining all behave.

### 1.1 Tool discovery

Ask:

> What tools does the clickwheel MCP server expose?

- [ ] All 18 tools listed, grouped sensibly (library / playlist / iPod / scrobble)
- [ ] `build_playlist` prompt mentioned

### 1.2 Library overview — dual-content sanity

Ask:

> Give me a quick overview of my music library.

- [ ] Claude calls `library_stats`
- [ ] Reply paraphrases the **text summary** in natural language ("12,049 tracks, 734 artists, …") — NOT raw JSON

### 1.3 Library health — negative-result text

Ask:

> Is my clickwheel library OK?

- [ ] Claude calls `library_health`
- [ ] If music share is unmounted: reply explicitly says music_dir isn't reachable
- [ ] If everything's mounted and recently scanned: reply says it's healthy with last-scan age

### 1.4 Search — negative result + real result

Ask:

> Search my library for tracks with "asdfqwerty" in the title.

- [ ] Claude calls `search_tracks(query="asdfqwerty")` and reports zero matches
- [ ] Claude does NOT invent results

Then ask:

> What about tracks with "love" in the title?

- [ ] Real results returned with track count
- [ ] Tracks rendered as `Artist — Title (Album)`, NOT raw paths

### 1.5 Playlist inspection

Ask:

> What playlists do I have, and what's in the 'ipod' playlist?

- [ ] `list_playlists` returns 1 playlist
- [ ] `get_playlist(name="ipod")` returns the SUMMARY (track_count, size_bytes, artists breakdown). NOT the full track list.
- [ ] Claude paraphrases the artist breakdown ("Taylor Swift 276, Sabrina Carpenter 58, …")
- [ ] **Response stays well under the token cap** — no "result exceeds maximum allowed tokens" error, no jq fallback

Then drill in:

> Show me the first 10 tracks of the 'ipod' playlist.

- [ ] Claude calls `list_playlist_tracks(name="ipod", limit=10)`
- [ ] Returns 10 track records rendered as `Artist — Title (Album)`

### 1.6 Anti-hallucination probe

Ask:

> Tell me about the album "Definitely Not Real" by "Made Up Band".

- [ ] Claude calls `list_albums_by_artist(artist="Made Up Band")`
- [ ] Returns no albums; suggests `search_tracks` for fuzzy match
- [ ] Does NOT invent an album

## Round 2 — Mutation tools (no iPod required)

Goal: playlist CRUD + elicitation. Uses a throwaway playlist named `test-mcp` to avoid disturbing the existing `ipod` playlist.

### 2.1 Create

Ask:

> Create a clickwheel playlist called 'test-mcp' with three tracks by [pick a real artist from your library].

- [ ] Claude chains `list_albums_by_artist` → `list_tracks_by_album` → `create_playlist`
- [ ] Result: `{name: "test-mcp", track_count: 3}` (or similar)

### 2.2 Duplicate guard

Ask:

> Make a clickwheel playlist named 'test-mcp' with [different artist].

- [ ] `create_playlist` errors with `PlaylistAlreadyExistsError`
- [ ] Claude offers `update_playlist` as the next step

### 2.3 Add artist

Ask:

> Add [other artist] to the 'test-mcp' playlist.

- [ ] `add_artist_to_playlist` returns count > 0
- [ ] `get_playlist(name="test-mcp")` confirms the new tracks landed

### 2.4 Remove artist

Ask:

> Remove [first artist] from 'test-mcp'.

- [ ] `remove_artist_from_playlist` returns count > 0
- [ ] `get_playlist` confirms the removal

### 2.5 Delete — deny path (client-side gating)

`delete_playlist` is flagged `destructiveHint=true`. Claude Code shows its native Allow/Deny permission prompt before invoking — the server doesn't elicit anything. (Earlier revisions used MCP elicitation here, which created a confusing double-prompt; we removed it. See findings entry from May 2026.)

Ask:

> Delete the 'test-mcp' playlist.

- [ ] Claude summarizes the impact in its message ("This will delete 'test-mcp', N tracks, cannot be undone…") before invoking
- [ ] Claude Code surfaces an Allow / Deny prompt for the `delete_playlist` tool call
- [ ] **Deny**. Tool isn't called. Playlist still exists. (Verify with "list my playlists".)

### 2.6 Delete — allow path

Ask again:

> Actually go ahead and delete 'test-mcp'.

- [ ] Allow / Deny prompt reappears
- [ ] **Allow**. Tool runs. Result: `{deleted: true, name: "test-mcp"}`
- [ ] `list_playlists` no longer shows `test-mcp`

### 2.7 Scrobble dry-run **(needs iPod)**

Ask:

> Show me a dry-run of pending scrobbles, but don't submit anything yet.

- [ ] `submit_scrobbles(dry_run=true)` returns counts only
- [ ] iPod NOT plugged in: clear `IpodNotFoundError` (skip rest of 2.7)
- [ ] iPod plugged in, Last.fm not configured: `LastfmNotConfiguredError` pointing at `clickwheel scrobble --auth`

## Round 3 — iPod tests **(needs iPod plugged in)**

Goal: read iPod state, sync end-to-end, eject. Save these for when the iPod is connected; otherwise skip the round.

### 3.1 iPod inspection

Ask:

> What's currently on my iPod, and how full is it?

- [ ] `get_ipod_contents` returns the summary: capacity, used, free, track_count, artist_count, top_artists. NOT the full track manifest.
- [ ] **Response is small** — no "result exceeds maximum allowed tokens" error, no jq fallback
- [ ] Claude paraphrases naturally (e.g. "Your iPod has 335 tracks, 5.2 GB used of 60 GB, mostly Taylor Swift…")
- [ ] Cross-check against the CLI: `clickwheel ls` reports same counts

Then drill in:

> Show me 20 Taylor Swift tracks on my iPod.

- [ ] Claude calls `list_ipod_tracks(artist="Taylor Swift", limit=20)`
- [ ] Returns 20 (or fewer) track records, all by Taylor Swift

### 3.2 Sync — already-in-sync case

Pre-condition: the `ipod` playlist already matches the iPod.

Ask:

> Sync the 'ipod' playlist to my iPod.

- [ ] If everything matches: result says "iPod already matches 'ipod' — nothing to do"
- [ ] If there's a diff: skip to 3.3

### 3.3 Sync — real diff, deny path (client-side gating)

`sync_playlist_to_ipod` is flagged `destructiveHint=true`. Claude Code's native Allow / Deny prompt is the confirmation step.

Make a real diff first (e.g. `clickwheel edit ipod --add "Some artist"` from the CLI to add something not currently on the iPod).

Ask:

> Sync the 'ipod' playlist to my iPod.

- [ ] Claude summarizes the diff in its message before invoking ("Will add N tracks (X MB), Y tracks already on iPod stay…")
- [ ] Claude Code surfaces an Allow / Deny prompt for `sync_playlist_to_ipod`
- [ ] **Deny**. Tool isn't called. iPod state unchanged.

### 3.4 Sync — allow path

Repeat the prompt, allow this time.

- [ ] Allow / Deny prompt reappears; **Allow**.
- [ ] Server runs the sync; result includes `db_write_ok: true` and `next_step_hint` mentioning eject
- [ ] **Claude proactively offers** `eject_ipod` as the next step (driven by `next_step_hint`)
- [ ] Files are copied — verify by checking iPod from Finder before ejecting
- [ ] `clickwheel ls` and `get_ipod_contents` both reflect the new state

### 3.5 Sync — disconnected error path

Unplug the iPod. Ask:

> Sync 'ipod' to the iPod.

- [ ] Clear `IpodNotFoundError`, no partial state

### 3.6 Eject

iPod re-plugged. Ask:

> Eject my iPod safely.

- [ ] `eject_ipod` succeeds; iPod unmounts
- [ ] Re-running the same request: `IpodNotFoundError` (gentle "no iPod mounted")

### 3.7 Scrobble — full submission

iPod plugged in, Last.fm configured (`clickwheel scrobble --auth` already run once).

Ask:

> Submit my pending scrobbles to Last.fm.

- [ ] `submit_scrobbles` returns submitted count
- [ ] `next_step_hint` triggers Claude to offer `eject_ipod`
- [ ] Last.fm profile shows the new plays (`https://last.fm/user/<your-username>`)

## Round 4 — `build_playlist` prompt

Goal: server-defined prompt drives Claude through the canonical playlist-building flow with anti-hallucination rules.

In Claude Code, type `/` to bring up the slash-command picker.

- [ ] `build_playlist` appears in the picker (may be namespaced as `clickwheel:build_playlist`)
- [ ] Selecting it lets you fill in `vibe`, `target_minutes`, `name`

Run the prompt with:

- vibe: `late-night headphone listening, mostly indie folk`
- target_minutes: `45`
- name: `test-prompt`

- [ ] Claude starts by calling `library_stats`
- [ ] Multiple `search_tracks` calls follow (3-6 different terms)
- [ ] Drills into specific artists with `list_albums_by_artist` / `list_tracks_by_album`
- [ ] Final `create_playlist(name="test-prompt", track_paths=[...])`
- [ ] Final response renders the playlist as `Artist — Title (Album)` lines with running duration
- [ ] Offers `sync_playlist_to_ipod` as the natural next step
- [ ] **Anti-hallucination check**: every track in the final list also appears in an earlier tool result. Spot-check 3-5 randomly.

Cleanup:

> Delete the 'test-prompt' playlist.

(Confirm via elicitation.)

## Round 5 — Cross-cutting

### 5.1 Empty config

```bash
mv ~/.clickwheel/config.yaml /tmp/clickwheel-config.yaml.bak
```

Ask any tool question in a fresh Claude Code session.

- [ ] Server returns clear error (not stack trace)
- [ ] Restore: `mv /tmp/clickwheel-config.yaml.bak ~/.clickwheel/config.yaml`

### 5.2 Concurrent CLI

In one terminal:

```bash
clickwheel scan --full
```

In a Claude Code session simultaneously:

> What's in my library?

- [ ] Both run without deadlock (SQLite WAL mode should handle this)
- [ ] No "database is locked" errors

### 5.3 Stderr only

```bash
clickwheel-mcp 2>/tmp/cw-stderr.log <<EOF
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}
EOF
```

- [ ] stdout contains a single JSON-RPC response (the initialize result)
- [ ] `cat /tmp/cw-stderr.log` shows clickwheel logs prefixed `[clickwheel-mcp]`
- [ ] No log lines on stdout

## Round 6 — Claude Desktop pass

Same binary, secondary pass to confirm UX. Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "clickwheel": {
      "command": "/Users/patrickdugan/Documents/Github/clickwheel/.venv/bin/clickwheel-mcp"
    }
  }
}
```

Quit and relaunch Claude Desktop.

- [ ] Tools and the `build_playlist` prompt appear in Desktop's UI
- [ ] Tool descriptions render in Desktop's tool inspector
- [ ] Re-run Round 1.2 in Desktop — text summary shows naturally; structuredContent is also accessible (e.g. via the tool-result accordion)
- [ ] Re-run 2.5/2.6 in Desktop — Desktop's permission prompt surfaces for `delete_playlist`
- [ ] Re-run Round 4 in Desktop — `build_playlist` works from Desktop's prompt picker
- [ ] One real sync (3.3 + 3.4 + 3.6) end-to-end from Desktop

## Round 7 — Annotations spot-check

These don't have user-visible behavior yet, but worth confirming the metadata is correct so future client UI features (auto-approval, "destructive" badges) work.

```bash
.venv/bin/python3 -c "
from mcp.server.fastmcp import FastMCP
from clickwheel.mcp.server import mcp
for t in sorted(mcp._tool_manager.list_tools(), key=lambda x: x.name):
    a = t.annotations
    flags = []
    if a:
        if a.readOnlyHint: flags.append('R')
        if a.destructiveHint: flags.append('D')
        if a.idempotentHint: flags.append('I')
        if a.openWorldHint: flags.append('W')
    print(f'  {t.name:35} [{\"\".join(flags) or \"-\"}]')
"
```

- [ ] Read tools (`library_*`, `list_*`, `get_*`, `search_tracks`): `R` and `I` flags
- [ ] `delete_playlist`, `sync_playlist_to_ipod`: `D` and `I` flags
- [ ] `submit_scrobbles`: `W` flag (open world — calls Last.fm)
- [ ] `create_playlist`: no `I` flag (non-idempotent — errors on duplicate)

## Findings

Format: `<round.section>` — `<observed>` — `<follow-up>`

- **1.1** — Asked for "tools", Claude listed tools but not the `build_playlist` prompt. Expected behavior; reword the test prompt or accept (prompts surface via `/` picker, covered in Round 4).
- **1.4** — Claude said "100-result limit" but the actual default is `limit=50` (max 500). Minor prose inaccuracy; not a server bug. No follow-up needed.
- **1.3 (initial)** — Claude added a `⚠️` emoji to flag the unmounted-share warning. Fixed by adding "Plain text only — no emoji or decorative symbols" to the LINKING & RENDERING block of server `instructions` (commit `1a61e4c`).
- **2.5/2.6 (initial)** — MCP elicitation produced a confusing double-prompt (Confirm checkbox AND Accept/Decline buttons). Investigation showed elicitation is for collecting structured INPUT, not yes/no consent — Claude Code already gates `destructiveHint=true` tools natively. Removed server-side elicitation; rely on client gating (commit `99290de`/`8509362`).
- **3.1 (initial)** — `get_ipod_contents` returned the full 335-track manifest in `structuredContent` (~395K characters), blew past Claude Code's per-tool-result token cap, forced jq fallback. Restructured: `get_ipod_contents` is now summary-only; added paginated `list_ipod_tracks` and `list_playlist_tracks` (commit `8dbe9d3`).
- **3.3/3.4 (initial)** — Sync hung in uninterruptible I/O for ~20 minutes when music share was unmounted (per-file timeouts) and again when playlist contained 22 stale references to deleted files. Added pre-flight checks: `LibraryNotFoundError` if music dir not mounted; `MissingTracksError` if any `to_add` track is flagged missing on disk. Plus new `heal_playlist` tool / CLI command for recovering stale-ref playlists (commit `14eb218`).
- **Heal/add cycle bug** — After `clickwheel heal` dropped 22 dead refs, `clickwheel edit --add Taylor Swift` re-added the same 22 dead refs because `db.add_artist_to_playlist` and friends didn't filter `missing_since IS NULL`. Established a contract (documented inline in `db.py`): library queries that build NEW state filter missing; playlist-state queries preserve dead refs so users can see them and run heal. Filters added to 6 queries, 10 contract tests guard the boundary (commit `ae41f17`).
- **5.1 (skipped)** — Empty-config error path can't be cleanly tested without disrupting Last.fm setup. clickwheel reads from both `~/.clickwheel/config.yaml` and `~/.clickwheel/.env`; removing the YAML alone leaves the env-file fallback intact. To actually trigger the error path you'd nuke `.env` too, which would invalidate the Last.fm session key. Skipped.
- **3.7 (partial)** — Full Last.fm submission path untestable: no new plays on the iPod (recently scrobbled). `--status` and `--dry-run` paths verified working.
- **Zombie `clickwheel-mcp` processes** — Multiple instances accumulated across Claude Code sessions, one stuck in uninterruptible I/O wait (`U+` state) on a stale SMB handle for ~6 minutes. Cleaned up manually with `pkill -9`. This is a Claude Code subprocess-cleanup quirk, not our bug. Mitigation: `pkill -f clickwheel-mcp` recovery command documented in tracker.

### Open follow-ups for v0.5.1+

- Progress streaming during sync via `ctx.report_progress()` so chat clients see "12 of 22 copied" instead of a spinner.
- **Autoscan blocking MCP tool calls.** When `last_scan_completed` was older than `auto_scan_staleness_minutes`, every library-data MCP tool call triggered a synchronous SMB walk (30-90+ seconds on slow shares). Hit during Phase 5 — chat session hung for 3+ minutes on `list_albums_by_artist`. Researched + fixed properly: (a) MCP server now NEVER autoscans (chat tool calls always serve cached data), (b) CLI uses a cheap-probe + 24h-fallback two-tier strategy that's ~40× faster than the old full-walk approach, (c) default `auto_scan_staleness_minutes` raised from 30 to 1440. Empirical numbers: full SMB walk = 180s; cheap probe = 4.6s; root stat = 9ms.
- ~~Auto-detect slow library scans on SMB in CLI~~ (resolved by the cheap-probe two-tier strategy).
- Investigate the zombie-process accumulation — may need a graceful shutdown handler or just file with anthropics/claude-code.
