"""Music library scanning — reads metadata from audio files."""

from __future__ import annotations

from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".flac", ".aac", ".wav", ".aiff", ".ogg", ".wma"}


def scan_file(path: Path) -> dict | None:
    """Extract metadata from a single audio file. Returns None on failure."""
    try:
        audio = MutagenFile(str(path), easy=True)
        if audio is None:
            return None

        info = audio.info if audio.info else None
        file_size = path.stat().st_size
        fmt = path.suffix.lstrip(".").lower()

        track = {
            "path": str(path),
            "title": _first(audio.get("title")),
            "artist": _first(audio.get("artist")),
            "album": _first(audio.get("album")),
            "album_artist": _first(audio.get("albumartist")),
            "genre": _first(audio.get("genre")),
            "track_number": _parse_track_number(audio.get("tracknumber")),
            "disc_number": _parse_track_number(audio.get("discnumber")),
            "year": _parse_year(audio.get("date")),
            "duration_seconds": round(info.length, 2) if info else None,
            "bitrate": getattr(info, "bitrate", None),
            "sample_rate": getattr(info, "sample_rate", None),
            "format": fmt,
            "file_size": file_size,
            "has_art": 0,
            "art_width": None,
            "art_height": None,
        }

        art = _get_album_art(path, audio)
        if art:
            track["has_art"] = 1
            track["art_width"] = art.get("width")
            track["art_height"] = art.get("height")

        return track
    except Exception:
        return None


def find_audio_files(music_dir: Path) -> list[Path]:
    """Recursively find all audio files in the given directory."""
    files = []
    for ext in AUDIO_EXTENSIONS:
        files.extend(music_dir.rglob(f"*{ext}"))
        files.extend(music_dir.rglob(f"*{ext.upper()}"))
    # Deduplicate (case-insensitive match might overlap)
    seen = set()
    unique = []
    for f in files:
        if f not in seen:
            seen.add(f)
            unique.append(f)
    return sorted(unique)


def _first(values: list | None) -> str | None:
    """Get first value from a tag list."""
    if values and len(values) > 0:
        return str(values[0])
    return None


def _parse_track_number(values: list | None) -> int | None:
    """Parse track number from tag, handling '3/12' format."""
    raw = _first(values)
    if not raw:
        return None
    try:
        return int(raw.split("/")[0])
    except (ValueError, IndexError):
        return None


def _parse_year(values: list | None) -> int | None:
    """Parse year from date tag."""
    raw = _first(values)
    if not raw:
        return None
    try:
        return int(raw[:4])
    except (ValueError, IndexError):
        return None


def _get_album_art(path: Path, audio: MutagenFile) -> dict | None:
    """Check for embedded album art and return dimensions if found."""
    try:
        raw_audio = MutagenFile(str(path))
        if raw_audio is None:
            return None

        if isinstance(raw_audio, MP3):
            tags = raw_audio.tags
            if tags:
                for key in tags:
                    if key.startswith("APIC"):
                        apic = tags[key]
                        return _image_dimensions(apic.data)

        elif isinstance(raw_audio, MP4):
            covr = raw_audio.tags.get("covr") if raw_audio.tags else None
            if covr and len(covr) > 0:
                return _image_dimensions(bytes(covr[0]))

        elif isinstance(raw_audio, FLAC):
            if raw_audio.pictures:
                pic = raw_audio.pictures[0]
                return {"width": pic.width, "height": pic.height}

    except Exception:
        pass
    return None


def _image_dimensions(data: bytes) -> dict | None:
    """Get image dimensions from raw bytes without PIL."""
    if not data or len(data) < 24:
        return None

    # JPEG
    if data[:2] == b"\xff\xd8":
        return {"width": None, "height": None}  # JPEG needs full parse, mark as present

    # PNG
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        if width > 0 and height > 0:
            return {"width": width, "height": height}

    return {"width": None, "height": None}
