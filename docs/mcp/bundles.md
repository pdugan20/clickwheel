# MCP UI bundles

Contributor-facing notes for the MCP Apps iframes clickwheel ships. The end-user-facing summary (which tools have bundles, what they look like) lives in [`README.md`](README.md#inline-ui-bundles); this page covers how they're built, edited, and added.

## Build flow

Bundles live under [`web/`](../../web/) (React 19 + Vite, TypeScript). Each bundle is a `web/<name>.tsx` entry with a matching `<name>.html` shell.

`web/scripts/inline_bundles.mjs` builds every `web/*.html` entry via Vite's programmatic API and `vite-plugin-singlefile`, then concatenates the resulting HTML into one Python module at [`clickwheel/mcp/_ui_bundles.py`](../../clickwheel/mcp/_ui_bundles.py). That generated module is checked in so `pip install clickwheel[mcp]` works without a Node toolchain — users don't need Vite installed to run the server.

CI rebuilds the bundles and fails if the checked-in `_ui_bundles.py` drifts from `web/`, so don't forget `make build-web` before committing a bundle change. The script also skips `*-showcase.html` entries so design-iteration bundles (workbench-only) don't bloat the inlined module.

## Editing a bundle

```bash
make dev-web        # http://localhost:5174/workbench/ — live preview with fixtures
# edit web/<bundle>.tsx, components/, lib/...
make build-web      # rebuild bundles + regenerate the Python module
make lint-web       # eslint + tsc
```

The workbench plays the host side of the MCP Apps protocol against your bundle: responds to `ui/initialize`, pushes mock `tool-result` notifications carrying fixture data, optionally simulates `state://clickwheel/sync-progress` for live-progress bundles. Vite HMR re-mounts the bundle on every save.

Fixtures live in `web/<bundle>.fixtures.ts` — the sidebar lets you switch between them. Tweak / add fixtures freely; they're workbench-only.

## Adding a new bundle

1. Drop `web/<name>.html`, `web/<name>.tsx`, `web/<name>.fixtures.ts`. Use an existing bundle as a template — `web/library-stats.tsx` is the simplest read-only example.
2. Register it in `web/workbench/registry.ts` so the workbench sidebar lists it.
3. Run `make build-web` — `_ui_bundles.py` regenerates with a new `<NAME>_HTML` constant.
4. In `clickwheel/mcp/ui_resources.py`, add a `register_ui_resource(...)` call pointing at the new constant + assign a `ui://clickwheel/<name>.html` URI.
5. In the tool you want to bind it to, add `meta=ui_tool_meta(URI)` to the `@mcp.tool` decorator.
6. Test in the workbench (`make dev-web`), then in a real Claude Desktop call after `make build-web` + restart.

For workbench-only design-iteration views (palette comparisons, layout exploration), use the `-showcase.html` filename suffix — `inline_bundles.mjs` will skip them so they don't ride along into production.

## Dev install (clone-based)

If you're hacking on clickwheel from a clone in `~/Documents/`, Claude Desktop's sandbox will refuse to read the in-tree venv's `pyvenv.cfg`: macOS applies a `com.apple.provenance` xattr to files in `Documents`, and Desktop's sandbox rejects sibling-file reads on them. Two ways around it:

- Install with `pipx install --editable .` so the venv lives in `~/.local/pipx/` (outside `Documents`), or
- Grant Claude Desktop access to your `Documents` folder under System Settings → Privacy & Security → Files & Folders.

Claude Code is unaffected.
