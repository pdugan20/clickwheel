# Contributing

## Setup

Install [uv](https://docs.astral.sh/uv/) first (`brew install uv` or the
[standalone installer](https://docs.astral.sh/uv/getting-started/installation/)),
then:

```bash
git clone https://github.com/pdugan20/clickwheel.git
cd clickwheel
make dev
```

This runs `uv sync` (dev + mcp extras) and sets up pre-commit hooks. Run tools
via `uv run …` (e.g. `uv run pytest`), or use the `make` targets.

## Running Tests

```bash
make test
```

Tests run with coverage reporting. The minimum threshold is 30% (excluding vendored `clickwheel/ipod/`).

## Linting and Formatting

```bash
make lint                            # check only
make format                          # auto-fix
make check-all                       # lint + test + shellcheck + shfmt
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

## Documentation

The docs site (Mintlify) lives in `docs-mintlify/`. The **CLI** and **MCP tool**
reference pages are **generated from source** — never edit them by hand:

```bash
make docs-reference   # regenerate reference/cli.mdx + reference/mcp-tools.mdx
make docs             # live-preview (needs the Mintlify CLI: npm i -g mint)
make docs-links       # check for broken links
```

If you add/change a CLI command or MCP tool, run `make docs-reference` and
commit the result — CI ("Docs Reference Freshness") fails if the committed
reference has drifted from the code. See
[docs/projects/docs-site/](docs/projects/docs-site/) for the plan.

## Building

```bash
make build
```

## Releasing

See [docs/releasing.md](docs/releasing.md) for how versioning and releases work.

## Pre-push Checks

Run the full validation suite before pushing:

```bash
./scripts/pre-push-checks.sh
```

This checks lint, tests, shell scripts, and debug artifacts.
