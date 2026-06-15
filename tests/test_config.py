"""Tests for configuration loading."""

from __future__ import annotations

import os
from pathlib import Path

from clickwheel.config import CONFIG_DIR, _find_data_dir, _load_dotenv, _parse_yaml


def test_parse_yaml_basic(tmp_path: Path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("music_dir: /Volumes/Music\nipod_mount: /Volumes/IPOD\n")
    result = _parse_yaml(cfg)
    assert result["music_dir"] == "/Volumes/Music"
    assert result["ipod_mount"] == "/Volumes/IPOD"


def test_parse_yaml_comments_and_blanks(tmp_path: Path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("# comment\n\nmusic_dir: /music\n\n# another\n")
    result = _parse_yaml(cfg)
    assert result == {"music_dir": "/music"}


def test_parse_yaml_quoted_values(tmp_path: Path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("music_dir: '/path/with spaces'\nkey: \"double quoted\"\n")
    result = _parse_yaml(cfg)
    assert result["music_dir"] == "/path/with spaces"
    assert result["key"] == "double quoted"


def test_parse_yaml_empty_value(tmp_path: Path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("music_dir:\n")
    result = _parse_yaml(cfg)
    assert "music_dir" not in result


def test_parse_yaml_no_colon(tmp_path: Path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("not a valid line\nmusic_dir: /music\n")
    result = _parse_yaml(cfg)
    assert result == {"music_dir": "/music"}


def test_load_dotenv_basic(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_VAR=hello\n")
    monkeypatch.delenv("TEST_VAR", raising=False)
    _load_dotenv(env_file)
    assert os.environ["TEST_VAR"] == "hello"
    monkeypatch.delenv("TEST_VAR")


def test_load_dotenv_no_override(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_VAR=from_file\n")
    monkeypatch.setenv("TEST_VAR", "from_env")
    _load_dotenv(env_file)
    assert os.environ["TEST_VAR"] == "from_env"


def test_load_dotenv_comments(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\n\nTEST_VAR2=value\n")
    monkeypatch.delenv("TEST_VAR2", raising=False)
    _load_dotenv(env_file)
    assert os.environ["TEST_VAR2"] == "value"
    monkeypatch.delenv("TEST_VAR2")


def test_find_data_dir_always_config_dir():
    result = _find_data_dir()
    assert result == CONFIG_DIR


def test_transcode_config_defaults(tmp_path):
    from clickwheel.config import Config

    cfg = Config(music_dir=tmp_path, project_dir=tmp_path)
    assert cfg.transcode_bitrate == 320
    assert cfg.transcode_dir == tmp_path / "transcoded"


def test_transcode_dir_override(tmp_path):
    from clickwheel.config import Config

    custom = tmp_path / "elsewhere"
    cfg = Config(music_dir=tmp_path, project_dir=tmp_path, transcode_dir=custom)
    assert cfg.transcode_dir == custom
