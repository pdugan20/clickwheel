"""FastMCP server entry point.

The FastMCP instance, session helper, and shared utilities live in
`clickwheel.mcp._runtime`. Tool definitions are split by domain under
`clickwheel.mcp.tools`. Importing the tools subpackage triggers
`@mcp.tool()` registration for every tool.
"""

from __future__ import annotations

import logging
import os
import sys

from clickwheel.actions import ClickwheelError
from clickwheel.mcp import (
    prompts as _prompts,  # noqa: F401  side-effect: registers prompts
)
from clickwheel.mcp import (
    tools as _tools,  # noqa: F401  side-effect: registers tools
)
from clickwheel.mcp._runtime import mcp

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure stderr logging. stdout is reserved for the MCP wire protocol."""
    level_name = os.environ.get("CLICKWHEEL_MCP_LOG_LEVEL", "WARNING").upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(
        level=level,
        format="[clickwheel-mcp] %(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )


def main() -> None:
    """Console-script entry point. Runs the server over stdio."""
    _setup_logging()
    logger.info("Starting clickwheel MCP server (stdio)")
    try:
        mcp.run(transport="stdio")
    except ClickwheelError as exc:
        logger.error("Server error: %s", exc)
        sys.exit(1)
