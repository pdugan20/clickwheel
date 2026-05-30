# Docs site — tracker

Phased task list. See [README.md](README.md) for the plan/decisions and
[DEFERRED.md](DEFERRED.md) for parked items.

**Legend** — Status: ✅ done · 🚧 in progress · ⬜ not started.
Owner: 🤖 in-repo (code/docs) · 🧑 owner-owned (Mintlify account / DNS).
**Discipline:** every not-started task names its blocker/reason; no silent
deferrals (parked items go in DEFERRED.md with a reason).

**Where we are:** Phases 0–2 **merged to `main`** (#52). The full Mintlify site
is in-repo (`docs-mintlify/`) with all narrative pages, and the CLI + MCP
reference is generated from source with anti-drift CI. Remaining is owner-owned:
stand up the Mintlify project + `docs.clickwheel.fm` (Phase 3), then cutover
(Phase 4).

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

## Phase 3 — Hosting / deploy 🧑

| ✓   | Owner | Task                                                                       | Blocked by / reason    |
| --- | ----- | -------------------------------------------------------------------------- | ---------------------- |
| ⬜  | 🧑    | Create Mintlify project (free OSS), connect the `pdugan20/clickwheel` repo | needs Mintlify account |
| ⬜  | 🧑    | Point `docs.clickwheel.fm` CNAME per Mintlify's custom-domain instructions | after project created  |
| ⬜  | 🧑    | Set logo/colors/theme in the dashboard if not fully driven by `docs.json`  | after project created  |
| ⬜  | 🧑    | Confirm auto-deploy on merge to `main`                                     | after connect          |

**Acceptance:** `https://docs.clickwheel.fm` serves the site and redeploys on merge.

---

## Phase 4 — Cutover + verify 🤖🧑

| ✓   | Owner | Task                                                                 | Blocked by / reason |
| --- | ----- | -------------------------------------------------------------------- | ------------------- |
| ⬜  | 🤖    | Shrink `README.md` to a blurb + link to `docs.clickwheel.fm`         | after site is live  |
| ⬜  | 🤖    | Cross-link in-repo `docs/` ↔ site where useful                       | —                   |
| ⬜  | 🧑    | Spot-check rendered site (nav, search, mobile, links, generated ref) | after deploy        |

**Acceptance:** README points to the live site; nav + search + generated reference all correct.

---

## Then

Resume the **remote-access round** (separate track): launchd persistence →
connector live-test (phone + iPod) → merge #48. Tracked in
`docs/mcp/remote-mobile-access-tracker.md`.
