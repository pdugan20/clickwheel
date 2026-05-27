"""SQLite database for library index and selections."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    title TEXT,
    artist TEXT,
    album TEXT,
    album_artist TEXT,
    genre TEXT,
    track_number INTEGER,
    disc_number INTEGER,
    year INTEGER,
    duration_seconds REAL,
    bitrate INTEGER,
    sample_rate INTEGER,
    format TEXT,
    file_size INTEGER,
    has_art INTEGER DEFAULT 0,
    art_width INTEGER,
    art_height INTEGER,
    scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id INTEGER NOT NULL,
    track_id INTEGER NOT NULL,
    position INTEGER,
    PRIMARY KEY (playlist_id, track_id),
    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
    FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS scrobble_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    artist TEXT NOT NULL,
    album TEXT,
    title TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    duration_seconds REAL,
    submitted INTEGER DEFAULT 0,
    submitted_at TIMESTAMP,
    UNIQUE(artist, title, timestamp)
);

CREATE TABLE IF NOT EXISTS scan_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS apple_music_song_map (
    track_path TEXT PRIMARY KEY,
    song_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    confidence REAL NOT NULL,
    storefront TEXT NOT NULL,
    matched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- MusicBrainz lookup cache. status='matched' rows have a real mbid +
-- year; status='unmatched' rows record albums MB couldn't resolve, so
-- subsequent fix runs don't burn the 1-req/s rate limit on known
-- no-matches. Invalidated wholesale by `clickwheel fix --refresh-mb`.
CREATE TABLE IF NOT EXISTS mb_matches (
    artist TEXT NOT NULL,
    album TEXT NOT NULL,
    status TEXT NOT NULL,
    mbid TEXT,
    year INTEGER,
    fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (artist, album)
);

-- Last.fm genre lookup cache. Same shape as mb_matches: positive +
-- negative outcomes are both cached so subsequent fix runs skip the
-- network entirely. Invalidated by `clickwheel fix --refresh-genres`.
CREATE TABLE IF NOT EXISTS genre_matches (
    artist TEXT NOT NULL,
    album TEXT NOT NULL,
    status TEXT NOT NULL,
    genre TEXT,
    fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (artist, album)
);

CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist);
CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album);
CREATE INDEX IF NOT EXISTS idx_tracks_album_artist ON tracks(album_artist);
CREATE INDEX IF NOT EXISTS idx_tracks_genre ON tracks(genre);
CREATE INDEX IF NOT EXISTS idx_tracks_format ON tracks(format);
CREATE INDEX IF NOT EXISTS idx_am_song_map_kind ON apple_music_song_map(kind);
"""


class Database:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Run schema migrations for columns added after initial release."""
        cur = self.conn.execute("PRAGMA table_info(tracks)")
        columns = {row["name"] for row in cur.fetchall()}
        if "mtime" not in columns:
            self.conn.execute("ALTER TABLE tracks ADD COLUMN mtime REAL")
        if "missing_since" not in columns:
            self.conn.execute("ALTER TABLE tracks ADD COLUMN missing_since TIMESTAMP")

        pl_columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(playlists)").fetchall()
        }
        if "description" not in pl_columns:
            self.conn.execute("ALTER TABLE playlists ADD COLUMN description TEXT")

    def upsert_track(self, track: dict) -> None:
        """Insert or update a track record."""
        columns = list(track.keys())
        placeholders = ", ".join(f":{c}" for c in columns)
        updates = ", ".join(f"{c} = :{c}" for c in columns if c != "path")
        sql = f"""
            INSERT INTO tracks ({", ".join(columns)})
            VALUES ({placeholders})
            ON CONFLICT(path) DO UPDATE SET {updates}, scanned_at = CURRENT_TIMESTAMP
        """
        self.conn.execute(sql, track)

    def commit(self) -> None:
        self.conn.commit()

    def clear_tracks(self) -> None:
        """Remove all tracks from the index."""
        self.conn.execute("DELETE FROM tracks")
        self.conn.commit()

    # ---------------------------------------------------------------------
    # Library queries
    #
    # Contract: queries that build NEW state (artist/album/track listings,
    # stats, "what's available to add to a playlist") filter
    # `missing_since IS NULL` — they reflect playable music. Queries that
    # report EXISTING playlist state (`get_playlist`, `list_playlists`,
    # `get_playlist_artists`, `get_playlist_size`) preserve dead refs so
    # users can see them and run `heal_playlist`.
    # ---------------------------------------------------------------------

    def get_stats(self) -> dict:
        """Return summary statistics about the playable library.

        Excludes tracks flagged missing on disk (set by the last scan).
        For total-with-missing counts and missing-track stats, see
        `actions.library_health`.
        """
        row = self.conn.execute("""
            SELECT
                COUNT(*) as total_tracks,
                COUNT(DISTINCT artist) as artists,
                COUNT(DISTINCT album) as albums,
                SUM(file_size) as total_bytes,
                SUM(duration_seconds) as total_seconds,
                SUM(CASE WHEN has_art = 1 THEN 1 ELSE 0 END) as with_art,
                SUM(CASE WHEN has_art = 0 THEN 1 ELSE 0 END) as without_art,
                SUM(CASE WHEN genre IS NULL OR genre = ''
                    THEN 1 ELSE 0 END) as missing_genre,
                SUM(CASE WHEN title IS NULL OR title = ''
                    THEN 1 ELSE 0 END) as missing_title,
                SUM(CASE WHEN artist IS NULL OR artist = ''
                    THEN 1 ELSE 0 END) as missing_artist
            FROM tracks
            WHERE missing_since IS NULL
        """).fetchone()
        return dict(row)

    def get_format_breakdown(self) -> list[dict]:
        """Return track counts grouped by format. Playable tracks only."""
        rows = self.conn.execute("""
            SELECT format, COUNT(*) as count, SUM(file_size) as total_bytes
            FROM tracks
            WHERE missing_since IS NULL
            GROUP BY format
            ORDER BY count DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def get_artists(self) -> list[dict]:
        """Return all artists with track/album counts and total size.
        Playable tracks only — artists with all-missing tracks disappear.

        When `album_artist == album`, the file is treated as having a
        corrupt albumartist tag (a legacy Zune/WMP pattern where the
        album title got written into the albumartist slot) and the
        per-track `artist` is used for the display name instead.
        """
        rows = self.conn.execute("""
            SELECT
                CASE WHEN album_artist = album THEN artist
                     ELSE COALESCE(album_artist, artist) END AS name,
                COUNT(*) as tracks,
                COUNT(DISTINCT album) as albums,
                SUM(file_size) as total_bytes
            FROM tracks
            WHERE format != 'flac' AND missing_since IS NULL
            GROUP BY name
            ORDER BY name COLLATE NOCASE
        """).fetchall()
        return [dict(r) for r in rows]

    def find_corrupt_albumartists(self, path_prefix: str) -> list[dict]:
        """Return tracks whose `album_artist` wrongly equals the album title.

        The legacy Zune/WMP corruption pattern: `album_artist == album` with
        a distinct per-track `artist`. Scoped by `path_prefix` so a
        `clickwheel fix <subdir>` invocation can target one folder.

        Used by `actions.repair_albumartist` to skip a full filesystem
        walk — only the known-broken files get opened over SMB.
        """
        # `_` and `%` are LIKE wildcards. Music paths legitimately contain
        # underscores (`Foo_Bar`), so we escape them — otherwise the
        # prefix match would silently include unrelated trees.
        escaped = (
            path_prefix.rstrip("/")
            .replace("\\", "\\\\")
            .replace("_", "\\_")
            .replace("%", "\\%")
        )
        pattern = escaped + "/%"
        rows = self.conn.execute(
            """
            SELECT path, artist, album_artist, album
            FROM tracks
            WHERE album_artist IS NOT NULL
              AND album IS NOT NULL
              AND artist IS NOT NULL
              AND album_artist = album
              AND album_artist != artist
              AND missing_since IS NULL
              AND path LIKE ? ESCAPE '\\'
            ORDER BY path
            """,
            (pattern,),
        ).fetchall()
        return [dict(r) for r in rows]

    def album_metadata_complete(self, paths: list[str]) -> bool:
        """True if every indexed track in `paths` already has art AND a
        year set. Used by the artwork pass to skip MB lookups for
        albums that are already fully populated.

        Returns False if any path is missing from the index — that
        means the album hasn't been scanned yet, so we can't claim
        completeness.
        """
        if not paths:
            return True
        placeholders = ",".join("?" * len(paths))
        row = self.conn.execute(
            f"""
            SELECT
                COUNT(*) AS indexed,
                SUM(CASE WHEN has_art = 1 AND year IS NOT NULL AND year != 0
                         THEN 1 ELSE 0 END) AS complete
            FROM tracks
            WHERE path IN ({placeholders})
              AND missing_since IS NULL
            """,
            paths,
        ).fetchone()
        if row is None or row["indexed"] != len(paths):
            return False
        return row["complete"] == len(paths)

    def get_mb_match(self, artist: str, album: str) -> dict | None:
        """Return the cached MusicBrainz match for (artist, album), or
        None if nothing's cached. A cached row with status='unmatched'
        is returned too — callers should treat that as a definitive
        no-match (don't re-query MB) until the cache is refreshed.
        """
        row = self.conn.execute(
            """
            SELECT status, mbid, year, fetched_at
            FROM mb_matches
            WHERE artist = ? AND album = ?
            """,
            (artist, album),
        ).fetchone()
        return dict(row) if row else None

    def save_mb_match(
        self,
        artist: str,
        album: str,
        *,
        mbid: str | None,
        year: int | None,
    ) -> None:
        """Cache a MusicBrainz lookup result. Pass `mbid=None` to
        record a definitive no-match (status='unmatched')."""
        status = "matched" if mbid else "unmatched"
        self.conn.execute(
            """
            INSERT INTO mb_matches (artist, album, status, mbid, year)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(artist, album) DO UPDATE SET
                status = excluded.status,
                mbid = excluded.mbid,
                year = excluded.year,
                fetched_at = CURRENT_TIMESTAMP
            """,
            (artist, album, status, mbid, year),
        )
        self.conn.commit()

    def clear_mb_cache(self) -> int:
        """Drop every cached MB match. Returns the number of rows
        removed. Called by `clickwheel fix --refresh-mb`."""
        cur = self.conn.execute("DELETE FROM mb_matches")
        self.conn.commit()
        return cur.rowcount

    def album_genres_complete(self, paths: list[str]) -> bool:
        """True if every indexed track in `paths` already has a non-empty
        `genre`. Used by the genre pass to skip albums that need no
        Last.fm call.
        """
        if not paths:
            return True
        placeholders = ",".join("?" * len(paths))
        row = self.conn.execute(
            f"""
            SELECT
                COUNT(*) AS indexed,
                SUM(CASE WHEN genre IS NOT NULL AND TRIM(genre) != ''
                         THEN 1 ELSE 0 END) AS with_genre
            FROM tracks
            WHERE path IN ({placeholders})
              AND missing_since IS NULL
            """,
            paths,
        ).fetchone()
        if row is None or row["indexed"] != len(paths):
            return False
        return row["with_genre"] == len(paths)

    def get_genre_match(self, artist: str, album: str) -> dict | None:
        """Cached Last.fm genre for (artist, album), or None. Mirrors
        get_mb_match: status='matched' rows carry a genre string;
        status='unmatched' rows record Last.fm misses."""
        row = self.conn.execute(
            """
            SELECT status, genre, fetched_at
            FROM genre_matches
            WHERE artist = ? AND album = ?
            """,
            (artist, album),
        ).fetchone()
        return dict(row) if row else None

    def save_genre_match(self, artist: str, album: str, *, genre: str | None) -> None:
        """Cache a Last.fm genre lookup. `genre=None` records a
        definitive no-match."""
        status = "matched" if genre else "unmatched"
        self.conn.execute(
            """
            INSERT INTO genre_matches (artist, album, status, genre)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(artist, album) DO UPDATE SET
                status = excluded.status,
                genre = excluded.genre,
                fetched_at = CURRENT_TIMESTAMP
            """,
            (artist, album, status, genre),
        )
        self.conn.commit()

    def clear_genre_cache(self) -> int:
        """Drop every cached genre match. Called by
        `clickwheel fix --refresh-genres`."""
        cur = self.conn.execute("DELETE FROM genre_matches")
        self.conn.commit()
        return cur.rowcount

    def get_albums_by_artist(self, artist: str) -> list[dict]:
        """Return albums for a given artist with track counts and size.
        Playable tracks only — albums with all-missing tracks disappear."""
        rows = self.conn.execute(
            """
            SELECT
                album,
                COUNT(*) as tracks,
                SUM(file_size) as total_bytes,
                MIN(year) as year
            FROM tracks
            WHERE (album_artist = ? OR artist = ?)
              AND format != 'flac'
              AND missing_since IS NULL
            GROUP BY album
            ORDER BY year, album COLLATE NOCASE
        """,
            (artist, artist),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_tracks_by_album(self, artist: str, album: str) -> list[dict]:
        """Return all tracks for a given artist/album. Playable tracks only.
        Used by `select` and `add_artist_to_playlist` flows; filtering here
        prevents dead refs from being added to new playlists."""
        rows = self.conn.execute(
            """
            SELECT * FROM tracks
            WHERE (album_artist = ? OR artist = ?)
              AND album = ?
              AND missing_since IS NULL
            ORDER BY disc_number, track_number
        """,
            (artist, artist, album),
        ).fetchall()
        return [dict(r) for r in rows]

    def save_playlist(
        self, name: str, track_paths: list[str], description: str | None = None
    ) -> None:
        """Create or replace a playlist with the given tracks.

        `description=None` leaves any existing description untouched (a
        fresh playlist gets a NULL description); pass a string to set it.
        """
        if description is None:
            self.conn.execute(
                """
                INSERT INTO playlists (name) VALUES (?)
                ON CONFLICT(name) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            """,
                (name,),
            )
        else:
            self.conn.execute(
                """
                INSERT INTO playlists (name, description) VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    updated_at = CURRENT_TIMESTAMP,
                    description = excluded.description
            """,
                (name, description),
            )
        playlist_id = self.conn.execute(
            "SELECT id FROM playlists WHERE name = ?", (name,)
        ).fetchone()["id"]

        self.conn.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,)
        )

        for i, path in enumerate(track_paths):
            track = self.conn.execute(
                "SELECT id FROM tracks WHERE path = ?", (path,)
            ).fetchone()
            if track:
                self.conn.execute(
                    "INSERT INTO playlist_tracks "
                    "(playlist_id, track_id, position) "
                    "VALUES (?, ?, ?)",
                    (playlist_id, track["id"], i),
                )
        self.conn.commit()

    def get_playlist(self, name: str) -> list[dict]:
        """Return tracks in a playlist, ordered by position."""
        rows = self.conn.execute(
            """
            SELECT t.* FROM tracks t
            JOIN playlist_tracks pt ON t.id = pt.track_id
            JOIN playlists p ON pt.playlist_id = p.id
            WHERE p.name = ?
            ORDER BY pt.position
        """,
            (name,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_missing_tracks_in_playlist(self, name: str) -> list[dict]:
        """Tracks referenced by a playlist whose underlying file is flagged
        missing (file no longer on disk per the last scan)."""
        rows = self.conn.execute(
            """
            SELECT t.* FROM tracks t
            JOIN playlist_tracks pt ON t.id = pt.track_id
            JOIN playlists p ON pt.playlist_id = p.id
            WHERE p.name = ? AND t.missing_since IS NOT NULL
            ORDER BY pt.position
            """,
            (name,),
        ).fetchall()
        return [dict(r) for r in rows]

    def remove_missing_tracks_from_playlist(self, name: str) -> int:
        """Drop playlist references to tracks flagged missing on disk.
        Returns the number of references removed."""
        row = self.conn.execute(
            "SELECT id FROM playlists WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            return 0
        pid = row["id"]
        before = self.conn.total_changes
        self.conn.execute(
            """
            DELETE FROM playlist_tracks WHERE playlist_id = ?
            AND track_id IN (
                SELECT id FROM tracks WHERE missing_since IS NOT NULL
            )
            """,
            (pid,),
        )
        removed = self.conn.total_changes - before
        if removed:
            self.conn.execute(
                "UPDATE playlists SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (pid,),
            )
        self.conn.commit()
        return removed

    def list_playlists(self) -> list[dict]:
        """Return all playlists with track counts and total size."""
        rows = self.conn.execute("""
            SELECT
                p.name,
                p.description,
                p.created_at,
                p.updated_at,
                COUNT(pt.track_id) as tracks,
                COALESCE(SUM(t.file_size), 0) as total_bytes
            FROM playlists p
            LEFT JOIN playlist_tracks pt ON p.id = pt.playlist_id
            LEFT JOIN tracks t ON pt.track_id = t.id
            GROUP BY p.id
            ORDER BY p.name
        """).fetchall()
        return [dict(r) for r in rows]

    def get_playlist_description(self, name: str) -> str | None:
        """Return a playlist's description, or None if unset / no such playlist."""
        row = self.conn.execute(
            "SELECT description FROM playlists WHERE name = ?", (name,)
        ).fetchone()
        return row["description"] if row else None

    def set_playlist_description(self, name: str, description: str) -> bool:
        """Set a playlist's description. Returns False if no such playlist."""
        cur = self.conn.execute(
            "UPDATE playlists SET description = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE name = ?",
            (description, name),
        )
        self.conn.commit()
        return cur.rowcount > 0

    def delete_playlist(self, name: str) -> bool:
        """Delete a playlist by name. Returns True if it existed."""
        row = self.conn.execute(
            "SELECT id FROM playlists WHERE name = ?", (name,)
        ).fetchone()
        if not row:
            return False
        self.conn.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id = ?",
            (row["id"],),
        )
        self.conn.execute("DELETE FROM playlists WHERE id = ?", (row["id"],))
        self.conn.commit()
        return True

    def add_artist_to_playlist(self, playlist_name: str, artist: str) -> int:
        """Add all tracks by an artist to a playlist. Returns count added."""
        playlist = self.conn.execute(
            "SELECT id FROM playlists WHERE name = ?",
            (playlist_name,),
        ).fetchone()
        if not playlist:
            self.conn.execute(
                "INSERT INTO playlists (name) VALUES (?)",
                (playlist_name,),
            )
            self.conn.commit()
            playlist = self.conn.execute(
                "SELECT id FROM playlists WHERE name = ?",
                (playlist_name,),
            ).fetchone()

        pid = playlist["id"]
        max_pos = self.conn.execute(
            "SELECT COALESCE(MAX(position), -1) FROM playlist_tracks "
            "WHERE playlist_id = ?",
            (pid,),
        ).fetchone()[0]

        tracks = self.conn.execute(
            """
            SELECT id FROM tracks
            WHERE (album_artist = ? OR artist = ?)
              AND format != 'flac'
              AND missing_since IS NULL
              AND id NOT IN (
                SELECT track_id FROM playlist_tracks
                WHERE playlist_id = ?
              )
            """,
            (artist, artist, pid),
        ).fetchall()

        for i, t in enumerate(tracks):
            self.conn.execute(
                "INSERT INTO playlist_tracks "
                "(playlist_id, track_id, position) "
                "VALUES (?, ?, ?)",
                (pid, t["id"], max_pos + 1 + i),
            )

        self.conn.commit()
        return len(tracks)

    def remove_artist_from_playlist(self, playlist_name: str, artist: str) -> int:
        """Remove all tracks by an artist from a playlist. Returns count."""
        row = self.conn.execute(
            "SELECT id FROM playlists WHERE name = ?",
            (playlist_name,),
        ).fetchone()
        if not row:
            return 0
        pid = row["id"]

        count = self.conn.execute(
            """
            SELECT COUNT(*) FROM playlist_tracks pt
            JOIN tracks t ON pt.track_id = t.id
            WHERE pt.playlist_id = ?
            AND (t.album_artist = ? OR t.artist = ?)
            """,
            (pid, artist, artist),
        ).fetchone()[0]

        self.conn.execute(
            """
            DELETE FROM playlist_tracks WHERE playlist_id = ?
            AND track_id IN (
                SELECT id FROM tracks
                WHERE album_artist = ? OR artist = ?
            )
            """,
            (pid, artist, artist),
        )
        self.conn.commit()
        return count

    def get_playlist_size(self, name: str) -> int:
        """Return total size in bytes of a playlist."""
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(t.file_size), 0) as total
            FROM tracks t
            JOIN playlist_tracks pt ON t.id = pt.track_id
            JOIN playlists p ON pt.playlist_id = p.id
            WHERE p.name = ?
            """,
            (name,),
        ).fetchone()
        return row["total"] if row else 0

    def get_playlist_artists(self, name: str) -> list[dict]:
        """Return artists in a playlist with track counts and size.

        Same display-name fallback as `get_artists`: a corrupt
        `album_artist == album` tag is ignored in favor of `artist`.

        The GROUP BY repeats the CASE expression rather than referring
        to the `name` alias because the joined `playlists` table also
        has a `name` column — SQLite resolves a bare `name` to the
        real column, collapsing every row into one group.
        """
        rows = self.conn.execute(
            """
            SELECT
                CASE WHEN t.album_artist = t.album THEN t.artist
                     ELSE COALESCE(t.album_artist, t.artist) END AS artist_name,
                COUNT(*) as tracks,
                SUM(t.file_size) as total_bytes
            FROM tracks t
            JOIN playlist_tracks pt ON t.id = pt.track_id
            JOIN playlists p ON pt.playlist_id = p.id
            WHERE p.name = ?
            GROUP BY
                CASE WHEN t.album_artist = t.album THEN t.artist
                     ELSE COALESCE(t.album_artist, t.artist) END
            ORDER BY artist_name COLLATE NOCASE
            """,
            (name,),
        ).fetchall()
        return [
            {
                "name": r["artist_name"],
                "tracks": r["tracks"],
                "total_bytes": r["total_bytes"],
            }
            for r in rows
        ]

    def get_scan_meta(self, key: str) -> str | None:
        """Get a scan metadata value."""
        row = self.conn.execute(
            "SELECT value FROM scan_meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_scan_meta(self, key: str, value: str) -> None:
        """Set a scan metadata value."""
        self.conn.execute(
            "INSERT INTO scan_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = ?",
            (key, value, value),
        )
        self.conn.commit()

    def get_track_mtime(self, path: str) -> tuple[float | None, int | None]:
        """Return (mtime, file_size) for a track, or (None, None) if not found."""
        row = self.conn.execute(
            "SELECT mtime, file_size FROM tracks WHERE path = ?", (path,)
        ).fetchone()
        if row:
            return row["mtime"], row["file_size"]
        return None, None

    def get_all_tracked_paths(self) -> set[str]:
        """Return all track paths currently in the database."""
        rows = self.conn.execute(
            "SELECT path FROM tracks WHERE missing_since IS NULL"
        ).fetchall()
        return {row["path"] for row in rows}

    def mark_missing(self, paths: set[str]) -> int:
        """Mark tracks as missing. Returns count marked."""
        if not paths:
            return 0
        count = 0
        for path in paths:
            self.conn.execute(
                "UPDATE tracks SET missing_since = CURRENT_TIMESTAMP "
                "WHERE path = ? AND missing_since IS NULL",
                (path,),
            )
            count += 1
        self.conn.commit()
        return count

    def clear_missing(self, path: str) -> None:
        """Clear the missing flag for a track that reappeared."""
        self.conn.execute(
            "UPDATE tracks SET missing_since = NULL WHERE path = ?",
            (path,),
        )

    # ------------------------------------------------------------------
    # Apple Music song-id cache (path → catalog/library song ID)
    # ------------------------------------------------------------------

    def get_apple_music_song(self, track_path: str) -> dict | None:
        """Return the cached Apple Music song mapping for a track path,
        or None if not yet matched. Result has keys: song_id, kind,
        confidence, storefront, matched_at."""
        row = self.conn.execute(
            "SELECT song_id, kind, confidence, storefront, matched_at "
            "FROM apple_music_song_map WHERE track_path = ?",
            (track_path,),
        ).fetchone()
        return dict(row) if row else None

    def upsert_apple_music_song(
        self,
        track_path: str,
        song_id: str,
        kind: str,
        confidence: float,
        storefront: str,
    ) -> None:
        """Insert or replace the song mapping for a track. Updates
        matched_at to CURRENT_TIMESTAMP on every call so the cache age
        is meaningful."""
        self.conn.execute(
            """
            INSERT INTO apple_music_song_map
                (track_path, song_id, kind, confidence, storefront, matched_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(track_path) DO UPDATE SET
                song_id = excluded.song_id,
                kind = excluded.kind,
                confidence = excluded.confidence,
                storefront = excluded.storefront,
                matched_at = CURRENT_TIMESTAMP
            """,
            (track_path, song_id, kind, confidence, storefront),
        )
        self.conn.commit()

    def clear_apple_music_song(self, track_path: str) -> None:
        """Drop the cached mapping for a track (e.g. user wants to
        force a re-match because tags changed)."""
        self.conn.execute(
            "DELETE FROM apple_music_song_map WHERE track_path = ?", (track_path,)
        )
        self.conn.commit()

    def get_track_path_by_apple_song_id(
        self, song_id: str, storefront: str | None = None
    ) -> str | None:
        """Reverse the song_map: given an Apple Music song id, find the
        local track path that previously matched to it. Pass
        `storefront` to scope to a single region; omit to accept any.

        When multiple paths map to the same song_id (rare but possible
        — duplicates across albums, re-tagged files), the highest-
        confidence row wins, breaking ties by most-recent match.
        """
        if storefront:
            row = self.conn.execute(
                "SELECT track_path FROM apple_music_song_map "
                "WHERE song_id = ? AND storefront = ? "
                "ORDER BY confidence DESC, matched_at DESC LIMIT 1",
                (song_id, storefront),
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT track_path FROM apple_music_song_map WHERE song_id = ? "
                "ORDER BY confidence DESC, matched_at DESC LIMIT 1",
                (song_id,),
            ).fetchone()
        return row["track_path"] if row else None

    def find_track_by_artist_title(
        self, artist: str, title: str, album: str = ""
    ) -> str | None:
        """Look up a local track path by metadata, case-insensitive.

        Exact-match-first: artist + title match (and album if given).
        Returns the first hit; callers wanting fuzzy fallback should
        check None and fall through to their own scorer. Used by the
        Apple Music pull to resolve catalog hits to local files when
        the song_map cache doesn't have the mapping yet.
        """
        norm_artist = (artist or "").strip().lower()
        norm_title = (title or "").strip().lower()
        if not norm_artist or not norm_title:
            return None
        if album:
            norm_album = album.strip().lower()
            row = self.conn.execute(
                "SELECT path FROM tracks "
                "WHERE lower(artist) = ? AND lower(title) = ? "
                "AND lower(album) = ? LIMIT 1",
                (norm_artist, norm_title, norm_album),
            ).fetchone()
            if row:
                return row["path"]
        row = self.conn.execute(
            "SELECT path FROM tracks WHERE lower(artist) = ? AND lower(title) = ? "
            "LIMIT 1",
            (norm_artist, norm_title),
        ).fetchone()
        return row["path"] if row else None

    def fuzzy_find_track(
        self,
        artist: str,
        title: str,
        album: str = "",
        min_confidence: float = 0.85,
    ) -> tuple[str | None, float]:
        """Fuzzy-match an Apple Music track against the local index.

        Filters candidates by lowercase artist substring overlap, then
        scores each by the same composite-confidence formula used in
        the catalog push (title 55%, artist 35%, album 10%). Returns
        (path, confidence) for the best candidate above the threshold,
        or (None, 0.0).
        """
        from difflib import SequenceMatcher

        if not title:
            return (None, 0.0)
        norm_artist = (artist or "").strip().lower()
        norm_title = (title or "").strip().lower()
        norm_album = (album or "").strip().lower()
        # Restrict candidate pool to rows whose lowercase artist contains
        # any 4+ char run from the target artist (or title if no artist).
        # This keeps the in-memory candidate set small for big libraries.
        key = norm_artist or norm_title
        if len(key) < 3:
            return (None, 0.0)
        like = f"%{key[:6]}%"
        rows = self.conn.execute(
            "SELECT path, artist, title, album FROM tracks "
            "WHERE lower(artist) LIKE ? OR lower(title) LIKE ?",
            (like, like),
        ).fetchall()
        best_path: str | None = None
        best_score = 0.0

        def _r(a: str, b: str) -> float:
            if not a or not b:
                return 0.0
            return SequenceMatcher(None, a, b).ratio()

        for r in rows:
            t_score = _r(norm_title, (r["title"] or "").strip().lower())
            a_score = _r(norm_artist, (r["artist"] or "").strip().lower())
            al_score = _r(norm_album, (r["album"] or "").strip().lower())
            score = 0.55 * t_score + 0.35 * a_score + 0.10 * al_score
            if score > best_score:
                best_score = score
                best_path = r["path"]
        if best_score < min_confidence:
            return (None, 0.0)
        return (best_path, best_score)

    def close(self) -> None:
        self.conn.close()
