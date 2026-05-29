.PHONY: dev lint format test build clean check-all dev-web build-web lint-web format-web

dev:
	pip install -e '.[dev]'
	pre-commit install --hook-type pre-commit --hook-type commit-msg

dev-web:
	cd web && npm install
	cd web && npm run dev

lint:
	ruff check clickwheel/
	ruff format --check clickwheel/

lint-web:
	cd web && npm run lint
	cd web && npm run typecheck

format:
	ruff check --fix clickwheel/
	ruff format clickwheel/

format-web:
	cd web && npm run format

test:
	python -m pytest tests/ -v

build: clean
	python -m build

# Build the React UI bundles via Vite + emit clickwheel/mcp/_ui_bundles.py.
# Run this after editing anything under web/ before committing.
build-web:
	cd web && npm install
	cd web && npm run build:bundles

clean:
	rm -rf dist/ build/ *.egg-info clickwheel/*.egg-info web/dist/

check-all: lint test
	shellcheck scripts/*.sh
	shfmt -d scripts/*.sh

# Releases are automated by release-please (.github/workflows/release-please.yml):
# merge conventional commits to main → it opens a release PR → merging that PR
# tags + publishes via publish.yml. Do not bump the version by hand
# (the no-manual-version-bump pre-commit hook enforces this).
