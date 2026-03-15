# Project Tracker

## Phase 1: Library Cleanup

Bash scripts for auditing and fixing metadata. Run once to get the library in shape.

- [x] Audit script — scan library for missing metadata and album art
- [x] Beets config — template-based, env-injected paths
- [x] Fix-metadata script — catalog, fetch art, fill genres, write tags
- [x] Test on single artist (Daft Punk — art fetched and embedded)
- [ ] Run full library cleanup from Mac Mini
- [ ] Review results — check audit report for remaining issues
- [ ] Manually fix stragglers (files beets couldn't auto-match)

## Phase 2: Project Setup

Repo scaffolding, CI, and tooling.

- [x] Git repo + GitHub remote
- [x] Generalize config (no hardcoded paths)
- [x] CI workflow (shellcheck, shfmt, markdownlint, prettier)
- [x] Dependabot + auto-merge
- [x] MIT license
- [x] Linter configs (shellcheck, shfmt, markdownlint, prettier, editorconfig)
- [ ] Rename repo to `clickwheel`
- [ ] CLAUDE.md for project
- [ ] Python project scaffolding (pyproject.toml, src layout)
- [ ] Python linting in CI (ruff)
- [ ] Pre-commit hooks

## Phase 3: clickwheel CLI — Library Index

Build the scan/index layer.

- [ ] Python package structure (`clickwheel/`)
- [ ] Typer CLI entry point with command stubs
- [ ] `clickwheel scan` — read metadata from library, store in SQLite
- [ ] SQLite schema (tracks, albums, artists, art status)
- [ ] `clickwheel fix` — wrapper around beets scripts
- [ ] Basic `--help` and version output

## Phase 4: clickwheel CLI — Selection

Interactive subset picker for iPod.

- [ ] `clickwheel select` — TUI for browsing artists/albums/genres
- [ ] Running size total vs. iPod capacity display
- [ ] Exclude FLAC files from selection
- [ ] `clickwheel playlist` — save/load/list selections as m3u
- [ ] Edit existing playlists (add/remove artists/albums)

## Phase 5: clickwheel CLI — iPod Sync

Wire up libgpod for actual iPod management.

- [ ] Detect and mount iPod
- [ ] `clickwheel ls` — show iPod contents
- [ ] `clickwheel diff` — preview adds/removes before syncing
- [ ] `clickwheel sync` — copy files + write iTunesDB via libgpod
- [ ] Progress bar (tqdm/rich) during sync
- [ ] Embed album art in iTunesDB
- [ ] `clickwheel eject` — safe unmount
- [ ] Error handling (disconnected iPod, full disk, corrupt files)

## Phase 6: Polish

- [ ] Config file support (`~/.clickwheel/config.yaml`)
- [ ] `--dry-run` flag on destructive commands
- [ ] Shell completion (Typer built-in)
- [ ] Improved TUI (album art preview, richer browsing)
