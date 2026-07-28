"""End-to-end smoke test: spawn `python -m clickwheel.mcp` over stdio and
exercise the MCP wire protocol. Skipped if the mcp SDK isn't installed."""

from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
import time
from contextlib import contextmanager

import pytest

pytest.importorskip("mcp", reason="mcp not installed")


def _list_tools_via_protocol(*, modern: bool):
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def _run() -> set[str]:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "clickwheel.mcp"],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                if modern:
                    await session.discover()
                else:
                    await session.initialize()
                tools = await session.list_tools()
                return {t.name for t in tools.tools}

    return asyncio.run(_run())


@pytest.mark.parametrize("modern", [True, False], ids=["discover", "initialize"])
def test_smoke_tools_list_includes_read_tools(modern):
    """Both protocol eras expose the expected read tools over stdio."""
    names = _list_tools_via_protocol(modern=modern)
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


@contextmanager
def _running_http_server():
    """Start the real Streamable HTTP entry point on an ephemeral port."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "clickwheel.mcp",
            "serve",
            "--http",
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stderr = process.stderr.read() if process.stderr else ""
                pytest.fail(f"HTTP MCP server exited early:\n{stderr}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                    break
            except OSError:
                time.sleep(0.05)
        else:
            pytest.fail("HTTP MCP server did not start within 10 seconds")
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.parametrize(
    ("mode", "expected_version"),
    [("auto", "2026-07-28"), ("legacy", "2025-11-25")],
    ids=["modern-stateless", "legacy-session"],
)
def test_streamable_http_supports_both_protocol_eras(mode, expected_version):
    """The production HTTP endpoint serves modern and legacy clients."""
    from mcp import Client

    async def _run(url: str) -> tuple[str, set[str]]:
        async with Client(url, mode=mode) as client:
            tools = await client.list_tools()
            return client.protocol_version, {tool.name for tool in tools.tools}

    with _running_http_server() as url:
        version, names = asyncio.run(_run(url))

    assert version == expected_version
    assert "library_stats" in names
