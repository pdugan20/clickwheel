"""Plex integration tools.

Four tools:

- `sync_playlist_to_plex` — push a clickwheel playlist into the user's
  Plex music library so Plexamp / Plex web see it alongside the iPod
  sync. Flagged destructive; clients gate with a native Allow/Deny
  prompt before invocation.
- `pull_playlist_from_plex` — read-back direction; recovers a Plex
  playlist into clickwheel's local store. Useful after a fresh install
  when local SQLite playlists are gone but the Plex server still has
  them. Destructive (writes to the local DB).
- `list_plex_playlists` — read-only listing of what's available on the
  Plex side, so callers can decide what to pull.
- `plex_health` — read-only probe. Useful when the user reports
  "Plex sync isn't working" — surfaces exactly which stage of the
  pipeline failed without changing anything.

The same library powers `clickwheel sync-plex`, `clickwheel plex pull`,
`clickwheel plex list`, and `clickwheel plex doctor` on the CLI. Logic
lives in `actions.py` per CLAUDE.md rule 11.
"""

from __future__ import annotations

import logging
from typing import Annotated

from pydantic import Field

from clickwheel import actions
from clickwheel.actions import (
    PlaylistAlreadyExistsError,
    PlexExtraNotInstalledError,
    PlexNotConfiguredError,
    PlexPathRemapError,
    PlexPlaylistNotFoundError,
    PlexSectionNotFoundError,
    PlexSmartPlaylistError,
    PlexUnreachableError,
)
from clickwheel.mcp._runtime import (
    DESTRUCTIVE,
    READ_ONLY,
    mcp,
    open_session,
    render,
)
from clickwheel.mcp.models import (
    PlexHealth,
    PlexPlaylistListResult,
    PlexPullResult,
    PlexSyncResult,
)

logger = logging.getLogger(__name__)


@mcp.tool(title="Plex health", annotations=READ_ONLY)
def plex_health() -> PlexHealth:
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
) -> PlexSyncResult:
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


@mcp.tool(title="List Plex playlists", annotations=READ_ONLY)
def list_plex_playlists() -> PlexPlaylistListResult:
    """List every audio playlist on the user's Plex server.

    Use before `pull_playlist_from_plex` so the user can pick which to
    recover. The `smart` flag matters: smart playlists are dynamically
    computed by Plex (e.g. "Recently Added", "Favorites") and pulling
    one freezes a snapshot rather than mirroring an ongoing query —
    require `include_smart=true` on the pull side. Manual playlists
    are the safe default targets.

    Cheap to call; safe to repeat. Errors mirror `plex_health` — see
    that tool's docstring for triage guidance.

    Errors
    ------
    - PlexNotConfiguredError, PlexExtraNotInstalledError,
      PlexUnreachableError: surface the message; the user needs to
      fix config or install the extra. `plex_health` pinpoints which.
    """
    with open_session() as (cfg, _db):
        try:
            playlists = actions.list_plex_playlists(cfg)
        except PlexExtraNotInstalledError as exc:
            return render(
                f"List Plex playlists failed: {exc}",
                {"error": "plex_extra_not_installed", "message": str(exc)},
            )
        except PlexNotConfiguredError as exc:
            return render(
                f"List Plex playlists failed: {exc}",
                {"error": "plex_not_configured", "message": str(exc)},
            )
        except PlexUnreachableError as exc:
            return render(
                f"List Plex playlists failed: {exc}",
                {"error": "plex_unreachable", "message": str(exc)},
            )

    entries = [
        {
            "name": p.name,
            "smart": p.smart,
            "track_count": p.track_count,
            "summary": p.summary,
        }
        for p in playlists
    ]
    manual = sum(1 for p in playlists if not p.smart)
    smart = len(playlists) - manual
    text = f"{len(playlists)} playlist(s) on Plex: {manual} manual, {smart} smart."
    return render(text, {"playlists": entries})


@mcp.tool(title="Pull playlist from Plex", annotations=DESTRUCTIVE)
def pull_playlist_from_plex(
    name: Annotated[
        str, Field(description="Plex playlist name to recover into clickwheel.")
    ],
    include_smart: Annotated[
        bool,
        Field(
            description=(
                "Required to pull a smart playlist — materializes a snapshot "
                "rather than mirroring the live query."
            )
        ),
    ] = False,
    overwrite: Annotated[
        bool,
        Field(
            description=(
                "Replace an existing clickwheel playlist with the same name. "
                "Without this, the operation refuses to clobber."
            )
        ),
    ] = False,
) -> PlexPullResult:
    """Recover a Plex audio playlist into clickwheel's local SQLite.

    The Plex playlist's track list is translated path-by-path back to
    clickwheel's view (inverse of `sync_playlist_to_plex`'s remap) and
    looked up in the scanned index. Matched tracks become the new
    clickwheel playlist's contents, in Plex's order; the Plex
    playlist's `summary` becomes the local description.

    Primary use case: a fresh clickwheel install (or a Mac wipe) lost
    the local SQLite playlists, but Plex still has them. This tool
    is the recovery path. It's also fine for ongoing one-direction
    mirroring — re-running with `overwrite=True` refreshes the local
    copy.

    Flagged destructive — clients gate with native Allow/Deny prompts.
    Before invoking, summarize for the user: "About to pull '<name>'
    from Plex (manual, <N> tracks) into clickwheel."

    Errors
    ------
    - PlexNotConfiguredError, PlexExtraNotInstalledError,
      PlexUnreachableError: config / install / network problem; see
      `plex_health` to triage.
    - PlexPlaylistNotFoundError: no audio playlist by that name on
      Plex. Use `list_plex_playlists` to see what's available.
    - PlexSmartPlaylistError: the named playlist is smart; re-call
      with `include_smart=true` if the user wants a snapshot.
    - PlaylistAlreadyExistsError: a clickwheel playlist already uses
      this name. Confirm with the user, then re-call with
      `overwrite=true`.
    """
    with open_session() as (cfg, db):
        try:
            result = actions.pull_playlist_from_plex(
                cfg, db, name, include_smart=include_smart, overwrite=overwrite
            )
        except PlexExtraNotInstalledError as exc:
            return render(
                f"Plex pull failed: {exc}",
                {"error": "plex_extra_not_installed", "message": str(exc)},
            )
        except PlexNotConfiguredError as exc:
            return render(
                f"Plex pull failed: {exc}",
                {"error": "plex_not_configured", "message": str(exc)},
            )
        except PlexUnreachableError as exc:
            return render(
                f"Plex pull failed: {exc}",
                {"error": "plex_unreachable", "message": str(exc)},
            )
        except PlexPlaylistNotFoundError as exc:
            return render(
                f"Plex pull failed: {exc}",
                {"error": "plex_playlist_not_found", "message": str(exc)},
            )
        except PlexSmartPlaylistError as exc:
            return render(
                f"Plex pull failed: {exc}",
                {"error": "plex_smart_playlist", "message": str(exc)},
            )
        except PlaylistAlreadyExistsError as exc:
            return render(
                f"Plex pull failed: {exc}",
                {"error": "playlist_already_exists", "message": str(exc)},
            )

    verb = "Replaced" if result.replaced else "Created"
    text = (
        f"{verb} clickwheel playlist '{result.playlist_name}': "
        f"{result.matched}/{result.total_plex_tracks} tracks matched"
    )
    if result.unmatched:
        text += f" ({result.unmatched} unmatched)"
    logger.info(
        "pull_playlist_from_plex name=%r matched=%d unmatched=%d replaced=%s",
        name,
        result.matched,
        result.unmatched,
        result.replaced,
    )
    return render(
        text,
        {
            "playlist": result.playlist_name,
            "smart": result.smart,
            "total_plex_tracks": result.total_plex_tracks,
            "matched": result.matched,
            "unmatched": result.unmatched,
            "skipped_no_path": result.skipped_no_path,
            "description": result.description,
            "replaced": result.replaced,
            "unmatched_details": result.unmatched_details,
        },
    )
