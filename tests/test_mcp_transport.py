"""Transport resolution for the MCP entry point.

`clickwheel-mcp` stays stdio by default; `serve --http` (or the
CLICKWHEEL_MCP_TRANSPORT env var) opts into the Streamable HTTP transport
used for remote access behind a tunnel. Skipped if the mcp SDK isn't
installed (importing server.py pulls in FastMCP)."""

from __future__ import annotations

import pytest

pytest.importorskip("mcp", reason="mcp not installed")

from clickwheel.mcp.server import (  # noqa: E402
    DEFAULT_HTTP_HOST,
    DEFAULT_HTTP_PORT,
    _resolve_transport,
)


def test_no_args_defaults_to_stdio(monkeypatch):
    monkeypatch.delenv("CLICKWHEEL_MCP_TRANSPORT", raising=False)
    transport, *_ = _resolve_transport([])
    assert transport == "stdio"


def test_serve_subcommand_selects_http_on_localhost(monkeypatch):
    monkeypatch.delenv("CLICKWHEEL_MCP_TRANSPORT", raising=False)
    transport, host, port, path = _resolve_transport(["serve", "--http"])
    assert transport == "http"
    assert host == DEFAULT_HTTP_HOST
    assert port == DEFAULT_HTTP_PORT
    assert path == "/mcp"


def test_serve_without_http_flag_still_serves_http(monkeypatch):
    monkeypatch.delenv("CLICKWHEEL_MCP_TRANSPORT", raising=False)
    transport, *_ = _resolve_transport(["serve"])
    assert transport == "http"


def test_serve_flags_override_defaults(monkeypatch):
    monkeypatch.delenv("CLICKWHEEL_MCP_TRANSPORT", raising=False)
    transport, host, port, path = _resolve_transport(
        ["serve", "--host", "0.0.0.0", "--port", "9001", "--path", "rpc"]
    )
    assert (transport, host, port) == ("http", "0.0.0.0", 9001)
    assert path == "/rpc"  # leading slash normalized


def test_env_transport_selects_http(monkeypatch):
    monkeypatch.setenv("CLICKWHEEL_MCP_TRANSPORT", "http")
    monkeypatch.setenv("CLICKWHEEL_MCP_PORT", "7000")
    transport, host, port, path = _resolve_transport([])
    assert (transport, port) == ("http", 7000)
    assert host == DEFAULT_HTTP_HOST


def test_env_transport_accepts_streamable_http_alias(monkeypatch):
    monkeypatch.setenv("CLICKWHEEL_MCP_TRANSPORT", "streamable-http")
    transport, *_ = _resolve_transport([])
    assert transport == "http"


def test_garbage_env_port_falls_back(monkeypatch):
    monkeypatch.setenv("CLICKWHEEL_MCP_TRANSPORT", "http")
    monkeypatch.setenv("CLICKWHEEL_MCP_PORT", "not-a-port")
    transport, _host, port, _path = _resolve_transport([])
    assert (transport, port) == ("http", DEFAULT_HTTP_PORT)


def test_cli_flags_take_precedence_over_env(monkeypatch):
    monkeypatch.setenv("CLICKWHEEL_MCP_TRANSPORT", "http")
    monkeypatch.setenv("CLICKWHEEL_MCP_PORT", "7000")
    _transport, _host, port, _path = _resolve_transport(["serve", "--port", "8123"])
    assert port == 8123
