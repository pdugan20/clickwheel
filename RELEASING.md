# Releasing

## How Releases Work

1. Merge PRs to `main` using conventional commit messages (`feat:`, `fix:`, etc.)
2. Run `make release` locally (or `make release-minor` / `make release-patch` for explicit bumps)
3. `python-semantic-release` determines the version bump from commit history
4. It updates `clickwheel/__init__.py`, `CHANGELOG.md`, commits, and tags
5. `git push origin main --tags` triggers the `publish.yml` workflow
6. GitHub Actions builds the wheel and publishes to PyPI via OIDC (no tokens)
7. A GitHub Release is created with changelog notes

## Quick Reference

```bash
make release-dry     # preview what would happen (no changes)
make release         # auto-determine bump from commits, tag, and push
make release-patch   # force a patch bump (0.1.0 -> 0.1.1)
make release-minor   # force a minor bump (0.1.0 -> 0.2.0)
make release-major   # force a major bump (0.1.0 -> 1.0.0)
```

## First-Time Setup

These are one-time steps before the first publish:

1. **PyPI account**: Create at [pypi.org](https://pypi.org)
2. **Reserve package name**: First publish claims the `clickwheel` name
3. **OIDC trusted publishing**: On PyPI, go to your account settings > Publishing > Add a new pending publisher:
   - Owner: `pdugan20`
   - Repository: `clickwheel`
   - Workflow: `publish.yml`
   - Environment: `pypi`
4. **GitHub environment**: In repo Settings > Environments, create `pypi`
5. **Branch ruleset**: Add required status checks for `main` so releases have a quality gate

## Troubleshooting

### Publish workflow fails with 403

OIDC trust isn't set up. Check that the PyPI trusted publisher matches the
GitHub repo owner, repo name, workflow filename, and environment name exactly.

### Version wasn't bumped

`python-semantic-release` only bumps when it finds conventional commit messages
since the last tag. Commits like "update thing" are ignored. Use `feat:`, `fix:`,
etc.

### Wrong version in package

The single source of truth is `clickwheel/__init__.py`. The `pyproject.toml`
reads it dynamically via `[tool.hatch.version]`. If they're out of sync,
update `__init__.py` and rebuild.

### Changelog section not extracted

The `publish.yml` workflow extracts the changelog section matching the tag version.
Make sure `CHANGELOG.md` has a heading like `## v0.2.0` (matching the tag `v0.2.0`).
