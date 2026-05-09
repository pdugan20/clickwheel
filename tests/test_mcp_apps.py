"""End-to-end MCP Apps wire-protocol checks.

Spawns `python -m clickwheel.mcp` over stdio and verifies the four moving
parts that have to line up before Claude Desktop will render an iframe:

1. Initialize handshake advertises `extensions["io.modelcontextprotocol/ui"]`
   with the right MIME type.
2. resources/list includes the `ui://clickwheel/ipod-capacity.html` URI
   with the `text/html;profile=mcp-app` MIME type.
3. resources/read returns the bundle HTML, also with the right MIME.
4. tools/list reports `get_ipod_contents` carrying both the nested
   `_meta.ui.resourceUri` and the legacy flat `_meta["ui/resourceUri"]`,
   pointing at the same URI.

If any of these drift, the manual Claude Desktop test will fail silently
(iframe just doesn't appear) — much easier to catch here.
"""

from __future__ import annotations

import asyncio
import sys

import pytest

pytest.importorskip("mcp", reason="mcp not installed")

from clickwheel.mcp.ui import (  # noqa: E402
    EXTENSION_ID,
    RESOURCE_MIME_TYPE,
    RESOURCE_URI_META_KEY,
)
from clickwheel.mcp.ui_resources import IPOD_CAPACITY_URI  # noqa: E402


def _exercise_protocol():
    """Drive a full stdio session: initialize, list resources, read the
    UI bundle, list tools. Returns the four payloads we need to assert on.
    """
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    async def _run():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "clickwheel.mcp"],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                resources = await session.list_resources()
                bundle = await session.read_resource(IPOD_CAPACITY_URI)
                tools = await session.list_tools()
                return init, resources, bundle, tools

    return asyncio.run(_run())


def test_initialize_advertises_mcp_apps_extension():
    init, *_ = _exercise_protocol()
    # ServerCapabilities is `extra="allow"`, so unknown fields land in
    # __pydantic_extra__ — fall back to model_dump for a stable view.
    caps = init.capabilities.model_dump(exclude_none=True)
    extensions = caps.get("extensions") or {}
    assert EXTENSION_ID in extensions, (
        f"missing {EXTENSION_ID} in capabilities.extensions; got {extensions!r}"
    )
    mime_types = extensions[EXTENSION_ID].get("mimeTypes") or []
    assert RESOURCE_MIME_TYPE in mime_types, (
        f"{RESOURCE_MIME_TYPE} missing from advertised mimeTypes: {mime_types!r}"
    )


def test_resources_list_includes_ui_bundle():
    _, resources, _, _ = _exercise_protocol()
    by_uri = {str(r.uri): r for r in resources.resources}
    assert IPOD_CAPACITY_URI in by_uri, (
        f"missing {IPOD_CAPACITY_URI} in resources/list; got {list(by_uri)!r}"
    )
    res = by_uri[IPOD_CAPACITY_URI]
    assert res.mimeType == RESOURCE_MIME_TYPE


def test_read_resource_returns_html_bundle():
    _, _, bundle, _ = _exercise_protocol()
    assert bundle.contents, "resources/read returned no contents"
    first = bundle.contents[0]
    assert first.mimeType == RESOURCE_MIME_TYPE
    text = getattr(first, "text", "") or ""
    assert "<!doctype html>" in text.lower()
    # Sanity-check the bundle is the capacity-bar stub, not some other HTML.
    assert "iPod capacity" in text


def test_get_ipod_contents_carries_ui_meta():
    _, _, _, tools = _exercise_protocol()
    by_name = {t.name: t for t in tools.tools}
    tool = by_name.get("get_ipod_contents")
    assert tool is not None, (
        f"get_ipod_contents missing from tools/list: {list(by_name)}"
    )
    meta = tool.meta or {}
    # Nested form (current spec).
    ui = meta.get("ui") or {}
    assert ui.get("resourceUri") == IPOD_CAPACITY_URI, (
        f"_meta.ui.resourceUri mismatch: {ui!r}"
    )
    # Flat form (deprecated, still dual-written for legacy hosts).
    assert meta.get(RESOURCE_URI_META_KEY) == IPOD_CAPACITY_URI, (
        f"_meta[{RESOURCE_URI_META_KEY!r}] mismatch: {meta!r}"
    )
