"""Tests for non-interactive edit command (--add / --remove flags)."""

from __future__ import annotations

from unittest.mock import patch

from typer.testing import CliRunner

from clickwheel.cli import app
from clickwheel.db import Database

runner = CliRunner()


def _make_config(db: Database):
    """Return a mock Config pointing at the db."""
    from clickwheel.config import Config

    return Config(
        music_dir=db.db_path.parent / "music",
        project_dir=db.db_path.parent,
        ipod_mount=db.db_path.parent / "ipod",
        ipod_capacity_gb=64,
    )


def _run_edit(populated_db: Database, args: list[str]):
    """Invoke the edit command and return (result, fresh_db)."""
    cfg = _make_config(populated_db)
    with patch("clickwheel.cli.load_config", return_value=cfg):
        with patch("clickwheel.cli.Database", return_value=populated_db):
            result = runner.invoke(app, ["edit", *args])
    # Reopen DB since edit command closes it
    fresh_db = Database(populated_db.db_path)
    return result, fresh_db


def test_edit_add_artist(populated_db: Database):
    result, db = _run_edit(populated_db, ["mylist", "--add", "ArtistA"])
    assert result.exit_code == 0
    assert "ArtistA" in result.output
    assert "3 tracks added" in result.output
    assert len(db.get_playlist("mylist")) == 3


def test_edit_add_multiple_artists(populated_db: Database):
    result, db = _run_edit(
        populated_db, ["mylist", "--add", "ArtistA", "--add", "ArtistB"]
    )
    assert result.exit_code == 0
    assert len(db.get_playlist("mylist")) == 5  # 3 + 2


def test_edit_remove_artist(populated_db: Database):
    populated_db.save_playlist(
        "mylist",
        [
            "/music/A/Album1/01 T1.mp3",
            "/music/A/Album1/02 T2.mp3",
            "/music/B/Album2/01 S1.mp3",
        ],
    )
    result, db = _run_edit(populated_db, ["mylist", "--remove", "ArtistA"])
    assert result.exit_code == 0
    assert "2 tracks removed" in result.output
    tracks = db.get_playlist("mylist")
    assert len(tracks) == 1
    assert tracks[0]["artist"] == "ArtistB"


def test_edit_add_nonexistent_artist(populated_db: Database):
    result, _ = _run_edit(populated_db, ["mylist", "--add", "Nobody"])
    assert result.exit_code == 0
    assert "No tracks found" in result.output


def test_edit_remove_nonexistent_artist(populated_db: Database):
    populated_db.save_playlist("mylist", ["/music/A/Album1/01 T1.mp3"])
    result, _ = _run_edit(populated_db, ["mylist", "--remove", "Nobody"])
    assert result.exit_code == 0
    assert "not in playlist" in result.output


def test_edit_add_and_remove(populated_db: Database):
    populated_db.save_playlist(
        "mylist",
        ["/music/A/Album1/01 T1.mp3", "/music/A/Album1/02 T2.mp3"],
    )
    result, db = _run_edit(
        populated_db, ["mylist", "--add", "ArtistB", "--remove", "ArtistA"]
    )
    assert result.exit_code == 0
    tracks = db.get_playlist("mylist")
    artists = {t["artist"] for t in tracks}
    assert "ArtistB" in artists
    assert "ArtistA" not in artists
