"""Verify sync_playlist_to_ipod streams MCP progress notifications.

The tool must:
  1. Report per-track progress via ctx.report_progress while the sync runs
     in a worker thread.
  2. Report values strictly in (current, total, "<artist> — <title>") shape
     so Claude Desktop's progress UI shows useful labels.
  3. Still return a normal CallToolResult on completion.

We swap out actions.compute_diff and actions.sync_playlist with stand-ins
that fire on_event with synthetic SyncEvent objects, then assert what the
fake Context observed. No real iPod, no real file copies.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any

import pytest

pytest.importorskip("mcp", reason="mcp not installed")

from clickwheel import actions
from clickwheel.config import Config
from clickwheel.db import Database


class _FakeContext:
    """Minimal Context stand-in that records report_progress calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[float, float | None, str | None]] = []

    async def report_progress(
        self,
        progress: float,
        total: float | None = None,
        message: str | None = None,
    ) -> None:
        # Match MCPServer's signature exactly so any future drift is caught.
        self.calls.append((progress, total, message))


def _setup(tmp_path, monkeypatch):
    """Build a Config in tmp_path and patch the tool's load_config."""
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    cfg = Config(
        music_dir=music_dir,
        project_dir=tmp_path,
        ipod_mount=tmp_path / "ipod-not-mounted",
        auto_scan=False,
    )
    Database(cfg.db_path).close()

    # The tool imports load_config directly (not via _runtime), so the
    # patch target is the tool module's binding.
    monkeypatch.setattr("clickwheel.mcp.tools.ipod.load_config", lambda: cfg)
    return cfg


def _fake_track(artist: str, title: str) -> dict[str, Any]:
    return {
        "path": f"/music/{artist}/{title}.mp3",
        "artist": artist,
        "album": "Album",
        "title": title,
        "file_size": 1_000_000,
    }


def test_sync_reports_per_track_progress(tmp_path, monkeypatch):
    from clickwheel.mcp.tools.ipod import sync_playlist_to_ipod

    _setup(tmp_path, monkeypatch)

    tracks = [
        _fake_track("Taylor Swift", "Cardigan"),
        _fake_track("Taylor Swift", "August"),
        _fake_track("Big Thief", "Not"),
    ]
    fake_diff = actions.Diff(playlist="test", to_add=list(tracks))

    def fake_compute_diff(_cfg, _db, _name):
        return fake_diff

    def fake_sync_playlist(
        _cfg, _db, _name, *, diff, on_event=None, on_conflict=None, target_name=None
    ):
        # Mimic copy_tracks_to_ipod: fire on_event once per track in order.
        for i, track in enumerate(diff.to_add, start=1):
            on_event(
                actions.SyncEvent(
                    current=i, total=len(diff.to_add), track=track, ok=True
                )
            )
        return actions.SyncResult(
            copied=list(diff.to_add),
            failed=[],
            kept_in_place_count=0,
            library_updated=True,
        )

    monkeypatch.setattr(actions, "compute_diff", fake_compute_diff)
    monkeypatch.setattr(actions, "sync_playlist", fake_sync_playlist)

    ctx = _FakeContext()

    # The tool is async — drive it directly. It schedules progress
    # notifications via run_coroutine_threadsafe; asyncio.run gives us
    # the event loop those tasks land on.
    assert inspect.iscoroutinefunction(sync_playlist_to_ipod)

    async def _drive():
        return await sync_playlist_to_ipod(playlist="test", ctx=ctx)

    result = asyncio.run(_drive())

    assert ctx.calls == [
        (1, 3, "Taylor Swift — Cardigan"),
        (2, 3, "Taylor Swift — August"),
        (3, 3, "Big Thief — Not"),
    ], f"unexpected progress calls: {ctx.calls!r}"

    # Sanity-check the tool result still surfaces the structured payload.
    sc = result.structured_content or {}
    assert sc.get("synced") is True
    assert sc.get("added") == 3
    assert sc.get("library_updated") is True


def test_sync_noop_when_diff_empty_skips_progress(tmp_path, monkeypatch):
    """Empty diff: sync_playlist still runs (to write/update the iPod
    playlist artifact), but no per-track copy happens so no progress
    notifications fire."""
    from clickwheel.mcp.tools.ipod import sync_playlist_to_ipod

    _setup(tmp_path, monkeypatch)

    fake_diff = actions.Diff(playlist="test", to_add=[], to_remove=[])
    monkeypatch.setattr(actions, "compute_diff", lambda *a, **k: fake_diff)

    def fake_sync(_cfg, _db, _name, *, diff, on_event=None, **_k):
        # No tracks to copy → no on_event calls.
        return actions.SyncResult(
            copied=[],
            failed=[],
            kept_in_place_count=0,
            library_updated=True,
        )

    monkeypatch.setattr(actions, "sync_playlist", fake_sync)

    ctx = _FakeContext()
    result = asyncio.run(sync_playlist_to_ipod(playlist="test", ctx=ctx))

    # No per-track progress because no tracks were copied.
    assert ctx.calls == []
    sc = result.structured_content or {}
    assert sc.get("synced") is True
    assert sc.get("added") == 0
    assert sc.get("library_updated") is True
