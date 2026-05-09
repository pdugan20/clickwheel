"""Register MCP Apps UI resources.

Imported for side effects from `clickwheel.mcp.tools.__init__` so the
resources are bound to the FastMCP instance at import time, before
`mcp.run()` starts the stdio transport.
"""

from __future__ import annotations

from clickwheel.mcp._runtime import mcp
from clickwheel.mcp._ui_bundles import IPOD_CAPACITY_HTML, LIBRARY_STATS_HTML
from clickwheel.mcp.ui import register_ui_resource

IPOD_CAPACITY_URI = "ui://clickwheel/ipod-capacity.html"
LIBRARY_STATS_URI = "ui://clickwheel/library-stats.html"


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


register_ui_resource(
    mcp,
    uri=LIBRARY_STATS_URI,
    html=LIBRARY_STATS_HTML,
    name="clickwheel — library overview",
    description=(
        "Headline counts (tracks, artists, albums, size, hours) plus a "
        "format-breakdown bar. Consumes the structured payload from "
        "library_stats."
    ),
)
