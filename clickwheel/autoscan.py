"""Auto-scan — incremental library scan that runs before commands."""

from __future__ import annotations

import time

from clickwheel.actions import LibraryNotFoundError, ScanResult, scan_library
from clickwheel.config import Config
from clickwheel.db import Database
from clickwheel.output import confirm, dim, warn


def should_auto_scan(cfg: Config, db: Database) -> tuple[bool, str | None]:
    """Decide whether an incremental scan should run.

    Returns (run, reason). If `run` is False and `reason` is set, the caller
    may want to surface a warning (e.g. "share_unavailable" when the music
    directory isn't reachable but we have cached data).
    """
    if not cfg.auto_scan:
        return False, None

    last_scan = db.get_scan_meta("last_scan_completed")
    if last_scan is not None:
        age_seconds = time.time() - float(last_scan)
        if age_seconds < cfg.auto_scan_staleness_minutes * 60:
            return False, None

    if not cfg.music_dir.is_dir():
        return False, "share_unavailable"

    return True, None


def maybe_auto_scan(cfg: Config, db: Database) -> ScanResult | None:
    """Run an incremental scan if the DB is stale, with CLI-friendly output."""
    from rich.console import Console

    run, reason = should_auto_scan(cfg, db)

    if reason == "share_unavailable":
        last_scan = db.get_scan_meta("last_scan_completed")
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

    if not run:
        return None

    console = Console()
    with console.status("Checking library...") as spinner:

        def _on_progress(p) -> None:
            spinner.update(f"Checking library... {p.current:,}/{p.total:,}")

        try:
            result = scan_library(cfg, db, full=False, on_progress=_on_progress)
        except LibraryNotFoundError:
            warn("Library share not available.")
            return None

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
