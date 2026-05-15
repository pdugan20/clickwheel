"""Plex integration tools.

Two tools:

- `sync_playlist_to_plex` — push a clickwheel playlist into the user's
  Plex music library so Plexamp / Plex web see it alongside the iPod
  sync. Flagged destructive; clients gate with a native Allow/Deny
  prompt before invocation.
- `plex_health` — read-only probe. Useful when the user reports
  "Plex sync isn't working" — surfaces exactly which stage of the
  pipeline failed without changing anything.

The same library powers `clickwheel sync-plex` and `clickwheel plex
doctor` on the CLI. Logic lives in `actions.py` per CLAUDE.md rule 11.
"""

from __future__ import annotations

import logging
from typing import Annotated

from pydantic import Field

from clickwheel import actions
from clickwheel.actions import (
    PlexExtraNotInstalledError,
    PlexNotConfiguredError,
    PlexPathRemapError,
    PlexSectionNotFoundError,
    PlexUnreachableError,
)
from clickwheel.mcp._runtime import (
    DESTRUCTIVE,
    READ_ONLY,
    mcp,
    open_session,
    render,
)

logger = logging.getLogger(__name__)


@mcp.tool(title="Plex health", annotations=READ_ONLY)
def plex_health() -> dict:
    """Probe the Plex integration end-to-end without changing anything.

    Walks five stages: config (enabled + url + token set), plexapi
    extra installed, server reachable, named music section exists,
    and a sample clickwheel mp3 resolves to the same physical file in
    Plex via the configured path remap. Each stage is reported with
    its own ok/detail so failures point at exactly the broken piece.

    When to use: the user reports the Plex side isn't working, or
    before the first `sync_playlist_to_plex` to confirm setup. Cheap
    to call; safe to repeat.

    After this: if any stage fails, surface the failing stage's detail
    verbatim — it's already written to be actionable (config keys to
    set, install commands to run, path-remap hints, etc.).
    """
    with open_session() as (cfg, db):
        result = actions.plex_doctor(cfg, db)

    stages = [{"name": s.name, "ok": s.ok, "detail": s.detail} for s in result.stages]
    if result.ok:
        text = "Plex is configured and reachable; sample track resolved."
    else:
        first_failure = next((s for s in result.stages if not s.ok), None)
        if first_failure is None:
            text = "Plex doctor produced no stages."
        else:
            text = (
                f"Plex doctor failed at stage {first_failure.name!r}: "
                f"{first_failure.detail}"
            )
    return render(text, {"ok": result.ok, "stages": stages})


@mcp.tool(title="Sync playlist to Plex", annotations=DESTRUCTIVE)
def sync_playlist_to_plex(
    playlist: Annotated[
        str, Field(description="Saved clickwheel playlist name to push to Plex.")
    ],
) -> dict:
    """Push a clickwheel playlist into the user's Plex music library so
    it shows up in Plex web and Plexamp alongside the iPod sync.

    Mechanism is M3U upload: we write `{playlist_name}.m3u` to the
    user's configured `plex_playlist_dir` (default:
    `{music_dir}/.clickwheel-playlists/`) and ask Plex to import it.
    Plex resolves the lines against its own indexed library, so the
    `resolved` count in the response can be lower than `pushed` if
    some clickwheel files aren't visible to Plex yet (typically
    because Plex hasn't scanned them).

    Re-running with the same playlist name overwrites the prior Plex
    playlist created from that M3U — the operation is idempotent. A
    hand-curated Plex playlist with the same name (not previously
    written by clickwheel) is left untouched.

    For "I want this on the iPod AND in Plexamp" the right pattern is
    two tool calls: this one plus `sync_playlist_to_ipod`. Don't
    pretend a single call handles both.

    Flagged destructive — clients gate with native Allow/Deny prompts.
    Before invoking, summarize for the user: "About to push '<name>'
    (<N> tracks) to your Plex music library."

    Errors
    ------
    - PlexNotConfiguredError: `plex_enabled` is false, or url/token
      missing. Surface the message; the user needs to set up config.
      `plex_health` reports the exact missing key.
    - PlexExtraNotInstalledError: the `clickwheel[plex]` extra isn't
      installed. Show the install command from the error message.
    - PlexUnreachableError: server unreachable or token bad. Suggest
      `plex_health` for diagnosis.
    - PlexSectionNotFoundError: the configured `plex_library_name`
      doesn't match any music section on the server.
    - PlexPathRemapError: a track path doesn't match the configured
      remap prefix — config bug. The detail has the offending path.
    - PlaylistNotFoundError: the clickwheel playlist doesn't exist.
    """
    with open_session() as (cfg, db):
        try:
            result = actions.sync_playlist_to_plex(cfg, db, playlist)
        except PlexExtraNotInstalledError as exc:
            return render(
                f"Plex sync failed: {exc}",
                {"error": "plex_extra_not_installed", "message": str(exc)},
            )
        except PlexNotConfiguredError as exc:
            return render(
                f"Plex sync failed: {exc}",
                {"error": "plex_not_configured", "message": str(exc)},
            )
        except PlexUnreachableError as exc:
            return render(
                f"Plex sync failed: {exc}",
                {"error": "plex_unreachable", "message": str(exc)},
            )
        except PlexSectionNotFoundError as exc:
            return render(
                f"Plex sync failed: {exc}",
                {"error": "plex_section_not_found", "message": str(exc)},
            )
        except PlexPathRemapError as exc:
            return render(
                f"Plex sync failed: {exc}",
                {"error": "plex_path_remap", "message": str(exc)},
            )

    unresolved = result.pushed - result.resolved
    if unresolved == 0:
        text = (
            f"Pushed '{playlist}' to Plex: "
            f"{result.resolved}/{result.pushed} tracks resolved."
        )
    else:
        text = (
            f"Pushed '{playlist}' to Plex: {result.resolved}/{result.pushed} "
            f"resolved. {unresolved} track(s) weren't in Plex's index — "
            "those files exist in clickwheel but Plex hasn't scanned them."
        )
    logger.info(
        "sync_playlist_to_plex playlist=%r pushed=%d resolved=%d",
        playlist,
        result.pushed,
        result.resolved,
    )
    return render(
        text,
        {
            "playlist": playlist,
            "pushed": result.pushed,
            "resolved": result.resolved,
            "unresolved": unresolved,
            "plex_rating_key": result.playlist_rating_key,
            "m3u_local_path": result.m3u_local_path,
            "m3u_plex_path": result.m3u_plex_path,
        },
    )
