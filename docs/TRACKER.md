# Remaining Tasks

Everything needed to go from "published on PyPI" to "daily-driving clickwheel on the iPod."

## 1. Install on Mac Mini

- [x] `pipx install clickwheel` on Mac Mini (clean install from PyPI)
- [x] Verify `clickwheel --version` prints 0.2.1
- [x] Verify `clickwheel --help` and all subcommand `--help` work

## 2. Library Cleanup

- [x] Run `clickwheel scan` on full music library
- [x] Review scan stats — 614 missing art, 598 missing genre, 34 missing title/artist
- [ ] Run `clickwheel fix` to batch-fix metadata via beets
- [ ] Review audit report for remaining issues
- [ ] Manually fix stragglers beets couldn't auto-match

## 3. End-to-End Testing

- [x] `clickwheel scan` — verify full library indexed correctly (12,049 tracks, 734 artists)
- [ ] `clickwheel select` — pick artists/albums, confirm capacity tracking
- [x] `clickwheel playlist` — save a selection, list saved playlists
- [x] `clickwheel edit` — add/remove artists from a playlist (tested via --add/--remove)
- [x] `clickwheel delete` — remove a playlist
- [x] `clickwheel diff` — preview adds/removes against iPod
- [x] `clickwheel sync` — 335/357 tracks synced, iTunesDB written (22 stale paths skipped)
- [x] `clickwheel ls` — 335 tracks, 17 artists, 2.8 GB confirmed
- [x] `clickwheel eject` — safe unmount
- [ ] `clickwheel scrobble` — submit plays to Last.fm, verify dedup

## 4. Nice-to-Have Polish

- [x] Shell completion (`--install-completion`) — built into Typer, works out of the box
- [x] TestPyPI for pre-release validation — `test-publish.yml` workflow, manual trigger from Actions tab
