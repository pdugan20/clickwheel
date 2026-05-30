# Remote mobile access — tracker

Phased, checkable task list for getting clickwheel reachable from the Claude
iOS app. The _why_ and design rationale live in the brief
([`remote-mobile-access.md`](remote-mobile-access.md)); the owner-side runbook
(commands + dashboard clicks) is in
[`deploy/README.md`](deploy/README.md). This is the _what, in order, and what's
blocking it_.

**Legend** — Status: ✅ done · 🚧 in progress · ⬜ not started.
Owner: 🤖 in-repo (code/docs, doable here) · 🧑 owner-owned (your Mac /
Cloudflare account / devices).
**Discipline:** every not-started task names its blocker/reason — no silent
deferrals. "—" means nothing blocks it but the owner's time.

**Where we are: WORKING.** #48 merged, **0.16.0 published to PyPI** (#53),
**launchd persistence is live** (server + tunnel run as LaunchAgents), and the
**Claude connector authenticates and works** — verified on web (`library_stats`
returned the real library). The auth path that finally worked: self-hosted
Access app + **Managed OAuth** enabled + `https://claude.ai/api/mcp/auth_callback`
in Allowed redirect URIs (see [`deploy/README.md`](deploy/README.md) §3 for the
full story incl. the `ofid_` cheat-sheet). Favicon is live; Google cache ~1 day.
**Remaining:** verify on phone + iPod docked/undocked (user), and the keep-awake
decision. The big unknown — can the connector auth through Cloudflare Access? —
is now a definitive **yes**.

---

## Phase 0 — In-repo foundation ✅

| ✓   | Owner | Task                                                                                                                                     | Blocked by / reason |
| --- | ----- | ---------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| ✅  | 🤖    | Streamable HTTP transport: `clickwheel-mcp serve --http` (+ env vars), localhost-bound, **stdio preserved** (`clickwheel/mcp/server.py`) | —                   |
| ✅  | 🤖    | Bump `[mcp]` extra pin to `mcp>=1.9`                                                                                                     | —                   |
| ✅  | 🤖    | Unit tests for transport/arg/env resolution (`tests/test_mcp_transport.py`)                                                              | —                   |
| ✅  | 🤖    | Local smoke test: HTTP `initialize` + `tools/list` (37 tools) + live `library_stats`                                                     | —                   |
| ✅  | 🤖    | Docs: brief revised, `CLAUDE.md` rule #12 corrected, README documents `serve --http`                                                     | —                   |

**Acceptance:** met — MCP client over `http://127.0.0.1:8000/mcp` lists tools and returns real data.

---

## Phase 1 — Cloudflare Tunnel ✅

`clickwheel.fm` now reaches the local MCP server through a named tunnel. Config:
[`deploy/cloudflared-config.example.yml`](deploy/cloudflared-config.example.yml).
Tunnel id `0c2c25a5-…`; config at `~/.cloudflared/config.yml`.

| ✓   | Owner | Task                                                                  | Blocked by / reason             |
| --- | ----- | --------------------------------------------------------------------- | ------------------------------- |
| ✅  | 🧑    | `cloudflared` installed (was already present, 2026.5.0)               | —                               |
| ✅  | 🧑    | `cloudflared tunnel login` + `tunnel create clickwheel`               | —                               |
| ✅  | 🧑    | Ingress `clickwheel.fm` → `http://127.0.0.1:8000`                     | —                               |
| ✅  | 🧑    | Deleted the stale Namecheap parking `A` record, then `route dns`      | apex A record blocked the CNAME |
| ✅  | 🤖    | Bring server + tunnel up; confirm `https://clickwheel.fm/mcp` reaches | —                               |

**Acceptance:** met — full MCP handshake over `https://clickwheel.fm/mcp` (37 tools + `library_stats`). Required a code fix: allowlist the public Host (`--allowed-host`) or the SDK returns 421.

---

## Phase 2 — Auth: Cloudflare Access (self-hosted app) ✅

**Correction to the brief:** a plain **self-hosted Access application** is all
that's needed — Cloudflare Access natively handles the MCP OAuth flow. No
"Access for SaaS / OIDC" app, no Claude redirect URL, no client ID/secret. We
verified Cloudflare serves the OAuth challenge:
`www-authenticate: Cloudflare-Access resource_metadata=".../.well-known/cloudflare-access-protected-resource/mcp"`,
and that metadata returns `authorization_servers: [<team>.cloudflareaccess.com]`.
Team domain: `sparkling-violet-bfb4.cloudflareaccess.com`. Steps:
[`deploy/README.md`](deploy/README.md) §3.

| ✓   | Owner | Task                                                                | Blocked by / reason |
| --- | ----- | ------------------------------------------------------------------- | ------------------- |
| ✅  | 🧑    | Enable Zero Trust (Free plan)                                       | —                   |
| ✅  | 🧑    | Self-hosted Access application over `clickwheel.fm` (whole host)    | —                   |
| ✅  | 🧑    | Policy `Only me`: Allow, Emails = `dugan.pat@gmail.com`             | —                   |
| ✅  | 🧑    | Identity = built-in One-time PIN (email code); no external IdP      | —                   |
| ✅  | 🤖    | Verify gating: `/`, `/mcp` now 302 → Access login; MCP OAuth served | —                   |

**Acceptance:** met — unauthenticated requests bounce to the Cloudflare Access login, and the MCP OAuth discovery metadata is served publicly so the connector can authenticate. (favicon paths are also gated for now — opened up in Phase 3.)

---

## Phase 3 — Favicon / connector icon 🤖🧑

The piece you asked for — a domain favicon so the connector shows the
clickwheel mark, the way rewind's does.

> **Favicon art is FINAL** — `clickwheel/mcp/assets/favicon.svg`, served as
> `/favicon.svg` + rasterized `/favicon.ico` + PNGs. Regenerate rasters with
> `./scripts/generate-favicon.sh` if the SVG changes. The go-public steps below
> are now unblocked.
>
> **Approach (simplified):** serve the favicon from the existing MCP HTTP
> endpoint (already built) + one Cloudflare Access **bypass** so Google's
> crawler reaches it unauthenticated. We did NOT replicate rewind's edge-Worker
> (`apex-worker`) — unnecessary here; once Google caches the icon it's sticky.

**Confirmed mechanism (not the MCP `icons` field):** Claude renders the
connector-list icon from Google's favicon service, keyed off the connector
URL's domain — `https://www.google.com/s2/favicons?domain=<domain>&sz=32`
(e.g. `rewind.rest`, `craft.do`, `figma.com`). For us that's
`domain=clickwheel.fm`. The MCP `icons=[SERVER_ICON]` field we ship is
_separate_ (server identity in the handshake) and does **not** drive the
connector-list icon — so this favicon work is genuinely required.

**Baseline (verified 2026-05-28):** `s2/favicons?domain=clickwheel.fm` returns
the **default globe** — byte-identical (same md5) to a nonexistent domain.
`rewind.rest`/`craft.do`/`figma.com` return distinct real PNGs.

**Why this is clickwheel-specific (rewind got it free):** rewind's MCP server
runs on **Cloudflare Workers with `workers-oauth-provider`**, which gates only
the MCP/OAuth routes — its favicon is public by default. clickwheel is **tunnel
→ Mac behind Cloudflare Access**, which gates the _entire_ hostname — hence the
explicit Access **bypass** below.

| ✓   | Owner | Task                                                                                                                                                              | Blocked by / reason      |
| --- | ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ |
| ✅  | 🤖    | Final favicon art committed (`clickwheel/mcp/assets/favicon.svg`); rasterized to `favicon.ico` + 32/180px PNG via `scripts/generate-favicon.sh`                   | —                        |
| ✅  | 🤖    | Serve `/favicon.svg`, `/favicon.ico`, `/favicon-32.png`, `/apple-touch-icon.png`, `/` from the MCP app (`_http_assets.py`); tests; packaged in the wheel          | —                        |
| ✅  | 🧑    | Cloudflare Access **bypass** for `/favicon.ico`, `/favicon.svg`, `/apple-touch-icon.png`, `/favicon-32.png` (separate "clickwheel-favicons" app, Bypass/Everyone) | —                        |
| ✅  | 🤖    | Verify unauthenticated: favicon paths → 200; `/mcp` still 302 gated                                                                                               | —                        |
| ⬜  | 🧑    | Nudge Google to crawl (open in browser / request indexing)                                                                                                        | after bypass (done)      |
| ⬜  | 🧑    | Confirm cached: `s2/favicons?domain=clickwheel.fm` md5 ≠ default globe                                                                                            | after crawl (~1 day lag) |
| ⬜  | 🧑    | Confirm icon renders in claude.ai, distinct from rewind/bibliocommons                                                                                             | after Phase 5 connect    |

**Acceptance:** `s2/favicons?domain=clickwheel.fm` returns the **final** clickwheel mark (md5 ≠ default globe), and the connector list shows it.

---

## Phase 4 — Keep it running (launchd) 🧑

Server + tunnel must survive logout/reboot. LaunchAgent template:
[`deploy/fm.clickwheel.mcp-http.plist`](deploy/fm.clickwheel.mcp-http.plist).

| ✓   | Owner | Task                                                                                                                                                                    | Blocked by / reason |
| --- | ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| ✅  | 🤖    | MCP-server LaunchAgent installed (`~/Library/LaunchAgents/fm.clickwheel.mcp-http.plist`, points at the pipx `clickwheel-mcp serve --http --allowed-host clickwheel.fm`) | —                   |
| ✅  | 🤖    | `cloudflared` LaunchAgent installed (`fm.clickwheel.cloudflared.plist`, no sudo); both verified live                                                                    | —                   |
| ⬜  | 🧑    | Keep-awake decision: `caffeinate` LaunchAgent vs. Power Settings vs. accept "desk-only"                                                                                 | judgment call       |

**Acceptance:** survives a reboot; tunnel auto-reconnects; server auto-restarts.

---

## Phase 5 — Connect + verify on devices 🧑 (batched to the end)

**Decision:** all live testing below is deferred until the favicon is locked, so
it runs once against the final setup rather than twice.

| ✓   | Owner | Task                                                                                               | Blocked by / reason         |
| --- | ----- | -------------------------------------------------------------------------------------------------- | --------------------------- |
| ✅  | 🧑    | On **claude.ai (desktop browser)**: add `clickwheel.fm` connector, complete OAuth, list tools (37) | —                           |
| ✅  | 🧑    | Web sanity: `library_stats` returned real data (12,910 tracks)                                     | —                           |
| ⬜  | 🧑    | **Phone:** connector (added on web) usable from iOS app                                            | after web connect (done)    |
| ⬜  | 🧑    | **iPod docked:** `get_ipod_contents`; `sync_playlist_to_ipod` surfaces Allow/Deny + completes      | after connect + iPod docked |
| ⬜  | 🧑    | **iPod undocked:** iPod tools fail gracefully ("not connected")                                    | after connect               |
| ⬜  | 🧑    | Connector icon renders for `clickwheel.fm`, distinct from rewind/bibliocommons                     | Phase 3 go-public           |

**Acceptance:** clickwheel is fully usable from the iOS app; iPod tools work when docked, degrade cleanly when not.

---

## Open questions (carried from the brief)

- Does claude.ai/mobile honor `destructiveHint` with an Allow/Deny prompt? (Phase 5)
- ~~Does the Claude connector complete Cloudflare Access auth?~~ **Resolved:** yes — a self-hosted Access app serves the MCP OAuth challenge + discovery metadata natively (verified via `www-authenticate` + the resource-metadata endpoint). (Phase 2)
- ~~Connector icon source: MCP `icons` field vs. domain favicon?~~ **Resolved:** Google `s2/favicons` keyed off the connector domain; the MCP `icons` field doesn't drive it. (Phase 3)
- Keep-awake approach without leaving the Mac wide open. (Phase 4)
- Do MCP Apps inline UI bundles render on mobile, or text-only fallback? (non-blocking)
