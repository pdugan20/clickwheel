"""Last.fm scrobbling — read iPod play counts and submit to Last.fm."""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Last.fm rejects scrobbles older than 14 days
MAX_SCROBBLE_AGE_SECONDS = 14 * 24 * 3600

# Last.fm allows up to 50 scrobbles per batch
BATCH_SIZE = 50


@dataclass
class PendingScrobble:
    """A play that should be scrobbled."""

    artist: str
    title: str
    album: str | None
    timestamp: int  # Unix timestamp when track started playing
    duration: int  # Duration in seconds


def read_ipod_plays(
    ipod_mount: Path,
) -> list[PendingScrobble]:
    """Read recent plays from iPod and return scrobble candidates.

    Reads the Play Counts file and correlates with iTunesDB track metadata.
    Estimates start timestamps by working backward from last_played using
    track duration.
    """
    from clickwheel.ipod import get_ipod_tracks, read_ipod, read_play_counts
    from clickwheel.ipod.itunesdb_parser.playcounts import merge_playcounts

    play_counts = read_play_counts(ipod_mount)
    if play_counts is None:
        logger.info("No Play Counts file on iPod — nothing played since last sync")
        return []

    ipod_db = read_ipod(ipod_mount)
    tracks = get_ipod_tracks(ipod_db)

    if not tracks:
        logger.warning("No tracks found in iTunesDB")
        return []

    merge_playcounts(tracks, play_counts)

    scrobbles: list[PendingScrobble] = []
    now = int(time.time())

    for track in tracks:
        recent = track.get("recent_playcount", 0)
        if recent <= 0:
            continue

        artist = track.get("artist", "")
        title = track.get("title", "")
        if not artist or not title:
            continue

        album = track.get("album")
        duration_ms = track.get("length", 0) or track.get("duration", 0) or 0
        duration_s = duration_ms // 1000 if duration_ms > 1000 else duration_ms

        # Skip tracks under 30 seconds (Last.fm won't accept them)
        if duration_s < 30:
            continue

        last_played = track.get("lastPlayed", 0)
        if last_played <= 0:
            last_played = now

        # Estimate timestamps for each play, working backward
        for i in range(recent):
            estimated_start = last_played - (duration_s * (recent - i))
            # Don't scrobble plays older than 14 days
            if now - estimated_start > MAX_SCROBBLE_AGE_SECONDS:
                logger.debug(
                    "Skipping old play: %s - %s (%.0f days ago)",
                    artist,
                    title,
                    (now - estimated_start) / 86400,
                )
                continue

            scrobbles.append(
                PendingScrobble(
                    artist=artist,
                    title=title,
                    album=album,
                    timestamp=estimated_start,
                    duration=duration_s,
                )
            )

    scrobbles.sort(key=lambda s: s.timestamp)
    return scrobbles


def cache_scrobbles(
    db_conn: sqlite3.Connection, scrobbles: list[PendingScrobble]
) -> int:
    """Store scrobbles in the cache, skipping duplicates. Returns count added."""
    added = 0
    for s in scrobbles:
        try:
            before = db_conn.total_changes
            db_conn.execute(
                """
                INSERT OR IGNORE INTO scrobble_cache
                    (artist, album, title, timestamp, duration_seconds)
                VALUES (?, ?, ?, ?, ?)
                """,
                (s.artist, s.album, s.title, s.timestamp, s.duration),
            )
            if db_conn.total_changes > before:
                added += 1
        except sqlite3.Error:
            pass
    db_conn.commit()
    return added


def get_pending_scrobbles(db_conn: sqlite3.Connection) -> list[dict]:
    """Get all unsubmitted scrobbles from the cache, oldest first."""
    rows = db_conn.execute(
        """
        SELECT id, artist, album, title, timestamp, duration_seconds
        FROM scrobble_cache
        WHERE submitted = 0
        ORDER BY timestamp ASC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def submit_scrobbles(
    api_key: str,
    api_secret: str,
    username: str,
    scrobbles: list[dict],
    db_conn: sqlite3.Connection,
) -> tuple[int, int]:
    """Submit scrobbles to Last.fm in batches.

    Returns (submitted_count, error_count).
    """
    import pylast

    network = pylast.LastFMNetwork(
        api_key=api_key,
        api_secret=api_secret,
        username=username,
    )

    submitted = 0
    errors = 0

    for i in range(0, len(scrobbles), BATCH_SIZE):
        batch = scrobbles[i : i + BATCH_SIZE]

        scrobble_dicts = [
            {
                "artist": s["artist"],
                "title": s["title"],
                "timestamp": s["timestamp"],
                "album": s.get("album") or "",
                "duration": int(s.get("duration_seconds") or 0),
            }
            for s in batch
        ]

        try:
            network.scrobble_many(scrobble_dicts)

            ids = [s["id"] for s in batch]
            placeholders = ",".join("?" * len(ids))
            db_conn.execute(
                f"UPDATE scrobble_cache SET submitted = 1, "
                f"submitted_at = CURRENT_TIMESTAMP "
                f"WHERE id IN ({placeholders})",
                ids,
            )
            db_conn.commit()
            submitted += len(batch)
        except pylast.WSError as exc:
            logger.error("Last.fm API error: %s", exc)
            errors += len(batch)
        except Exception:
            logger.exception("Failed to submit scrobble batch")
            errors += len(batch)

    return submitted, errors


def get_lastfm_profile(api_key: str, api_secret: str, username: str) -> dict | None:
    """Fetch basic Last.fm user profile info."""
    try:
        import pylast

        network = pylast.LastFMNetwork(
            api_key=api_key,
            api_secret=api_secret,
        )
        user = network.get_user(username)
        return {
            "name": user.get_name(),
            "playcount": user.get_playcount(),
            "url": f"https://www.last.fm/user/{username}",
        }
    except Exception:
        logger.exception("Failed to fetch Last.fm profile")
        return None
