"""Register MCP Apps UI resources.

Imported for side effects from `clickwheel.mcp.tools.__init__` so the
resources are bound to the FastMCP instance at import time, before
`mcp.run()` starts the stdio transport.
"""

from __future__ import annotations

from clickwheel.mcp._runtime import mcp
from clickwheel.mcp._ui_bundles import IPOD_CAPACITY_HTML
from clickwheel.mcp.ui import register_ui_resource

IPOD_CAPACITY_URI = "ui://clickwheel/ipod-capacity.html"


register_ui_resource(
    mcp,
    uri=IPOD_CAPACITY_URI,
    html=IPOD_CAPACITY_HTML,
    name="clickwheel — iPod capacity",
    description=(
        "Stacked capacity bar for the connected iPod, segmented by top "
        "artists with free space on the right. Consumes the structured "
        "payload from get_ipod_contents."
    ),
)
