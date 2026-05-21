"""Apple Music integration tools.

One read-only tool for now:

- `apple_music_health` — probe the Apple Music integration end-to-end
  (config, .p8, dev token signing, catalog reachable, user token
  validity, iCloud Music Library state, storefront agreement). Mirrors
  `plex_health`'s shape.

Push/pull tools land in follow-up PRs. Logic lives in `actions.py` per
CLAUDE.md rule 11.
"""

from __future__ import annotations

import logging

from clickwheel import actions
from clickwheel.mcp._runtime import READ_ONLY, mcp, open_session, render
from clickwheel.mcp.models import AppleMusicHealth

logger = logging.getLogger(__name__)


@mcp.tool(title="Apple Music health", annotations=READ_ONLY)
def apple_music_health() -> AppleMusicHealth:
    """Probe the Apple Music integration end-to-end without changing
    anything.

    Walks (up to) nine stages: config (enabled + key id + team id +
    .p8 path), the `[applemusic]` extra installed, .p8 readable,
    developer-token signing, catalog reachability with that token,
    Music User Token present, user token verified against
    /v1/me/storefront, iCloud Music Library state, and storefront
    agreement between config and the user's actual region.

    When to use: the user reports the Apple Music side isn't working,
    or before any future push/pull tool to confirm setup. Cheap to
    call; safe to repeat.

    After this: if any stage fails, surface the failing stage's detail
    verbatim — it's already written to be actionable (config keys,
    install commands, hints to re-run `clickwheel apple auth`).
    """
    with open_session() as (cfg, _db):
        result = actions.apple_music_doctor(cfg)

    stages = [{"name": s.name, "ok": s.ok, "detail": s.detail} for s in result.stages]
    if result.ok:
        text = "Apple Music is configured, reachable, and authorized."
    else:
        first_failure = next((s for s in result.stages if not s.ok), None)
        if first_failure is None:
            text = "Apple Music doctor produced no stages."
        else:
            text = (
                f"Apple Music doctor failed at stage {first_failure.name!r}: "
                f"{first_failure.detail}"
            )
    return render(text, {"ok": result.ok, "stages": stages})
