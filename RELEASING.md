# Releasing

Releases are automated by [release-please](https://github.com/googleapis/release-please) — there are no local release commands.

1. Merge PRs to `main` with conventional commits (`feat:`, `fix:`, …).
2. release-please opens/updates a **release PR** that bumps `clickwheel/__init__.py` + `CHANGELOG.md`.
3. Merge that release PR → it tags `vX.Y.Z` and creates the GitHub Release.
4. The tag triggers `publish.yml`, which builds and publishes to PyPI via OIDC.

Never bump the version by hand (enforced by the `no-manual-version-bump` pre-commit hook).

See [`docs/releasing.md`](docs/releasing.md) for bump rules, configuration, test publishing, first-time setup, and troubleshooting.
