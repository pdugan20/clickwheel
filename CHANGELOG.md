# Changelog

All notable changes to this project will be documented in this file.

This project uses [Semantic Versioning](https://semver.org/) and
[Conventional Commits](https://www.conventionalcommits.org/).

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
