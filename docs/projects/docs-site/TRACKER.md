# Docs site — tracker

Phased task list. See [README.md](README.md) for the plan/decisions and
[DEFERRED.md](DEFERRED.md) for parked items.

**Legend** — Status: ✅ done · 🚧 in progress · ⬜ not started.
Owner: 🤖 in-repo (code/docs) · 🧑 owner-owned (Mintlify account / DNS).
**Discipline:** every not-started task names its blocker/reason; no silent
deferrals (parked items go in DEFERRED.md with a reason).

**Where we are: PAUSED (2026-05-30), holding on Mintlify.** Phases 0–2 merged to
`main` (#52) — all Mintlify content + the generated CLI/MCP reference + anti-rot
CI. **Hosting is blocked:** Mintlify's free tier allows one self-serve site
(rewind has it) and a second is sales-gated, so **we emailed `gtm@mintlify.com`
about a free/OSS second site and are waiting** (see [README.md](README.md)). **No
tool change is decided** — Starlight/MkDocs are researched fallbacks only if
Mintlify declines. The content/generators/CI stay green on `main`.

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

## Phase 3 — Host the site 🧑 — PAUSED (waiting on Mintlify)

The decision point. **Blocked on Mintlify's reply** to the `gtm@mintlify.com`
email about a free/OSS second site.

| ✓   | Owner | Task                                                                                                                                   | Blocked by / reason          |
| --- | ----- | -------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- |
| ⬜  | 🧑    | Mintlify reply re: free second site for OSS                                                                                            | waiting on Mintlify          |
| ⬜  | 🧑    | **If yes** → connect `pdugan20/clickwheel` (monorepo subdir `/docs-mintlify`) under the `dugan.pat@` account; add `docs.clickwheel.fm` | after reply                  |
| ⬜  | 🤖🧑  | **If no** → choose a fallback (Starlight on Pages / MkDocs — _not yet decided_), then build + deploy it                                | after reply (fresh decision) |

**Acceptance:** the site is hosted at `https://docs.clickwheel.fm`.

---

## Phase 4 — Cutover + verify 🤖🧑 — PAUSED

| ✓   | Owner | Task                                                                 | Blocked by / reason |
| --- | ----- | -------------------------------------------------------------------- | ------------------- |
| ⬜  | 🤖    | Shrink `README.md` to a blurb + link to `docs.clickwheel.fm`         | after site is live  |
| ⬜  | 🧑    | Spot-check rendered site (nav, search, mobile, links, generated ref) | after deploy        |

**Acceptance:** README points to the live site; nav + generated reference correct.

---

## Then

Resume the **remote-access round** (separate track): launchd persistence →
connector live-test (phone + iPod) → merge #48. Tracked in
`docs/mcp/remote-mobile-access-tracker.md`.
