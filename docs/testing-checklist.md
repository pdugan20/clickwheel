# Testing Checklist

Manual testing checklist for clickwheel on a Mac with an iPod and music library.

## Prerequisites

- [ ] macOS machine with music library accessible
- [ ] iPod Classic connected via USB, visible in Finder as `/Volumes/IPOD`
- [ ] `~/.clickwheel/config.yaml` configured with `music_dir` pointing to library
- [ ] Last.fm API credentials configured (for scrobble tests)
- [ ] clickwheel installed: `pipx install clickwheel` or `pip install -e '.[dev]'`
- [ ] Verify install: `clickwheel --version` prints current version

## 1. Help and Version

- [ ] `clickwheel --help` — shows all commands with descriptions
- [ ] `clickwheel scan --help` — shows scan-specific options
- [ ] `clickwheel --version` — prints version string

## 2. Scan (incremental + progress)

- [ ] `clickwheel scan`
  - [ ] Live counter shows files found during discovery
  - [ ] tqdm progress bar appears for metadata scanning
  - [ ] Incremental: skips unchanged files (fast on repeat runs)
  - [ ] Library Summary table shows tracks, artists, albums, size, duration
  - [ ] Formats table shows breakdown (MP3, FLAC, etc.)
  - [ ] Metadata Quality table shows art/genre/title/artist counts
  - [ ] Hint at bottom: "Run `clickwheel select` to pick music for your iPod."
- [ ] `clickwheel scan --stats`
  - [ ] Shows stats tables without re-scanning (fast)
- [ ] `clickwheel scan --full`
  - [ ] Re-scans everything from scratch (slower than incremental)

## 3. Fix (spinner per phase)

- [ ] `clickwheel fix --dry-run`
  - [ ] Shows target path and planned steps, no changes made
- [ ] `clickwheel fix` (requires `clickwheel[fix]` extras)
  - [ ] Each of the 5 phases shows an animated spinner
  - [ ] Spinners disappear as each phase completes, replaced by status
  - [ ] "Metadata cleanup complete." at the end

## 4. Select (questionary checkbox + auto-scan)

- [ ] `clickwheel select`
  - [ ] Auto-scans library if stale (spinner or skip message)
  - [ ] Shows artist count and iPod capacity header
  - [ ] Checkbox list appears with all artists
  - [ ] Each choice shows: artist name, track count, total size
  - [ ] Arrow keys navigate the list
  - [ ] Space toggles selection (circle fills in)
  - [ ] Enter confirms selection
  - [ ] Selected artists print confirmation lines ("+ ArtistName: N tracks")
  - [ ] Capacity bar shows after selection (green if under 80%, yellow if over)
  - [ ] "Playlist 'ipod' saved" success message with track count and size
- [ ] `clickwheel select --name custom`
  - [ ] Saves with the custom playlist name
- [ ] `clickwheel select --no-scan`
  - [ ] Skips auto-scan
- [ ] Ctrl+C during selection
  - [ ] Exits cleanly without saving

## 5. Playlist

- [ ] `clickwheel playlist`
  - [ ] Table shows all playlists with name, track count, size, last updated
- [ ] `clickwheel playlist ipod`
  - [ ] Table shows all tracks in the playlist (artist, album, title, size)
  - [ ] Footer shows total tracks and size

## 6. Edit (non-interactive + questionary interactive)

- [ ] `clickwheel edit --add "ArtistName"`
  - [ ] Non-interactive: adds artist, shows summary
- [ ] `clickwheel edit --remove "ArtistName"`
  - [ ] Non-interactive: removes artist, shows summary
- [ ] `clickwheel edit ipod` (no flags — interactive mode)
  - [ ] Shows current playlist info and capacity bar
  - [ ] Menu appears: "Add artists", "Remove artists", "Show current playlist", "Done"
  - [ ] **Add artists**: checkbox list of artists NOT in playlist, with track/size info
  - [ ] **Remove artists**: checkbox list of artists currently IN playlist
  - [ ] **Show current playlist**: table of current artists with track/size breakdown
  - [ ] **Done**: saves and shows final summary
  - [ ] Capacity bar updates after each add/remove action
  - [ ] Over-capacity warning shows if applicable

## 7. Delete (confirmation)

- [ ] `clickwheel delete ipod`
  - [ ] Warning shows playlist name and track count
  - [ ] Asks "Are you sure? [y/N]" (default No)
  - [ ] Pressing Enter (default) cancels — "Cancelled."
  - [ ] Typing `y` deletes — "Deleted playlist 'ipod'."
- [ ] `clickwheel delete ipod --force`
  - [ ] Skips confirmation, deletes immediately
- [ ] `clickwheel delete nonexistent`
  - [ ] Error: "Playlist 'nonexistent' not found."

## 8. Diff (panel + colored tables)

Requires a playlist saved and iPod connected.

- [ ] `clickwheel diff`
  - [ ] Bordered cyan panel shows summary: "N to add, N to remove, N already on iPod"
  - [ ] If tracks to add: green-titled table "+ To Add" with artist/album/title
  - [ ] If tracks to remove: red-titled table "- To Remove" with artist/album/title
  - [ ] If everything matches: "Your iPod matches this playlist."

## 9. Sync (confirmation + live table + error recovery)

Requires a playlist saved and iPod connected.

- [ ] `clickwheel sync --dry-run`
  - [ ] Shows add/remove summary
  - [ ] "Dry run -- nothing was changed."
- [ ] `clickwheel sync`
  - [ ] Shows add/remove summary
  - [ ] Asks "Proceed with sync? [Y/n]" (default Yes)
  - [ ] Pressing `n` cancels — "Cancelled."
  - [ ] Pressing Enter starts sync
  - [ ] Live table appears showing each file as it copies (artist, title, size, green "OK")
  - [ ] Table updates in place (doesn't scroll)
  - [ ] After copying: "Copied N tracks to iPod."
  - [ ] Failed copies grouped by artist/album (v0.4.0 feature)
  - [ ] Spinner during "Updating iPod database..."
  - [ ] "iPod database updated." on success
  - [ ] If DB write fails: asks "Retry writing the iPod database?"

## 10. ls

- [ ] `clickwheel ls`
  - [ ] Table shows artists on iPod with track count and album count
  - [ ] Footer shows total tracks, artists, and size

## 11. Eject (spinner)

- [ ] `clickwheel eject`
  - [ ] Animated spinner during "Ejecting iPod..."
  - [ ] "iPod ejected. Safe to unplug." on success
  - [ ] Error message if iPod not mounted

## 12. Scrobble (web auth + spinner + error recovery)

Requires Last.fm credentials configured and iPod with recent plays.

- [ ] `clickwheel scrobble --auth`
  - [ ] Opens browser for Last.fm authorization
  - [ ] Prompts to press Enter after approval
  - [ ] Saves session key to config
- [ ] `clickwheel scrobble --status`
  - [ ] Shows Last.fm username, total scrobble count, profile URL
- [ ] `clickwheel scrobble --dry-run`
  - [ ] Spinner during "Checking iPod for recent listens..."
  - [ ] Table of pending scrobbles (time, artist, title, album)
  - [ ] "Dry run -- nothing was submitted."
- [ ] `clickwheel scrobble`
  - [ ] Spinner during iPod read
  - [ ] Shows listen count found
  - [ ] Spinner during "Sending N listens to Last.fm..."
  - [ ] "Sent N listens to Last.fm." on success
  - [ ] If failures: asks "Retry failed scrobbles now?"
- [ ] `clickwheel scrobble` (run again immediately)
  - [ ] "All listens already submitted." (dedup works)

## 13. Edge Cases

- [ ] Run any iPod command without iPod connected
  - [ ] "No iPod found. Make sure it's plugged in and shows up in Finder."
- [ ] Run `clickwheel select` with no library scanned
  - [ ] "No music found. Run `clickwheel scan` first."
- [ ] Run `clickwheel edit nonexistent`
  - [ ] "Playlist 'nonexistent' not found."
- [ ] Run `clickwheel scrobble` without Last.fm config
  - [ ] "Last.fm isn't configured."
- [ ] Run `clickwheel scrobble` without `--auth` first
  - [ ] "Last.fm not authorized. Run `clickwheel scrobble --auth`"

## 14. Full Workflow (end-to-end)

Run these in order to verify the complete lifecycle:

1. [ ] `clickwheel scan` — index the library
2. [ ] `clickwheel select` — pick some artists
3. [ ] `clickwheel playlist` — verify the playlist saved
4. [ ] `clickwheel diff` — see what would change on iPod
5. [ ] `clickwheel sync` — push to iPod
6. [ ] `clickwheel ls` — verify iPod contents
7. [ ] Disconnect and play some tracks on the iPod
8. [ ] Reconnect the iPod
9. [ ] `clickwheel scrobble` — submit plays to Last.fm
10. [ ] `clickwheel eject` — safely disconnect

## Notes

Use this space to record any issues found during testing:

```text

```
