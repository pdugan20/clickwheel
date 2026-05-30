"""Cloud album metadata — MusicBrainz lookup + Cover Art Archive.

clickwheel fetches canonical cover art the way Plex does: identify the
album's MusicBrainz *release group* and pull art keyed to it. The release
group is the unambiguous unit — an album has exactly one, even though it
may have many individual pressings (releases). beets' import matcher
stalls on that pressing-level ambiguity in non-interactive mode; resolving
straight to the release group sidesteps it entirely.

The release group also carries `first-release-date`, so the same lookup
yields the canonical year.

Pure functions, stdlib only (urllib) — no extra dependency, no API key.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from clickwheel import __version__

# MusicBrainz asks every client to identify itself with a descriptive
# User-Agent, or it may rate-limit / reject the request.
_USER_AGENT = f"clickwheel/{__version__} (https://github.com/pdugan20/clickwheel)"
_MB_SEARCH = "https://musicbrainz.org/ws/2/release-group/"
# Cover Art Archive serves a per-release-group front image; the 1200px
# thumbnail is a good size for embedded album art.
_CAA_FRONT = "https://coverartarchive.org/release-group/{mbid}/front-1200"

# MusicBrainz search scores are 0-100; below this the match is too weak
# to trust for an automated, non-interactive operation.
_MIN_SCORE = 90

# Transient failures — network blips, CAA/archive.org 5xx, rate limits —
# are common enough that a single bare attempt routinely drops art that is
# genuinely available. Retry those; a 4xx is definitive and is not retried.
_MAX_ATTEMPTS = 3
_RETRY_BACKOFF = 1.0  # seconds before the first retry, doubled each attempt


class ArtworkLookupError(RuntimeError):
    """A network or API failure talking to MusicBrainz / Cover Art Archive."""


@dataclass(frozen=True)
class AlbumMatch:
    """A resolved MusicBrainz release group."""

    mbid: str
    title: str
    year: int | None


def _get(url: str, timeout: float) -> bytes:
    """Fetch a URL, retrying transient failures with exponential backoff.

    A 4xx (including 404) is a definitive answer and is raised at once;
    5xx, 429, and connection errors are retried up to _MAX_ATTEMPTS times.
    """
    last_exc: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                raise
            last_exc = exc
        except OSError as exc:
            last_exc = exc
        if attempt + 1 < _MAX_ATTEMPTS:
            time.sleep(_RETRY_BACKOFF * 2**attempt)
    assert last_exc is not None  # the loop always records an exception here
    raise last_exc


def lookup_release_group(
    artist: str, album: str, *, timeout: float = 15.0
) -> AlbumMatch | None:
    """Resolve an album to its MusicBrainz release group.

    Returns the best-scoring match, or None when nothing scores above the
    confidence floor. Raises ArtworkLookupError on a network/API failure.
    """
    query = f'releasegroup:"{album}" AND artist:"{artist}"'
    url = (
        _MB_SEARCH
        + "?"
        + urllib.parse.urlencode({"query": query, "fmt": "json", "limit": 5})
    )
    try:
        payload = json.loads(_get(url, timeout))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtworkLookupError(f"MusicBrainz lookup failed: {exc}") from exc

    groups = payload.get("release-groups") or []
    if not groups:
        return None
    # MusicBrainz returns results already sorted by score, descending.
    best = groups[0]
    if best.get("score", 0) < _MIN_SCORE:
        return None

    year: int | None = None
    date = str(best.get("first-release-date") or "")
    if len(date) >= 4 and date[:4].isdigit():
        year = int(date[:4])
    return AlbumMatch(mbid=best["id"], title=str(best.get("title") or album), year=year)


def fetch_front_cover(mbid: str, *, timeout: float = 30.0) -> bytes | None:
    """Fetch the front-cover image bytes for a release group.

    Returns None when the Cover Art Archive has no art for it (HTTP 404).
    Raises ArtworkLookupError on any other network/API failure.
    """
    try:
        return _get(_CAA_FRONT.format(mbid=mbid), timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise ArtworkLookupError(f"Cover Art Archive error: HTTP {exc.code}") from exc
    except OSError as exc:
        raise ArtworkLookupError(f"Cover Art Archive request failed: {exc}") from exc
