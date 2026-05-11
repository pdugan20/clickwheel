"""Register MCP Apps UI resources.

Imported for side effects from `clickwheel.mcp.tools.__init__` so the
resources are bound to the FastMCP instance at import time, before
`mcp.run()` starts the stdio transport.
"""

from __future__ import annotations

from clickwheel.mcp._runtime import mcp
from clickwheel.mcp._ui_bundles import (
    IPOD_CAPACITY_HTML,
    LIBRARY_HEALTH_HTML,
    LIBRARY_STATS_HTML,
    SYNC_RESULT_HTML,
)
from clickwheel.mcp.ui import register_ui_resource

IPOD_CAPACITY_URI = "ui://clickwheel/ipod-capacity.html"
LIBRARY_STATS_URI = "ui://clickwheel/library-stats.html"
LIBRARY_HEALTH_URI = "ui://clickwheel/library-health.html"
SYNC_RESULT_URI = "ui://clickwheel/sync-result.html"


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


register_ui_resource(
    mcp,
    uri=LIBRARY_HEALTH_URI,
    html=LIBRARY_HEALTH_HTML,
    name="clickwheel — library health",
    description=(
        "Status grid for the library scan: music-folder reachability, "
        "indexed/missing counts, last-scan freshness, auto-scan toggle. "
        "Consumes the structured payload from library_health."
    ),
)


register_ui_resource(
    mcp,
    uri=SYNC_RESULT_URI,
    html=SYNC_RESULT_HTML,
    name="clickwheel — sync result",
    description=(
        "Post-completion summary for an iPod write: tracks added, "
        "failed, already-present counts, conflict resolution mode. "
        "Bound to sync_playlist_to_ipod, add_tracks_to_ipod, and "
        "add_artist_to_ipod. The 'Working on it…' placeholder is the "
        "preload-experiment surface — if visible during a long-running "
        "sync, Claude Desktop mounted the iframe mid-call and we can "
        "layer live progress on top in a later change."
    ),
)
