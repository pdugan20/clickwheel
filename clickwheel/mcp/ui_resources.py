"""Register MCP Apps UI resources.

Imported for side effects from `clickwheel.mcp.tools.__init__` so the
resources are bound to the FastMCP instance at import time, before
`mcp.run()` starts the stdio transport.
"""

from __future__ import annotations

from clickwheel.mcp._runtime import mcp
from clickwheel.mcp._ui_bundles import (
    IPOD_CAPACITY_HTML,
    LIBRARY_STATS_HTML,
    SYNC_RESULT_HTML,
)
from clickwheel.mcp.ui import register_ui_resource

IPOD_CAPACITY_URI = "ui://clickwheel/ipod-capacity.html"
LIBRARY_STATS_URI = "ui://clickwheel/library-stats.html"
SYNC_RESULT_URI = "ui://clickwheel/sync-result.html"


register_ui_resource(
    mcp,
    uri=IPOD_CAPACITY_URI,
    html=IPOD_CAPACITY_HTML,
    name="ipod-capacity",
    title="clickwheel — iPod capacity",
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
    name="library-stats",
    title="clickwheel — library overview",
    description=(
        "Headline counts (tracks, artists, albums, size, hours) plus a "
        "format-breakdown bar. Consumes the structured payload from "
        "library_stats."
    ),
)


register_ui_resource(
    mcp,
    uri=SYNC_RESULT_URI,
    html=SYNC_RESULT_HTML,
    name="sync-result",
    title="clickwheel — sync result",
    description=(
        "Live progress + post-completion summary for any iPod write "
        "(sync_playlist_to_ipod, add_tracks_to_ipod, add_artist_to_ipod, "
        "remove_tracks_from_ipod, remove_artist_from_ipod, "
        "remove_ipod_playlist). While the tool runs, polls "
        "state://clickwheel/sync-progress and renders a per-track "
        "progress bar. When the tool result lands, switches to a "
        "summary card."
    ),
)


# Live-progress state resource. The sync-result bundle polls this while
# a long-running write tool is in flight (Claude Desktop mounts the
# iframe mid-call thanks to _meta.ui.resourceUri preload). The tools
# update the underlying state dict via clickwheel.mcp._sync_state from
# their per-track callbacks.
SYNC_PROGRESS_URI = "state://clickwheel/sync-progress"


@mcp.resource(
    SYNC_PROGRESS_URI,
    name="sync-progress",
    title="clickwheel — sync progress (live)",
    description=(
        "Snapshot of the in-flight sync/add/remove operation. Kind, "
        "current, total, last-track message, done flag. Polled by the "
        "sync-result bundle every ~500ms while waiting for a tool "
        "result. Not user-facing; consumed by the iframe."
    ),
    mime_type="application/json",
)
def _read_sync_progress() -> str:
    import json

    from clickwheel.mcp import _sync_state

    return json.dumps(_sync_state.snapshot())
