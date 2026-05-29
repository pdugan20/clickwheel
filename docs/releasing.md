# Releasing

clickwheel uses [release-please](https://github.com/googleapis/release-please)
for automated versioning and changelog generation from
[Conventional Commits](https://www.conventionalcommits.org/). Releases are
driven entirely by GitHub Actions — **there are no local release commands and
you never bump the version by hand** (the `no-manual-version-bump` pre-commit
hook enforces this).

## How it works

1. Merge PRs to `main` using conventional commit messages (`feat:`, `fix:`, etc.).
2. On each push to `main`, `release-please` (`.github/workflows/release-please.yml`)
   opens or updates a **release PR** that bumps the version in
   `clickwheel/__init__.py` and updates `CHANGELOG.md` from the commits since the
   last release.
3. When you **merge the release PR**, release-please tags `vX.Y.Z` and creates
   the GitHub Release with the changelog notes.
4. The tag push triggers `publish.yml`, which builds the wheel and publishes to
   PyPI via OIDC trusted publishing (no tokens).

## Version bump rules

Determined from commit types since the last release:

- `fix:` → **patch** (0.4.0 → 0.4.1)
- `feat:` → **minor** (0.4.0 → 0.5.0)
- `feat!:` / `fix!:` or a `BREAKING CHANGE:` footer → **major** (0.4.0 → 1.0.0)
- `chore:`, `docs:`, `style:`, `refactor:`, `test:`, `build:`, `ci:` → no version
  bump (they may still appear in the changelog)

## Configuration

- `release-please-config.json` — release type (`python`), package name,
  changelog path, and the `extra-files` entry that keeps
  `clickwheel/__init__.py` in sync.
- `.release-please-manifest.json` — the current released version (the source of
  truth release-please reads/writes).
- `pyproject.toml` `[tool.hatch.version]` reads the version dynamically from
  `clickwheel/__init__.py`, so the package, the manifest, and the tag stay
  aligned.

## Test publishing

To validate a build before a real release: **Actions → Test Publish** → run the
workflow manually. It publishes to TestPyPI.

## First-time setup (one-time)

1. **PyPI account** at [pypi.org](https://pypi.org); the first publish claims the
   `clickwheel` name.
2. **OIDC trusted publishing** on PyPI → Publishing → add a pending publisher:
   Owner `pdugan20`, Repository `clickwheel`, Workflow `publish.yml`, Environment
   `pypi`.
3. **GitHub environment** `pypi` in repo Settings → Environments.
4. **`RELEASE_PLEASE_TOKEN`** secret — a PAT so the release-PR merge's tag push
   cascades into `publish.yml` (the default `GITHUB_TOKEN` does not trigger
   downstream workflows).

## Troubleshooting

- **Publish fails with 403** — OIDC trust mismatch. The PyPI trusted publisher
  must match the repo owner, repo name, workflow filename (`publish.yml`), and
  environment (`pypi`) exactly.
- **No release PR appeared** — there were no release-worthy commits since the
  last release (only `chore:`/`docs:`/etc.), or the messages weren't conventional.
- **Wrong version in the package** — the single source of truth is
  `clickwheel/__init__.py` (kept in sync by release-please's `extra-files`);
  don't edit it by hand.
