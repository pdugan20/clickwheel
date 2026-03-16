"""Configuration management — reads from config file, .env, and environment."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ENV_FILE = ".env"
CONFIG_DIR = Path.home() / ".clickwheel"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
DEFAULT_IPOD_MOUNT = "/Volumes/IPOD"
DEFAULT_IPOD_CAPACITY_GB = 64
DEFAULT_AUTO_SCAN_STALENESS_MINUTES = 30

# Config file keys mapped to env var names
_YAML_TO_ENV = {
    "music_dir": "MUSIC_DIR",
    "ipod_mount": "IPOD_MOUNT",
    "ipod_capacity_gb": "IPOD_CAPACITY_GB",
    "lastfm_api_key": "LASTFM_API_KEY",
    "lastfm_api_secret": "LASTFM_API_SECRET",
    "lastfm_username": "LASTFM_USERNAME",
    "lastfm_session_key": "LASTFM_SESSION_KEY",
    "auto_scan": "AUTO_SCAN",
    "auto_scan_staleness_minutes": "AUTO_SCAN_STALENESS_MINUTES",
}


@dataclass
class Config:
    music_dir: Path
    project_dir: Path
    ipod_mount: Path = field(default_factory=lambda: Path(DEFAULT_IPOD_MOUNT))
    ipod_capacity_gb: int = DEFAULT_IPOD_CAPACITY_GB
    lastfm_api_key: str = ""
    lastfm_api_secret: str = ""
    lastfm_username: str = ""
    lastfm_session_key: str = ""
    auto_scan: bool = True
    auto_scan_staleness_minutes: int = DEFAULT_AUTO_SCAN_STALENESS_MINUTES
    db_path: Path = field(init=False)

    @property
    def ipod_capacity_bytes(self) -> int:
        return self.ipod_capacity_gb * 1024 * 1024 * 1024

    def __post_init__(self) -> None:
        self.music_dir = Path(self.music_dir)
        self.ipod_mount = Path(self.ipod_mount)
        self.db_path = self.project_dir / "clickwheel.db"
        # Ensure the data directory exists for installed (non-dev) users
        self.project_dir.mkdir(parents=True, exist_ok=True)


def load_config() -> Config:
    """Load config with priority: env vars > .env > ~/.clickwheel/config.yaml."""
    # Load config file defaults first (lowest priority)
    _load_config_file()

    # Then load .env (overrides config file, but not real env vars)
    data_dir = _find_data_dir()
    env_file = data_dir / ENV_FILE
    if env_file.exists():
        _load_dotenv(env_file)

    music_dir = os.environ.get("MUSIC_DIR", "")
    if not music_dir:
        raise SystemExit(
            "[ERROR] Music folder not configured. "
            "Set music_dir in ~/.clickwheel/config.yaml"
        )

    return Config(
        music_dir=Path(music_dir),
        project_dir=data_dir,
        ipod_mount=Path(os.environ.get("IPOD_MOUNT", DEFAULT_IPOD_MOUNT)),
        ipod_capacity_gb=int(
            os.environ.get("IPOD_CAPACITY_GB", DEFAULT_IPOD_CAPACITY_GB)
        ),
        lastfm_api_key=os.environ.get("LASTFM_API_KEY", ""),
        lastfm_api_secret=os.environ.get("LASTFM_API_SECRET", ""),
        lastfm_username=os.environ.get("LASTFM_USERNAME", ""),
        lastfm_session_key=os.environ.get("LASTFM_SESSION_KEY", ""),
        auto_scan=os.environ.get("AUTO_SCAN", "true").lower()
        not in ("false", "0", "no"),
        auto_scan_staleness_minutes=int(
            os.environ.get(
                "AUTO_SCAN_STALENESS_MINUTES",
                DEFAULT_AUTO_SCAN_STALENESS_MINUTES,
            )
        ),
    )


def _load_config_file() -> None:
    """Load ~/.clickwheel/config.yaml as environment defaults."""
    if not CONFIG_FILE.exists():
        return

    try:
        data = _parse_yaml(CONFIG_FILE)
    except Exception:
        return

    for yaml_key, env_key in _YAML_TO_ENV.items():
        if yaml_key in data and env_key not in os.environ:
            os.environ[env_key] = str(data[yaml_key])


def _parse_yaml(path: Path) -> dict:
    """Minimal YAML parser for flat key: value files. No dependency needed."""
    result = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip("'\"")
            if value:
                result[key] = value
    return result


def _find_data_dir() -> Path:
    """Return the data directory for clickwheel (~/.clickwheel/)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIG_DIR


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
