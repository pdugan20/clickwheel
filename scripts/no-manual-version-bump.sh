#!/usr/bin/env bash
# Prevent manual edits to clickwheel/__init__.py:__version__ and
# .release-please-manifest.json. Both are owned by release-please.
#
# release-please commits arrive on a branch named
# release-please--branches--main--components--<component>; on that
# branch we let the edits through.

set -euo pipefail

branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

if [[ "$branch" == release-please--* ]]; then
    exit 0
fi

# Bail early if neither protected file is staged.
staged=$(git diff --cached --name-only)
if ! grep -qE '^(clickwheel/__init__\.py|\.release-please-manifest\.json)$' <<<"$staged"; then
    exit 0
fi

if git diff --cached -- clickwheel/__init__.py \
    | grep -qE '^\+__version__[[:space:]]*='; then
    cat >&2 <<'MSG'
ERROR: Manual __version__ bump detected in clickwheel/__init__.py.

This value is owned by release-please. Don't edit it by hand or in a
'chore: bump version' commit. Push your conventional commits to main
and let release-please-action open a 'chore(main): release X.Y.Z' PR.
Merging that PR is the only way __version__ should change.

(Bypass with --no-verify only as a real emergency. Don't make it a habit.)
MSG
    exit 1
fi

if git diff --cached -- .release-please-manifest.json | grep -qE '^[+-]'; then
    cat >&2 <<'MSG'
ERROR: Manual edit to .release-please-manifest.json detected.

This file tracks release-please's view of the current version. It
should only be modified by release-please-action when a release PR
merges.

(Bypass with --no-verify only as a real emergency.)
MSG
    exit 1
fi

exit 0
