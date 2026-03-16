# Changelog

All notable changes to this project will be documented in this file.

This project uses [Semantic Versioning](https://semver.org/) and
[Conventional Commits](https://www.conventionalcommits.org/).

## v0.3.0 (2026-03-15)

### Features

- Non-interactive playlist editing: `clickwheel edit --add "Artist"` / `--remove "Artist"`
- Live file counter during scan discovery phase (no more staring at a blank screen)
- Scan progress indicator using tqdm for file discovery

### Fixes

- Always use `~/.clickwheel/` for data dir instead of varying by working directory
- Fix iPod sync: use `shutil.copy` instead of `copy2` to avoid FAT32 xattr errors
- Fix sync error output: group failures by artist/album instead of per-file path noise
- Fix vendored iPod imports: bare `from device_info` → `from clickwheel.ipod.device_info`
- Fix iTunesDB reader to handle both flat and nested track list formats
- Normalize capitalized track keys (Title/Artist/Album) from iTunesDB writer format

### Infrastructure

- Add release-please for automated changelog and version management
- 83 tests (6 new for non-interactive edit)

## v0.2.1 (2026-03-15)

### Fixes and Cleanup

- Remove unused acoustid_api_key from config
- Fix duplicate warn() in capacity bar
- Fix README capacity default to match code (64 GB)
- Rewrite README for end users (pipx install, clean config example)
- Update all dependencies to latest versions
- Add repo description, website, and topics on GitHub

## v0.2.0 (2026-03-15)

### Fixes

- Move macOS platform guard to individual commands so `--help` works on any OS
- Add test matrix job to CI (ubuntu + macos, Python 3.11-3.13)

## v0.1.0 (2026-03-15)

### Features

- Core CLI with Typer: `scan`, `fix`, `select`, `playlist`, `diff`, `sync`, `ls`, `eject` commands
- SQLite library index with metadata quality reporting
- Interactive artist/album/genre picker with capacity tracking
- iPod sync via vendored iOpenPodv2 (no libgpod dependency)
- Last.fm scrobbling via `scrobble` command with play count caching
- Playlist management: `edit`, `delete` commands
- Centralized Rich output helpers with consistent formatting
- macOS platform guard for clear error messaging
- Optional `[artwork]` extra for album art embedding (Pillow/numpy)
- Consumer-friendly CLI text throughout

### Infrastructure

- Pre-commit hooks: ruff, shellcheck, shfmt, prettier, markdownlint, commitlint
- 78 tests across 7 test modules (db, config, library, output, CLI helpers, scrobble, smoke)
- CI workflow with lint, format, and test jobs (ubuntu + macos, Python 3.11-3.13)
- Dynamic versioning via hatchling reading from `clickwheel/__init__.py`
- PyPI-ready packaging with classifiers, URLs, and optional dependency extras
