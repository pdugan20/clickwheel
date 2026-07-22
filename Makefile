.PHONY: dev lint typecheck format test build clean check-all dev-web build-web lint-web format-web docs-reference docs docs-links

dev:
	uv sync --extra dev --extra mcp
	npm ci --prefix tools/ci
	uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

dev-web:
	cd web && npm ci
	cd web && npm run dev

lint:
	uv run ruff check clickwheel/
	uv run ruff format --check clickwheel/

typecheck:
	uv run mypy clickwheel

lint-web:
	cd web && npm run lint
	cd web && npm run typecheck

format:
	uv run ruff check --fix clickwheel/
	uv run ruff format clickwheel/

format-web:
	cd web && npm run format

# Regenerate the CLI + MCP tool reference + changelog (docs-mintlify/) from
# source. CI ("Docs Reference Freshness") fails if the committed output drifts.
docs-reference:
	uv run --extra mcp python scripts/gen-cli-reference.py
	uv run --extra mcp python scripts/gen-mcp-reference.py
	uv run python scripts/gen-changelog.py

# Live-preview the docs site with the same locked Mint CLI used by CI.
docs:
	cd docs-mintlify && ../tools/ci/node_modules/.bin/mint dev

# Check the docs for broken links (same as CI).
docs-links:
	cd docs-mintlify && ../tools/ci/node_modules/.bin/mint broken-links

test:
	uv run pytest tests/ -v

build: clean
	uv build

# Build the React UI bundles via Vite + emit clickwheel/mcp/_ui_bundles.py.
# Run this after editing anything under web/ before committing.
build-web:
	cd web && npm ci
	cd web && npm run build:bundles

clean:
	rm -rf dist/ build/ *.egg-info clickwheel/*.egg-info web/dist/

check-all: lint typecheck test
	shellcheck scripts/*.sh
	shfmt -d scripts/*.sh

# Releases are automated by release-please (.github/workflows/release-please.yml):
# merge conventional commits to main → it opens a release PR → merging that PR
# tags + publishes via publish.yml. Do not bump the version by hand
# (the no-manual-version-bump pre-commit hook enforces this).
