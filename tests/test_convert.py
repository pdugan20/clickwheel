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

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(MP3_BYTES)  # write the .part file
        return FakeProc()

    import subprocess as _sp

    monkeypatch.setattr(_sp, "run", fake_run)
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

    import subprocess as _sp

    monkeypatch.setattr(_sp, "run", lambda *a, **k: FakeProc())
    src = tmp_path / "a.flac"
    src.write_bytes(b"x")
    with pytest.raises(transcode.TranscodeError):
        transcode.transcode_to_mp3(src, tmp_path / "o.mp3", 320, "/usr/bin/ffmpeg")


def test_transcode_to_mp3_real_ffmpeg(tmp_path):
    """Integration: run the real ffmpeg command on art + no-art FLACs."""
    import shutil
    import subprocess

    from clickwheel import transcode

    ffmpeg = transcode.find_ffmpeg()
    if ffmpeg is None:
        pytest.skip("ffmpeg not installed")

    # FLAC with no embedded cover art.
    noart = tmp_path / "noart.flac"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:a", "flac", str(noart)],
        capture_output=True, check=True,
    )
    out_noart = tmp_path / "out" / "noart.mp3"
    transcode.transcode_to_mp3(noart, out_noart, 320, ffmpeg)
    assert out_noart.exists() and out_noart.stat().st_size > 0

    # FLAC WITH embedded cover art.
    cover = tmp_path / "cover.png"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=red:s=120x120:d=1",
         "-frames:v", "1", str(cover)],
        capture_output=True, check=True,
    )
    art = tmp_path / "art.flac"
    subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-i", str(cover), "-map", "0:a", "-map", "1:v", "-c:a", "flac",
         "-c:v", "copy", "-disposition:v", "attached_pic", str(art)],
        capture_output=True, check=True,
    )
    out_art = tmp_path / "out" / "art.mp3"
    transcode.transcode_to_mp3(art, out_art, 320, ffmpeg)
    assert out_art.exists() and out_art.stat().st_size > 0

    # Cover art should be carried into the MP3 (a video/image stream present).
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        probe = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0",
             str(out_art)],
            capture_output=True, text=True,
        )
        assert probe.stdout.strip() != ""  # art stream preserved


def _make_flac_source(tmp_db, music_dir):
    flac = music_dir / "Olivia Rodrigo" / "GUTS" / "01 bad idea right.flac"
    flac.parent.mkdir(parents=True, exist_ok=True)
    flac.write_bytes(b"fakeflac")
    tmp_db.upsert_track(
        {
            "path": str(flac),
            "title": "bad idea right!",
            "artist": "Olivia Rodrigo",
            "album_artist": "Olivia Rodrigo",
            "album": "GUTS",
            "format": "flac",
            "track_number": 1,
            "disc_number": 1,
            "file_size": 8,
            "mtime": flac.stat().st_mtime,
            "duration_seconds": 180.0,
        }
    )
    tmp_db.commit()
    return flac


def _patch_transcode(monkeypatch):
    from clickwheel import transcode

    monkeypatch.setattr(transcode, "find_ffmpeg", lambda: "/usr/bin/ffmpeg")

    def fake(src, dest, bitrate, ffmpeg):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(MP3_BYTES)

    monkeypatch.setattr(transcode, "transcode_to_mp3", fake)


def test_convert_tracks_transcodes_and_indexes(tmp_db, tmp_path, monkeypatch):
    from clickwheel import actions
    from clickwheel.config import Config

    music = tmp_path / "music"
    music.mkdir()
    flac = _make_flac_source(tmp_db, music)
    _patch_transcode(monkeypatch)
    cfg = Config(music_dir=music, project_dir=tmp_path)

    result = actions.convert_tracks(
        cfg,
        tmp_db,
        scopes=[{"artist": "Olivia Rodrigo", "album": "GUTS"}],
        bitrate=320,
    )

    assert len(result.converted) == 1
    out = Path(result.converted[0])
    assert out.exists() and out.suffix == ".mp3"
    assert str(out) in tmp_db.get_all_tracked_paths()  # indexed as playable mp3
    assert tmp_db.get_transcode(str(flac)) is not None  # cached


def test_convert_tracks_is_idempotent(tmp_db, tmp_path, monkeypatch):
    from clickwheel import actions
    from clickwheel.config import Config

    music = tmp_path / "music"
    music.mkdir()
    flac = _make_flac_source(tmp_db, music)
    _patch_transcode(monkeypatch)
    cfg = Config(music_dir=music, project_dir=tmp_path)
    scopes = [{"artist": "Olivia Rodrigo", "album": "GUTS"}]

    actions.convert_tracks(cfg, tmp_db, scopes=scopes, bitrate=320)
    second = actions.convert_tracks(cfg, tmp_db, scopes=scopes, bitrate=320)

    assert second.converted == []
    assert second.skipped == [str(flac)]


def test_convert_tracks_raises_without_ffmpeg(tmp_db, tmp_path, monkeypatch):
    from clickwheel import actions, transcode
    from clickwheel.config import Config

    monkeypatch.setattr(transcode, "find_ffmpeg", lambda: None)
    cfg = Config(music_dir=tmp_path, project_dir=tmp_path)
    with pytest.raises(actions.FfmpegNotFoundError):
        actions.convert_tracks(cfg, tmp_db, all_flac=True)
