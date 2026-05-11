"""Helpers that build the sync-result `detail` subtitle.

Lives at the top of the package (not under `clickwheel.mcp`) so unit
tests can import it without needing the mcp SDK installed. The MCP
tools call these right before kicking off a destructive iPod write to
populate `_sync_state.detail` — the static one-liner the sync-result
bundle renders under its title.
"""

from __future__ import annotations

from clickwheel.db import Database


def fmt_bytes(n: int) -> str:
    """Render a byte count as a one-decimal GB, whole MB, or whole KB.
    Matches the bundle's TS `fmtBytes` so the server-emitted subtitle
    visually agrees with anything the bundle formats client-side.
    """
    gb = n / 1024**3
    if gb >= 1:
        return f"{gb:.1f} GB"
    mb = n / 1024**2
    if mb >= 1:
        return f"{mb:.0f} MB"
    return f"{n / 1024:.0f} KB"


def detail_for_tracks(tracks: list[dict]) -> str:
    """Build "145 MB · 8 albums" from a list of resolved track dicts.

    Skips empty/missing album values so a few tagless tracks don't
    inflate the album count. Returns "" when there's nothing meaningful
    to say.
    """
    if not tracks:
        return ""
    total_bytes = sum(t.get("file_size") or 0 for t in tracks)
    albums = {t.get("album") or "" for t in tracks if t.get("album")}
    parts: list[str] = []
    if total_bytes > 0:
        parts.append(fmt_bytes(total_bytes))
    if len(albums) == 1:
        parts.append("1 album")
    elif len(albums) > 1:
        parts.append(f"{len(albums)} albums")
    return " · ".join(parts)


def detail_for_paths(db: Database, paths: list[str]) -> str:
    """Same as `detail_for_tracks`, but looks the rows up by path."""
    if not paths:
        return ""
    placeholders = ",".join("?" * len(paths))
    rows = db.conn.execute(
        f"SELECT album, file_size FROM tracks WHERE path IN ({placeholders})",
        paths,
    ).fetchall()
    return detail_for_tracks([dict(r) for r in rows])
