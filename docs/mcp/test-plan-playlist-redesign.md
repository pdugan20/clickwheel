# Playlist redesign — manual test script

End-to-end walkthrough for the `add_tracks_to_ipod` / `add_artist_to_ipod`
/ `sync_playlist_to_ipod` / `list_ipod_playlists` work. Run from Claude
Desktop with the iPod plugged in. Expect ~15 minutes.

For each step, the **prompt** is what you paste into Claude Desktop, and
the **expected** describes what should happen. Tick items as you go.

## Pre-flight

- [ ] Quit Claude Desktop fully (⌘Q) and reopen. New code is loaded
      automatically because clickwheel-mcp is installed editable via
      `pip install -e '.[dev]'`.
- [ ] iPod is plugged in and mounted at `/Volumes/iPod`.
- [ ] In a fresh chat: **"What tools does clickwheel expose?"** —
      verify the list now includes `add_tracks_to_ipod`,
      `add_artist_to_ipod`, and `list_ipod_playlists` (in addition to
      the existing tools).
- [ ] Open a terminal and tail the MCP log to catch errors:

      ```bash
      tail -f ~/Library/Logs/Claude/mcp-server-clickwheel.log
      ```

## Phase 1 — add tracks without a playlist vehicle

The whole point: pushing music to the iPod no longer requires creating
a clickwheel-side playlist first.

### 1.1 Add a single artist

- **Prompt:** _"Add Weezer to my iPod."_
- **Expect:**
  - [ ] Claude calls `add_artist_to_ipod` (NOT `create_playlist` +
        `sync_playlist_to_ipod`).
  - [ ] You see the native Allow/Deny destructive prompt. Allow.
  - [ ] Progress line shows `Weezer — <title>` per track as files copy.
  - [ ] Final message says something like "Added N tracks by Weezer to
        the iPod."
  - [ ] Offer to eject.

### 1.2 Verify on the iPod

- [ ] On the iPod itself: navigate to Music → Artists → Weezer. The
      tracks should appear, browsable by album.
- [ ] On the iPod: Music → Playlists. **There should be no "Weezer"
      playlist.** This is the key behavior change — no throwaway
      playlist clutter.
- [ ] In Claude Desktop, ask **"How full is the iPod?"** — used space
      should reflect the new tracks.

### 1.3 Re-run (idempotency)

- **Prompt:** _"Add Weezer to my iPod."_ (again)
- **Expect:**
  - [ ] Claude calls `add_artist_to_ipod` again. The deduplication path
        catches that all tracks are already on the device.
  - [ ] Result text says something like "All N tracks by Weezer are
        already on the iPod — nothing to copy."
  - [ ] No progress events (nothing to copy).

### 1.4 Add specific tracks (path-based)

- **Prompt:** _"Add the first three tracks from Big Thief's Two Hands to
  my iPod."_
- **Expect:**
  - [ ] Claude first calls `list_tracks_by_album` to get paths.
  - [ ] Then calls `add_tracks_to_ipod(paths=[...])`.
  - [ ] Allow. Progress events fire.
  - [ ] Tracks land in the iPod's Big Thief artist view (no playlist).

## Phase 2 — sync_playlist actually creates the iPod playlist

This was the broken implicit promise: syncing a playlist used to copy
tracks only. Now it also writes the playlist under Music → Playlists.

### 2.1 Build a small clickwheel playlist

- **Prompt:** _"Create a playlist called 'test-mix' with three tracks
  by Big Thief."_
- **Expect:**
  - [ ] Claude calls `create_playlist`.
  - [ ] Confirms creation. Asks if you want to sync (does NOT auto-sync).

### 2.2 Sync it

- **Prompt:** _"Yes, sync 'test-mix' to the iPod."_
- **Expect:**
  - [ ] Claude calls `sync_playlist_to_ipod`. Native Allow/Deny. Allow.
  - [ ] Progress events per track (if not already on iPod) — should be
        a no-op copy since Big Thief tracks are already there from 1.4.
  - [ ] Final message: synced as `'test-mix'`.

### 2.3 Verify the iPod playlist exists

- [ ] **On the iPod**: Music → Playlists → there should now be a
      `test-mix` entry alongside whatever else (Music, Audiobooks).
- [ ] Open it on the iPod. The three Big Thief tracks should be inside.
- [ ] In Claude Desktop: **"What playlists are on my iPod?"** — expect
      `list_ipod_playlists` to fire and surface `test-mix` (plus any
      iTunes-created smart playlists).

### 2.4 Conflict — same-name sync

- **Prompt:** _"Sync 'test-mix' to the iPod again."_
- **Expect:**
  - [ ] The tool returns a conflict — Claude says something like _"The
        iPod already has a playlist called 'test-mix' with 3 tracks.
        Do you want to merge, replace, or rename?"_
  - [ ] Claude does NOT silently overwrite. (This is the elicit-the-
        user behavior we built.)

### 2.5 Conflict: merge

- Add a fourth track to the clickwheel playlist first:
- **Prompt:** _"Add one Wilco track to the 'test-mix' playlist, then
  sync to the iPod, merging if needed."_
- **Expect:**
  - [ ] Claude calls `add_artist_to_playlist` (or `update_playlist`) to
        add the Wilco track to the clickwheel playlist.
  - [ ] Then calls `sync_playlist_to_ipod` with `on_conflict='merge'`.
  - [ ] After sync: open `test-mix` on the iPod. It should now have
        the original three Big Thief tracks **plus** the new Wilco
        track. Order preserves the original first.

### 2.6 Conflict: rename

- **Prompt:** _"Sync 'test-mix' to the iPod again, but rename it to
  'test-mix-v2' on the device."_
- **Expect:**
  - [ ] Claude calls with `on_conflict='rename'` and
        `target_name='test-mix-v2'`.
  - [ ] On the iPod: both `test-mix` and `test-mix-v2` exist.

### 2.7 Conflict: replace

- Edit the clickwheel playlist again, drop a track:
- **Prompt:** _"Remove Wilco from 'test-mix' and sync it to the iPod,
  replacing what's there."_
- **Expect:**
  - [ ] Claude calls with `on_conflict='replace'`.
  - [ ] On the iPod: `test-mix` now has only the original three Big
        Thief tracks (Wilco is gone from this playlist, but the Wilco
        TRACK itself stays in the library — `add_artist_to_ipod` put
        it there in 1.x and replace doesn't delete tracks, only
        rewrites the playlist's contents).

## Phase 3 — list_ipod_playlists

Already exercised in 2.3, but a couple more sanity prompts:

### 3.1 Direct query

- **Prompt:** _"List the playlists currently on my iPod."_
- **Expect:**
  - [ ] `list_ipod_playlists` returns the playlists. Should include
        `test-mix` and `test-mix-v2` from earlier rounds.
  - [ ] The auto-generated master library playlist (often named "iPod")
        should NOT appear — that's intentional.
  - [ ] iTunes-created smart playlists (Music, Audiobooks, etc.) may
        appear with `is_smart: true`.

### 3.2 Disambiguation prompt

- **Prompt:** _"What playlists do I have?"_ (deliberately ambiguous)
- **Expect:**
  - [ ] Claude should either call both `list_playlists` and
        `list_ipod_playlists` to give the full picture, or ask "do you
        mean drafts (clickwheel) or on the iPod?" The disambiguation
        instructions in `_runtime.py` should steer it.

## Cleanup

Once you're done testing:

- **Prompt:** _"Delete the 'test-mix' and 'test-mix-v2' playlists from
  the iPod, and remove 'test-mix' from clickwheel too."_
- **Expect:**
  - [ ] Claude points out we don't have a "remove iPod playlist" tool
        yet (Phase 4 work). It can delete the clickwheel-side draft
        via `delete_playlist`.
  - [ ] To clean up the iPod-side playlists, use the iPod itself
        (Settings → ...) or wait for the Phase 4 `remove_ipod_playlist`
        tool. Worst case, the playlists are harmless — they reference
        tracks that stay on the device anyway.
- [ ] Eject the iPod via Claude (**"Eject the iPod."**) or Finder.

## Findings

Record anything surprising here:

- _e.g. "Claude tried to create a playlist for the Weezer add — needs
  better instruction prompt"_
- _e.g. "Conflict response didn't surface clearly to the user — needs
  text tweak"_
- _e.g. "Smart playlists got dropped from the iPod"_

Any failures or unexpected behavior should be filed as a follow-up.
