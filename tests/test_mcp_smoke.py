"""End-to-end smoke test: spawn `python -m clickwheel.mcp` over stdio and
exercise the MCP wire protocol. Skipped if the mcp SDK isn't installed."""

from __future__ import annotations

import asyncio
import sys

import pytest

pytest.importorskip("mcp", reason="mcp not installed")


def _list_tools_via_protocol():
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def _run() -> set[str]:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "clickwheel.mcp"],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                return {t.name for t in tools.tools}

    return asyncio.run(_run())


def test_smoke_tools_list_includes_read_tools():
    """Server starts, responds to initialize, and reports the expected
    read tools via tools/list."""
    names = _list_tools_via_protocol()
    expected = {
        "library_stats",
        "list_artists",
        "list_albums_by_artist",
        "list_tracks_by_album",
        "search_tracks",
        "list_playlists",
        "get_playlist",
        "get_ipod_contents",
        "get_pending_scrobbles",
        "library_health",
    }
    assert expected <= names, f"missing tools: {expected - names}"
