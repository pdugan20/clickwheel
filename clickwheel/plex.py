"""Plex integration helpers — pure functions consumed by actions.py.

This module owns the mechanical work of talking to Plex: connection,
path remapping between the clickwheel-side and Plex-side views of the
same physical music library, M3U authoring, and the playlist upload
call. It deliberately raises bare exceptions; `actions.py` is the layer
that catches them and re-raises typed ClickwheelError variants so the
CLI and MCP surface can present consistent errors.

The `plexapi` package is an optional extra (`pip install
'clickwheel[plex]'`). Importing this module without it installed is
fine — only `connect()` and friends actually touch plexapi.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from plexapi.library import MusicSection
    from plexapi.playlist import Playlist
    from plexapi.server import PlexServer


class PlexExtraMissingError(RuntimeError):
    """Raised when plexapi isn't installed."""


class PlexConfigInvalidError(ValueError):
    """Raised for a malformed plex config block."""


class PathRemapFailedError(ValueError):
    """A local path didn't start with the configured remap prefix."""


def _import_plexapi() -> Any:
    try:
        import plexapi  # noqa: F401  (presence check)
        import plexapi.server as server_mod

        return server_mod
    except ImportError as exc:
        raise PlexExtraMissingError(
            "plexapi is not installed. Install the optional extra:\n"
            "  pip install 'clickwheel[plex]'  (or `pipx inject clickwheel "
            "'clickwheel[plex]'` if you installed with pipx)"
        ) from exc


def connect(url: str, token: str) -> PlexServer:
    """Open a PlexServer connection. Raises PlexExtraMissingError if plexapi
    isn't installed, or plexapi's own exceptions on network/auth errors.
    """
    server_mod = _import_plexapi()
    return server_mod.PlexServer(url, token)


def find_music_section(plex: PlexServer, library_name: str) -> MusicSection:
    """Return the named music section, or raise LookupError. Matches by
    exact title because Plex allows multiple music sections (e.g. a
    'Music' library and an 'Audiobooks' library both have type=artist),
    and picking by type alone is ambiguous.
    """
    for section in plex.library.sections():
        if section.type == "artist" and section.title == library_name:
            return section
    available = [s.title for s in plex.library.sections() if s.type == "artist"]
    raise LookupError(
        f"No Plex music section named {library_name!r}. "
        f"Available: {available or '(none)'}"
    )


def local_to_plex_path(local_path: str, remap_local: str, remap_plex: str) -> str:
    """Translate a clickwheel-side path to the path Plex sees.

    If `remap_local` and `remap_plex` are both empty, returns the path
    unchanged — that's the case where Plex runs on the same host as
    clickwheel and sees the music dir at exactly the same path.

    Raises PathRemapFailedError if remap is configured but `local_path`
    doesn't start with `remap_local` — silently leaving such a path
    unchanged would produce an M3U Plex couldn't resolve, with no clear
    error message.
    """
    if not remap_local and not remap_plex:
        return local_path
    if not remap_local or not remap_plex:
        raise PlexConfigInvalidError(
            "plex_path_remap_local and plex_path_remap_plex must both be "
            "set, or both empty."
        )
    if not local_path.startswith(remap_local):
        raise PathRemapFailedError(
            f"Path {local_path!r} doesn't start with remap prefix "
            f"{remap_local!r}; can't translate to Plex's view."
        )
    return remap_plex + local_path[len(remap_local) :]


def plex_to_local_path(plex_path: str, remap_local: str, remap_plex: str) -> str:
    """Translate a Plex-side path to the clickwheel-side path.

    Inverse of `local_to_plex_path`. Used when pulling a Plex playlist
    back into clickwheel: each track in the Plex playlist exposes the
    file path *as Plex sees it* (e.g. `/share/CACHEDEV1_DATA/Music/...`
    on a QNAP), which has to be translated to the SMB-mounted path
    (e.g. `/Volumes/Music/...`) before we can match it against the
    SQLite index.

    Same rules as the forward direction: both remaps empty -> identity;
    one set without the other -> PlexConfigInvalidError; configured
    remap but the input path doesn't start with `remap_plex` ->
    PathRemapFailedError.
    """
    if not remap_local and not remap_plex:
        return plex_path
    if not remap_local or not remap_plex:
        raise PlexConfigInvalidError(
            "plex_path_remap_local and plex_path_remap_plex must both be "
            "set, or both empty."
        )
    if not plex_path.startswith(remap_plex):
        raise PathRemapFailedError(
            f"Path {plex_path!r} doesn't start with remap prefix "
            f"{remap_plex!r}; can't translate to clickwheel's view."
        )
    return remap_local + plex_path[len(remap_plex) :]


def build_m3u(
    tracks: list[dict],
    dest_local: Path,
    remap_local: str,
    remap_plex: str,
) -> Path:
    """Write an EXTM3U file at `dest_local` whose body contains
    Plex-side paths to each track.

    Returns the local path written. The corresponding Plex-side path of
    the M3U itself (which is what gets POSTed to Plex's upload
    endpoint) is the caller's responsibility — typically a single
    `local_to_plex_path(dest_local.as_posix(), …)` call. Keeping that
    out of here means the caller decides where the M3U lives (inside
    or outside the remapped tree) and gets a clear error if the
    location is incompatible with the configured remap.
    """
    dest_local.parent.mkdir(parents=True, exist_ok=True)
    lines = ["#EXTM3U"]
    for t in tracks:
        dur = int(t.get("duration_seconds") or -1)
        artist = (t.get("artist") or "").strip()
        title = (t.get("title") or "").strip()
        lines.append(f"#EXTINF:{dur},{artist} - {title}")
        lines.append(local_to_plex_path(t["path"], remap_local, remap_plex))
    dest_local.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest_local


def list_audio_playlists(plex: PlexServer) -> list[Playlist]:
    """Return every audio playlist on the server.

    Plex doesn't scope playlists to a single library section, so we
    just filter by `playlistType == "audio"`. Smart vs manual is
    available on each playlist as `.smart` (bool); callers decide
    whether to surface or skip smart ones.
    """
    return [pl for pl in plex.playlists() if pl.playlistType == "audio"]


def read_playlist_tracks(playlist: Playlist) -> list[dict]:
    """Extract the track list from a Plex playlist into clickwheel dicts.

    Each track yields a dict with `plex_path` (the file path as Plex
    sees it), `title`, `artist`, `album`, and `duration_seconds`.
    Path remap to the clickwheel view is the caller's job — keeping it
    out of here means this function never raises a PathRemapFailedError
    and stays pure-Plex.

    Tracks whose Plex media metadata is missing a file part are
    skipped silently (rare, but possible for stale playlists pointing
    at deleted media).
    """
    out: list[dict] = []
    for t in playlist.items():
        media = getattr(t, "media", None) or []
        if not media:
            continue
        parts = getattr(media[0], "parts", None) or []
        if not parts:
            continue
        file_path = getattr(parts[0], "file", None)
        if not file_path:
            continue
        duration_ms = getattr(t, "duration", None)
        out.append(
            {
                "plex_path": file_path,
                "title": getattr(t, "title", "") or "",
                "artist": getattr(t, "grandparentTitle", "") or "",
                "album": getattr(t, "parentTitle", "") or "",
                "duration_seconds": (duration_ms / 1000.0)
                if isinstance(duration_ms, (int, float))
                else None,
            }
        )
    return out


def find_audio_playlist(plex: PlexServer, name: str) -> Playlist | None:
    """Return the audio playlist matching `name`, or None.

    Plex doesn't enforce unique playlist names — if there are multiple
    matches, we return the first. Callers that want to clear all
    duplicates should use `delete_audio_playlist`.
    """
    for pl in plex.playlists():
        if pl.playlistType == "audio" and pl.title == name:
            return pl
    return None


def delete_audio_playlist(plex: PlexServer, name: str) -> int:
    """Delete every audio playlist named `name`. Returns the count
    actually deleted (0 if none existed)."""
    deleted = 0
    for pl in list(plex.playlists()):
        if pl.playlistType == "audio" and pl.title == name:
            pl.delete()
            deleted += 1
    return deleted


def upload_playlist(
    plex: PlexServer, section: MusicSection, name: str, m3u_plex_path: str
) -> Playlist:
    """Upload an M3U as a Plex playlist named `name`.

    Re-uploading an M3U from the same path overwrites the previously-
    created playlist (this is plexapi's documented behavior and is what
    makes the sync idempotent). If the user has manually created a
    playlist with the same name in Plex, that one is left alone — Plex
    permits duplicate names.
    """
    from plexapi.playlist import Playlist as _Playlist

    return _Playlist.create(
        plex, title=name, section=section, m3ufilepath=m3u_plex_path
    )


def set_playlist_summary(playlist: Playlist, summary: str) -> None:
    """Set a Plex playlist's description (its `summary` field).

    M3U import carries no description, so callers run this after
    `upload_playlist` to mirror the clickwheel-side description onto the
    Plex playlist. Raises plexapi's own exceptions on network/auth errors.
    """
    playlist.editSummary(summary)
