"""Auto-scan — incremental library scan that runs before CLI commands.

Two-tier strategy (added 2026-05-07 to fix slow-SMB UX):

- **Cheap probe** (~5s on SMB, <100ms local): stat the music dir + iterate
  first-level subdirs, compare max child mtime against the last-known value
  stored in `scan_meta.last_probe_max_child_mtime`. Catches the common case
  ("user dropped a new album in") without doing a full ~3-minute SMB walk.
  POSIX directory mtimes update on immediate-child add/remove/rename, so
  this works for new albums under existing artists too.

- **Time-based fallback** (default 24h via `auto_scan_staleness_minutes`):
  even if the probe says "no change," run a full incremental scan once a
  day to catch in-place metadata edits (beets/Picard rewriting tags) — those
  don't bump any directory mtime.

The MCP server never runs autoscan; tool calls always serve cached data,
matching the manual-refresh model used by beets/Picard/Apple Music. Users
refresh by running `clickwheel scan` when they've added new music.
"""

from __future__ import annotations

import time
from pathlib import Path

from clickwheel.actions import LibraryNotFoundError, ScanResult, scan_library
from clickwheel.config import Config
from clickwheel.db import Database
from clickwheel.output import confirm, dim, warn


def _max_child_mtime(music_dir: Path) -> float | None:
    """Return the max mtime across `music_dir` and its first-level children.

    Returns None if the dir is unreachable. Catches stat failures on
    individual children (e.g. a vanished symlink) — they don't fail the
    whole probe.
    """
    try:
        max_mt = music_dir.stat().st_mtime
    except OSError:
        return None
    try:
        for child in music_dir.iterdir():
            try:
                ct = child.stat().st_mtime
                if ct > max_mt:
                    max_mt = ct
            except OSError:
                continue
    except OSError:
        return None
    return max_mt


def cheap_probe_says_changed(cfg: Config, db: Database) -> bool | None:
    """Run the cheap probe. Returns:

    - True: the top-level mtime is newer than the last recorded probe value
      (something added/removed/renamed at artist level — likely new music)
    - False: nothing changed at the top level
    - None: probe failed (share unreachable mid-call)

    First call ever (no stored value) returns True so the initial scan
    establishes a baseline.
    """
    current = _max_child_mtime(cfg.music_dir)
    if current is None:
        return None
    stored = db.get_scan_meta("last_probe_max_child_mtime")
    if stored is None:
        return True
    try:
        return current > float(stored)
    except ValueError:
        return True  # corrupt stored value; force a scan


def should_auto_scan(cfg: Config, db: Database) -> tuple[bool, str | None]:
    """Decide whether an incremental scan should run.

    Returns (run, reason). Reason values:
    - None: no scan needed (or autoscan disabled)
    - "share_unavailable": music dir isn't reachable; caller may want to warn
    - "stale": last scan older than the staleness threshold (24h fallback)
    - "probe_detected_change": cheap probe found a top-level mtime change
    - "first_run": no scan has ever completed; baseline is needed
    """
    if not cfg.auto_scan:
        return False, None

    if not cfg.music_dir.is_dir():
        return False, "share_unavailable"

    last_scan = db.get_scan_meta("last_scan_completed")
    if last_scan is None:
        return True, "first_run"

    # Time-based fallback first (catches in-place metadata edits from
    # beets/Picard that don't bump any directory mtime).
    age_seconds = time.time() - float(last_scan)
    if age_seconds >= cfg.auto_scan_staleness_minutes * 60:
        return True, "stale"

    # Cheap probe: ~5s on SMB, basically free locally. Catches the common
    # case (user dropped a new album in since the last scan).
    changed = cheap_probe_says_changed(cfg, db)
    if changed is True:
        return True, "probe_detected_change"
    # changed is False or None — fall through, no scan
    return False, None


def maybe_auto_scan(cfg: Config, db: Database) -> ScanResult | None:
    """Run an incremental scan if needed, with CLI-friendly output."""
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
