# Changelog

All notable changes to this project will be documented in this file.

This project uses [Semantic Versioning](https://semver.org/) and
[Conventional Commits](https://www.conventionalcommits.org/).

## [0.7.0](https://github.com/pdugan20/clickwheel/compare/v0.6.1...v0.7.0) (2026-05-15)


### Features

* **mcp:** add tool titles, server icon, and resource display titles ([#18](https://github.com/pdugan20/clickwheel/issues/18)) ([d9d53bd](https://github.com/pdugan20/clickwheel/commit/d9d53bd1edfc60f146e3336929cd9ca9e5fc6555))
* **mcp:** emit output schemas for all tools via typed return models ([#19](https://github.com/pdugan20/clickwheel/issues/19)) ([16898f4](https://github.com/pdugan20/clickwheel/commit/16898f42cd85b31f55dc316e4ce209a762fc81be))
* **plex:** add optional plex playlist sync ([#12](https://github.com/pdugan20/clickwheel/issues/12)) ([d8afd75](https://github.com/pdugan20/clickwheel/commit/d8afd75ea6dd4334a9cc7007cc75b6685b635fd0))
* **plex:** mcp tools, doctor command, and docs ([#13](https://github.com/pdugan20/clickwheel/issues/13)) ([b7a9094](https://github.com/pdugan20/clickwheel/commit/b7a90946da822e7237e09954925bbaa5bbb4d749))


### Documentation

* **plex:** drop design-rationale section ([#16](https://github.com/pdugan20/clickwheel/issues/16)) ([3d70d8d](https://github.com/pdugan20/clickwheel/commit/3d70d8d4d51600b9e3fbfa63107df252890044c6))
* trim readme integrations, extract docs/lastfm.md ([#15](https://github.com/pdugan20/clickwheel/issues/15)) ([1277ffb](https://github.com/pdugan20/clickwheel/commit/1277ffba5e8d53128f25e2715e51be9b008f42d6))

## [0.6.1](https://github.com/pdugan20/clickwheel/compare/v0.6.0...v0.6.1) (2026-05-12)


### Documentation

* **mcp:** drop test plans, split bundles deep-dive into bundles.md ([51a1174](https://github.com/pdugan20/clickwheel/commit/51a117488fd631818872b6d629559beef42fa633))

## [0.6.0](https://github.com/pdugan20/clickwheel/compare/v0.5.0...v0.6.0) (2026-05-12)


### Features

* **mcp:** add_tracks_to_ipod / add_artist_to_ipod (no playlist required) ([13c37c6](https://github.com/pdugan20/clickwheel/commit/13c37c685277c8568a7a938d2c05c6dd473e1410))
* **mcp:** compute sync-result detail subtitle server-side ([0413361](https://github.com/pdugan20/clickwheel/commit/0413361749ffc6efaa2a4e7887bcf10c716fc3d1))
* **mcp:** library_health bundle (status grid) ([d2b24d5](https://github.com/pdugan20/clickwheel/commit/d2b24d50005b784e73600928821d173b358b573a))
* **mcp:** library_stats bundle (overview dashboard) ([5bb5548](https://github.com/pdugan20/clickwheel/commit/5bb5548fcd56f9a1f22da3f73b8fe2224a6e662e))
* **mcp:** live progress notifications for sync_playlist_to_ipod ([a9c3b53](https://github.com/pdugan20/clickwheel/commit/a9c3b531826cc0512dc4a4e713c27e56e9caa602))
* **mcp:** live progress polling in the sync-result iframe ([bd0638f](https://github.com/pdugan20/clickwheel/commit/bd0638f669b0bd927a55fb75d8ef342a12031df0))
* **mcp:** mcp apps ui bundles with react + vite workbench ([afb3506](https://github.com/pdugan20/clickwheel/commit/afb350695519e4fe6f46975fcee7252bec80b4fe))
* **mcp:** primary-artist rollup, host theme tokens, click-to-message ([770a08c](https://github.com/pdugan20/clickwheel/commit/770a08cb6cef84fb066c13b767d041cd2d7e95b3))
* **mcp:** remove_tracks / remove_artist / remove_ipod_playlist (phase 4) ([2a37a4c](https://github.com/pdugan20/clickwheel/commit/2a37a4cd1f8605ca8331d75c65b74670cdf6120e))
* **mcp:** sync creates the ipod playlist + new list_ipod_playlists tool ([a3575c7](https://github.com/pdugan20/clickwheel/commit/a3575c7c8fb4a8685e96ecb9e5c5058e30138ca7))
* **mcp:** sync-result summary card iframe + preload experiment ([85e3e10](https://github.com/pdugan20/clickwheel/commit/85e3e10d76a6d19477bf10e057be887a6d115a32))
* **web,mcp:** rewind card chrome + route artist-browse away from search_tracks ([abe69f2](https://github.com/pdugan20/clickwheel/commit/abe69f254e0405216f96a503ce288163acc88e6b))
* **web:** align ipod-capacity to library-stats header + tooltip pattern ([43bf893](https://github.com/pdugan20/clickwheel/commit/43bf8937b8e4b2a761f8c3e171722d7416f3d982))
* **web:** balanced-5 categorical palette + workbench showcase ([a4a5c55](https://github.com/pdugan20/clickwheel/commit/a4a5c558364a6f81bdff1bd79b64ab0e01596e24))
* **web:** finder-style library-stats + floating-ui tooltips ([21e02a7](https://github.com/pdugan20/clickwheel/commit/21e02a797af3496914ec05dfda8f4deaab974169))
* **web:** static detail subtitle, inline status text, drop library-health + stats-showcase ([f8df644](https://github.com/pdugan20/clickwheel/commit/f8df644f39066afd1be896c1baeb24f7ad6e4846))
* **web:** unified header + done-state progress bar + capacity legend cap ([6d42233](https://github.com/pdugan20/clickwheel/commit/6d42233878d43eaeee4d38a2ab7a62176b1c58a0))
* **workbench:** live-progress simulation for sync-result preview ([faba9b3](https://github.com/pdugan20/clickwheel/commit/faba9b303804f126b381ff9068b49383bb427148))
* **workbench:** viewport + theme toggles, transparent iframe bg, claude chat bg ([1de4536](https://github.com/pdugan20/clickwheel/commit/1de45366400ab4097e30b5ecb8c4d964f025d807))


### Bug Fixes

* **ci:** exclude auto-generated _ui_bundles.py from ruff format check ([ab6b831](https://github.com/pdugan20/clickwheel/commit/ab6b8319bd7b93eb0ec4842ead541c53ea187926))
* **mcp:** handle classic-ipod auto-disconnect gracefully ([b5effce](https://github.com/pdugan20/clickwheel/commit/b5effceb9890afdf9395068e62e82b50cc86ad65))
* **mcp:** instruct the agent to check ipod state before curating a playlist for sync ([8efaafa](https://github.com/pdugan20/clickwheel/commit/8efaafa6fc22dc1933aa9bdbd2ee19d411eadd06))
* **mcp:** primary_artist now trusts album_artist instead of parsing strings ([cae3b23](https://github.com/pdugan20/clickwheel/commit/cae3b230c34c3d8eecca24b908e06daf17af2cfe))
* **mcp:** teach the model to stop fuzzy-searching n times for known tracks ([88cccd3](https://github.com/pdugan20/clickwheel/commit/88cccd3591641cde5df171623e31c548f92fe181))
* **web:** register ontoolresult before app.connect() so initial fixture renders ([852130b](https://github.com/pdugan20/clickwheel/commit/852130b234cacc6c1f567dadcaa7f8a6e0d46416))
* **web:** smooth out sync-result live progress + no end-of-sync flash ([d84c02c](https://github.com/pdugan20/clickwheel/commit/d84c02c283a64ca0cbf89ea5b1d6a1ae6bea39a9))
* **web:** workbench drops first fixture on initial mount ([d44bd82](https://github.com/pdugan20/clickwheel/commit/d44bd82d096b41df777e064014c5d4644aff479d))


### Documentation

* **mcp:** document inline ui bundles + web workspace workflow ([6b658e7](https://github.com/pdugan20/clickwheel/commit/6b658e7c7bbe39d5326466413e7e71e3ebfbdb9a))
* **mcp:** manual test script for the playlist redesign ([4cb48a5](https://github.com/pdugan20/clickwheel/commit/4cb48a52ef570f1efc0311a60f239bea62ff3c8c))
* **mcp:** refresh bundles + tool tables after recent feature work ([aea99b3](https://github.com/pdugan20/clickwheel/commit/aea99b33c7eea2a2d1e34a0fcabff4e952a282ef))
* **web:** note that fixtures must match post-tool output, not raw tags ([4e3fefa](https://github.com/pdugan20/clickwheel/commit/4e3fefa89a52916b1a6524037908e1e605219db4))

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
