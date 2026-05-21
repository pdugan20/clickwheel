"""Apple Music integration tools.

- `apple_music_health` — read-only end-to-end probe. Run before push.
- `sync_playlist_to_apple_music` — destructive (creates a new playlist
  in the user's Apple Music account). Confirms via the native Allow /
  Deny prompt that destructive-flagged tools get.

Logic lives in `actions.py` per CLAUDE.md rule 11.
"""

from __future__ import annotations

import logging
from typing import Annotated

from pydantic import Field

from clickwheel import actions
from clickwheel.actions import (
    AppleMusicExtraNotInstalledError,
    AppleMusicKeyFileError,
    AppleMusicNoMatchesError,
    AppleMusicNotConfiguredError,
    AppleMusicUnreachableError,
    PlaylistNotFoundError,
)
from clickwheel.mcp._runtime import DESTRUCTIVE, READ_ONLY, mcp, open_session, render
from clickwheel.mcp.models import AppleMusicHealth, AppleMusicPushResult

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


@mcp.tool(title="Sync playlist to Apple Music", annotations=DESTRUCTIVE)
def sync_playlist_to_apple_music(
    playlist: Annotated[
        str,
        Field(description="Saved clickwheel playlist name to push to Apple Music."),
    ],
    refresh: Annotated[
        bool,
        Field(
            description=(
                "Ignore the cached catalog matches and re-match every "
                "track. Useful after retagging files."
            )
        ),
    ] = False,
    min_confidence: Annotated[
        float,
        Field(
            description=(
                "Confidence threshold (0.0–1.0). Tracks scoring below this "
                "are skipped unless `include_low_confidence=true`."
            ),
            ge=0.0,
            le=1.0,
        ),
    ] = 0.85,
    include_low_confidence: Annotated[
        bool,
        Field(
            description=(
                "Push low-confidence matches anyway. Use only after a "
                "match preview confirms the candidates look right."
            )
        ),
    ] = False,
) -> AppleMusicPushResult:
    """Create a playlist in the user's Apple Music account from a
    clickwheel playlist.

    Matches every track first (ISRC → catalog fuzzy → user library if
    iCloud Music Library is on), then posts the matches to
    `POST /v1/me/library/playlists`. The new playlist syncs across
    the user's Apple devices via iCloud Music Library.

    Flagged destructive — clients gate with native Allow/Deny prompts.
    Before invoking, summarize: "About to push '<name>' (<N> tracks)
    to your Apple Music library. <M> are low-confidence and will be
    skipped." Run `match_playlist_to_apple_music`-style preview via
    `clickwheel apple match` first if accuracy matters.

    Errors
    ------
    - AppleMusicNotConfiguredError: integration disabled, missing key/
      team/.p8, or no user token. Run `clickwheel apple auth`.
    - AppleMusicExtraNotInstalledError: install `clickwheel[applemusic]`.
    - AppleMusicUnreachableError: Apple's API rejected auth or the
      network failed. Run `apple_music_health` to triage.
    - AppleMusicNoMatchesError: zero matches at the threshold. The
      error payload's `matched_low_confidence` shows how many would
      be pushable with `include_low_confidence=true`.
    - PlaylistNotFoundError: the clickwheel playlist doesn't exist.
    """
    with open_session() as (cfg, db):
        try:
            result = actions.sync_playlist_to_apple_music(
                cfg,
                db,
                playlist,
                refresh=refresh,
                min_confidence=min_confidence,
                include_low_confidence=include_low_confidence,
            )
        except AppleMusicExtraNotInstalledError as exc:
            return render(
                f"Apple Music push failed: {exc}",
                {"error": "apple_music_extra_not_installed", "message": str(exc)},
            )
        except AppleMusicNotConfiguredError as exc:
            return render(
                f"Apple Music push failed: {exc}",
                {"error": "apple_music_not_configured", "message": str(exc)},
            )
        except AppleMusicKeyFileError as exc:
            return render(
                f"Apple Music push failed: {exc}",
                {"error": "apple_music_key_file", "message": str(exc)},
            )
        except AppleMusicUnreachableError as exc:
            return render(
                f"Apple Music push failed: {exc}",
                {"error": "apple_music_unreachable", "message": str(exc)},
            )
        except AppleMusicNoMatchesError as exc:
            return render(
                f"Apple Music push failed: {exc}",
                {
                    "error": "apple_music_no_matches",
                    "message": str(exc),
                    "low_confidence_skipped": exc.matched_low_confidence,
                },
            )
        except PlaylistNotFoundError as exc:
            return render(
                f"Apple Music push failed: {exc}",
                {"error": "playlist_not_found", "message": str(exc)},
            )

    text = (
        f"Pushed '{result.playlist_name}' to Apple Music — {result.pushed} tracks "
        f"(playlist id {result.apple_music_playlist_id})."
    )
    if result.unmatched or result.low_confidence_skipped:
        text += (
            f" {result.unmatched} unmatched, "
            f"{result.low_confidence_skipped} low-confidence skipped."
        )
    logger.info(
        "sync_playlist_to_apple_music name=%r pushed=%d unmatched=%d",
        playlist,
        result.pushed,
        result.unmatched,
    )
    return render(
        text,
        {
            "playlist": result.playlist_name,
            "apple_music_playlist_id": result.apple_music_playlist_id,
            "pushed": result.pushed,
            "unmatched": result.unmatched,
            "low_confidence_skipped": result.low_confidence_skipped,
            "storefront": result.storefront,
        },
    )
