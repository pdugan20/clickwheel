"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from clickwheel.config import Config
from clickwheel.db import Database


@pytest.fixture
def tmp_db(tmp_path: Path) -> Database:
    """Create a fresh database in a temp directory."""
    return Database(tmp_path / "test.db")


@pytest.fixture
def sample_track() -> dict:
    """A minimal valid track dict for testing."""
    return {
        "path": "/music/Artist/Album/01 Track.mp3",
        "title": "Track",
        "artist": "Artist",
        "album": "Album",
        "album_artist": "Artist",
        "genre": "Rock",
        "track_number": 1,
        "disc_number": 1,
        "year": 2020,
        "duration_seconds": 180.0,
        "bitrate": 320000,
        "sample_rate": 44100,
        "format": "mp3",
        "file_size": 5_000_000,
        "has_art": 1,
        "art_width": 500,
        "art_height": 500,
    }


@pytest.fixture
def populated_db(tmp_db: Database, sample_track: dict) -> Database:
    """Database pre-loaded with a few tracks across two artists."""
    tracks = [
        {
            **sample_track,
            "path": f"/music/A/Album1/0{i} T{i}.mp3",
            "title": f"T{i}",
            "artist": "ArtistA",
            "album_artist": "ArtistA",
            "album": "Album1",
            "track_number": i,
            "file_size": 5_000_000,
        }
        for i in range(1, 4)
    ] + [
        {
            **sample_track,
            "path": f"/music/B/Album2/0{i} S{i}.mp3",
            "title": f"S{i}",
            "artist": "ArtistB",
            "album_artist": "ArtistB",
            "album": "Album2",
            "track_number": i,
            "file_size": 3_000_000,
        }
        for i in range(1, 3)
    ]
    for t in tracks:
        tmp_db.upsert_track(t)
    tmp_db.commit()
    return tmp_db


@pytest.fixture
def mock_config(tmp_path: Path) -> Config:
    """A Config pointing at temp directories."""
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    return Config(
        music_dir=music_dir,
        project_dir=tmp_path,
        ipod_mount=tmp_path / "ipod",
        ipod_capacity_gb=64,
    )


@pytest.fixture
def music_dir_with_mp3(tmp_path: Path) -> Path:
    """Create a temp dir with a minimal valid MP3 file using mutagen."""
    from mutagen.id3 import TALB, TIT2, TPE1
    from mutagen.mp3 import MP3

    music_dir = tmp_path / "music" / "TestArtist" / "TestAlbum"
    music_dir.mkdir(parents=True)
    mp3_path = music_dir / "01 TestTrack.mp3"

    # Create minimal valid MP3: MPEG frame header + silence
    # Minimal MPEG1 Layer 3 frame: sync=0xFFE0, bitrate=128k, 44100Hz
    frame = (
        b"\xff\xfb\x90\x00"  # MPEG1, Layer 3, 128kbps, 44100Hz, stereo
        + b"\x00" * 413  # pad to frame size (417 bytes for 128k/44100)
    )
    mp3_path.write_bytes(frame * 10)  # ~10 frames of silence

    # Add ID3 tags
    audio = MP3(str(mp3_path))
    audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text=["TestTrack"]))
    audio.tags.add(TPE1(encoding=3, text=["TestArtist"]))
    audio.tags.add(TALB(encoding=3, text=["TestAlbum"]))
    audio.save()

    return tmp_path / "music"
