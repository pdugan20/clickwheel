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

from mcp.types import CallToolResult
from pydantic import Field

from clickwheel import actions
from clickwheel.actions import (
    AppleMusicAppleScriptError,
    AppleMusicExtraNotInstalledError,
    AppleMusicKeyFileError,
    AppleMusicNoMatchesError,
    AppleMusicNotConfiguredError,
    AppleMusicPlaylistNotFoundError,
    AppleMusicUnreachableError,
    PlaylistAlreadyExistsError,
    PlaylistNotFoundError,
)
from clickwheel.mcp._runtime import DESTRUCTIVE, READ_ONLY, mcp, open_session, render
from clickwheel.mcp.models import (
    AppleMusicDeleteResult,
    AppleMusicHealth,
    AppleMusicPlaylistListResult,
    AppleMusicPullResult,
    AppleMusicPushResult,
)

logger = logging.getLogger(__name__)


@mcp.tool(title="Apple Music health", annotations=READ_ONLY)
def apple_music_health() -> Annotated[CallToolResult, AppleMusicHealth]:
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
) -> Annotated[CallToolResult, AppleMusicPushResult]:
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


@mcp.tool(title="List Apple Music playlists", annotations=READ_ONLY)
def list_apple_music_playlists() -> Annotated[
    CallToolResult, AppleMusicPlaylistListResult
]:
    """List every library playlist in the user's Apple Music account.

    Use before `pull_playlist_from_apple_music` so the user (or agent)
    can pick which one to import. `can_edit=False` rows are
    Apple-managed smart playlists; we can pull them but you can't push
    to them.

    Errors mirror `apple_music_health` — see that tool's docstring for
    triage guidance.
    """
    with open_session() as (cfg, _db):
        try:
            playlists = actions.list_apple_music_playlists(cfg)
        except AppleMusicExtraNotInstalledError as exc:
            return render(
                f"List Apple Music playlists failed: {exc}",
                {"error": "apple_music_extra_not_installed", "message": str(exc)},
            )
        except AppleMusicNotConfiguredError as exc:
            return render(
                f"List Apple Music playlists failed: {exc}",
                {"error": "apple_music_not_configured", "message": str(exc)},
            )
        except AppleMusicKeyFileError as exc:
            return render(
                f"List Apple Music playlists failed: {exc}",
                {"error": "apple_music_key_file", "message": str(exc)},
            )
        except AppleMusicUnreachableError as exc:
            return render(
                f"List Apple Music playlists failed: {exc}",
                {"error": "apple_music_unreachable", "message": str(exc)},
            )

    entries = [
        {
            "playlist_id": p.playlist_id,
            "name": p.name,
            "description": p.description,
            "track_count": p.track_count,
            "can_edit": p.can_edit,
        }
        for p in playlists
    ]
    text = f"{len(entries)} library playlist(s) on Apple Music."
    return render(text, {"playlists": entries})


@mcp.tool(title="Pull playlist from Apple Music", annotations=DESTRUCTIVE)
def pull_playlist_from_apple_music(
    name: Annotated[
        str,
        Field(
            description="Apple Music library playlist name to import into clickwheel."
        ),
    ],
    overwrite: Annotated[
        bool,
        Field(
            description=(
                "Replace an existing clickwheel playlist with the same name. "
                "Without this, the operation refuses to clobber."
            )
        ),
    ] = False,
    min_fuzzy_confidence: Annotated[
        float,
        Field(
            description=(
                "Threshold for the fuzzy-fallback match against the local "
                "library. Tracks below this score are reported as unmatched."
            ),
            ge=0.0,
            le=1.0,
        ),
    ] = 0.85,
) -> Annotated[CallToolResult, AppleMusicPullResult]:
    """Import a library playlist from Apple Music into clickwheel.

    Each Apple Music track is resolved to a local file in three steps:
    (1) the song_map cache from prior pushes, (2) exact lowercase
    artist+title (and album, if available) match against clickwheel's
    SQLite index, (3) fuzzy composite-confidence scoring (title 55% +
    artist 35% + album 10%). Tracks that don't match at any stage are
    reported in `unmatched_details`.

    Use case: curate a playlist on iPhone via the Music app, then pull
    it into clickwheel for sync to the iPod.

    Flagged destructive — clients gate with native Allow/Deny prompts.
    Before invoking, summarize: "About to import '<name>' (<N>
    tracks) from Apple Music into clickwheel; existing local playlist
    with this name will be overwritten."

    Errors
    ------
    - AppleMusicNotConfiguredError, AppleMusicExtraNotInstalledError,
      AppleMusicUnreachableError: see `apple_music_health` to triage.
    - AppleMusicPlaylistNotFoundError: no library playlist by that
      name. Call `list_apple_music_playlists` to see what's available.
    - PlaylistAlreadyExistsError: a clickwheel playlist already uses
      this name. Confirm with the user, then retry with `overwrite=true`.
    """
    with open_session() as (cfg, db):
        try:
            result = actions.pull_playlist_from_apple_music(
                cfg,
                db,
                name,
                overwrite=overwrite,
                min_fuzzy_confidence=min_fuzzy_confidence,
            )
        except AppleMusicExtraNotInstalledError as exc:
            return render(
                f"Apple Music pull failed: {exc}",
                {"error": "apple_music_extra_not_installed", "message": str(exc)},
            )
        except AppleMusicNotConfiguredError as exc:
            return render(
                f"Apple Music pull failed: {exc}",
                {"error": "apple_music_not_configured", "message": str(exc)},
            )
        except AppleMusicKeyFileError as exc:
            return render(
                f"Apple Music pull failed: {exc}",
                {"error": "apple_music_key_file", "message": str(exc)},
            )
        except AppleMusicUnreachableError as exc:
            return render(
                f"Apple Music pull failed: {exc}",
                {"error": "apple_music_unreachable", "message": str(exc)},
            )
        except AppleMusicPlaylistNotFoundError as exc:
            return render(
                f"Apple Music pull failed: {exc}",
                {"error": "apple_music_playlist_not_found", "message": str(exc)},
            )
        except PlaylistAlreadyExistsError as exc:
            return render(
                f"Apple Music pull failed: {exc}",
                {"error": "playlist_already_exists", "message": str(exc)},
            )

    verb = "Replaced" if result.replaced else "Created"
    text = (
        f"{verb} clickwheel playlist '{result.playlist_name}': "
        f"{result.matched}/{result.total} matched"
    )
    if result.unmatched:
        text += f" ({result.unmatched} unmatched)"
    unmatched_details = [
        {
            "apple_song_id": t.apple_song_id,
            "kind": t.kind,
            "artist": t.artist,
            "title": t.title,
            "album": t.album,
        }
        for t in result.tracks
        if t.local_path is None
    ]
    logger.info(
        "pull_playlist_from_apple_music name=%r matched=%d unmatched=%d replaced=%s",
        name,
        result.matched,
        result.unmatched,
        result.replaced,
    )
    return render(
        text,
        {
            "playlist": result.playlist_name,
            "apple_music_playlist_id": result.apple_music_playlist_id,
            "total": result.total,
            "matched": result.matched,
            "unmatched": result.unmatched,
            "replaced": result.replaced,
            "description": result.description,
            "unmatched_details": unmatched_details,
        },
    )


@mcp.tool(title="Delete Apple Music playlist", annotations=DESTRUCTIVE)
def delete_apple_music_playlist(
    name: Annotated[
        str, Field(description="Library playlist name to delete from Apple Music.")
    ],
) -> Annotated[CallToolResult, AppleMusicDeleteResult]:
    """Delete a library playlist from the user's Apple Music account.

    Apple's REST API doesn't expose DELETE on library playlists, so
    this tool drives Music.app on macOS via AppleScript instead.
    Music.app's iCloud Music Library sync propagates the deletion to
    the user's iPhone/iPad and Apple Music account.

    macOS-only. Music.app must be launchable, and the user must be
    signed into the same Apple ID that holds the playlist. Deletes
    EVERY playlist matching the name — useful for cleaning up
    duplicates left by earlier failed pushes.

    Flagged destructive — clients gate with native Allow/Deny prompts.
    Before invoking, summarize the impact in chat: "About to delete
    '<name>' from your Apple Music library via Music.app on this Mac.
    This will sync to your iPhone and Apple Music account via iCloud."

    Errors
    ------
    - AppleMusicAppleScriptError: osascript failed, Music.app missing,
      or non-macOS platform. Surface the message verbatim.
    """
    with open_session() as (_cfg, _db):
        try:
            result = actions.delete_apple_music_playlist(name)
        except AppleMusicAppleScriptError as exc:
            return render(
                f"Apple Music delete failed: {exc}",
                {"error": "apple_music_applescript", "message": str(exc)},
            )

    if result.deleted == 0:
        text = (
            f"No Music.app playlist named '{name}' found. "
            "It may have already been deleted or the name is misspelled."
        )
    else:
        text = (
            f"Deleted {result.deleted} playlist(s) named '{name}' from Music.app. "
            "iCloud Music Library will propagate to other devices."
        )
    logger.info("delete_apple_music_playlist name=%r deleted=%d", name, result.deleted)
    return render(text, {"name": result.name, "deleted": result.deleted})
