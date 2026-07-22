"""Fail-closed policy checks for repository-owned GitHub automation."""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"

EXPECTED_WORKFLOW_PERMISSIONS = {
    "ci.yml": {"contents": "read"},
    "pr-lint.yml": {"pull-requests": "read"},
    "publish.yml": {"contents": "read", "id-token": "write"},
    "release-please.yml": {"contents": "write", "pull-requests": "write"},
    "test-publish.yml": {"contents": "read", "id-token": "write"},
    "version-guard.yml": {"contents": "read"},
}

EXPECTED_NPM_TOOLS = {
    "claude-code-lint": "0.7.0",
    "mint": "4.2.729",
    "prettier": "3.9.6",
}
EXPECTED_NPM_OVERRIDES = {
    "adm-zip": "0.6.0",
    "axios": "1.18.1",
    "js-yaml": "4.3.0",
    "qs": "6.15.3",
    "sharp": "0.35.3",
    "tar": "7.5.21",
}

PINNED_ACTION_COMMENTS = {
    "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0": "v7.0.0",
    "actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e": "v6.4.0",
    (
        "amannn/action-semantic-pull-request@48f256284bd46cdaab1048c3721360e808335d50"
    ): "v6.1.1",
    "astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990": "v8.3.2",
    "codecov/codecov-action@fb8b3582c8e4def4969c97caa2f19720cb33a72f": "v6.0.2",
    (
        "DavidAnson/markdownlint-cli2-action@ded1f9488f68a970bc66ea5619e13e9b52e601cd"
    ): "v23.2.0",
    (
        "googleapis/release-please-action@45996ed1f6d02564a971a2fa1b5860e934307cf7"
    ): "v5.0.0",
    ("pypa/gh-action-pypi-publish@ba38be9e461d3875417946c167d0b5f3d385a247"): "v1.14.1",
}

USES_LINE = re.compile(
    r"^\s*(?:-\s*)?uses:\s*['\"]?(?P<value>[^'\"\s#]+)['\"]?"
    r"\s*(?:#\s*(?P<comment>.*))?$"
)
EXTERNAL_ACTION = re.compile(r"^[^/@\s]+/[^@\s]+(?:/[^@\s]+)*@(?P<ref>[^\s]+)$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
FORBIDDEN_COMMANDS = (
    re.compile(r"\bgh\s+pr\s+merge\b", re.IGNORECASE),
    re.compile(r"\bgh\s+pr\s+review\b[^\n]*(?:--approve|-a)\b", re.IGNORECASE),
    re.compile(r"\benablePullRequestAutoMerge\b", re.IGNORECASE),
    re.compile(r"\b(?:merge|approve)PullRequest\b", re.IGNORECASE),
    re.compile(r"\baddPullRequestReview\b", re.IGNORECASE),
    re.compile(r"\bpulls?/[^\s]+/(?:merge|reviews)\b", re.IGNORECASE),
)
MUTABLE_INSTALLS = (
    re.compile(r"\bnpx\b"),
    re.compile(r"\bnpm\s+exec\b"),
    re.compile(r"\bnpm\s+(?:install|i|add)\b"),
    re.compile(r"@latest\b"),
    re.compile(r"\bpipx?\s+install\b"),
    re.compile(r"\buvx\b|\buv\s+tool\s+install\b"),
)


def workflow_paths() -> list[Path]:
    return sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])


def automation_paths() -> list[Path]:
    action_dir = ROOT / ".github" / "actions"
    return sorted(
        [
            *workflow_paths(),
            *action_dir.glob("**/action.yml"),
            *action_dir.glob("**/action.yaml"),
        ]
    )


def load_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text())
    assert isinstance(loaded, dict), f"{path.relative_to(ROOT)} must contain a mapping"
    return loaded


def iter_key_values(node: Any, key: str) -> Iterator[Any]:
    if isinstance(node, dict):
        for child_key, value in node.items():
            if child_key == key:
                yield value
            yield from iter_key_values(value, key)
    elif isinstance(node, list):
        for value in node:
            yield from iter_key_values(value, key)


def parsed_uses(path: Path) -> list[str]:
    return [
        value
        for value in iter_key_values(load_yaml(path), "uses")
        if isinstance(value, str)
    ]


def source_uses(path: Path) -> list[tuple[str, str | None]]:
    matches = []
    for line in path.read_text().splitlines():
        if match := USES_LINE.match(line):
            matches.append((match.group("value"), match.group("comment")))
    return matches


def local_action_exists(value: str) -> bool:
    target = (ROOT / value.removeprefix("./")).resolve()
    if ROOT not in target.parents:
        return False
    if target.is_file():
        return target.suffix in {".yml", ".yaml"}
    return any((target / name).is_file() for name in ("action.yml", "action.yaml"))


@pytest.mark.parametrize(
    "path", automation_paths(), ids=lambda path: str(path.relative_to(ROOT))
)
def test_every_action_reference_is_immutable_and_audited(path: Path) -> None:
    parsed = parsed_uses(path)
    sourced = source_uses(path)
    assert Counter(parsed) == Counter(value for value, _ in sourced), (
        f"{path.relative_to(ROOT)} has a uses reference that is not a single "
        "auditable line"
    )

    for value, comment in sourced:
        if value.startswith("./"):
            assert local_action_exists(value), (
                f"missing local action or workflow: {value}"
            )
            continue
        if value.startswith("docker://"):
            assert re.search(r"@sha256:[0-9a-f]{64}$", value), (
                f"container action must use a sha256 digest: {value}"
            )
            continue

        match = EXTERNAL_ACTION.fullmatch(value)
        assert match, f"dynamic or malformed action reference: {value}"
        assert FULL_SHA.fullmatch(match.group("ref")), (
            f"external action must use a full commit SHA: {value}"
        )
        assert value in PINNED_ACTION_COMMENTS, f"unaudited action pin: {value}"
        assert comment == PINNED_ACTION_COMMENTS[value], (
            f"version comment for {value} must be '# {PINNED_ACTION_COMMENTS[value]}'"
        )


def test_action_pin_allowlist_contains_no_unused_entries() -> None:
    observed = {
        value
        for path in automation_paths()
        for value in parsed_uses(path)
        if not value.startswith(("./", "docker://"))
    }
    assert observed == PINNED_ACTION_COMMENTS.keys()


def test_workflow_set_and_permissions_are_explicit_and_minimal() -> None:
    actual = {path.name for path in workflow_paths()}
    assert actual == EXPECTED_WORKFLOW_PERMISSIONS.keys()

    for path in workflow_paths():
        workflow = load_yaml(path)
        assert workflow.get("permissions") == EXPECTED_WORKFLOW_PERMISSIONS[path.name]
        for job_name, job in workflow.get("jobs", {}).items():
            assert "permissions" not in job, (
                f"{path.name}:{job_name} must use the audited workflow-level "
                "permissions"
            )


def test_checkout_credentials_are_disabled_except_for_the_release_push() -> None:
    checkout = "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"
    for path in workflow_paths():
        workflow = load_yaml(path)
        for job_name, job in workflow.get("jobs", {}).items():
            for step in job.get("steps", []):
                if step.get("uses") != checkout:
                    continue
                is_release_push = (
                    path.name == "release-please.yml"
                    and step.get("name") == "Check out the release PR branch"
                )
                expected = is_release_push
                assert step.get("with", {}).get("persist-credentials") is expected, (
                    f"{path.name}:{job_name}:{step.get('name', 'checkout')} must set "
                    f"persist-credentials: {str(expected).lower()}"
                )


def test_no_repository_workflow_can_merge_or_approve_pull_requests() -> None:
    for path in automation_paths():
        for command in iter_key_values(load_yaml(path), "run"):
            assert isinstance(command, str)
            for forbidden in FORBIDDEN_COMMANDS:
                assert not forbidden.search(command), (
                    f"{path.name} contains a merge or approval operation: "
                    f"{forbidden.pattern}"
                )


def test_ci_tools_are_locked_and_downloads_are_checksum_verified() -> None:
    for path in automation_paths():
        for command in iter_key_values(load_yaml(path), "run"):
            assert isinstance(command, str)
            for mutable in MUTABLE_INSTALLS:
                assert not mutable.search(command), (
                    f"{path.name} uses mutable tool acquisition: {mutable.pattern}"
                )
            assert not re.search(r"\b(?:curl|wget)\b", command), (
                f"{path.name} must delegate downloads to a checksum-verified script"
            )

    installer = ROOT / ".github" / "scripts" / "install-shfmt.sh"
    source = installer.read_text()
    assert 'readonly SHFMT_VERSION="3.10.0"' in source
    assert (
        'readonly SHFMT_SHA256="1f57a384d59542f8fac5f503da1f3ea44242f46dff'
        '969569e80b524d64b71dbc"' in source
    )
    assert "sha256sum --check" in source
    assert "curl --fail" in source

    for script in sorted((ROOT / ".github" / "scripts").glob("*.sh")):
        source = script.read_text()
        for mutable in MUTABLE_INSTALLS:
            assert not mutable.search(source), (
                f"{script.relative_to(ROOT)} uses mutable tool acquisition: "
                f"{mutable.pattern}"
            )
        if re.search(r"\b(?:curl|wget)\b", source):
            assert "sha256sum --check" in source
            assert re.search(r'readonly [A-Z_]*SHA256="[0-9a-f]{64}"', source)

    for entrypoint in (ROOT / "Makefile", ROOT / ".pre-commit-config.yaml"):
        source = entrypoint.read_text()
        for mutable in MUTABLE_INSTALLS:
            assert not mutable.search(source), (
                f"{entrypoint.relative_to(ROOT)} uses mutable tool acquisition: "
                f"{mutable.pattern}"
            )


def test_ci_npm_tools_and_security_overrides_are_integrity_locked() -> None:
    package = json.loads((ROOT / "tools" / "ci" / "package.json").read_text())
    lock = json.loads((ROOT / "tools" / "ci" / "package-lock.json").read_text())

    assert package["devDependencies"] == EXPECTED_NPM_TOOLS
    assert package["overrides"] == EXPECTED_NPM_OVERRIDES
    assert lock["lockfileVersion"] == 3
    assert lock["packages"][""]["devDependencies"] == EXPECTED_NPM_TOOLS

    for location, metadata in lock["packages"].items():
        if not location or metadata.get("link"):
            continue
        assert "integrity" in metadata, f"{location} lacks registry integrity metadata"

    for package_name, expected_version in EXPECTED_NPM_OVERRIDES.items():
        matches = [
            metadata["version"]
            for location, metadata in lock["packages"].items()
            if location.endswith(f"node_modules/{package_name}")
        ]
        assert matches, f"override target is no longer installed: {package_name}"
        assert set(matches) == {expected_version}


def test_setup_uv_and_node_select_exact_tool_versions() -> None:
    setup_uv = "astral-sh/setup-uv@11f9893b081a58869d3b5fccaea48c9e9e46f990"
    setup_node = "actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e"
    for path in automation_paths():
        for node in iter_key_values(load_yaml(path), "steps"):
            if not isinstance(node, list):
                continue
            for step in node:
                if not isinstance(step, dict):
                    continue
                if step.get("uses") == setup_uv:
                    assert step.get("with", {}).get("version") == "0.11.17"
                if step.get("uses") == setup_node:
                    version = step.get("with", {}).get("node-version")
                    version_file = step.get("with", {}).get("node-version-file")
                    assert version == "22.23.1" or version_file == ".nvmrc"

    assert (ROOT / ".nvmrc").read_text().strip() == "22.23.1"


def test_markdownlint_excludes_generated_and_internal_documents_consistently() -> None:
    config = load_yaml(ROOT / ".pre-commit-config.yaml")
    hooks = {
        hook["id"]: hook
        for repository in config["repos"]
        for hook in repository["hooks"]
    }
    assert hooks["markdownlint"]["exclude"] == (r"^(CHANGELOG\.md|docs/superpowers/)")

    ci = load_yaml(WORKFLOW_DIR / "ci.yml")
    globs = ci["jobs"]["markdownlint"]["steps"][1]["with"]["globs"]
    assert "!CHANGELOG.md" in globs
    assert "!docs/superpowers" in globs
