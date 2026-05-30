# Project: clickwheel docs site

An industry-grade documentation site for clickwheel at **`docs.clickwheel.fm`**,
built docs-as-code with anti-staleness guarantees.

- **[TRACKER.md](TRACKER.md)** — phased task list (status, owner, blockers).
- **[DEFERRED.md](DEFERRED.md)** — explicitly parked / out-of-scope items.

> **Status: PAUSED (2026-05-30).** Content, generators, and anti-rot CI are done
> and merged to `main` (they're host-agnostic). **Hosting tool changed: Mintlify
> → Astro Starlight on Cloudflare Pages** (see "Decisions" + the Mintlify
> post-mortem below). Resume = build the Starlight site, repoint the generators +
> CI from `docs-mintlify/` to it, deploy to Pages, README cutover.

## Goals

1. A real docs site for clickwheel (a Python CLI + optional MCP server), not just
   a README — discoverable, structured, and pleasant.
2. **Docs that can't silently rot.** Reference content is generated from source
   and drift-checked in CI; links are validated in CI; everything is docs-as-code
   (in-repo, PR-reviewed, auto-deployed).
3. One authoring workflow consistent with the sibling `rewind` project.

## Decisions (settled — don't re-litigate without new info)

- **Tool: Astro Starlight, self-hosted on Cloudflare Pages**, at
  `docs.clickwheel.fm`. (Superseded Mintlify — see the post-mortem below.)
  Rationale: free + self-serve with **no per-account site limits**; actively
  developed (not maintenance-mode); clean modern aesthetic; and maximally aligned
  with our stack — **Cloudflare's own developer docs run on Starlight, and Astro
  joined Cloudflare in Jan 2026**. Same Astro + `wrangler pages deploy` pattern
  rewind uses for its `www` site.
- **Structure: Diátaxis** — Tutorial / How-to / Reference / Explanation, kept in
  separate sections (better for humans and AI assistants).
- **Subdomain `docs.clickwheel.fm`**, separate from the Access-gated MCP apex.
  Does not touch the tunnel / Access / favicon setup. Favicons are per-host; the
  docs site has its own and it does not affect the connector icon.
- **Source of truth**: the docs site becomes canonical for _user-facing_ docs;
  `README.md` shrinks to a blurb + link. In-repo `docs/` (architecture, mcp
  internals, releasing) stays for _contributors_.

## Mintlify post-mortem (why we left, so we don't retry it)

We scaffolded a Mintlify site (`docs-mintlify/`, merged in #52) and tried to host
it. It's a dead end for clickwheel, for cited reasons:

- **Free (Hobby) tier = one self-serve hosted site, and it's already used by
  `rewind`.** A second site is **sales-gated**: the dashboard's "new site"
  literally opens a `mailto:gtm@mintlify.com` "new deployment request." This
  limit is **not documented** on the [pricing page](https://www.mintlify.com/pricing)
  or [Deployments doc](https://www.mintlify.com/docs/deploy/deployments) — the
  dashboard behavior is the only signal. A second site means **Pro (~$250/mo)**.
- **GitHub App linkage:** one Mintlify GitHub-App install maps to one Mintlify
  account; the `rewind` account (`dugan.pat@`) owns it, so a separate
  `dugan.pat+clickwheel@` account couldn't connect `pdugan20/clickwheel` at all.
- Not worth $250/mo for an OSS tool's docs. (Aesthetic note: also didn't want
  Material-style design, and Material-for-MkDocs entered maintenance mode in
  early 2026 — both ruled out as alternatives.)

The `docs-mintlify/` content + generators + CI stay on `main` for now (they're
the source we'll convert to Starlight); the CI link check uses `mint broken-links`
locally and needs no Mintlify account, so it's still green.

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
2. **Link checking in CI** — broken links / nav references block merge.
3. **Auto-deploy** on merge to `main` (Cloudflare Pages, via `wrangler` in CI or
   the Pages GitHub integration).
4. **Single source of truth** — README links to the site; no duplicated prose to
   drift.
5. **Git-derived "last updated"** timestamps.

## Out of this project's scope

See [DEFERRED.md](DEFERRED.md). Notably: this does **not** include finishing the
remote-access round (launchd + connector live-test + merging #48) — that's its
own track, resumed after this.
