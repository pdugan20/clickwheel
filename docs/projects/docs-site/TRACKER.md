# Docs site — tracker

Phased task list. See [README.md](README.md) for the plan/decisions and
[DEFERRED.md](DEFERRED.md) for parked items.

**Legend** — Status: ✅ done · 🚧 in progress · ⬜ not started.
Owner: 🤖 in-repo (code/docs) · 🧑 owner-owned (Mintlify account / DNS).
**Discipline:** every not-started task names its blocker/reason; no silent
deferrals (parked items go in DEFERRED.md with a reason).

---

## Phase 0 — Plan ✅

| ✓   | Owner | Task                                                        | Notes |
| --- | ----- | ----------------------------------------------------------- | ----- |
| ✅  | 🤖    | Research (rewind model, Diátaxis, docs-as-code, anti-rot)   | —     |
| ✅  | 🤖    | Plan + tracker + deferred docs in `docs/projects/docs-site` | —     |

---

## Phase 1 — Scaffold + narrative content 🤖

Stand up the Mintlify site skeleton and write the hand-authored (Diátaxis)
pages, porting from the existing `README.md` + `docs/`.

| ✓   | Owner | Task                                                                                                 | Blocked by / reason |
| --- | ----- | ---------------------------------------------------------------------------------------------------- | ------------------- |
| ⬜  | 🤖    | `docs-mintlify/docs.json` — nav (Diátaxis tabs/groups), theme, colors, `docs.clickwheel.fm`          | —                   |
| ⬜  | 🤖    | Logo + `favicon.svg` + `styles.css` (reuse the clickwheel mark)                                      | —                   |
| ⬜  | 🤖    | `introduction.mdx` — overview / landing                                                              | —                   |
| ⬜  | 🤖    | `quickstart.mdx` — TUTORIAL (install → scan → select → sync → eject)                                 | —                   |
| ⬜  | 🤖    | `guides/` — HOW-TO: sync-to-ipod, playlists, plex, apple-music, scrobbling, fix-metadata, remote-mcp | —                   |
| ⬜  | 🤖    | `concepts/` — EXPLANATION: architecture, single-tenant/Mac-as-truth, FLAC exclusion                  | —                   |
| ⬜  | 🤖    | `reference/configuration.mdx` — config.yaml + env vars                                               | —                   |
| ⬜  | 🤖    | `changelog.mdx` (link to / mirror CHANGELOG)                                                         | —                   |

**Acceptance:** `mint dev` renders the full nav with all narrative pages.

---

## Phase 2 — Generated reference + anti-rot CI 🤖

The anti-staleness core. Reference is generated from source and drift-checked.

| ✓   | Owner | Task                                                                                            | Blocked by / reason |
| --- | ----- | ----------------------------------------------------------------------------------------------- | ------------------- |
| ⬜  | 🤖    | `scripts/gen-cli-reference.py` — introspect the Typer app → `reference/cli.mdx`                 | —                   |
| ⬜  | 🤖    | `scripts/gen-mcp-reference.py` — introspect FastMCP (37 tools) → `reference/mcp-tools.mdx`      | —                   |
| ⬜  | 🤖    | Commit the generated MDX; `make docs-reference` target                                          | —                   |
| ⬜  | 🤖    | CI **"Docs Reference Freshness"** job — regenerate + fail on diff (mirror Web Bundle Freshness) | —                   |
| ⬜  | 🤖    | CI **`mint validate`** (broken links / nav) job                                                 | —                   |
| ⬜  | 🤖    | `make docs` (mint dev) + `make docs-validate` targets; CONTRIBUTING note                        | —                   |

**Acceptance:** editing a CLI command or MCP tool without regenerating fails CI; `mint validate` passes.

---

## Phase 3 — Hosting / deploy 🧑

| ✓   | Owner | Task                                                                        | Blocked by / reason    |
| --- | ----- | --------------------------------------------------------------------------- | ---------------------- |
| ⬜  | 🧑    | Create Mintlify project (free OSS), connect the `pdugan20/clickwheel` repo  | needs Mintlify account |
| ⬜  | 🧑    | Point `docs.clickwheel.fm` CNAME per Mintlify's custom-domain instructions  | after project created  |
| ⬜  | 🧑    | Set logo/colors/theme in the Mintlify dashboard if not fully in `docs.json` | after project created  |
| ⬜  | 🧑    | Confirm auto-deploy on merge to `main` works                                | after connect          |

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
