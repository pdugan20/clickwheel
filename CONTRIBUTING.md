# Contributing

## Setup

```bash
git clone https://github.com/pdugan20/clickwheel.git
cd clickwheel
pip install -e '.[dev]'
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

## Running Tests

```bash
python -m pytest tests/ -v
```

## Commit Messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/).
Commitlint enforces this via a pre-commit hook.

### Format

```text
<type>: <description>
```

### Types

- **feat** — new feature or command
- **fix** — bug fix
- **docs** — documentation changes
- **chore** — maintenance, dependencies, CI
- **refactor** — code changes that don't add features or fix bugs
- **test** — adding or updating tests
- **style** — formatting, linting fixes

### Examples

```text
feat: add scrobble command for Last.fm play tracking
fix: correct playlist artist grouping in SQL query
docs: update README install instructions for pipx
chore: add pytest CI job for ubuntu and macos
test: add unit tests for scrobble dedup logic
```

### Rules

- Use lowercase for the subject line
- Keep the header under 100 characters
- No period at the end of the subject

## Linting

```bash
ruff check clickwheel/
ruff format clickwheel/
```

## Building

```bash
python -m build
```
