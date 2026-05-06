# MCP integration project

Tracks the work to add an MCP server to clickwheel so Claude Code (and other MCP clients) can query and operate on the user's music library and iPod conversationally.

**Status:** Phase 0 complete (research + design). Awaiting design review before code.

## Documents

- [`research.md`](research.md) — Findings from web research on the Python MCP SDK, spec features, Claude Code integration, naming conventions. Sources cited.
- [`design.md`](design.md) — Locked design: package layout, tool surface (read + mutation), error model, lifecycle.
- [`tracker.md`](tracker.md) — Live phased task list. Update statuses as work progresses.
- [`test-plan.md`](test-plan.md) — Manual iPod test scenarios for Phase 5.

## TL;DR

Adding `clickwheel/mcp/` — a stdio MCP server using the official `mcp` Python SDK with FastMCP-style decorators. Ships as a `[mcp]` extra and a `clickwheel-mcp` console script. Phase 1 is a CLI refactor that extracts pure logic from `cli.py` into `actions.py` (valuable on its own); Phase 2 builds 10 read-only tools on top; Phase 3 adds 7 mutation tools using MCP's elicitation feature for confirmations. Final phase is manual iPod testing.

## Why now

Three concrete wins over CLI + `--json` flags: typed tool schemas Claude discovers automatically, stateful process (DB connection + scan cache held open), structured progress streaming during long ops. None individually killer; together they're enough to justify the work — especially because the prerequisite refactor improves the CLI regardless.

## Why not now

If conversational queries against the library don't sound appealing in practice, skip MCP and add `--json` flags to existing CLI commands instead. ~30 lines, done.
