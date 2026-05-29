# Project: clickwheel docs site

An industry-grade documentation site for clickwheel at **`docs.clickwheel.fm`**,
built docs-as-code with anti-staleness guarantees.

- **[TRACKER.md](TRACKER.md)** — phased task list (status, owner, blockers).
- **[DEFERRED.md](DEFERRED.md)** — explicitly parked / out-of-scope items.

## Goals

1. A real docs site for clickwheel (a Python CLI + optional MCP server), not just
   a README — discoverable, structured, and pleasant.
2. **Docs that can't silently rot.** Reference content is generated from source
   and drift-checked in CI; links are validated in CI; everything is docs-as-code
   (in-repo, PR-reviewed, auto-deployed).
3. One authoring workflow consistent with the sibling `rewind` project.

## Decisions (settled — don't re-litigate without new info)

- **Tool: Mintlify**, hosted, at `docs.clickwheel.fm`. Free for OSS, fastest to
  stand up, matches rewind's `docs-mintlify/` so authoring is consistent. Its
  intro page doubles as the landing — **no separate marketing site** (rewind has
  an Astro `www` because rewind.rest is a product; clickwheel is an OSS tool).
  Considered + rejected for now: Cloudflare Pages + Astro Starlight (more setup,
  only worth it to avoid a second SaaS — see DEFERRED).
- **Structure: Diátaxis** — Tutorial / How-to / Reference / Explanation, kept in
  separate sections (better for humans and AI assistants).
- **Subdomain `docs.clickwheel.fm`**, separate from the Access-gated MCP apex.
  Does not touch the tunnel / Access / favicon setup. Favicons are per-host; the
  docs site has its own and it does not affect the connector icon.
- **Source of truth**: the docs site becomes canonical for _user-facing_ docs;
  `README.md` shrinks to a blurb + link. In-repo `docs/` (architecture, mcp
  internals, releasing) stays for _contributors_.

## Architecture

```text
clickwheel repo
├── docs-mintlify/                 # the Mintlify site (docs-as-code)
│   ├── docs.json                  # nav (Diátaxis tabs/groups), theme, domain
│   ├── introduction.mdx           # landing/overview
│   ├── quickstart.mdx             # TUTORIAL
│   ├── guides/*.mdx               # HOW-TO (sync, playlists, plex, apple, scrobble, fix, remote-mcp)
│   ├── concepts/*.mdx             # EXPLANATION (architecture, single-tenant design)
│   ├── reference/
│   │   ├── cli.mdx                # GENERATED from the Typer app
│   │   ├── mcp-tools.mdx          # GENERATED from the FastMCP instance
│   │   └── configuration.mdx      # config.yaml / env vars
│   ├── logo/ + favicon.svg + styles.css
│   └── changelog.mdx
└── scripts/
    ├── gen-cli-reference.py       # Typer app  -> reference/cli.mdx
    └── gen-mcp-reference.py       # FastMCP     -> reference/mcp-tools.mdx
```

## Anti-staleness strategy (the point of "industry-grade")

Mirrors rewind's snapshot/drift pattern and clickwheel's existing
"Web Bundle Freshness" CI convention:

1. **Generated reference** — `cli.mdx` and `mcp-tools.mdx` are emitted by
   generators from the actual Typer commands + FastMCP tool definitions. They are
   committed, and a **"Docs Reference Freshness" CI job** regenerates them and
   fails if the committed copies differ. → reference can't drift from code.
2. **`mint validate` in CI** — broken links / nav references block merge.
3. **Auto-deploy** on merge to `main` via Mintlify's GitHub integration.
4. **Single source of truth** — README links to the site; no duplicated prose to
   drift.
5. **Git-derived "last updated"** (Mintlify native).

## Out of this project's scope

See [DEFERRED.md](DEFERRED.md). Notably: this does **not** include finishing the
remote-access round (launchd + connector live-test + merging #48) — that's its
own track, resumed after this.
