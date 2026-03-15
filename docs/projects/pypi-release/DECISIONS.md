# PyPI Release — Design Decisions

Key decisions and rationale for the public release work.

## Platform Support

**macOS only.** The iPod sync workflow depends on `diskutil`, `/Volumes/` mount detection, and Finder-oriented error messages. Linux iPod users exist but are a different audience with different tooling (they already use libgpod directly). Adding Linux support would require abstracting the mount/eject layer behind a platform interface, which isn't worth the complexity for v1.

**Guard, don't crash.** Rather than letting macOS-specific calls fail with cryptic errors on Linux, detect the platform early and exit with a clear message.

## Dependency Strategy

**numpy is optional.** It's only used for RGB565 artwork conversion in the vendored ArtworkDB writer. At ~30MB installed, it's a heavy tax for users who don't need album art on their iPod. Move it (and Pillow) to an `artwork` extra: `pipx install clickwheel[artwork]`.

**Base install should be lightweight.** The core dependencies (typer, rich, tqdm, mutagen, pylast) are all small and well-maintained. A base install should be under 20MB.

## Vendored Code

**Keep vendoring iOpenPodv2.** The alternatives (forking to a separate PyPI package, contributing upstream) all add maintenance overhead for a niche dependency. The vendored code is MIT-licensed, ~2,000 lines, and stable. The ruff exclusions are an acceptable tradeoff.

**`__init__.py` files already exist** in all vendored subdirs — verified during project setup.

## Project Root vs. User Data Dir

**Installed packages don't have a project root.** The current `_find_project_root()` walks up from cwd looking for `pyproject.toml`, which only works in a dev checkout. For installed users, use `~/.clickwheel/` as the data directory (it already exists for config). The db file (`clickwheel.db`) should live there.

**Detection order:** If `pyproject.toml` is found in an ancestor dir, use that (editable dev install). Otherwise, use `~/.clickwheel/`.

## The `fix` Command

**Rewrite in Python, don't bundle the shell script.** `pip install` only installs Python packages, not repo scripts. Bundling `fix-metadata.sh` as package data is fragile (it depends on beets being installed, BEETSDIR being set, etc.). Better to invoke beets directly from Python using `subprocess.run(["beet", "import", ...])` with the right arguments. This also makes `--dry-run` more reliable.

## Testing Strategy

**Test the logic, not the hardware.** Unit tests cover db operations, config loading, size formatting, scrobble caching — all pure Python with no iPod dependency. The iPod sync path is tested manually on real hardware; mocking the iPod filesystem would be brittle and low-value.

**Audio fixtures should be tiny.** Use mutagen to create minimal valid .mp3 files (a few KB each) as test fixtures. Don't commit real music files.

**CI runs on both ubuntu and macos.** The platform guard should make non-macOS tests skip iPod-specific commands gracefully, but db/config/scan tests should pass everywhere.

## Release Tooling

**python-semantic-release over manual tagging.** It reads conventional commits, determines the version bump automatically, generates a changelog, and creates the git tag. This mirrors the release-it setup in claudelint but in the Python ecosystem.

**OIDC trusted publishing over stored tokens.** PyPI supports the same OIDC flow as npm. The GitHub Actions workflow authenticates directly with PyPI — no API tokens to rotate or leak.

**Makefile over custom scripts.** Python doesn't have `npm run`. A Makefile with `release`, `test`, `lint`, `build` targets is the standard approach for Python projects. Keep it simple — no nox/tox/invoke unless complexity demands it.

## Version Management

**Single source of truth in `__init__.py`.** Configure hatchling to read the version from `clickwheel/__init__.py:__version__`. python-semantic-release updates both `pyproject.toml` and `__init__.py` automatically via `version_toml` and `version_variables` config.

## README Audience

**End users first, contributors second.** The README should lead with `pipx install clickwheel` and the user workflow. Dev setup goes in a "Contributing" section at the bottom or in a separate `CONTRIBUTING.md`. The current README is dev-oriented (starts with `git clone`) and references stale internals (libgpod, selector.py).
