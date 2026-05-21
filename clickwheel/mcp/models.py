"""Pydantic models for MCP tool structured output.

Each MCP tool annotates its return type with a model from here so FastMCP
emits an `outputSchema`. The models mirror exactly what `render()` places
in `structuredContent` (sourced from `actions.py` return shapes) — the MCP
spec requires structured results to conform to the advertised schema.

Values stay raw: bytes as ints, durations as seconds, timestamps as unix
seconds. Human formatting happens in each tool's text summary, never here.

Tools whose response varies by branch (conflict vs success, dry-run vs
real) use a single model with the branch-specific fields optional.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Record models — list elements and nested blocks
# ---------------------------------------------------------------------------


class FullTrack(BaseModel):
    """A complete library track record as stored in the index."""

    id: int = Field(description="Internal track row id.")
    path: str | None = Field(description="Absolute file path.")
    title: str | None = Field(description="Track title.")
    artist: str | None = Field(description="Track artist.")
    album: str | None = Field(description="Album title.")
    album_artist: str | None = Field(description="Album artist, if tagged.")
    genre: str | None = Field(description="Genre, if tagged.")
    track_number: int | None = Field(description="Track number on its disc.")
    disc_number: int | None = Field(description="Disc number.")
    year: int | None = Field(description="Release year, if known.")
    duration_seconds: float | None = Field(description="Duration in seconds.")
    bitrate: int | None = Field(description="Bitrate in bits per second.")
    sample_rate: int | None = Field(description="Sample rate in Hz.")
    format: str | None = Field(description="Audio format (mp3, m4a, flac).")
    file_size: int | None = Field(description="File size in bytes.")
    has_art: int | None = Field(description="1 if embedded artwork is present, else 0.")
    art_width: int | None = Field(description="Embedded artwork width in pixels.")
    art_height: int | None = Field(description="Embedded artwork height in pixels.")
    scanned_at: str | None = Field(description="When this row was last scanned.")
    mtime: float | None = Field(description="File modification time (unix seconds).")
    missing_since: float | None = Field(
        description="Unix time the file was first seen missing from disk, else null."
    )


class LibraryTrack(BaseModel):
    """A library track in the slim shape returned by search."""

    path: str | None = Field(description="Absolute file path.")
    artist: str | None = Field(description="Track artist.")
    album: str | None = Field(description="Album title.")
    title: str | None = Field(description="Track title.")
    duration_seconds: float | None = Field(description="Duration in seconds.")
    file_size: int | None = Field(description="File size in bytes.")
    format: str | None = Field(description="Audio format (mp3, m4a, flac).")


class IpodTrack(BaseModel):
    """A track on the iPod, chat-friendly slim projection."""

    artist: str = Field(description="Track artist.")
    title: str = Field(description="Track title.")
    album: str = Field(description="Album title.")
    size_bytes: int = Field(description="File size on the iPod in bytes.")


class ArtistSummary(BaseModel):
    """One artist with aggregate counts, as listed for the whole library."""

    name: str | None = Field(description="Artist name.")
    tracks: int = Field(description="Number of tracks by this artist.")
    albums: int = Field(description="Number of albums by this artist.")
    total_bytes: int = Field(description="Total size of this artist's tracks in bytes.")


class PlaylistArtistSummary(BaseModel):
    """One artist's contribution to a single playlist."""

    name: str | None = Field(description="Artist name.")
    tracks: int = Field(description="Number of this artist's tracks in the playlist.")
    total_bytes: int = Field(description="Total size of those tracks in bytes.")


class TopArtist(BaseModel):
    """An artist in the iPod's top-artists-by-track-count breakdown."""

    artist: str = Field(description="Artist name (canonical lead-artist rollup).")
    track_count: int = Field(description="Number of this artist's tracks on the iPod.")


class AlbumSummary(BaseModel):
    """One album with aggregate counts."""

    album: str | None = Field(description="Album title.")
    year: int | None = Field(description="Release year, if known.")
    tracks: int = Field(description="Number of tracks on the album.")
    total_bytes: int = Field(description="Total size of the album's tracks in bytes.")


class PlaylistSummary(BaseModel):
    """A saved clickwheel playlist with aggregate counts."""

    name: str = Field(description="Playlist name.")
    description: str | None = Field(
        description="Free-text playlist description, or null if unset."
    )
    tracks: int = Field(description="Number of tracks in the playlist.")
    total_bytes: int = Field(
        description="Total size of the playlist's tracks in bytes."
    )
    created_at: str = Field(description="When the playlist was created.")
    updated_at: str = Field(description="When the playlist was last modified.")


class IpodPlaylist(BaseModel):
    """A playlist currently on the iPod."""

    name: str = Field(description="Playlist name.")
    track_count: int = Field(description="Number of tracks in the playlist.")
    total_bytes: int = Field(
        description="Best-effort total size of its tracks in bytes."
    )
    is_smart: bool = Field(description="Whether this is an iTunes smart playlist.")


class ScrobbleRecord(BaseModel):
    """A cached iPod play awaiting submission to Last.fm."""

    id: int = Field(description="Internal scrobble-cache row id.")
    artist: str | None = Field(description="Track artist.")
    album: str | None = Field(description="Album title.")
    title: str | None = Field(description="Track title.")
    timestamp: int = Field(description="When the track was played (unix seconds).")
    duration_seconds: float | None = Field(description="Track duration in seconds.")


class FormatBreakdown(BaseModel):
    """Track count and size for one audio format."""

    format: str = Field(description="Audio format (mp3, m4a, flac).")
    count: int = Field(description="Number of tracks in this format.")
    total_bytes: int = Field(description="Total size of those tracks in bytes.")


class HealthStage(BaseModel):
    """One stage of the Plex integration health probe."""

    name: str = Field(description="Stage name.")
    ok: bool = Field(description="Whether the stage passed.")
    detail: str = Field(description="Human-readable detail for the stage.")


class LibraryStatsBlock(BaseModel):
    """Headline counts for the indexed library."""

    total_tracks: int = Field(description="Total indexed tracks.")
    artists: int = Field(description="Distinct artists.")
    albums: int = Field(description="Distinct albums.")
    total_bytes: int = Field(description="Total size of all tracks in bytes.")
    total_seconds: float = Field(description="Total duration of all tracks in seconds.")
    with_art: int = Field(description="Tracks with embedded artwork.")
    without_art: int = Field(description="Tracks without embedded artwork.")
    missing_genre: int = Field(description="Tracks missing a genre tag.")
    missing_title: int = Field(description="Tracks missing a title tag.")
    missing_artist: int = Field(description="Tracks missing an artist tag.")


class SyncConflict(BaseModel):
    """Details of a same-name iPod playlist that blocked a sync."""

    kind: str = Field(description="Always 'conflict'.")
    existing_name: str = Field(description="Name of the conflicting iPod playlist.")
    existing_track_count: int = Field(
        description="Track count of the existing playlist."
    )
    message: str = Field(description="Human-readable conflict description.")


# ---------------------------------------------------------------------------
# Response models — one per dict-returning tool
# ---------------------------------------------------------------------------


class LibraryStats(BaseModel):
    """Result of `library_stats`."""

    stats: LibraryStatsBlock = Field(description="Headline library counts.")
    formats: list[FormatBreakdown] = Field(description="Per-format breakdown.")


class LibraryHealth(BaseModel):
    """Result of `library_health`."""

    library_dir: str = Field(description="Configured music directory.")
    library_dir_exists: bool = Field(description="Whether that directory exists.")
    total_tracks: int = Field(description="Total indexed tracks.")
    missing_tracks: int = Field(description="Indexed tracks no longer on disk.")
    last_scan_at: float | None = Field(
        description="Last scan time (unix seconds), or null."
    )
    auto_scan_enabled: bool = Field(description="Whether CLI auto-scan is enabled.")
    last_scan_iso: str | None = Field(
        default=None,
        description="Last scan time as an ISO 8601 string, if ever scanned.",
    )


class PlaylistDetail(BaseModel):
    """Result of `get_playlist`."""

    name: str = Field(description="Playlist name.")
    description: str | None = Field(
        description="Free-text playlist description, or null if unset."
    )
    track_count: int = Field(description="Number of tracks in the playlist.")
    size_bytes: int = Field(description="Total size of the playlist's tracks in bytes.")
    artists: list[PlaylistArtistSummary] = Field(description="Per-artist breakdown.")


class SetPlaylistDescriptionResult(BaseModel):
    """Result of `set_playlist_description`."""

    name: str = Field(description="Playlist name.")
    description: str = Field(description="The description that was set.")


class CreatePlaylistResult(BaseModel):
    """Result of `create_playlist`."""

    name: str = Field(description="Name of the created playlist.")
    track_count: int = Field(description="Number of tracks it was created with.")


class UpdatePlaylistResult(BaseModel):
    """Result of `update_playlist`."""

    name: str = Field(description="Playlist name.")
    track_count: int = Field(description="New track count after the replace.")
    replaced: bool = Field(
        description="True if a playlist by this name already existed."
    )


class DeletePlaylistResult(BaseModel):
    """Result of `delete_playlist`."""

    deleted: bool = Field(description="Whether a playlist was deleted.")
    name: str | None = Field(default=None, description="Name of the deleted playlist.")
    reason: str | None = Field(
        default=None, description="Why nothing was deleted, when deleted is false."
    )


class AddArtistToPlaylistResult(BaseModel):
    """Result of `add_artist_to_playlist`."""

    added: int = Field(description="Number of tracks added (duplicates skipped).")
    playlist: str = Field(description="Target playlist name.")
    artist: str = Field(description="Artist whose tracks were added.")


class RemoveArtistFromPlaylistResult(BaseModel):
    """Result of `remove_artist_from_playlist`."""

    removed: int = Field(description="Number of tracks removed.")
    playlist: str = Field(description="Target playlist name.")
    artist: str = Field(description="Artist whose tracks were removed.")


class HealPlaylistResult(BaseModel):
    """Result of `heal_playlist`."""

    dropped: int = Field(description="Number of dead track references removed.")
    remaining: int = Field(description="Number of tracks still in the playlist.")
    dropped_tracks: list[FullTrack] = Field(description="The removed track records.")


class IpodContents(BaseModel):
    """Result of `get_ipod_contents`."""

    capacity_bytes: int = Field(description="Total iPod capacity in bytes.")
    used_bytes: int = Field(description="Used space in bytes.")
    free_bytes: int = Field(description="Free space in bytes.")
    track_count: int = Field(description="Number of tracks on the iPod.")
    artist_count: int = Field(description="Number of distinct artists on the iPod.")
    album_count: int = Field(description="Number of distinct albums on the iPod.")
    top_artists: list[TopArtist] = Field(
        description="Top 25 artists by track count, descending."
    )


class SyncToIpodResult(BaseModel):
    """Result of `sync_playlist_to_ipod` — success or same-name conflict."""

    synced: bool = Field(description="Whether the playlist was synced.")
    playlist: str = Field(description="The clickwheel playlist name.")
    conflict: SyncConflict | None = Field(
        default=None, description="Set when a same-name iPod playlist blocked the sync."
    )
    ipod_playlist: str | None = Field(
        default=None, description="Name of the playlist created/updated on the iPod."
    )
    on_conflict: str | None = Field(
        default=None, description="Conflict resolution applied (merge/replace/rename)."
    )
    added: int | None = Field(default=None, description="Tracks copied to the iPod.")
    failed: int | None = Field(default=None, description="Tracks that failed to copy.")
    also_on_ipod: int | None = Field(
        default=None, description="Pre-existing iPod tracks left untouched."
    )
    library_updated: bool | None = Field(
        default=None, description="Whether the iPod's library database was updated."
    )


class AddTracksToIpodResult(BaseModel):
    """Result of `add_tracks_to_ipod`."""

    added: int = Field(description="Tracks copied to the iPod.")
    failed: int = Field(description="Tracks that failed to copy.")
    already_present: int = Field(description="Requested tracks already on the iPod.")
    library_updated: bool = Field(
        description="Whether the iPod's library database was updated."
    )


class AddArtistToIpodResult(BaseModel):
    """Result of `add_artist_to_ipod`."""

    artist: str = Field(description="Artist whose tracks were added.")
    added: int = Field(description="Tracks copied to the iPod.")
    failed: int | None = Field(default=None, description="Tracks that failed to copy.")
    already_present: int | None = Field(
        default=None, description="The artist's tracks already on the iPod."
    )
    found_in_library: int | None = Field(
        default=None, description="The artist's tracks found in the library index."
    )
    library_updated: bool | None = Field(
        default=None, description="Whether the iPod's library database was updated."
    )


class RemoveTracksFromIpodResult(BaseModel):
    """Result of `remove_tracks_from_ipod`."""

    removed: int = Field(description="Tracks removed from the iPod.")
    not_matched: int = Field(description="Requested tracks that weren't on the iPod.")
    bytes_freed: int = Field(description="Space freed on the iPod in bytes.")
    library_updated: bool = Field(
        description="Whether the iPod's library database was updated."
    )


class RemoveArtistFromIpodResult(BaseModel):
    """Result of `remove_artist_from_ipod`."""

    artist: str = Field(description="Artist whose tracks were removed.")
    removed: int = Field(description="Tracks removed from the iPod.")
    bytes_freed: int = Field(description="Space freed on the iPod in bytes.")
    library_updated: bool = Field(
        description="Whether the iPod's library database was updated."
    )


class RemoveIpodPlaylistResult(BaseModel):
    """Result of `remove_ipod_playlist`."""

    ipod_playlist: str = Field(description="Name of the removed iPod playlist.")
    removed_playlist: bool = Field(description="Whether the playlist was removed.")
    library_updated: bool = Field(
        description="Whether the iPod's library database was updated."
    )


class EjectResult(BaseModel):
    """Result of `eject_ipod`."""

    ejected: bool = Field(description="Whether an eject command was issued.")
    mount: str | None = Field(
        default=None, description="The iPod mount path that was ejected."
    )
    already_unmounted: bool | None = Field(
        default=None, description="True if the iPod was already disconnected."
    )


class PlexHealth(BaseModel):
    """Result of `plex_health`."""

    ok: bool = Field(description="Whether every probe stage passed.")
    stages: list[HealthStage] = Field(description="Per-stage probe results.")


class AppleMusicHealth(BaseModel):
    """Result of `apple_music_health` — same shape as PlexHealth, separate
    model so the schemas stay independent and one can evolve without the
    other.
    """

    ok: bool = Field(description="Whether every probe stage passed.")
    stages: list[HealthStage] = Field(description="Per-stage probe results.")


class AppleMusicPushResult(BaseModel):
    """Result of `sync_playlist_to_apple_music`."""

    playlist: str | None = Field(
        default=None, description="The clickwheel playlist name pushed."
    )
    apple_music_playlist_id: str | None = Field(
        default=None,
        description="ID of the new playlist in the user's Apple Music account.",
    )
    pushed: int | None = Field(
        default=None,
        description="Tracks that landed in the Apple Music playlist.",
    )
    unmatched: int | None = Field(
        default=None,
        description="Tracks Apple Music couldn't resolve at all.",
    )
    low_confidence_skipped: int | None = Field(
        default=None,
        description=(
            "Tracks matched only at low confidence and skipped (unless the "
            "caller passed include_low_confidence=True)."
        ),
    )
    storefront: str | None = Field(
        default=None, description="Catalog storefront used for matching."
    )
    error: str | None = Field(
        default=None, description="Machine-readable error code, on failure."
    )
    message: str | None = Field(
        default=None, description="Human-readable error message, on failure."
    )


class PlexSyncResult(BaseModel):
    """Result of `sync_playlist_to_plex` — success or a configuration error."""

    playlist: str | None = Field(
        default=None, description="The clickwheel playlist name."
    )
    pushed: int | None = Field(default=None, description="Tracks written to the M3U.")
    resolved: int | None = Field(
        default=None, description="Tracks Plex matched against its own index."
    )
    unresolved: int | None = Field(
        default=None, description="Tracks Plex could not resolve."
    )
    plex_rating_key: str | int | None = Field(
        default=None, description="Rating key of the Plex playlist created/updated."
    )
    m3u_local_path: str | None = Field(
        default=None, description="Local path of the written M3U file."
    )
    m3u_plex_path: str | None = Field(
        default=None, description="Path of the M3U file as seen by Plex."
    )
    error: str | None = Field(
        default=None, description="Machine-readable error code, on failure."
    )
    message: str | None = Field(
        default=None, description="Human-readable error message, on failure."
    )


class PlexPlaylistEntry(BaseModel):
    """One audio playlist on the user's Plex server."""

    name: str = Field(description="The Plex playlist title.")
    smart: bool = Field(
        description=(
            "True if this is a smart playlist (dynamically computed by Plex). "
            "Smart playlists need include_smart=True to pull."
        )
    )
    track_count: int = Field(description="Number of tracks Plex reports for it.")
    summary: str = Field(
        default="", description="Plex's description for the playlist (may be empty)."
    )


class PlexPlaylistListResult(BaseModel):
    """Result of `list_plex_playlists`."""

    playlists: list[PlexPlaylistEntry] = Field(
        description="All audio playlists found on the server."
    )
    error: str | None = Field(
        default=None, description="Machine-readable error code, on failure."
    )
    message: str | None = Field(
        default=None, description="Human-readable error message, on failure."
    )


class PlexPullUnmatched(BaseModel):
    """One Plex track that couldn't be matched into the clickwheel index."""

    title: str = Field(default="", description="Track title as Plex sees it.")
    artist: str = Field(default="", description="Artist as Plex sees it.")
    album: str = Field(default="", description="Album as Plex sees it.")
    plex_path: str = Field(description="The file path as Plex reports it.")
    local_path: str | None = Field(
        default=None,
        description=(
            "Translated clickwheel-side path, when the remap succeeded but the "
            "path wasn't in the scan index."
        ),
    )
    reason: str = Field(description="`path_remap_failed` or `not_in_clickwheel_index`.")


class PlexPullResult(BaseModel):
    """Result of `pull_playlist_from_plex`."""

    playlist: str | None = Field(
        default=None, description="The Plex playlist name that was pulled."
    )
    smart: bool | None = Field(
        default=None, description="True if the source playlist was smart."
    )
    total_plex_tracks: int | None = Field(
        default=None, description="Tracks the Plex playlist contained."
    )
    matched: int | None = Field(
        default=None,
        description=(
            "Tracks whose remapped path was found in clickwheel's index — "
            "these are what landed in the new playlist."
        ),
    )
    unmatched: int | None = Field(
        default=None,
        description="Tracks Plex had that clickwheel couldn't resolve locally.",
    )
    skipped_no_path: int | None = Field(
        default=None,
        description=(
            "Tracks Plex returned with no file path (stale references to "
            "deleted media)."
        ),
    )
    description: str | None = Field(
        default=None,
        description="Playlist description carried over from Plex's `summary` field.",
    )
    replaced: bool | None = Field(
        default=None,
        description="True if a clickwheel playlist with this name already existed.",
    )
    unmatched_details: list[PlexPullUnmatched] | None = Field(
        default=None,
        description="Per-track details for the unmatched count, for triage.",
    )
    error: str | None = Field(
        default=None, description="Machine-readable error code, on failure."
    )
    message: str | None = Field(
        default=None, description="Human-readable error message, on failure."
    )


class SubmitScrobblesResult(BaseModel):
    """Result of `submit_scrobbles` — dry-run preview or a real submission."""

    newly_cached: int = Field(description="New plays read from the iPod and cached.")
    plays_found_on_ipod: int = Field(description="Total plays found on the iPod.")
    dry_run: bool | None = Field(
        default=None, description="True when this was a preview, not a real submission."
    )
    pending_total: int | None = Field(
        default=None, description="Scrobbles ready to send (dry-run only)."
    )
    oldest_age_days: float | None = Field(
        default=None,
        description="Age of the oldest pending play in days (dry-run only).",
    )
    submitted: int | None = Field(
        default=None, description="Scrobbles submitted to Last.fm (real run only)."
    )
    failed: int | None = Field(
        default=None, description="Scrobbles that failed to submit (real run only)."
    )
    remaining_pending: int | None = Field(
        default=None,
        description="Scrobbles still pending after the run (real run only).",
    )
