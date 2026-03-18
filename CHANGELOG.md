# Changelog

All notable changes to this project will be documented in this file.

This project uses [Semantic Versioning](https://semver.org/) and
[Conventional Commits](https://www.conventionalcommits.org/).

## [0.4.0](https://github.com/pdugan20/clickwheel/compare/v0.3.0...v0.4.0) (2026-03-18)


### Features

* add last.fm web auth flow for scrobbling ([0776e2e](https://github.com/pdugan20/clickwheel/commit/0776e2ea6941b363aef9c37e719686870eec3235))
* auto-scan library before commands, incremental scan, fix improvements ([bb56ab2](https://github.com/pdugan20/clickwheel/commit/bb56ab20966db12c4f01dd74b5cbb140955006aa))
* modernize CLI UX with interactive prompts, spinners, and live displays ([5b12137](https://github.com/pdugan20/clickwheel/commit/5b12137f43e6939072a62bade6e28ddf47a26961))


### Bug Fixes

* allow dashes and double blanks in markdownlint for release-please compat ([8575db8](https://github.com/pdugan20/clickwheel/commit/8575db84572f2a9ad51cdb0d166190af4ec5ed10))
* lint issues — line length, table alignment, changelog headings ([3e8a9c7](https://github.com/pdugan20/clickwheel/commit/3e8a9c773899b58e193b98a3c73f0418ba8b8389))
* resolve table title truncation in tests ([428a44e](https://github.com/pdugan20/clickwheel/commit/428a44e3dcf35980bb7a8f4b61a47e67a0a3e3f3))
* standardize table styling across cli output ([52ef6f0](https://github.com/pdugan20/clickwheel/commit/52ef6f0d9940f92483c08d69bea0e28f92f18082))


### Documentation

* update architecture, readme, and claude.md for new features ([b33eef0](https://github.com/pdugan20/clickwheel/commit/b33eef044da603ad0f690ad8d98037bf9f075e86))
* update tracker with completed end-to-end testing ([054d5eb](https://github.com/pdugan20/clickwheel/commit/054d5eb7d0fb16f7905cf9d789d371a3952a571a))

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
