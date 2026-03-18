.PHONY: dev lint format test build clean check-all release release-dry release-patch release-minor release-major

dev:
	pip install -e '.[dev]'
	pre-commit install --hook-type pre-commit --hook-type commit-msg

lint:
	ruff check clickwheel/
	ruff format --check clickwheel/

format:
	ruff check --fix clickwheel/
	ruff format clickwheel/

test:
	python -m pytest tests/ -v

build: clean
	python -m build

clean:
	rm -rf dist/ build/ *.egg-info clickwheel/*.egg-info

check-all: lint test
	shellcheck scripts/*.sh
	shfmt -d scripts/*.sh

release-dry:
	semantic-release version --print

release:
	semantic-release version
	git push origin main --tags

release-patch:
	semantic-release version --patch
	git push origin main --tags

release-minor:
	semantic-release version --minor
	git push origin main --tags

release-major:
	semantic-release version --major
	git push origin main --tags
