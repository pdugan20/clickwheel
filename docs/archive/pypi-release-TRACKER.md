# PyPI Release Project Tracker

Get clickwheel ready for public release on PyPI so anyone can `pipx install clickwheel`.

## Phase 1: Package Fixes

Make the installed package work outside of a dev checkout.

- [x] Add `__init__.py` to vendored subdirs (itunesdb_parser, itunesdb_writer, artworkdb_writer)
- [x] Fix `_find_project_root()` — renamed to `_find_data_dir()`, falls back to `~/.clickwheel/` for installed users
- [x] Fix `fix` command — rewritten to call `beet` directly via subprocess, no shell script dependency
- [x] Add macOS platform guard — checks `sys.platform` in `main()` callback
- [x] Make numpy optional — moved Pillow/numpy to `[artwork]` extra, ImportError handled gracefully with install hint
- [x] Verify the built wheel works end-to-end — wheel builds, installs into clean venv, `--help` and `--version` work

## Phase 2: Testing

No tests exist today. Add enough coverage to catch breakage before releases.

- [x] Create `tests/` directory with `conftest.py` (shared fixtures: temp music dir, temp db, mock config)
- [x] Smoke tests — `clickwheel --help` exits 0, `clickwheel --version` prints version, every command's `--help` works
- [x] Unit tests for `db.py` — upsert_track, get_stats, save_playlist, delete_playlist, add/remove artist, playlist size calculations
- [x] Unit tests for `output.py` — each helper produces the expected Rich markup (capture console output)
- [x] Unit tests for `config.py` — priority chain (env > .env > config.yaml), missing MUSIC_DIR error, `_parse_yaml` edge cases
- [x] Unit tests for `library.py` — scan_file with real tagged audio fixtures (create small .mp3 test files with mutagen)
- [x] Unit tests for `_fmt_size`, `_calc_size`, `_print_capacity_bar` logic
- [x] Unit tests for `scrobble.py` — cache_scrobbles dedup logic, timestamp estimation, pending scrobble filtering
- [x] Integration test for `scan` command — create temp dir with tagged files, run scan, verify db contents
- [x] Add pytest + pytest-cov to dev dependencies in `pyproject.toml`
- [x] Add test job to CI workflow (`ci.yml`) — run pytest on ubuntu and macos
- [x] Verify all tests pass locally before moving on

## Phase 3: Packaging Metadata

Make the PyPI listing informative and discoverable.

- [x] Add PyPI classifiers to `pyproject.toml`:
  - `Environment :: Console`
  - `Operating System :: MacOS`
  - `Topic :: Multimedia :: Sound/Audio`
  - `License :: OSI Approved :: MIT License`
  - `Programming Language :: Python :: 3.11`
  - `Programming Language :: Python :: 3.12`
  - `Intended Audience :: End Users/Desktop`
- [x] Add `project.urls` to `pyproject.toml` — Homepage, Repository, Issues, Changelog
- [x] Set up dynamic versioning — single source of truth. Configure hatchling to read version from `clickwheel/__init__.py` so we stop maintaining it in two places.
- [x] Add `[project.optional-dependencies]` for artwork extra: `artwork = ["Pillow>=10.0", "numpy>=1.24"]`. Move Pillow and numpy out of base dependencies.
- [x] Add `[project.optional-dependencies]` for dev extra: `dev = ["pytest", "pytest-cov", "ruff"]`
- [x] Verify `python -m build` produces a clean wheel with correct metadata: `unzip -l dist/*.whl` should show all clickwheel files, no junk.

## Phase 4: README Rewrite

The README is stale (references libgpod, wrong project structure, dev-oriented). Rewrite for end users.

- [x] Update description — emphasize what it does for users, not how it's built
- [x] Add install instructions for end users: `pipx install clickwheel` (or `pip install clickwheel`)
- [x] Update commands table — add `delete`, `edit`, `scrobble` commands, update descriptions to match new consumer-friendly voice
- [x] Update configuration section — document `~/.clickwheel/config.yaml` as the primary config method, `.env` as alternative
- [x] Update project structure section — removed (dev detail, not needed for users; covered in Contributing section)
- [x] Update stack section — replace libgpod with iOpenPodv2 (vendored), add pylast
- [x] Add Last.fm scrobbling section
- [x] Add badges — PyPI version, downloads, Python version
- [x] Remove git clone instructions from Quick Start (that's for contributors, not users)
- [x] Add a "Contributing" section pointing to dev setup

## Phase 5: Commit Enforcement

Conventional commits so changelogs generate automatically.

- [x] Add commitlint pre-commit hook (reuse config pattern from claudelint)
- [x] Create `.commitlintrc.json` — conventional config, max header 100 chars, lowercase subject
- [x] Update existing pre-commit config to include commit-msg stage hook
- [x] Document commit message format in a `CONTRIBUTING.md` (feat, fix, docs, chore, etc.)
- [ ] Retroactively tag current state as `v0.1.0` if not already tagged
- [x] Verify commitlint rejects bad messages and passes good ones locally

## Phase 6: Release Tooling

Automate version bumps, changelog, and git tagging.

- [x] Install and configure `python-semantic-release` in `pyproject.toml`:
  - `version_variables` pointing to `clickwheel/__init__.py:__version__`
  - `build_command = "python -m build"`
  - `commit_message = "chore: release v{version}"`
  - Changelog output to `CHANGELOG.md`
  - Branch config for `main`
- [x] Create initial `CHANGELOG.md` with existing history (manual summary of phases 1-7)
- [x] Add release targets to `Makefile`:
  - `make release` — run semantic-release version, push commit + tag
  - `make release-dry` — preview what would happen
  - `make lint` — ruff check + format
  - `make test` — pytest
  - `make build` — python -m build
  - `make clean` — remove dist/, build/, egg-info
- [ ] Test full local release flow: `make release-dry` shows correct version bump and changelog preview
- [ ] Run first real release: `make release` to create `v0.2.0` tag (0.1.0 is the pre-release state)

## Phase 7: CI Publish Pipeline

Automate PyPI publishing and GitHub releases on tag push.

- [ ] Create PyPI account at pypi.org (manual)
- [ ] Register `clickwheel` as a pending package name (manual, first-come-first-served)
- [ ] Configure OIDC trusted publishing on PyPI: owner=`pdugan20`, repo=`clickwheel`, workflow=`publish.yml`, environment=`pypi` (manual)
- [ ] Create `pypi` environment in GitHub repo settings: Settings > Environments > New (manual)
- [x] Create `.github/workflows/publish.yml`:
  - Trigger on `v*` tag push
  - Job 1: Build + publish to PyPI via `pypa/gh-action-pypi-publish` (OIDC, no tokens)
  - Job 2: Extract changelog section for this version, create GitHub release with notes
- [ ] Add branch ruleset for `main` requiring CI pass (manual)
- [ ] Test the full pipeline:
  - Push a tag manually: `git tag v0.2.0 && git push origin v0.2.0`
  - Verify publish workflow runs, package appears on PyPI
  - Verify GitHub release is created with correct changelog section
  - Verify `pipx install clickwheel` works from PyPI in a clean environment
- [x] Add PyPI badge to README

## Phase 8: Post-Release

Polish after the first public release is live.

- [ ] Test install from PyPI on a clean Mac (no dev checkout)
- [ ] Run `clickwheel scan`, `clickwheel select`, `clickwheel sync` end-to-end from the PyPI install
- [ ] Fix any issues found during clean-install testing
- [x] Add a `RELEASING.md` doc with the full release checklist and troubleshooting
- [x] Add `make release-patch`, `make release-minor`, `make release-major` convenience targets
- [ ] Consider TestPyPI for pre-release validation in future releases
- [ ] Announce on relevant communities (r/ipod, r/commandline, etc.)
