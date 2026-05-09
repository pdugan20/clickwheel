# clickwheel web bundles

Interactive UI for the clickwheel MCP server. Each bundle here is a React 19 +
TypeScript app that gets built into a single self-contained HTML file via
[`vite-plugin-singlefile`](https://github.com/richardtallent/vite-plugin-singlefile),
then inlined into [`clickwheel/mcp/_ui_bundles.py`](../clickwheel/mcp/_ui_bundles.py)
so the Python MCP server can serve it as a [`ui://` resource](https://modelcontextprotocol.io/extensions/apps/overview)
to compatible hosts (Claude Desktop, Claude.ai, VS Code Copilot, Goose).

The Python module is committed to the repo, so `pip install clickwheel[mcp]`
works without a Node toolchain. CI runs the rebuild and fails if the committed
bundle drifts from the source.

## Layout

```text
web/
  package.json              # React 19, Vite 5, ext-apps SDK
  vite.config.ts            # used by the inline-bundles script
  eslint.config.js          # flat-config: tseslint + react + react-hooks
  tsconfig.json
  components/               # reusable UI primitives (CapacityBar, StatGrid, ...)
  lib/                      # shared style helpers (rootStyle, ...)
  <name>.tsx                # React entry per bundle (uses useApp + useHostStyles)
  <name>.html               # Vite entry HTML — Vite picks up the <script type=module>
  <name>.fixtures.ts        # workbench preview data (one or more samples)
  workbench/                # local Vite dev server for design iteration
  scripts/inline_bundles.mjs # build all entries → clickwheel/mcp/_ui_bundles.py
```

## Workflow

```bash
make dev-web              # opens http://localhost:5174/workbench/ — HMR
                          # while you edit bundles + components
make build-web            # rebuild bundles + regenerate the Python module
make lint-web             # eslint --max-warnings=0 + tsc --noEmit
make format-web           # prettier --write
```

The workbench mounts each bundle's HTML entry in an iframe and plays the host
side of the [MCP Apps](https://github.com/modelcontextprotocol/ext-apps) protocol
against it: responds to `ui/initialize`, posts `ui/notifications/tool-result`
with the selected fixture's `structuredContent`. Same connect/initialize/render
path Claude Desktop will run, just with mock data.

## Adding a new bundle

1. **Source files.** Add `<name>.html`, `<name>.tsx`, `<name>.fixtures.ts`.
   Use an existing bundle (`ipod-capacity.tsx`) as a template — the entry
   should call `useApp`, `useHostStyles`, and react to `app.ontoolresult`.

2. **Workbench registry.** Append an entry to
   [`workbench/registry.ts`](workbench/registry.ts) so the sidebar lists it
   and the iframe can load `/<name>.html`.

3. **Build.** `make build-web` to regenerate `_ui_bundles.py` with the new
   `<NAME>_HTML` constant + an entry in `UI_BUNDLES`.

4. **Server-side wiring.** In [`clickwheel/mcp/ui_resources.py`](../clickwheel/mcp/ui_resources.py)
   add a `register_ui_resource(...)` call pointing at `ui://clickwheel/<name>.html`
   and the corresponding `*_HTML` import. In the matching tool, add
   `meta=ui_tool_meta(URI)` to the `@mcp.tool` decorator.

5. **Test.** Restart Claude Desktop (it pre-fetches `ui://` resources at
   connect time, so a hot reload won't pick up the new bundle bytes), then
   trigger the tool from a chat.

## Node version

Pinned via [`.nvmrc`](../.nvmrc) at the repo root. CI honors it via
`actions/setup-node@v5` with `node-version-file`. Run `nvm use` in the repo
root before `make build-web` so your local builds match CI's bytes.

## Lint stack

- **TypeScript** strict mode (`tsc --noEmit`) — caught by `npm run typecheck`
  and the `tsc (web bundles)` pre-commit hook.
- **ESLint 9** flat config — `typescript-eslint` recommended +
  `eslint-plugin-react` + `eslint-plugin-react-hooks` + `eslint-config-prettier`.
- **Prettier 3** — single quote, trailing comma, 88 char line. Format on
  save with the `Prettier` extension or `make format-web`.

All three run in pre-commit (`.pre-commit-config.yaml`) and in CI
(`.github/workflows/ci.yml`).
