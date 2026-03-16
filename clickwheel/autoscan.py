"""Auto-scan — incremental library scan that runs before commands."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from clickwheel.config import Config
from clickwheel.db import Database
from clickwheel.library import AUDIO_EXTENSIONS, scan_file
from clickwheel.output import confirm, dim, warn


@dataclass
class ScanResult:
    added: int = 0
    updated: int = 0
    missing: int = 0
    unchanged: int = 0
    errors: int = 0
    total: int = 0


def maybe_auto_scan(cfg: Config, db: Database) -> ScanResult | None:
    """Run an incremental scan if the DB is stale enough.

    Returns a ScanResult if a scan ran, or None if skipped.
    """
    if not cfg.auto_scan:
        return None

    # Check staleness
    last_scan = db.get_scan_meta("last_scan_completed")
    if last_scan is not None:
        age_seconds = time.time() - float(last_scan)
        if age_seconds < cfg.auto_scan_staleness_minutes * 60:
            return None

    # Check if music dir is reachable
    if not cfg.music_dir.is_dir():
        if last_scan:
            age_min = (time.time() - float(last_scan)) / 60
            if age_min < 60:
                age_str = f"{age_min:.0f} minutes ago"
            else:
                age_str = f"{age_min / 60:.1f} hours ago"
            warn(
                f"Library share not available, using cached data (last scan: {age_str})"
            )
        else:
            warn("Library share not available and no cached data exists.")
        return None

    return incremental_scan(cfg, db)


def incremental_scan(cfg: Config, db: Database) -> ScanResult:
    """Walk the library, compare against DB, and update only what changed."""
    from rich.console import Console

    console = Console()
    result = ScanResult()

    with console.status("Checking library...") as spinner:
        # Phase 1: Walk filesystem and collect current files
        disk_files: dict[str, Path] = {}
        for entry in cfg.music_dir.rglob("*"):
            if entry.suffix.lower() in AUDIO_EXTENSIONS:
                disk_files[str(entry)] = entry

        result.total = len(disk_files)
        spinner.update(f"Checking library... {result.total:,} files found")

        # Phase 2: Compare against DB
        db_paths = db.get_all_tracked_paths()

        for path_str, path in disk_files.items():
            try:
                stat = path.stat()
            except OSError:
                result.errors += 1
                continue

            db_mtime, db_size = db.get_track_mtime(path_str)

            if db_mtime is not None and db_size is not None:
                # Existing track — check if changed
                if stat.st_mtime == db_mtime and stat.st_size == db_size:
                    result.unchanged += 1
                    # Clear missing flag if it was set (file reappeared)
                    if path_str not in db_paths:
                        db.clear_missing(path_str)
                    continue
                # Changed — re-read metadata
                track = scan_file(path)
                if track:
                    db.upsert_track(track)
                    result.updated += 1
                else:
                    result.errors += 1
            else:
                # New file
                track = scan_file(path)
                if track:
                    db.upsert_track(track)
                    result.added += 1
                else:
                    result.errors += 1

        db.commit()

        # Phase 3: Detect deleted files
        missing_paths = db_paths - set(disk_files.keys())
        if missing_paths:
            result.missing = db.mark_missing(missing_paths)

    # Record scan completion
    db.set_scan_meta("last_scan_completed", str(time.time()))

    # Print summary
    if result.added or result.updated or result.missing:
        parts = []
        if result.added:
            parts.append(f"+{result.added} new")
        if result.updated:
            parts.append(f"{result.updated} updated")
        if result.missing:
            parts.append(f"{result.missing} missing")
        confirm(f"Library scan: {', '.join(parts)} ({result.total:,} tracks)")
    else:
        dim(f"Library up to date ({result.total:,} tracks)")

    return result
