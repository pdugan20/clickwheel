"""Tool modules. Importing this package registers every tool on the
FastMCP instance held in `clickwheel.mcp._runtime`. UI bundles are
registered here too so the resource list is fully populated before the
stdio transport starts.
"""

from clickwheel.mcp import (
    ui_resources,  # noqa: F401  side-effect: registers ui:// resources
)
from clickwheel.mcp.tools import (
    apple,  # noqa: F401
    ipod,  # noqa: F401
    library,  # noqa: F401
    playlist,  # noqa: F401
    plex,  # noqa: F401
    scrobble,  # noqa: F401
)
