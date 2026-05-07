# Changelog

All notable changes to this project will be documented in this file.

This project uses [Semantic Versioning](https://semver.org/) and
[Conventional Commits](https://www.conventionalcommits.org/).

## [0.5.0](https://github.com/pdugan20/clickwheel/compare/v0.4.1...v0.5.0) (2026-05-07)


### Features

* add build-playlist mcp prompt ([50c44e8](https://github.com/pdugan20/clickwheel/commit/50c44e8a588204b054da2cab0d60b287f18958a1))
* add eject_ipod tool and richer mcp tool descriptions ([6b82b32](https://github.com/pdugan20/clickwheel/commit/6b82b32bb8b41546328b8e6fb37663dff50ee8ab))
* add mcp mutation tools ([1bba30d](https://github.com/pdugan20/clickwheel/commit/1bba30d06bc3596aba6014dc044c22651d17b6ab))
* add read-only mcp server ([74ba924](https://github.com/pdugan20/clickwheel/commit/74ba924411361c83a4c7fbf7750c9a9520d6b23c))
* dual-content mcp responses with text summaries ([6be17db](https://github.com/pdugan20/clickwheel/commit/6be17dbd32d8c53898452dea20f1808c2b89c6fe))


### Bug Fixes

* clearer copy on the elicitation confirm field ([269433e](https://github.com/pdugan20/clickwheel/commit/269433e3fb69f0d67bde8a4118bd7e71106f0bd0))
* drop server-side elicitation; rely on client gating ([99290de](https://github.com/pdugan20/clickwheel/commit/99290de8dc7c6ad83e76023864559367e78a5c11))
* elicit_confirm — accept = yes, no double-toggle required ([8509362](https://github.com/pdugan20/clickwheel/commit/850936214598060a5d7acb9cb033ab3b1046ab71))
* filter missing tracks in library queries; preserve in playlist queries ([ae41f17](https://github.com/pdugan20/clickwheel/commit/ae41f17bd7bcaa65b6a2b69f80b964c664af1290))
* **mcp:** dual-emit structured tool output for clients that hide it ([2a160e1](https://github.com/pdugan20/clickwheel/commit/2a160e1db0b46048a39dedc4ab3e8c4777279164))
* paginate ipod and playlist tracks to fit the tool-result token cap ([8dbe9d3](https://github.com/pdugan20/clickwheel/commit/8dbe9d383d29565e43c30262e12a1ebdc5f7dea9))
* pre-flight checks on sync + heal_playlist for stale refs ([14eb218](https://github.com/pdugan20/clickwheel/commit/14eb2180c6002b57b8ed5f51a765a6b79588a0ad))
* two-tier autoscan + mcp never autoscans ([180afb3](https://github.com/pdugan20/clickwheel/commit/180afb3c91cf26a1c197f794eda0ce392190f9c9))
* write_ipod_db merges with existing itunesdb instead of clobbering ([d38830c](https://github.com/pdugan20/clickwheel/commit/d38830c78f5669e8c8bdbd973b1ee8ff971ec77a))


### Documentation

* add autoscan-blocking-mcp-tool-calls to phase 5 findings ([53057a1](https://github.com/pdugan20/clickwheel/commit/53057a1eeb8c6558d66992ca97041af16cf2b89b))
* add mcp integration project plan ([7e7c796](https://github.com/pdugan20/clickwheel/commit/7e7c796cfd255da3f4be6ec493ccd79543e89721))
* capture phase 5 testing findings ([397b4c1](https://github.com/pdugan20/clickwheel/commit/397b4c1b1fcae9c7613b6a2873d4b017943ebbd2))
* claude desktop install path, stale readme defaults, round 6 findings ([b269e15](https://github.com/pdugan20/clickwheel/commit/b269e15535ad19cea2d94b59095ddf55ff9f9158))
* discourage emoji in mcp client output ([1a61e4c](https://github.com/pdugan20/clickwheel/commit/1a61e4c9aff112c2227818af539502c6ad5159ff))
* document mcp server install and usage ([40f2fe5](https://github.com/pdugan20/clickwheel/commit/40f2fe5167bac0c3bc6d2be5f8476cab38f227e9))
* refresh mcp test plan for phases 4.5a–d ([a0bac9c](https://github.com/pdugan20/clickwheel/commit/a0bac9cf4a0aafaf5730e47febb9310e87a9df98))
* restructure as a two-surface project — slim readme, dedicated client/config guides ([8cf0339](https://github.com/pdugan20/clickwheel/commit/8cf0339cbde6afdeaa1b697b5331c3619b2253db))
* restructure mcp test plan as a round-by-round walkthrough ([a7d8d44](https://github.com/pdugan20/clickwheel/commit/a7d8d442cb266b4dd78caac436ce626444a86bec))
* round out readme — heal command, heal_playlist tool, autoscan subsection ([d2c2ae0](https://github.com/pdugan20/clickwheel/commit/d2c2ae0a2cd0cc06a2c8ee0226a630ad1fb8cbc8))
* scrub internal jargon from user-facing mcp copy ([586077e](https://github.com/pdugan20/clickwheel/commit/586077e5f0b13ef9f594a422c8bb8f7b73cf6539))

## [0.4.1](https://github.com/pdugan20/clickwheel/compare/v0.4.0...v0.4.1) (2026-03-17)

### Features

- modernize CLI UX with interactive prompts, spinners, and live displays ([5b12137](https://github.com/pdugan20/clickwheel/commit/5b12137f43e6939072a62bade6e28ddf47a26961))

### Bug Fixes

- allow dashes and double blanks in markdownlint for release-please compat ([8575db8](https://github.com/pdugan20/clickwheel/commit/8575db84572f2a9ad51cdb0d166190af4ec5ed10))
- standardize table styling across cli output ([52ef6f0](https://github.com/pdugan20/clickwheel/commit/52ef6f0d9940f92483c08d69bea0e28f92f18082))
- resolve table title truncation in tests ([428a44e](https://github.com/pdugan20/clickwheel/commit/428a44e3dcf35980bb7a8f4b61a47e67a0a3e3f3))

## [0.4.0](https://github.com/pdugan20/clickwheel/compare/v0.3.0...v0.4.0) (2026-03-16)

### Features

- add last.fm web auth flow for scrobbling ([0776e2e](https://github.com/pdugan20/clickwheel/commit/0776e2ea6941b363aef9c37e719686870eec3235))
- auto-scan library before commands, incremental scan, fix improvements ([bb56ab2](https://github.com/pdugan20/clickwheel/commit/bb56ab20966db12c4f01dd74b5cbb140955006aa))

### Bug Fixes

- lint issues — line length, table alignment, changelog headings ([3e8a9c7](https://github.com/pdugan20/clickwheel/commit/3e8a9c773899b58e193b98a3c73f0418ba8b8389))

### Documentation

- update architecture, readme, and claude.md for new features ([b33eef0](https://github.com/pdugan20/clickwheel/commit/b33eef044da603ad0f690ad8d98037bf9f075e86))
- update tracker with completed end-to-end testing ([054d5eb](https://github.com/pdugan20/clickwheel/commit/054d5eb7d0fb16f7905cf9d789d371a3952a571a))

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
