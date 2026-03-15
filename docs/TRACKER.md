# Remaining Tasks

Everything needed to go from "published on PyPI" to "daily-driving clickwheel on the iPod."

## 1. Install on Mac Mini

- [ ] `pipx install clickwheel` on Mac Mini (clean install from PyPI)
- [ ] Verify `clickwheel --version` prints 0.2.0
- [ ] Verify `clickwheel --help` and all subcommand `--help` work

## 2. Library Cleanup

- [ ] Run `clickwheel scan` on full music library
- [ ] Review scan stats — check for missing metadata, missing art
- [ ] Run `clickwheel fix` to batch-fix metadata via beets
- [ ] Review audit report for remaining issues
- [ ] Manually fix stragglers beets couldn't auto-match

## 3. End-to-End Testing

- [ ] `clickwheel scan` — verify full library indexed correctly
- [ ] `clickwheel select` — pick artists/albums, confirm capacity tracking
- [ ] `clickwheel playlist` — save a selection, list saved playlists
- [ ] `clickwheel playlist edit` — add/remove artists from a playlist
- [ ] `clickwheel playlist delete` — remove a playlist
- [ ] `clickwheel diff` — preview adds/removes against iPod
- [ ] `clickwheel sync` — copy files to iPod, verify iTunesDB written
- [ ] `clickwheel ls` — confirm iPod contents match expectations
- [ ] `clickwheel eject` — safe unmount
- [ ] `clickwheel scrobble` — submit plays to Last.fm, verify dedup

## 4. Nice-to-Have Polish

- [ ] Shell completion (`--install-completion`)
- [ ] Improved TUI (album art preview, richer browsing)
- [ ] TestPyPI for pre-release validation in future releases
- [ ] Announce on r/ipod, r/commandline
