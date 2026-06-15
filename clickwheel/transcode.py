"""FLAC→MP3 transcoding via ffmpeg.

Pure logic: no Rich, typer, tqdm, or questionary. The actions layer resolves
the ffmpeg binary once and passes it in; per-track failures raise
TranscodeError, which the caller aggregates.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


class TranscodeError(Exception):
    """A single ffmpeg transcode invocation failed."""

    def __init__(self, source: str, detail: str) -> None:
        super().__init__(f"Transcode failed for {source}: {detail}")
        self.source = source
        self.detail = detail


def find_ffmpeg() -> str | None:
    """Locate the ffmpeg binary on PATH, or None if not installed."""
    return shutil.which("ffmpeg")


def transcode_to_mp3(src: Path, dest: Path, bitrate: int, ffmpeg: str) -> None:
    """Transcode one FLAC to CBR MP3, preserving tags and embedded cover art.

    Writes atomically (temp ``.part`` file then os.replace) so an interrupted
    run never leaves a half-written MP3 that a later run mistakes for complete.
    Raises TranscodeError on non-zero ffmpeg exit.
    """
    import subprocess

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-map",
        "0:a:0",  # first audio stream
        "-map",
        "0:v?",  # embedded cover art if present (optional)
        "-c:a",
        "libmp3lame",
        "-b:a",
        f"{bitrate}k",  # CBR
        "-c:v",
        "copy",  # copy art stream as-is into ID3 APIC
        "-id3v2_version",
        "3",
        "-map_metadata",
        "0",  # carry tags across
        "-f",
        "mp3",
        str(part),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        part.unlink(missing_ok=True)
        raise TranscodeError(str(src), (proc.stderr or "")[-2000:])
    os.replace(part, dest)
