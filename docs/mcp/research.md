# MCP research notes

Findings from web research on current MCP best practices, SDK status, and Claude Code integration. Captured 2026-05-06. Update if any of this drifts.

## Python SDK choice: `mcp` (official) with FastMCP

The official `mcp` SDK (`pip install mcp`) ships FastMCP-style decorators under `mcp.server.fastmcp`. This is the canonical path — what the official quickstart uses, what most servers ship today.

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("clickwheel")

@mcp.tool()
async def list_artists(limit: int = 100) -> list[dict]:
    """List all artists in the indexed library."""
    ...

def main() -> None:
    mcp.run(transport="stdio")
```

There is also a standalone `fastmcp` package (FastMCP 3.0, Jan 2026) which is more featureful but adds a second dependency surface. **Decision: use the official `mcp` SDK.** We don't need FastMCP 3.0's extras (auth, deployment helpers, etc.) for a local stdio server. If we ever do, swapping is mechanical.

Pin: `mcp>=1.2` (the floor cited as "production-ready"). Recent versions are 1.27.x as of April 2026.

## MCP spec features worth knowing (2025-06-18 spec)

**Tools** — what we'll lean on for everything. `outputSchema` (JSON Schema for return values) is now supported and lets clients validate; FastMCP infers it from type hints if we return Pydantic models or typed dicts.

**Structured tool output** — return structured data (not just text). FastMCP handles this when the return type is a serializable object. Cleaner than stuffing JSON into a string.

**Elicitation** (multi-turn human-in-the-loop) — server can mid-call ask the client to gather more input from the user. Two modes: form (structured prompt with JSON schema) and URL (redirect for OAuth-y flows). **Use case for us:** mutation tools in Phase 3 (`delete_playlist`, `sync_to_ipod`) — server elicits a confirmation rather than the LLM guessing whether `confirm=true` is safe to pass.

**Resource templates / `resource_link`** — tools can return links to URIs instead of inlining everything. We're skipping resources in v1 per design, so we won't use this yet, but worth keeping in mind for v3.

**Security: Resource Indicators (RFC 8707)** — clients are required to implement these to prevent token misuse. Not relevant for our local stdio server (no OAuth), but flagged.

## Claude Code scope precedence

Three levels, precedence: **local > project > user > plugin > connectors**.

- **Local**: `~/.claude.json` keyed by project path. Private to user.
- **Project**: `.mcp.json` at repo root. Shared via VCS.
- **User**: `~/.claude.json` global section. Across all projects.

For clickwheel users: **user scope is the right answer**. It's a personal tool, not a team-shared MCP, and they want it available wherever they're chatting with Claude. We'll document `claude mcp add --scope user` as the install path.

**Known bug (April 2026, Claude Code 2.1.122):** `--scope user` writes the entry but it's invisible to `claude mcp list` and the loader. Workaround: edit `~/.claude.json` manually or use project scope. **Action item:** verify this bug is fixed before publishing install instructions; if not, document the workaround.

## Tool naming conventions

Empirical analysis of real MCP servers:

- ~90% of tools use snake_case
- ~95% are multi-word
- <1% use camelCase

Two valid patterns:

- **verb_noun** (`get_alerts`, `fetch_forecast`) — what the official quickstart uses, reads naturally
- **noun_verb** (`github_issue_create`, `github_issue_list`) — AWS recommendation; clusters related tools when listed alphabetically

**Decision: verb_noun.** Matches official examples (which is what the model has seen most), reads naturally in tool descriptions. We'll use prefixes (`playlist_*`, `ipod_*`) to cluster where helpful.

Other guidance applied:

- One tool = one specific action; no swiss-army-knife tools
- Descriptions explain _purpose, return value, and when to use_
- Avoid jargon, version numbers, abbreviations in names
- Cap server at ~50 tools (we'll have ~15)

## Transport

**stdio** for local servers. HTTP/SSE exists but is for remote/multi-client setups. No reason to use it here.

## Sources

- [Official Python SDK (modelcontextprotocol/python-sdk)](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Python SDK on PyPI](https://pypi.org/project/mcp/)
- [Build an MCP server (official tutorial)](https://modelcontextprotocol.io/docs/develop/build-server)
- [MCP 2025-06-18 spec update — elicitation, structured content, OAuth](https://blogs.cisco.com/developer/whats-new-in-mcp-elicitation-structured-content-and-oauth-enhancements)
- [Elicitation spec](https://modelcontextprotocol.io/specification/draft/client/elicitation)
- [Claude Code settings docs](https://code.claude.com/docs/en/settings)
- [`claude mcp add --scope user` bug report](https://github.com/anthropics/claude-code/issues/54803)
- [MCP server naming conventions analysis](https://zazencodes.com/blog/mcp-server-naming-conventions)
- [AWS MCP tool organization guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/mcp-strategies/mcp-tool-strategy-organization.html)
