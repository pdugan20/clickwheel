# Release Pipeline Reference

How a release flows from commit to PyPI, step by step.

## Overview

```text
Developer                     GitHub Actions              PyPI / GitHub
─────────                     ──────────────              ─────────────

1. Write code
2. Commit (conventional)
3. `make release`
   ├─ semantic-release
   │  ├─ reads git log
   │  ├─ determines bump
   │  ├─ updates version
   │  ├─ generates changelog
   │  ├─ commits + tags
   │  └─ pushes to origin ──► tag push triggers ──────►
                               publish.yml
                               ├─ build wheel ──────────► PyPI package
                               └─ create release ───────► GitHub release
```

## Step 1: Local — Developer Commits

All commits follow Conventional Commits format:

```text
feat: add playlist export to m3u files
fix: handle missing album art gracefully
docs: update install instructions
chore: update dependencies
```

commitlint enforces this via pre-commit hook on the commit-msg stage.

## Step 2: Local — Developer Runs Release

```bash
make release          # auto-detect bump from commits
make release-dry      # preview without doing anything
make release-patch    # force patch bump
make release-minor    # force minor bump
make release-major    # force major bump
```

Under the hood, `make release` runs:

```bash
semantic-release version    # bump, changelog, commit, tag
git push && git push --tags # trigger CI
```

semantic-release does the following:

1. Reads commits since the last `v*` tag
2. Determines bump type: `feat:` → minor, `fix:` → patch, `BREAKING CHANGE:` → major
3. Updates version in `pyproject.toml` and `clickwheel/__init__.py`
4. Prepends new section to `CHANGELOG.md`
5. Creates commit: `chore: release v0.3.0`
6. Creates annotated tag: `v0.3.0`

## Step 3: CI — Tag Push Triggers Publish

`.github/workflows/publish.yml` runs on `v*` tag push.

### Job 1: Publish to PyPI

```yaml
- Checkout tagged commit
- Setup Python 3.11
- pip install build
- python -m build # creates dist/clickwheel-0.3.0-py3-none-any.whl
- Publish via pypa/gh-action-pypi-publish (OIDC, no tokens)
```

### Job 2: Create GitHub Release

```yaml
- Checkout with full history
- Extract version from tag name
- Parse CHANGELOG.md for this version's section
- gh release create v0.3.0 --notes "..."
```

## Step 4: Users Install

```bash
pipx install clickwheel            # base install
pipx install clickwheel[artwork]   # with album art support
```

## PyPI Trusted Publishing Setup

One-time configuration on pypi.org:

1. Log in at pypi.org
2. Go to "Your projects" > "Publishing" > "Add a new pending publisher"
3. Fill in:
   - PyPI project name: `clickwheel`
   - Owner: `pdugan20`
   - Repository: `clickwheel`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
4. Create a `pypi` environment in GitHub repo settings (Settings > Environments)

After this, the publish workflow authenticates via OIDC — no API tokens needed.

## Troubleshooting

### Tag pushed but publish workflow didn't run

Check that the workflow trigger matches:

```yaml
on:
  push:
    tags: ['v*']
```

And that the tag starts with `v` (e.g., `v0.3.0`, not `0.3.0`).

### Publish workflow ran but PyPI rejected the upload

- Check that trusted publishing is configured for the exact workflow file name
- Check that the GitHub environment name matches (`pypi`)
- Check that the package name isn't already taken on PyPI

### GitHub release created but changelog is empty

The changelog extraction uses sed to pull the section between two `## v` headings. If the CHANGELOG.md format doesn't match, the extraction fails silently. Verify the format:

```markdown
## v0.3.0

### Features

- Add playlist export

## v0.2.0

...
```

### Need to redo a release

```bash
# Delete the tag locally and remotely
git tag -d v0.3.0
git push origin :refs/tags/v0.3.0

# Delete the GitHub release (if created)
gh release delete v0.3.0 --yes

# Fix the issue, then re-run
make release
```

### Need to publish manually (CI is broken)

```bash
python -m build
pip install twine
twine upload dist/*   # will prompt for PyPI credentials
```
