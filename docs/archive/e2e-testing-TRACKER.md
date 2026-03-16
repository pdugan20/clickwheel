# Remaining Tasks

Everything needed to go from "published on PyPI" to "daily-driving clickwheel on the iPod."

## 1. Install on Mac Mini

- [x] `pipx install clickwheel` on Mac Mini (clean install from PyPI)
- [x] Verify `clickwheel --version` prints 0.2.1
- [x] Verify `clickwheel --help` and all subcommand `--help` work

## 2. Library Cleanup

- [x] Run `clickwheel scan` on full music library
- [x] Review scan stats — 614 missing art, 598 missing genre, 34 missing title/artist
- [x] Run `clickwheel fix` to batch-fix metadata via beets
- [x] Review audit report — 562 missing art, 33 missing genre after fix
- [ ] Manually fix stragglers beets couldn't auto-match (11 skipped folders, 34 tracks missing title/artist)

## 3. End-to-End Testing

- [x] `clickwheel scan` — verify full library indexed correctly (12,049 tracks, 734 artists)
- [x] `clickwheel select` — verified help output, --no-scan flag
- [x] `clickwheel playlist` — save a selection, list saved playlists
- [x] `clickwheel edit` — add/remove artists from a playlist (tested via --add/--remove)
- [x] `clickwheel delete` — remove a playlist
- [x] `clickwheel diff` — preview adds/removes against iPod
- [x] `clickwheel sync` — 335/357 tracks synced, iTunesDB written (22 stale paths skipped)
- [x] `clickwheel ls` — 335 tracks, 17 artists, 2.8 GB confirmed
- [x] `clickwheel eject` — safe unmount
- [x] `clickwheel scrobble` — 7 Olivia Rodrigo listens submitted to Last.fm

## 4. Nice-to-Have Polish

- [x] Shell completion (`--install-completion`) — built into Typer, works out of the box
- [x] TestPyPI for pre-release validation — `test-publish.yml` workflow, manual trigger from Actions tab
- [x] Auto-scan before commands (select, edit, diff, sync) with staleness threshold
- [x] Incremental scan via mtime+size comparison
- [x] Last.fm web auth flow (`clickwheel scrobble --auth`)
- [x] Auto-generate beets config on first `fix` run
