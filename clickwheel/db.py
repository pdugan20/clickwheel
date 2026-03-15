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
        self.conn.commit()

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

    def close(self) -> None:
        self.conn.close()
