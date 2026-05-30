"""Music library scanning — reads metadata from audio files."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen import FileType
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
        stat = path.stat()
        file_size = stat.st_size
        fmt = path.suffix.lstrip(".").lower()

        track = {
            "path": str(path),
            "mtime": stat.st_mtime,
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


def find_audio_files(
    music_dir: Path, progress_callback: Callable[[int], None] | None = None
) -> list[Path]:
    """Recursively find all audio files in the given directory."""
    seen: set[Path] = set()
    unique: list[Path] = []
    for entry in music_dir.rglob("*"):
        if entry.suffix.lower() in AUDIO_EXTENSIONS and entry not in seen:
            seen.add(entry)
            unique.append(entry)
            if progress_callback:
                progress_callback(len(unique))
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


def _get_album_art(path: Path, audio: FileType) -> dict | None:
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


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def write_album_metadata(
    path: Path, *, art: bytes | None = None, year: int | None = None
) -> tuple[bool, bool]:
    """Embed front-cover `art` (only when the file has none) and/or set the
    release `year` on a track, in place.

    Returns (art_embedded, year_set). MP3 and MP4/M4A are supported; other
    formats are skipped and return (False, False).
    """
    suffix = path.suffix.lower()
    if suffix == ".mp3":
        return _write_mp3_metadata(path, art, year)
    if suffix in (".m4a", ".aac", ".mp4"):
        return _write_mp4_metadata(path, art, year)
    return (False, False)


def _write_mp3_metadata(
    path: Path, art: bytes | None, year: int | None
) -> tuple[bool, bool]:
    from mutagen.id3 import APIC, ID3, TDRC, ID3NoHeaderError

    try:
        tags = ID3(str(path))
    except ID3NoHeaderError:
        tags = ID3()

    art_done = year_done = False
    if art and not any(k.startswith("APIC") for k in tags):
        mime = "image/png" if art[:8] == _PNG_MAGIC else "image/jpeg"
        tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=art))
        art_done = True
    if year:
        tags.setall("TDRC", [TDRC(encoding=3, text=[str(year)])])
        tags.pop("TYER", None)
        year_done = True
    if art_done or year_done:
        tags.save(str(path))
    return (art_done, year_done)


def _write_mp4_metadata(
    path: Path, art: bytes | None, year: int | None
) -> tuple[bool, bool]:
    from mutagen.mp4 import MP4Cover

    mp4 = MP4(str(path))
    if mp4.tags is None:
        mp4.add_tags()
    tags = mp4.tags
    assert tags is not None  # add_tags() above guarantees a tag block

    art_done = year_done = False
    if art and "covr" not in tags:
        fmt = MP4Cover.FORMAT_PNG if art[:8] == _PNG_MAGIC else MP4Cover.FORMAT_JPEG
        tags["covr"] = [MP4Cover(art, imageformat=fmt)]
        art_done = True
    if year:
        tags["\xa9day"] = [str(year)]
        year_done = True
    if art_done or year_done:
        mp4.save()
    return (art_done, year_done)
