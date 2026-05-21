"""Apple Music integration helpers — pure functions consumed by actions.py.

This module owns the mechanical work of talking to Apple Music: JWT
developer-token signing, the Music User Token auth dance (a tiny local
HTTP server that serves a MusicKit-JS page and catches the redirect),
and thin REST helpers for the catalog/library probes the doctor uses.
It deliberately raises bare exceptions; `actions.py` is the layer that
catches them and re-raises typed ClickwheelError variants so the CLI
and MCP surface can present consistent errors.

The `pyjwt[crypto]` package is an optional extra (`pip install
'clickwheel[applemusic]'`). Importing this module without it is fine;
only the JWT helpers actually touch pyjwt.
"""

from __future__ import annotations

import gzip
import json
import logging
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import zlib
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Apple Music's REST root. Same host for catalog and library endpoints;
# /v1/catalog/... is public-catalog-scoped, /v1/me/... requires both
# the developer token AND a Music User Token.
API_ROOT = "https://api.music.apple.com"


class AppleMusicExtraMissingError(RuntimeError):
    """Raised when pyjwt[crypto] isn't installed."""


class AppleMusicConfigInvalidError(ValueError):
    """Raised for a malformed apple_music config block."""


class AppleMusicAuthFailedError(RuntimeError):
    """Raised when the user-token auth dance didn't yield a token."""


class AppleScriptError(RuntimeError):
    """Raised when an osascript subprocess returns non-zero or the
    output can't be parsed. Used by `delete_local_music_playlist`.
    """


class AppleScriptUnavailableError(RuntimeError):
    """Raised when AppleScript can't be used — non-macOS platform, or
    `osascript` not on PATH (vanishingly rare on a normal Mac).
    """


class AppleMusicHTTPError(RuntimeError):
    """Wrapper for non-2xx responses from api.music.apple.com.

    Carries the status code and the response body (if any) so the
    doctor can surface Apple's error detail without callers needing
    to know the urllib exception shape.
    """

    def __init__(self, status: int, body: str, url: str) -> None:
        excerpt = body[:200] or "(empty body)"
        super().__init__(f"Apple Music returned HTTP {status} for {url}: {excerpt}")
        self.status = status
        self.body = body
        self.url = url


def _import_jwt() -> Any:
    """Import pyjwt lazily so the rest of clickwheel doesn't pay the
    cryptography cost. Re-raises as AppleMusicExtraMissingError with a
    pip install command in the message.
    """
    try:
        import jwt  # PyJWT

        return jwt
    except ImportError as exc:
        raise AppleMusicExtraMissingError(
            "pyjwt is not installed. Install the optional extra:\n"
            "  pip install 'clickwheel[applemusic]'  (or `pipx inject clickwheel "
            "'clickwheel[applemusic]'` if you installed with pipx)"
        ) from exc


def read_isrc(file_path: str | Path) -> str | None:
    """Extract the ISRC code from an audio file's tags via mutagen.

    Supports MP3 (ID3 TSRC frame), M4A (©ISR atom / "----:com.apple.iTunes:ISRC"),
    and FLAC (Vorbis comment 'ISRC' field). Returns the normalized ISRC
    string (uppercase, no hyphens) or None if the file has no ISRC tag
    or the file can't be read.

    ISRC tagging is inconsistent — many MP3s from older sources lack
    it. The matcher uses ISRC as the fast path and falls back to fuzzy
    search when it's missing.
    """
    from mutagen import File as MutagenFile  # lazy: avoids cycle with library.py

    try:
        audio = MutagenFile(str(file_path))
    except Exception:  # noqa: BLE001  — mutagen raises a zoo of exceptions
        return None
    if audio is None:
        return None

    # MP3 (ID3) — TSRC frame; mutagen exposes via tags.getall("TSRC")
    tsrc = audio.tags.getall("TSRC") if getattr(audio, "tags", None) else []
    if tsrc:
        return _normalize_isrc(str(tsrc[0]))

    # M4A — atoms come back as a dict-like; iTunes-specific atoms live
    # under "----:com.apple.iTunes:ISRC" and the value is a list of
    # MP4FreeForm bytes objects.
    if hasattr(audio, "tags") and audio.tags is not None:
        m4a_value = audio.tags.get("----:com.apple.iTunes:ISRC")
        if m4a_value:
            try:
                raw = bytes(m4a_value[0]).decode("utf-8")
            except Exception:  # noqa: BLE001
                raw = ""
            if raw:
                return _normalize_isrc(raw)

    # FLAC / Vorbis comments — flat dict with uppercase keys.
    vorbis = audio.get("ISRC") or audio.get("isrc") if hasattr(audio, "get") else None
    if vorbis:
        return _normalize_isrc(str(vorbis[0]))

    return None


def _normalize_isrc(raw: str) -> str:
    """Strip whitespace and hyphens; uppercase. ISRC is 12 chars
    (2-char country + 3-char registrant + 2-digit year + 5-digit
    designation), case-insensitive but Apple's filter expects the
    canonical form."""
    return raw.strip().replace("-", "").upper()


def read_private_key(path: str | Path) -> str:
    """Read a MusicKit .p8 private key, expanding ~ in the path.

    Returns the PEM string. Raises FileNotFoundError or
    AppleMusicConfigInvalidError if the file isn't a PEM private key.
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f".p8 key file not found: {p}")
    text = p.read_text()
    if "BEGIN PRIVATE KEY" not in text:
        raise AppleMusicConfigInvalidError(
            f"{p} doesn't look like a PEM private key (no 'BEGIN PRIVATE KEY' "
            "marker). Re-download the .p8 from developer.apple.com."
        )
    return text


def generate_developer_token(
    key_pem: str,
    key_id: str,
    team_id: str,
    ttl_seconds: int = 180 * 24 * 3600,
) -> str:
    """Sign a MusicKit developer token (JWT, ES256).

    Apple caps token lifetime at 180 days; we default to that ceiling
    so the token's good for as long as possible without re-signing.
    Callers that want shorter tokens (e.g. CI tests) can pass
    `ttl_seconds`.
    """
    jwt = _import_jwt()
    now = int(time.time())
    payload = {"iss": team_id, "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(payload, key_pem, algorithm="ES256", headers={"kid": key_id})


def _decode_body(raw: bytes, encoding: str | None) -> str:
    """Decompress (if needed) and decode an HTTP body to text.

    Apple Music's REST API sometimes returns gzip-compressed responses
    even when the client doesn't send `Accept-Encoding: gzip` — the
    library/playlists POST endpoint is the most consistent offender.
    Detecting and unwrapping here keeps callers naive.
    """
    if encoding == "gzip":
        raw = gzip.decompress(raw)
    elif encoding == "deflate":
        raw = zlib.decompress(raw)
    return raw.decode("utf-8") if raw else ""


def _request_json(
    url: str,
    *,
    headers: dict[str, str],
    method: str = "GET",
    data: bytes | None = None,
    timeout: float = 10.0,
) -> dict:
    """Minimal JSON HTTP helper. Returns the decoded body or raises
    AppleMusicHTTPError with status + body."""
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = _decode_body(resp.read(), resp.headers.get("Content-Encoding"))
            return json.loads(text) if text else {}
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = _decode_body(exc.read(), exc.headers.get("Content-Encoding"))
        except Exception:
            pass
        raise AppleMusicHTTPError(exc.code, body, url) from exc


def verify_developer_token(token: str, storefront: str = "us") -> dict:
    """Round-trip the developer token against the catalog search
    endpoint. Returns the first hit if any. Raises AppleMusicHTTPError
    on auth failure or network problems.

    A 401 here typically means the key behind `kid` was revoked on
    developer.apple.com, or the signature doesn't match the kid header.
    """
    url = f"{API_ROOT}/v1/catalog/{storefront}/search?term=nirvana&types=songs&limit=1"
    body = _request_json(url, headers={"Authorization": f"Bearer {token}"})
    songs = body.get("results", {}).get("songs", {}).get("data", [])
    return songs[0] if songs else {}


def verify_user_token(dev_token: str, user_token: str, storefront: str = "us") -> dict:
    """Round-trip a Music User Token against /v1/me/storefront.

    Returns the user's storefront record (which carries the
    authoritative country code Apple thinks the user is in). Raises
    AppleMusicHTTPError on 401/403 (user token expired or rejected) or
    if the dev token itself isn't accepted.
    """
    return _request_json(
        f"{API_ROOT}/v1/me/storefront",
        headers={
            "Authorization": f"Bearer {dev_token}",
            "Music-User-Token": user_token,
        },
    )


def detect_icloud_music_library(
    dev_token: str, user_token: str, storefront: str = "us"
) -> bool:
    """Probe whether iCloud Music Library is on for this user.

    Strategy: hit /v1/me/library/songs?limit=1. If we get a 200 with a
    songs array (even empty), iCML is on. If Apple returns 403
    "USER_LIBRARY_DISABLED" (or similar), it's off. Other failures
    propagate as AppleMusicHTTPError.
    """
    try:
        _request_json(
            f"{API_ROOT}/v1/me/library/songs?limit=1",
            headers={
                "Authorization": f"Bearer {dev_token}",
                "Music-User-Token": user_token,
            },
        )
        return True
    except AppleMusicHTTPError as exc:
        # 403 typically signals iCML disabled. We don't trust the body
        # message format (it varies); the status is the load-bearing
        # signal. 401 would be an auth problem, not an iCML problem —
        # let that re-raise.
        if exc.status == 403:
            return False
        raise


# ---------------------------------------------------------------------------
# Catalog + library matching
# ---------------------------------------------------------------------------

# Confidence floor below which we refuse to claim a match. The matcher
# returns the candidate anyway so callers can show "low confidence"
# rows; the floor only controls whether the doctor/push treats it as
# a usable hit. Adjusted empirically; raise if you see false positives.
MATCH_MIN_CONFIDENCE = 0.60


@dataclass
class CatalogMatch:
    """One catalog/library hit for a clickwheel track. `kind` is
    `'catalog'` for `/v1/catalog/...` results (public catalog, works
    without subscription for reading) or `'library'` for
    `/v1/me/library/...` results (user-uploaded tracks via iCloud
    Music Library; need an active subscription).
    """

    song_id: str
    kind: str  # 'catalog' | 'library'
    confidence: float  # 0.0-1.0
    matched_artist: str = ""
    matched_title: str = ""
    matched_album: str = ""
    isrc: str | None = None


def catalog_by_isrc(
    dev_token: str, isrc: str, storefront: str = "us"
) -> CatalogMatch | None:
    """Look up a song in the public catalog by ISRC. ISRC is the
    canonical identifier for a recording, so a hit here is high-
    confidence — we return confidence 1.0.

    Returns None if Apple has no catalog entry for the ISRC. Other
    errors (auth, network) propagate as AppleMusicHTTPError.
    """
    url = (
        f"{API_ROOT}/v1/catalog/{storefront}/songs"
        f"?filter%5Bisrc%5D={urllib.parse.quote(isrc)}&limit=1"
    )
    body = _request_json(url, headers={"Authorization": f"Bearer {dev_token}"})
    data = body.get("data", [])
    if not data:
        return None
    item = data[0]
    attrs = item.get("attributes", {})
    return CatalogMatch(
        song_id=item["id"],
        kind="catalog",
        confidence=1.0,
        matched_artist=attrs.get("artistName", ""),
        matched_title=attrs.get("name", ""),
        matched_album=attrs.get("albumName", ""),
        isrc=attrs.get("isrc"),
    )


def _score(want: str, got: str) -> float:
    """SequenceMatcher ratio between two normalized strings. Treats
    None / empty inputs as zero, so missing tags don't score as 1.0."""
    from difflib import SequenceMatcher

    if not want or not got:
        return 0.0
    return SequenceMatcher(None, want.strip().lower(), got.strip().lower()).ratio()


def _composite_confidence(
    want_artist: str,
    want_title: str,
    want_album: str,
    got_artist: str,
    got_title: str,
    got_album: str,
) -> float:
    """Combine per-field similarity into a single confidence score.

    Title is the strongest signal (artists routinely have many
    different track titles, but title collisions across artists are
    rare), so it gets the highest weight. Album is the noisiest
    (deluxe / remaster suffixes wreck similarity) so it gets the
    lowest. Tuned on the user's clickwheel library — adjust if
    fielded false-positive rate is bad.
    """
    title_score = _score(want_title, got_title)
    artist_score = _score(want_artist, got_artist)
    album_score = _score(want_album, got_album)
    return 0.55 * title_score + 0.35 * artist_score + 0.10 * album_score


def catalog_fuzzy_search(
    dev_token: str,
    artist: str,
    title: str,
    album: str = "",
    storefront: str = "us",
    limit: int = 10,
) -> CatalogMatch | None:
    """Catalog search by artist + title (album as tiebreaker).

    Returns the highest-scoring candidate, or None if no candidate
    scores above MATCH_MIN_CONFIDENCE. The confidence comes from
    `_composite_confidence`; weighted toward title.
    """
    if not title and not artist:
        return None
    term = f"{artist} {title}".strip()
    url = (
        f"{API_ROOT}/v1/catalog/{storefront}/search"
        f"?term={urllib.parse.quote(term)}"
        f"&types=songs&limit={limit}"
    )
    body = _request_json(url, headers={"Authorization": f"Bearer {dev_token}"})
    songs = body.get("results", {}).get("songs", {}).get("data", [])
    if not songs:
        return None

    best: CatalogMatch | None = None
    for item in songs:
        attrs = item.get("attributes", {})
        score = _composite_confidence(
            artist,
            title,
            album,
            attrs.get("artistName", ""),
            attrs.get("name", ""),
            attrs.get("albumName", ""),
        )
        if best is None or score > best.confidence:
            best = CatalogMatch(
                song_id=item["id"],
                kind="catalog",
                confidence=score,
                matched_artist=attrs.get("artistName", ""),
                matched_title=attrs.get("name", ""),
                matched_album=attrs.get("albumName", ""),
                isrc=attrs.get("isrc"),
            )
    if best is None or best.confidence < MATCH_MIN_CONFIDENCE:
        return None
    return best


def library_search(
    dev_token: str,
    user_token: str,
    artist: str,
    title: str,
    album: str = "",
    limit: int = 10,
) -> CatalogMatch | None:
    """Same shape as catalog_fuzzy_search but against the user's
    library (iCloud Music Library). Returns library-songs IDs (prefixed
    with `i.`) that are playlist-eligible when iCML is on. Useful for
    matching tracks the user uploaded that aren't in the public catalog.
    """
    if not title and not artist:
        return None
    term = f"{artist} {title}".strip()
    url = (
        f"{API_ROOT}/v1/me/library/search"
        f"?term={urllib.parse.quote(term)}"
        f"&types=library-songs&limit={limit}"
    )
    body = _request_json(
        url,
        headers={
            "Authorization": f"Bearer {dev_token}",
            "Music-User-Token": user_token,
        },
    )
    songs = body.get("results", {}).get("library-songs", {}).get("data", [])
    if not songs:
        return None
    best: CatalogMatch | None = None
    for item in songs:
        attrs = item.get("attributes", {})
        score = _composite_confidence(
            artist,
            title,
            album,
            attrs.get("artistName", ""),
            attrs.get("name", ""),
            attrs.get("albumName", ""),
        )
        if best is None or score > best.confidence:
            best = CatalogMatch(
                song_id=item["id"],
                kind="library",
                confidence=score,
                matched_artist=attrs.get("artistName", ""),
                matched_title=attrs.get("name", ""),
                matched_album=attrs.get("albumName", ""),
            )
    if best is None or best.confidence < MATCH_MIN_CONFIDENCE:
        return None
    return best


def match_track(
    *,
    dev_token: str,
    user_token: str | None,
    storefront: str,
    artist: str,
    title: str,
    album: str = "",
    isrc: str | None = None,
    icml: bool = False,
) -> CatalogMatch | None:
    """Top-level matcher: tries ISRC → catalog fuzzy → library fuzzy
    (last only when iCloud Music Library is on AND a user token is
    available). Returns the first usable hit.

    Order matters: ISRC is exact, so even a low-confidence fuzzy hit
    shouldn't override it. Library only gets a vote if the catalog
    couldn't satisfy the request.
    """
    if isrc:
        try:
            isrc_hit = catalog_by_isrc(dev_token, isrc, storefront)
        except AppleMusicHTTPError as exc:
            logger.debug("ISRC lookup %s failed: %s", isrc, exc)
            isrc_hit = None
        if isrc_hit is not None:
            return isrc_hit

    try:
        fuzzy_hit = catalog_fuzzy_search(dev_token, artist, title, album, storefront)
    except AppleMusicHTTPError as exc:
        logger.debug("catalog fuzzy %s/%s failed: %s", artist, title, exc)
        fuzzy_hit = None
    if fuzzy_hit is not None:
        return fuzzy_hit

    if icml and user_token:
        try:
            lib_hit = library_search(dev_token, user_token, artist, title, album)
        except AppleMusicHTTPError as exc:
            logger.debug("library search %s/%s failed: %s", artist, title, exc)
            lib_hit = None
        if lib_hit is not None:
            return lib_hit

    return None


# ---------------------------------------------------------------------------
# Library playlist mutation
# ---------------------------------------------------------------------------


@dataclass
class UserPlaylistSummary:
    """One entry in `list_user_playlists`."""

    playlist_id: str  # 'p.xxxxx'
    name: str
    description: str = ""
    track_count: int = 0
    can_edit: bool = True


def list_user_playlists(dev_token: str, user_token: str) -> list[UserPlaylistSummary]:
    """List every library playlist in the user's Apple Music account.

    Pages through `/v1/me/library/playlists` (default 100 per page)
    until the server stops returning a `next` cursor. Returns a flat
    list of summaries.
    """
    out: list[UserPlaylistSummary] = []
    offset = 0
    while True:
        body = _request_json(
            f"{API_ROOT}/v1/me/library/playlists?limit=100&offset={offset}",
            headers={
                "Authorization": f"Bearer {dev_token}",
                "Music-User-Token": user_token,
            },
        )
        data = body.get("data", [])
        if not data:
            break
        for item in data:
            attrs = item.get("attributes", {})
            desc = attrs.get("description", {})
            # description can be either a dict {standard: ..., short: ...}
            # or absent. Be defensive.
            desc_text = (
                desc.get("standard", "") if isinstance(desc, dict) else str(desc or "")
            )
            out.append(
                UserPlaylistSummary(
                    playlist_id=item["id"],
                    name=attrs.get("name", ""),
                    description=desc_text,
                    track_count=int(attrs.get("trackCount", 0) or 0),
                    can_edit=bool(attrs.get("canEdit", True)),
                )
            )
        if "next" not in body:
            break
        offset += len(data)
    return out


def read_user_playlist_tracks(
    dev_token: str, user_token: str, playlist_id: str
) -> list[dict]:
    """Return the track records inside a single library playlist.

    Each entry has `song_id` (the catalog `songs` id or library
    `library-songs` id), `kind` (`'catalog' | 'library'`), and
    `artist`/`title`/`album`/`isrc`/`duration_seconds` extracted from
    Apple's response. Pages until exhausted.
    """
    out: list[dict] = []
    offset = 0
    while True:
        body = _request_json(
            f"{API_ROOT}/v1/me/library/playlists/{playlist_id}/tracks"
            f"?limit=100&offset={offset}",
            headers={
                "Authorization": f"Bearer {dev_token}",
                "Music-User-Token": user_token,
            },
        )
        data = body.get("data", [])
        if not data:
            break
        for item in data:
            attrs = item.get("attributes", {})
            duration_ms = attrs.get("durationInMillis")
            # Track records from the user's library carry catalog
            # IDs in `playParams.catalogId` (when the track is the
            # catalog edition) and library IDs in `playParams.id`
            # (always). Apple's `id` field on the row itself is the
            # library id. We prefer catalog id when available so the
            # push direction round-trips cleanly.
            play_params = attrs.get("playParams", {}) or {}
            catalog_id = play_params.get("catalogId")
            song_id = catalog_id or item["id"]
            kind = "catalog" if catalog_id else "library"
            out.append(
                {
                    "song_id": str(song_id),
                    "kind": kind,
                    "artist": attrs.get("artistName", ""),
                    "title": attrs.get("name", ""),
                    "album": attrs.get("albumName", ""),
                    "isrc": attrs.get("isrc"),
                    "duration_seconds": (
                        duration_ms / 1000.0
                        if isinstance(duration_ms, (int, float))
                        else None
                    ),
                }
            )
        if "next" not in body:
            break
        offset += len(data)
    return out


def create_library_playlist(
    dev_token: str,
    user_token: str,
    name: str,
    description: str,
    song_ids: list[dict],
) -> dict:
    """POST a new library playlist. `song_ids` is a list of
    `{"id": ..., "type": "songs"|"library-songs"}` records — catalog
    hits use type `songs`, library hits use type `library-songs`.

    Returns Apple's playlist record (carrying the new library
    playlist's ID, which has the `p.` prefix for cross-references).
    Raises AppleMusicHTTPError on failure.
    """
    payload = {
        "attributes": {"name": name, "description": description},
        "relationships": {
            "tracks": {"data": song_ids},
        },
    }
    return _request_json(
        f"{API_ROOT}/v1/me/library/playlists",
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {dev_token}",
            "Music-User-Token": user_token,
            "Content-Type": "application/json",
        },
    )


# ---------------------------------------------------------------------------
# Music User Token auth dance
# ---------------------------------------------------------------------------


_AUTH_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>clickwheel — Apple Music auth</title>
<style>
  body {{ font: 16px/1.5 -apple-system, system-ui, sans-serif; max-width: 36rem;
         margin: 4rem auto; padding: 0 1rem; color: #222; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 0.5rem; }}
  button {{ font: inherit; padding: 0.6rem 1rem; background: #fa233b; color: #fff;
            border: 0; border-radius: 6px; cursor: pointer; }}
  button:disabled {{ background: #ccc; cursor: not-allowed; }}
  .status {{ margin-top: 1.5rem; padding: 0.75rem 1rem; border-radius: 6px;
             background: #f4f4f4; }}
  .ok {{ background: #d6f5d6; }}
  .err {{ background: #fde2e2; }}
  code {{ background: #f4f4f4; padding: 0.1rem 0.3rem; border-radius: 3px; }}
</style>
</head>
<body>
<h1>clickwheel — Apple Music authorization</h1>
<p>
  Click below to sign in with your Apple ID. clickwheel will receive a
  Music User Token so it can create and read playlists on your behalf.
  This window will close automatically when authorization completes.
</p>
<button id="auth-btn" disabled>Loading MusicKit…</button>
<div id="status" class="status">Waiting for MusicKit to load…</div>

<script src="https://js-cdn.music.apple.com/musickit/v3/musickit.js"
        data-web-components async></script>
<script>
const DEV_TOKEN = {dev_token_json};
const APP_NAME  = "clickwheel";
const APP_BUILD = {build_json};

document.addEventListener("musickitloaded", async () => {{
  try {{
    await MusicKit.configure({{
      developerToken: DEV_TOKEN,
      app: {{ name: APP_NAME, build: APP_BUILD }},
    }});
    const btn = document.getElementById("auth-btn");
    const stat = document.getElementById("status");
    btn.disabled = false;
    btn.textContent = "Authorize with Apple Music";
    stat.textContent = "MusicKit ready. Click the button to sign in.";

    btn.addEventListener("click", async () => {{
      btn.disabled = true;
      btn.textContent = "Authorizing…";
      try {{
        const userToken = await MusicKit.getInstance().authorize();
        stat.className = "status ok";
        stat.innerHTML = "Authorized. Sending token back to clickwheel… "
                       + "you can close this window once it confirms.";
        const r = await fetch("/callback", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ user_token: userToken }}),
        }});
        if (r.ok) {{
          stat.innerHTML = "Done. Token saved. You can close this window.";
        }} else {{
          stat.className = "status err";
          stat.textContent = "clickwheel rejected the token (HTTP " + r.status + ").";
        }}
      }} catch (e) {{
        stat.className = "status err";
        stat.textContent = "Authorization failed: " + (e && e.message || e);
        btn.disabled = false;
        btn.textContent = "Try again";
      }}
    }});
  }} catch (e) {{
    const stat = document.getElementById("status");
    stat.className = "status err";
    stat.textContent = "MusicKit.configure failed: " + (e && e.message || e);
  }}
}});
</script>
</body>
</html>
"""


def _pick_free_port() -> int:
    """Bind a socket to 127.0.0.1:0 to let the kernel pick a free
    ephemeral port, then close it. Tiny race window but fine for a
    one-shot interactive flow."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class AuthServerResult:
    user_token: str | None
    error: str | None


def run_user_token_auth(
    dev_token: str,
    *,
    build: str,
    port: int | None = None,
    timeout_seconds: float = 300.0,
    open_browser: bool = True,
) -> AuthServerResult:
    """Run the local MusicKit-JS auth dance.

    Spins up an HTTP server on 127.0.0.1, opens the user's browser to
    it, waits for the browser to POST the user token back to /callback.
    Returns the captured token (or an error string explaining what went
    wrong), then shuts the server down.

    `timeout_seconds` is the upper bound on how long we wait for the
    user. The browser is opened best-effort — if the open fails, the
    URL is still surfaced via the returned result so the user can
    paste it manually.
    """
    if not dev_token:
        raise AppleMusicAuthFailedError(
            "developer token is empty; can't run user-token auth without it."
        )

    selected_port = port if port is not None else _pick_free_port()
    result = AuthServerResult(user_token=None, error=None)
    done = threading.Event()

    html = _AUTH_HTML.format(
        dev_token_json=json.dumps(dev_token),
        build_json=json.dumps(build),
    )

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # noqa: N802  (stdlib API)
            # Silence the default per-request stderr logging; we route
            # through the module logger instead.
            logger.debug("auth-server: " + fmt, *args)

        def do_GET(self):  # noqa: N802
            if self.path in ("/", "/index.html"):
                payload = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):  # noqa: N802
            if self.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                result.error = "callback body wasn't valid JSON"
                done.set()
                return
            token = body.get("user_token")
            if not token:
                self.send_response(400)
                self.end_headers()
                result.error = "callback body missing 'user_token'"
                done.set()
                return
            result.user_token = token
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            done.set()

    server = HTTPServer(("127.0.0.1", selected_port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{selected_port}/"
    logger.info("Apple Music auth server listening at %s", url)

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception as exc:
            logger.debug("webbrowser.open failed: %s", exc)

    try:
        completed = done.wait(timeout=timeout_seconds)
        if not completed:
            result.error = (
                f"Timed out after {int(timeout_seconds)}s waiting for the "
                "browser to complete the MusicKit auth flow."
            )
    finally:
        server.shutdown()
        server.server_close()

    return result


# ---------------------------------------------------------------------------
# AppleScript-based delete (the workaround for Apple's REST API gap)
# ---------------------------------------------------------------------------


def _escape_applescript_string(value: str) -> str:
    """AppleScript double-quoted strings escape `\\` and `"`. Returns
    the contents (no surrounding quotes) ready to be interpolated
    inside `"..."`.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _run_osascript(script: str, *, timeout: float = 30.0) -> str:
    """Run an AppleScript snippet and return its stdout.

    Raises AppleScriptUnavailableError on non-macOS (or if osascript
    is missing — vanishingly rare on a real Mac). Raises
    AppleScriptError on a non-zero exit, carrying stderr.
    """
    if sys.platform != "darwin":
        raise AppleScriptUnavailableError(
            "AppleScript delete only works on macOS — Music.app isn't "
            "available on this platform."
        )
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AppleScriptUnavailableError(
            "osascript binary not found on PATH. Is this really a Mac?"
        ) from exc
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or "(no stderr)"
        raise AppleScriptError(f"osascript exited {proc.returncode}: {stderr}")
    return proc.stdout.strip()


def delete_local_music_playlist(name: str) -> int:
    """Delete every Music.app playlist matching `name`.

    Drives Music.app via AppleScript — Apple's REST API doesn't
    support library playlist deletion, so this is the documented
    workaround. Music.app's iCloud Music Library sync propagates the
    deletion to the user's iPhone/iPad/Apple Music account.

    Returns the count of playlists actually deleted (matches by exact
    case-sensitive name; 0 if no match). Raises AppleScriptError on
    any osascript-level failure or AppleScriptUnavailableError on
    non-macOS.

    Caveats:
    - Music.app must be launchable (it is on every recent Mac).
    - The user must be signed into the same Apple ID that holds the
      playlist for the iCML propagation to reach other devices.
    - Smart playlists can be deleted too — AppleScript bypasses the
      `canEdit=false` restriction the REST API enforces.
    """
    safe_name = _escape_applescript_string(name)
    script = f'''
        tell application "Music"
            set _matches to (every playlist whose name is "{safe_name}")
            set _count to (count of _matches)
            repeat with _p in _matches
                delete _p
            end repeat
            return _count
        end tell
    '''
    output = _run_osascript(script)
    try:
        return int(output)
    except ValueError as exc:
        raise AppleScriptError(
            f"osascript returned non-integer count: {output!r}"
        ) from exc
