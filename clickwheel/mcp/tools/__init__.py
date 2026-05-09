"""Tool modules. Importing this package registers every tool on the
FastMCP instance held in `clickwheel.mcp._runtime`. UI bundles are
registered here too so the resource list is fully populated before the
stdio transport starts.
"""

from clickwheel.mcp import (
    ui_resources,  # noqa: F401  side-effect: registers ui:// resources
)
from clickwheel.mcp.tools import ipod, library, playlist, scrobble  # noqa: F401
