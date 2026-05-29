.PHONY: dev lint typecheck format test build clean check-all dev-web build-web lint-web format-web

dev:
	uv sync --extra dev --extra mcp
	uv run pre-commit install --hook-type pre-commit --hook-type commit-msg

dev-web:
	cd web && npm install
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

test:
	uv run pytest tests/ -v

build: clean
	uv build

# Build the React UI bundles via Vite + emit clickwheel/mcp/_ui_bundles.py.
# Run this after editing anything under web/ before committing.
build-web:
	cd web && npm install
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
