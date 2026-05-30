# Docs site — tracker

Phased task list. See [README.md](README.md) for the plan/decisions and
[DEFERRED.md](DEFERRED.md) for parked items.

**Legend** — Status: ✅ done · 🚧 in progress · ⬜ not started.
Owner: 🤖 in-repo (code/docs) · 🧑 owner-owned (Mintlify account / DNS).
**Discipline:** every not-started task names its blocker/reason; no silent
deferrals (parked items go in DEFERRED.md with a reason).

**Where we are: PAUSED (2026-05-30).** Phases 0–2 merged to `main` (#52) — all
narrative content + the generated CLI/MCP reference + anti-rot CI. **The hosting
tool changed from Mintlify to Astro Starlight on Cloudflare Pages** (Mintlify
free tier is one self-serve site, already used by rewind; see the post-mortem in
[README.md](README.md)). The content/generators/CI are **host-agnostic** and stay
green on `main`. Remaining work is re-scoped below for Starlight; **paused until
we pick it back up.**

---

## Phase 0 — Plan ✅

| ✓   | Owner | Task                                                        |
| --- | ----- | ----------------------------------------------------------- |
| ✅  | 🤖    | Research (rewind model, Diátaxis, docs-as-code, anti-rot)   |
| ✅  | 🤖    | Plan + tracker + deferred docs in `docs/projects/docs-site` |

---

## Phase 1 — Scaffold + narrative content ✅

| ✓   | Owner | Task                                                                                |
| --- | ----- | ----------------------------------------------------------------------------------- |
| ✅  | 🤖    | `docs.json` — nav (Guides + Reference tabs, Diátaxis groups), theme, colors         |
| ✅  | 🤖    | Logo + `favicon.svg` (clickwheel mark)                                              |
| ✅  | 🤖    | `introduction.mdx` — overview / landing                                             |
| ✅  | 🤖    | `quickstart.mdx` — TUTORIAL                                                         |
| ✅  | 🤖    | `guides/` — sync-to-ipod, playlists, plex, apple-music, scrobbling, fix, remote-mcp |
| ✅  | 🤖    | `concepts/` — architecture, design, mcp-server                                      |
| ✅  | 🤖    | `reference/configuration.mdx`                                                       |
| ✅  | 🤖    | `changelog.mdx`                                                                     |

**Acceptance:** met locally — `mint broken-links` passes; nav resolves all pages.

---

## Phase 2 — Generated reference + anti-rot CI ✅

| ✓   | Owner | Task                                                                             |
| --- | ----- | -------------------------------------------------------------------------------- |
| ✅  | 🤖    | `scripts/gen-cli-reference.py` → `reference/cli.mdx` (15 commands)               |
| ✅  | 🤖    | `scripts/gen-mcp-reference.py` → `reference/mcp-tools.mdx` (37 tools, by module) |
| ✅  | 🤖    | CI **"Docs Reference Freshness"** — regenerate + fail on drift                   |
| ✅  | 🤖    | CI **"Docs Links"** — `mint broken-links`                                        |
| ✅  | 🤖    | `make docs-reference` / `docs` / `docs-links` + CONTRIBUTING note                |

**Acceptance:** met — generators idempotent; editing a command/tool without regenerating fails CI; links pass.

---

## Phase 3 — Build Starlight site (re-scoped from Mintlify) 🤖 — PAUSED

| ✓   | Owner | Task                                                                                                       | Blocked by / reason |
| --- | ----- | ---------------------------------------------------------------------------------------------------------- | ------------------- |
| ⬜  | 🤖    | Stand up Astro Starlight project in-repo (`docs-site/`); Astro config sidebar = Diátaxis nav               | paused              |
| ⬜  | 🤖    | Port the 13 pages from `docs-mintlify/` (Mintlify components → Starlight equivalents)                      | paused              |
| ⬜  | 🤖    | Repoint `gen-cli-reference.py` / `gen-mcp-reference.py` output at the Starlight content dir                | paused              |
| ⬜  | 🤖    | Repoint CI: keep "Docs Reference Freshness"; replace `mint broken-links` with a Starlight/Astro link check | paused              |
| ⬜  | 🤖    | Remove the dead `docs-mintlify/` scaffold once Starlight replaces it                                       | paused              |

**Acceptance:** `astro build` succeeds; nav + generated reference render; link check passes.

---

## Phase 4 — Deploy + cutover 🤖🧑 — PAUSED

| ✓   | Owner | Task                                                                           | Blocked by / reason    |
| --- | ----- | ------------------------------------------------------------------------------ | ---------------------- |
| ⬜  | 🤖🧑  | Create Cloudflare Pages project; `wrangler pages deploy` (one command)         | after Starlight builds |
| ⬜  | 🧑    | Add `docs.clickwheel.fm` custom domain in Cloudflare Pages (DNS already on CF) | after Pages project    |
| ⬜  | 🤖    | Shrink `README.md` to a blurb + link to `docs.clickwheel.fm`                   | after site is live     |
| ⬜  | 🧑    | Spot-check rendered site (nav, search, mobile, links, generated ref)           | after deploy           |

**Acceptance:** `https://docs.clickwheel.fm` serves the Starlight site; README points to it.

---

## Then

Resume the **remote-access round** (separate track): launchd persistence →
connector live-test (phone + iPod) → merge #48. Tracked in
`docs/mcp/remote-mobile-access-tracker.md`.
