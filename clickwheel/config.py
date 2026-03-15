"""Configuration management — reads from .env and config file."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ENV_FILE = ".env"
DEFAULT_IPOD_MOUNT = "/Volumes/IPOD"


@dataclass
class Config:
    music_dir: Path
    project_dir: Path
    ipod_mount: Path = field(default_factory=lambda: Path(DEFAULT_IPOD_MOUNT))
    acoustid_api_key: str = ""
    db_path: Path = field(init=False)

    def __post_init__(self) -> None:
        self.music_dir = Path(self.music_dir)
        self.ipod_mount = Path(self.ipod_mount)
        self.db_path = self.project_dir / "clickwheel.db"


def load_config() -> Config:
    """Load config from .env file, walking up to find project root."""
    project_dir = _find_project_root()
    env_file = project_dir / ENV_FILE

    if env_file.exists():
        _load_dotenv(env_file)

    music_dir = os.environ.get("MUSIC_DIR", "")
    if not music_dir:
        raise SystemExit(
            "[ERROR] MUSIC_DIR not set. Copy .env.example to .env and configure it."
        )

    return Config(
        music_dir=Path(music_dir),
        project_dir=project_dir,
        ipod_mount=Path(os.environ.get("IPOD_MOUNT", DEFAULT_IPOD_MOUNT)),
        acoustid_api_key=os.environ.get("ACOUSTID_API_KEY", ""),
    )


def _find_project_root() -> Path:
    """Walk up from cwd to find the project root (contains pyproject.toml)."""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return current


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader — no external dependency needed."""
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key not in os.environ:
                os.environ[key] = value
