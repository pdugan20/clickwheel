"""MCP Apps integration for clickwheel.

The MCP Apps extension (`io.modelcontextprotocol/ui`) lets a host like
Claude Desktop render an HTML iframe inline beneath a tool result. The
server advertises support during the initialize handshake, registers each
view as a `ui://` resource with a special MIME type, and attaches a
`_meta.ui.resourceUri` pointer to any tool that should trigger an iframe.

Constants here mirror the upstream `@modelcontextprotocol/ext-apps` spec
package — keep them in sync when the SDK ships a new protocol version.

Stage A scope: this module wires a single placeholder bundle so we can
verify FastMCP advertises the capability, serves the resource, and ships
the right `_meta` on tool registration. Stage B replaces the inline HTML
with real React bundles produced by a Vite pipeline.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP

# Spec constants. Mirror @modelcontextprotocol/ext-apps. See:
#   node_modules/@modelcontextprotocol/ext-apps/dist/src/server/index.js
EXTENSION_ID = "io.modelcontextprotocol/ui"
RESOURCE_MIME_TYPE = "text/html;profile=mcp-app"
RESOURCE_URI_META_KEY = "ui/resourceUri"


def enable_mcp_apps(mcp: FastMCP) -> None:
    """Advertise the MCP Apps extension on the initialize handshake.

    FastMCP's `get_capabilities()` doesn't expose an `extensions` hook —
    it only knows about the spec'd capability fields (prompts, resources,
    tools, etc.). The underlying `ServerCapabilities` model has
    `extra="allow"` though, so we wrap the low-level server's
    `get_capabilities` to inject the extension marker.

    Without this advertisement, Claude Desktop sees `_meta.ui.resourceUri`
    on tool registrations but silently skips iframe rendering because
    capability negotiation failed.
    """
    server = mcp._mcp_server
    original = server.get_capabilities

    def patched(notification_options, experimental_capabilities):  # type: ignore[no-untyped-def]
        caps = original(notification_options, experimental_capabilities)
        # ServerCapabilities has model_config = ConfigDict(extra="allow"),
        # so we can stash arbitrary fields via __pydantic_extra__.
        existing = getattr(caps, "__pydantic_extra__", None) or {}
        extensions = dict(existing.get("extensions") or {})
        extensions[EXTENSION_ID] = {"mimeTypes": [RESOURCE_MIME_TYPE]}
        existing["extensions"] = extensions
        caps.__pydantic_extra__ = existing
        return caps

    server.get_capabilities = patched  # type: ignore[method-assign]


def ui_tool_meta(uri: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the `_meta` dict for a tool that drives a UI bundle.

    Writes both the nested `ui.resourceUri` (current spec) and the flat
    `ui/resourceUri` (deprecated, slated for removal before GA). Hosts in
    the wild read one or the other depending on when they shipped, so we
    dual-write — same approach rewind takes — and drop the flat key once
    the spec finalizes.
    """
    meta: dict[str, Any] = dict(extra or {})
    meta[RESOURCE_URI_META_KEY] = uri
    ui_block = dict(meta.get("ui") or {})
    ui_block["resourceUri"] = uri
    meta["ui"] = ui_block
    return meta


def register_ui_resource(
    mcp: FastMCP,
    *,
    uri: str,
    html: str,
    name: str | None = None,
    title: str | None = None,
    description: str | None = None,
    csp: dict[str, Any] | None = None,
) -> Callable[[], str]:
    """Register a `ui://` resource that returns inlined HTML.

    `name` is the programmatic slug; `title` is the human display string
    hosts render. `csp` is forwarded under the resource's `_meta.ui.csp`
    so the host knows which extra origins (e.g. an artwork CDN) the iframe
    is allowed to load — without it, the host's default CSP blocks
    external assets.
    """
    meta: dict[str, Any] = {}
    if csp is not None:
        meta["ui"] = {"csp": csp}

    @mcp.resource(
        uri,
        name=name,
        title=title,
        description=description,
        mime_type=RESOURCE_MIME_TYPE,
        meta=meta or None,
    )
    def _read() -> str:
        return html

    return _read
