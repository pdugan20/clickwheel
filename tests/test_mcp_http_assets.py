"""Favicon/static routes served by the Streamable HTTP transport.

These drive the Claude connector-list icon (via Google's favicon service) and
must be reachable over plain HTTP GET, separate from the MCP protocol on
/mcp. Skipped if the mcp SDK isn't installed."""

from __future__ import annotations

import pytest

pytest.importorskip("mcp", reason="mcp not installed")
pytest.importorskip("starlette", reason="starlette not installed")


@pytest.fixture(scope="module")
def client():
    from starlette.testclient import TestClient

    from clickwheel.mcp._runtime import mcp

    return TestClient(mcp.streamable_http_app())


def test_favicon_ico_served(client):
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/x-icon"
    assert r.content[:4] == b"\x00\x00\x01\x00"  # ICO magic
    assert "max-age" in r.headers.get("cache-control", "")


def test_favicon_png_served(client):
    r = client.get("/favicon-32.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic


def test_apple_touch_icon_served(client):
    r = client.get("/apple-touch-icon.png")
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_index_links_favicon(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert 'rel="icon"' in r.text


def test_mcp_endpoint_still_present(client):
    # The favicon routes must not shadow the protocol mount.
    paths = {getattr(route, "path", None) for route in client.app.routes}
    assert "/mcp" in paths
