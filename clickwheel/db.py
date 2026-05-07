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

CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist);
CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album);
CREATE INDEX IF NOT EXISTS idx_tracks_album_artist ON tracks(album_artist);
CREATE INDEX IF NOT EXISTS idx_tracks_genre ON tracks(genre);
CREATE INDEX IF NOT EXISTS idx_tracks_format ON tracks(format);
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

    def get_stats(self) -> dict:
        """Return summary statistics about the indexed library."""
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
        """).fetchone()
        return dict(row)

    def get_format_breakdown(self) -> list[dict]:
        """Return track counts grouped by format."""
        rows = self.conn.execute("""
            SELECT format, COUNT(*) as count, SUM(file_size) as total_bytes
            FROM tracks
            GROUP BY format
            ORDER BY count DESC
        """).fetchall()
        return [dict(r) for r in rows]

    def get_artists(self) -> list[dict]:
        """Return all artists with track/album counts and total size."""
        rows = self.conn.execute("""
            SELECT
                COALESCE(album_artist, artist) as name,
                COUNT(*) as tracks,
                COUNT(DISTINCT album) as albums,
                SUM(file_size) as total_bytes
            FROM tracks
            WHERE format != 'flac'
            GROUP BY name
            ORDER BY name COLLATE NOCASE
        """).fetchall()
        return [dict(r) for r in rows]

    def get_albums_by_artist(self, artist: str) -> list[dict]:
        """Return albums for a given artist with track counts and size."""
        rows = self.conn.execute(
            """
            SELECT
                album,
                COUNT(*) as tracks,
                SUM(file_size) as total_bytes,
                MIN(year) as year
            FROM tracks
            WHERE (album_artist = ? OR artist = ?) AND format != 'flac'
            GROUP BY album
            ORDER BY year, album COLLATE NOCASE
        """,
            (artist, artist),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_tracks_by_album(self, artist: str, album: str) -> list[dict]:
        """Return all tracks for a given artist/album."""
        rows = self.conn.execute(
            """
            SELECT * FROM tracks
            WHERE (album_artist = ? OR artist = ?) AND album = ?
            ORDER BY disc_number, track_number
        """,
            (artist, artist, album),
        ).fetchall()
        return [dict(r) for r in rows]

    def save_playlist(self, name: str, track_paths: list[str]) -> None:
        """Create or replace a playlist with the given tracks."""
        self.conn.execute(
            """
            INSERT INTO playlists (name) VALUES (?)
            ON CONFLICT(name) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
        """,
            (name,),
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
            WHERE (album_artist = ? OR artist = ?) AND format != 'flac'
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
        """Return artists in a playlist with track counts and size."""
        rows = self.conn.execute(
            """
            SELECT
                COALESCE(t.album_artist, t.artist) as name,
                COUNT(*) as tracks,
                SUM(t.file_size) as total_bytes
            FROM tracks t
            JOIN playlist_tracks pt ON t.id = pt.track_id
            JOIN playlists p ON pt.playlist_id = p.id
            WHERE p.name = ?
            GROUP BY COALESCE(t.album_artist, t.artist)
            ORDER BY name COLLATE NOCASE
            """,
            (name,),
        ).fetchall()
        return [dict(r) for r in rows]

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

    def close(self) -> None:
        self.conn.close()
