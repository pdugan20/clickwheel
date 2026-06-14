"""Tests for FLAC→MP3 conversion: transcode module + actions.convert_tracks."""

from __future__ import annotations

from pathlib import Path

import pytest

# A minimal valid MP3 frame (matches tests/conftest.py music_dir_with_mp3).
MP3_BYTES = (b"\xff\xfb\x90\x00" + b"\x00" * 413) * 10


def test_transcode_to_mp3_invokes_ffmpeg_and_moves(tmp_path, monkeypatch):
    from clickwheel import transcode

    src = tmp_path / "a.flac"
    src.write_bytes(b"fakeflac")
    dest = tmp_path / "out" / "a.mp3"
    captured = {}

    class FakeProc:
        returncode = 0
        stderr = ""

    def fake_run(cmd, capture_output, text):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(MP3_BYTES)  # write the .part file
        return FakeProc()

    monkeypatch.setattr(transcode.subprocess, "run", fake_run)
    transcode.transcode_to_mp3(src, dest, 320, "/usr/bin/ffmpeg")

    assert dest.exists()
    assert not dest.with_name(dest.name + ".part").exists()
    assert "libmp3lame" in captured["cmd"]
    assert "320k" in captured["cmd"]


def test_transcode_to_mp3_raises_on_failure(tmp_path, monkeypatch):
    from clickwheel import transcode

    class FakeProc:
        returncode = 1
        stderr = "boom"

    monkeypatch.setattr(transcode.subprocess, "run", lambda *a, **k: FakeProc())
    src = tmp_path / "a.flac"
    src.write_bytes(b"x")
    with pytest.raises(transcode.TranscodeError):
        transcode.transcode_to_mp3(src, tmp_path / "o.mp3", 320, "/usr/bin/ffmpeg")
