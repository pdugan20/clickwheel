# Releasing

clickwheel uses [python-semantic-release](https://python-semantic-release.readthedocs.io/) for automated versioning based on conventional commits.

## How It Works

Semantic-release reads commit messages since the last tag and determines the next version:

- `fix:` commits bump the **patch** version (0.4.0 -> 0.4.1)
- `feat:` commits bump the **minor** version (0.4.0 -> 0.5.0)
- `BREAKING CHANGE:` in the commit body bumps the **major** version (0.4.0 -> 1.0.0)
- `chore:`, `docs:`, `style:`, `refactor:`, `test:` commits do **not** trigger a release

## Release Commands

```bash
# Preview what the next version would be (no changes)
make release-dry

# Auto-detect version bump from commits and release
make release

# Force a specific bump level
make release-patch
make release-minor
make release-major
```

## What Happens During a Release

1. Semantic-release reads commits since the last tag
2. Determines the version bump (patch/minor/major)
3. Updates `clickwheel/__init__.py` with the new version
4. Updates `CHANGELOG.md` with release notes
5. Creates a commit: `chore: release vX.Y.Z`
6. Tags the commit: `vX.Y.Z`
7. `make release` then pushes to `origin main --tags`

## Publishing to PyPI

The `publish.yml` GitHub Action triggers on new tags matching `v*`. It builds the package and uploads to PyPI.

To test a release before publishing:

1. Go to Actions > Test Publish
2. Manually trigger the workflow
3. It publishes to TestPyPI for validation

## Configuration

Release settings are in `pyproject.toml` under `[tool.semantic_release]`:

- `version_variables`: where the version string lives in code
- `build_command`: how to build the package
- `changelog_file`: where to write the changelog
- `branches.main`: only releases from the main branch
