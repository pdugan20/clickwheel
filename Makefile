.PHONY: lint test build clean release release-dry release-patch release-minor release-major

lint:
	ruff check clickwheel/
	ruff format --check clickwheel/

test:
	python -m pytest tests/ -v

build: clean
	python -m build

clean:
	rm -rf dist/ build/ *.egg-info clickwheel/*.egg-info

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
