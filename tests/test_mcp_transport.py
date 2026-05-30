"""Transport resolution for the MCP entry point.

`clickwheel-mcp` stays stdio by default; `serve --http` (or the
CLICKWHEEL_MCP_TRANSPORT env var) opts into the Streamable HTTP transport
used for remote access behind a tunnel. Skipped if the mcp SDK isn't
installed (importing server.py pulls in FastMCP)."""

from __future__ import annotations

import pytest

pytest.importorskip("mcp", reason="mcp not installed")

from clickwheel.mcp.server import (
    DEFAULT_HTTP_HOST,
    DEFAULT_HTTP_PORT,
    _resolve_transport,
)


def test_no_args_defaults_to_stdio(monkeypatch):
    monkeypatch.delenv("CLICKWHEEL_MCP_TRANSPORT", raising=False)
    assert _resolve_transport([]).transport == "stdio"


def test_serve_subcommand_selects_http_on_localhost(monkeypatch):
    monkeypatch.delenv("CLICKWHEEL_MCP_TRANSPORT", raising=False)
    cfg = _resolve_transport(["serve", "--http"])
    assert cfg.transport == "http"
    assert cfg.host == DEFAULT_HTTP_HOST
    assert cfg.port == DEFAULT_HTTP_PORT
    assert cfg.path == "/mcp"


def test_serve_without_http_flag_still_serves_http(monkeypatch):
    monkeypatch.delenv("CLICKWHEEL_MCP_TRANSPORT", raising=False)
    assert _resolve_transport(["serve"]).transport == "http"


def test_serve_flags_override_defaults(monkeypatch):
    monkeypatch.delenv("CLICKWHEEL_MCP_TRANSPORT", raising=False)
    cfg = _resolve_transport(
        ["serve", "--host", "0.0.0.0", "--port", "9001", "--path", "rpc"]
    )
    assert (cfg.transport, cfg.host, cfg.port) == ("http", "0.0.0.0", 9001)
    assert cfg.path == "/rpc"  # leading slash normalized


def test_env_transport_selects_http(monkeypatch):
    monkeypatch.setenv("CLICKWHEEL_MCP_TRANSPORT", "http")
    monkeypatch.setenv("CLICKWHEEL_MCP_PORT", "7000")
    cfg = _resolve_transport([])
    assert (cfg.transport, cfg.port) == ("http", 7000)
    assert cfg.host == DEFAULT_HTTP_HOST


def test_env_transport_accepts_streamable_http_alias(monkeypatch):
    monkeypatch.setenv("CLICKWHEEL_MCP_TRANSPORT", "streamable-http")
    assert _resolve_transport([]).transport == "http"


def test_garbage_env_port_falls_back(monkeypatch):
    monkeypatch.setenv("CLICKWHEEL_MCP_TRANSPORT", "http")
    monkeypatch.setenv("CLICKWHEEL_MCP_PORT", "not-a-port")
    cfg = _resolve_transport([])
    assert (cfg.transport, cfg.port) == ("http", DEFAULT_HTTP_PORT)


def test_cli_flags_take_precedence_over_env(monkeypatch):
    monkeypatch.setenv("CLICKWHEEL_MCP_TRANSPORT", "http")
    monkeypatch.setenv("CLICKWHEEL_MCP_PORT", "7000")
    assert _resolve_transport(["serve", "--port", "8123"]).port == 8123


def test_local_bind_always_allowed(monkeypatch):
    monkeypatch.delenv("CLICKWHEEL_MCP_ALLOWED_HOSTS", raising=False)
    cfg = _resolve_transport(["serve"])
    # The local bind host:port is always allowlisted so on-box clients work.
    assert f"{DEFAULT_HTTP_HOST}:{DEFAULT_HTTP_PORT}" in cfg.allowed_hosts


def test_allowed_host_flag_and_derived_origin(monkeypatch):
    monkeypatch.delenv("CLICKWHEEL_MCP_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("CLICKWHEEL_MCP_ALLOWED_ORIGINS", raising=False)
    cfg = _resolve_transport(["serve", "--allowed-host", "clickwheel.fm"])
    assert "clickwheel.fm" in cfg.allowed_hosts
    # A public (port-less) host gets a matching https origin derived for it.
    assert "https://clickwheel.fm" in cfg.allowed_origins


def test_allowed_hosts_from_env(monkeypatch):
    monkeypatch.setenv("CLICKWHEEL_MCP_TRANSPORT", "http")
    monkeypatch.setenv("CLICKWHEEL_MCP_ALLOWED_HOSTS", "clickwheel.fm, alt.example")
    cfg = _resolve_transport([])
    assert "clickwheel.fm" in cfg.allowed_hosts
    assert "alt.example" in cfg.allowed_hosts


def test_explicit_allow_origin_flag(monkeypatch):
    monkeypatch.delenv("CLICKWHEEL_MCP_ALLOWED_ORIGINS", raising=False)
    cfg = _resolve_transport(
        [
            "serve",
            "--allowed-host",
            "clickwheel.fm",
            "--allow-origin",
            "https://claude.ai",
        ]
    )
    assert "https://claude.ai" in cfg.allowed_origins
    assert "https://clickwheel.fm" in cfg.allowed_origins
