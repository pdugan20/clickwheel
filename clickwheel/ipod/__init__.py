"""iPod interface — vendored from iOpenPodv2 (MIT license).

Provides read/write access to iPod iTunesDB and Play Counts files.
See LICENSE-iOpenPodv2 for the original license.
"""

from __future__ import annotations

import logging
from pathlib import Path

from clickwheel.ipod.itunesdb_parser import parse_itunesdb
from clickwheel.ipod.itunesdb_parser.playcounts import (
    PlayCountEntry,
    merge_playcounts,
    parse_playcounts,
)

logger = logging.getLogger(__name__)

# Standard iPod control paths
ITUNES_DIR = "iPod_Control/iTunes"
ITUNESDB_FILE = "iTunesDB"
ITUNESCDB_FILE = "iTunesCDB"
PLAYCOUNTS_FILE = "Play Counts"


def find_ipod(mount_path: str | Path) -> Path | None:
    """Check if an iPod is mounted at the given path.

    Returns the mount path if valid, None otherwise.
    """
    mount = Path(mount_path)
    itunes_dir = mount / ITUNES_DIR
    if itunes_dir.is_dir():
        return mount
    return None


def read_ipod(mount_path: str | Path) -> dict:
    """Read and parse the iTunesDB from a mounted iPod.

    Returns the parsed database as a nested dict/list structure.
    """
    mount = Path(mount_path)
    itunes_dir = mount / ITUNES_DIR

    # Try iTunesCDB first (compressed, newer devices), then iTunesDB
    cdb_path = itunes_dir / ITUNESCDB_FILE
    db_path = itunes_dir / ITUNESDB_FILE

    if cdb_path.exists():
        logger.info("Reading iTunesCDB from %s", cdb_path)
        return parse_itunesdb(str(cdb_path))
    elif db_path.exists():
        logger.info("Reading iTunesDB from %s", db_path)
        return parse_itunesdb(str(db_path))
    else:
        raise FileNotFoundError(f"No iTunesDB or iTunesCDB found at {itunes_dir}")


def read_play_counts(
    mount_path: str | Path,
) -> list[PlayCountEntry] | None:
    """Read play count deltas from the iPod.

    Returns list of PlayCountEntry (one per track), or None if no
    Play Counts file exists (iPod hasn't been played since last sync).
    """
    mount = Path(mount_path)
    pc_path = mount / ITUNES_DIR / PLAYCOUNTS_FILE
    return parse_playcounts(pc_path)


def get_ipod_tracks(db: dict) -> list[dict]:
    """Extract the flat track list from a parsed iTunesDB.

    Handles both the nested chunk format (mhsd > mhlt > children)
    and the flat format where mhlt is a top-level list.
    """
    # Flat format: mhlt is a top-level list of track dicts
    # Normalize capitalized keys (Title, Artist, Album) to lowercase
    mhlt = db.get("mhlt")
    if isinstance(mhlt, list):
        key_map = {
            "Title": "title",
            "Artist": "artist",
            "Album": "album",
            "Album Artist": "album_artist",
            "Genre": "genre",
            "Location": "location",
        }
        normalized = []
        for t in mhlt:
            norm = dict(t)
            for old_key, new_key in key_map.items():
                if old_key in norm:
                    norm[new_key] = norm.pop(old_key)
            normalized.append(norm)
        return normalized

    # Nested chunk format: walk children to find mhsd > mhlt
    tracks = []
    for child in db.get("children", []):
        if child.get("type") == "mhsd":
            for sub in child.get("children", []):
                if sub.get("type") == "mhlt":
                    tracks = sub.get("children", [])
                    break
            if tracks:
                break
    return tracks


__all__ = [
    "PlayCountEntry",
    "find_ipod",
    "get_ipod_tracks",
    "merge_playcounts",
    "read_ipod",
    "read_play_counts",
]
