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


# Streamable-HTTP defaults. The HTTP transport is meant to sit behind a
# Cloudflare Tunnel for remote access (see docs/mcp/remote-mobile-access.md),
# so it binds loopback only — the tunnel is the sole public ingress; the
# server never listens on a routable interface itself.
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8000
DEFAULT_HTTP_PATH = "/mcp"
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _env_int(name: str, default: int) -> int:
    """Read an int from the environment, falling back on missing/garbage."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Ignoring non-integer %s=%r; using %d", name, raw, default)
        return default


def _resolve_transport(argv: list[str]) -> tuple[str, str, int, str]:
    """Decide stdio vs streamable-http from argv + environment.

    Returns ``(transport, host, port, path)``. ``transport`` is ``"stdio"``
    (the unchanged default for local desktop clients) or ``"http"``. The
    host/port/path fields only apply to the HTTP transport.

    Selection, highest precedence first:
    - ``serve`` subcommand (with optional ``--http``/``--host``/``--port``/
      ``--path``) -> HTTP.
    - ``CLICKWHEEL_MCP_TRANSPORT=http`` (or ``streamable-http``) -> HTTP, with
      host/port/path from ``CLICKWHEEL_MCP_HOST``/``_PORT``/``_PATH``.
    - otherwise -> stdio.
    """
    import argparse

    env_transport = os.environ.get("CLICKWHEEL_MCP_TRANSPORT", "").strip().lower()
    env_http = env_transport in {"http", "streamable-http", "streamable_http"}

    env_host = os.environ.get("CLICKWHEEL_MCP_HOST", DEFAULT_HTTP_HOST)
    env_port = _env_int("CLICKWHEEL_MCP_PORT", DEFAULT_HTTP_PORT)
    env_path = os.environ.get("CLICKWHEEL_MCP_PATH", DEFAULT_HTTP_PATH)

    parser = argparse.ArgumentParser(
        prog="clickwheel-mcp",
        description="clickwheel MCP server. No arguments runs over stdio for "
        "local desktop clients; `serve --http` runs a Streamable HTTP server "
        "for remote access behind a tunnel.",
    )
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser(
        "serve",
        help="Run an explicit transport (defaults to Streamable HTTP on localhost).",
    )
    serve.add_argument(
        "--http",
        action="store_true",
        help="Serve Streamable HTTP (the default for `serve`; flag kept for clarity).",
    )
    serve.add_argument(
        "--host", default=env_host, help=f"Bind address (default {env_host})."
    )
    serve.add_argument(
        "--port", type=int, default=env_port, help=f"Bind port (default {env_port})."
    )
    serve.add_argument(
        "--path", default=env_path, help=f"HTTP path (default {env_path})."
    )
    args = parser.parse_args(argv)

    if args.command == "serve":
        host, port, path = args.host, args.port, args.path
    elif env_http:
        host, port, path = env_host, env_port, env_path
    else:
        return ("stdio", DEFAULT_HTTP_HOST, DEFAULT_HTTP_PORT, DEFAULT_HTTP_PATH)

    if not path.startswith("/"):
        path = "/" + path
    return ("http", host, port, path)


def main() -> None:
    """Console-script entry point.

    Default (no arguments) runs over stdio, unchanged, for local desktop MCP
    clients (Claude Code / Claude Desktop via the `clickwheel-mcp` script or
    `python -m clickwheel.mcp`). `clickwheel-mcp serve --http` runs a
    Streamable HTTP server bound to localhost for remote access behind a
    Cloudflare Tunnel — see docs/mcp/remote-mobile-access.md.
    """
    _setup_logging()
    transport, host, port, path = _resolve_transport(sys.argv[1:])
    try:
        if transport == "http":
            if host not in _LOOPBACK_HOSTS:
                logger.warning(
                    "Binding %s (not loopback); the HTTP transport is intended to "
                    "sit behind a tunnel and listen on localhost only.",
                    host,
                )
            mcp.settings.host = host
            mcp.settings.port = port
            mcp.settings.streamable_http_path = path
            logger.info(
                "Starting clickwheel MCP server (streamable-http) on http://%s:%d%s",
                host,
                port,
                path,
            )
            mcp.run(transport="streamable-http")
        else:
            logger.info("Starting clickwheel MCP server (stdio)")
            mcp.run(transport="stdio")
    except ClickwheelError as exc:
        logger.error("Server error: %s", exc)
        sys.exit(1)
