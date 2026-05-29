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

**Where we are:** Phases 0–2 done — transport shipped, tunnel live, and the
endpoint is locked behind Cloudflare Access (verified: Cloudflare serves the MCP
OAuth challenge, so the connector can authenticate). Phase 3's serving code is
done with a **provisional** icon (go-public steps gated on final art).
**Decision:** all live testing (Phase 5 — claude.ai connector + phone + iPod) is
batched to the end, after the favicon is locked. Remaining: Phase 4 (launchd
persistence), favicon finalize + go-public, then the one test batch. On a
branch, not merged.

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

> ⚠️ **Favicon art is PROVISIONAL.** The serving mechanism is built and tested,
> but the current icon is the existing clickwheel mark (`SERVER_ICON`) used as a
> placeholder — we're iterating on the design. **Do not run the "go public"
> steps until the design is locked:** Google's favicon cache is sticky (~1 day+
> lag), so a published draft is annoying to replace. Regenerate with
> `./scripts/generate-favicon.sh` once final.

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

| ✓   | Owner | Task                                                                                                                                                                  | Blocked by / reason                                 |
| --- | ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| ✅  | 🤖    | Raster favicon from the mark → `favicon.ico` + 32/180px PNG (`scripts/generate-favicon.sh` → `clickwheel/mcp/assets/`)                                                | **provisional art** — regenerate when design locked |
| ✅  | 🤖    | Serve `/favicon.ico`, `/favicon-32.png`, `/apple-touch-icon.png`, `/` from the MCP app (`_http_assets.py`); tests in `test_mcp_http_assets.py`; packaged in the wheel | —                                                   |
| ⬜  | 🧑    | Cloudflare Access **bypass** for `/favicon.ico`, `/apple-touch-icon.png`, `/favicon-32.png`, `/.well-known/*`                                                         | **final favicon design** + Phase 2                  |
| ⬜  | 🧑    | Verify unauthenticated: `curl -I https://clickwheel.fm/favicon.ico` → 200, no redirect                                                                                | after bypass                                        |
| ⬜  | 🧑    | Nudge Google to crawl (open in browser / request indexing)                                                                                                            | after bypass                                        |
| ⬜  | 🧑    | Confirm cached: `s2/favicons?domain=clickwheel.fm` md5 ≠ default globe                                                                                                | after crawl (~1 day lag)                            |
| ⬜  | 🧑    | Confirm icon renders in claude.ai, distinct from rewind/bibliocommons                                                                                                 | after Phase 5 connect                               |

**Acceptance:** `s2/favicons?domain=clickwheel.fm` returns the **final** clickwheel mark (md5 ≠ default globe), and the connector list shows it.

---

## Phase 4 — Keep it running (launchd) 🧑

Server + tunnel must survive logout/reboot. LaunchAgent template:
[`deploy/fm.clickwheel.mcp-http.plist`](deploy/fm.clickwheel.mcp-http.plist).

| ✓   | Owner | Task                                                                               | Blocked by / reason |
| --- | ----- | ---------------------------------------------------------------------------------- | ------------------- |
| ⬜  | 🧑    | Install the MCP-server LaunchAgent (`KeepAlive`, `RunAtLoad`); fill `<USER>` paths | — (template ready)  |
| ⬜  | 🧑    | `cloudflared` as a service (`sudo cloudflared service install`)                    | after Phase 1       |
| ⬜  | 🧑    | Keep-awake decision: `caffeinate` vs. Power Settings vs. accept "desk-only"        | judgment call       |

**Acceptance:** survives a reboot; tunnel auto-reconnects; server auto-restarts.

---

## Phase 5 — Connect + verify on devices 🧑 (batched to the end)

**Decision:** all live testing below is deferred until the favicon is locked, so
it runs once against the final setup rather than twice.

| ✓   | Owner | Task                                                                                          | Blocked by / reason         |
| --- | ----- | --------------------------------------------------------------------------------------------- | --------------------------- |
| ⬜  | 🧑    | On **claude.ai (desktop browser)**: add `clickwheel.fm` connector, complete OAuth, list tools | Phases 1–2                  |
| ⬜  | 🧑    | Web sanity: `library_stats` + `search_tracks`                                                 | after connect               |
| ⬜  | 🧑    | **Phone:** connector (added on web) usable from iOS app                                       | after web connect           |
| ⬜  | 🧑    | **iPod docked:** `get_ipod_contents`; `sync_playlist_to_ipod` surfaces Allow/Deny + completes | after connect + iPod docked |
| ⬜  | 🧑    | **iPod undocked:** iPod tools fail gracefully ("not connected")                               | after connect               |
| ⬜  | 🧑    | Connector icon renders for `clickwheel.fm`, distinct from rewind/bibliocommons                | Phase 3 go-public           |

**Acceptance:** clickwheel is fully usable from the iOS app; iPod tools work when docked, degrade cleanly when not.

---

## Open questions (carried from the brief)

- Does claude.ai/mobile honor `destructiveHint` with an Allow/Deny prompt? (Phase 5)
- ~~Does the Claude connector complete Cloudflare Access auth?~~ **Resolved:** yes — a self-hosted Access app serves the MCP OAuth challenge + discovery metadata natively (verified via `www-authenticate` + the resource-metadata endpoint). (Phase 2)
- ~~Connector icon source: MCP `icons` field vs. domain favicon?~~ **Resolved:** Google `s2/favicons` keyed off the connector domain; the MCP `icons` field doesn't drive it. (Phase 3)
- Keep-awake approach without leaving the Mac wide open. (Phase 4)
- Do MCP Apps inline UI bundles render on mobile, or text-only fallback? (non-blocking)
