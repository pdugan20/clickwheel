"""MCP Apps integration for clickwheel.

The MCP Apps extension (`io.modelcontextprotocol/ui`) lets a host like
Claude Desktop render an HTML iframe inline beneath a tool result. The
server advertises support through MCP's extensions framework, registers
each view as a `ui://` resource with a special MIME type, and attaches a
`_meta.ui.resourceUri` pointer to any tool that should trigger an iframe.

Constants here mirror the upstream `@modelcontextprotocol/ext-apps` spec
package — keep them in sync with the versioned MCP Apps extension.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer
from mcp.server.extension import Extension

# Spec constants. Mirror @modelcontextprotocol/ext-apps. See:
#   node_modules/@modelcontextprotocol/ext-apps/dist/src/server/index.js
EXTENSION_ID = "io.modelcontextprotocol/ui"
RESOURCE_MIME_TYPE = "text/html;profile=mcp-app"


class MCPAppsExtension(Extension):
    """Advertise the stable MCP Apps extension during modern discovery."""

    identifier = EXTENSION_ID

    def settings(self) -> dict[str, Any]:
        return {"mimeTypes": [RESOURCE_MIME_TYPE]}


def ui_tool_meta(uri: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the `_meta` dict for a tool that drives a UI bundle.

    MCP Apps is now a stable extension, so only the standardized nested
    `ui.resourceUri` form is emitted.
    """
    meta: dict[str, Any] = dict(extra or {})
    ui_block = dict(meta.get("ui") or {})
    ui_block["resourceUri"] = uri
    meta["ui"] = ui_block
    return meta


def register_ui_resource(
    mcp: MCPServer,
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
