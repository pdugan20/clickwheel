# Remote access — run clickwheel from Claude mobile

> **Status: transport landed; tunnel + auth are owner-owned.** The Streamable
> HTTP transport (step 1) is implemented and verified locally — see
> `clickwheel-mcp serve --http`. Steps 2–3 (Cloudflare Tunnel + Access, launchd)
> happen on the owner's Mac and Cloudflare account and can't be done in-repo.
> Self-contained on purpose — the reference servers it draws on (`rewind`,
> `nextup-backend-mcp`) and the sibling brief (`bibliocommons-mcp`) live in
> _other repos_ you can't see, so the relevant patterns are extracted inline.
>
> **For the step-by-step task list, see the
> [tracker](remote-mobile-access-tracker.md).** This page is the rationale.

## Goal

Reach clickwheel from the **Claude mobile (iOS) app** while **preserving 100%
of functionality — including iPod sync**. Domain: **`clickwheel.fm`**.

## The decision, up front (read this before proposing anything else)

**clickwheel stays single-tenant and the Mac stays the source of truth.** We
expose the existing server to the internet through a **Cloudflare Tunnel**,
not by re-hosting it in the cloud. Two approaches were considered and
**rejected** — don't re-litigate them without new information:

- **Cloud-replica (sync the SQLite up to a hosted server):** high effort (DB
  replication + keeping it fresh + config→env migration) and it _still can't
  touch the iPod_. You'd rebuild half the system to get a strictly degraded
  subset. The valuable data — the library index and the playlists — is built
  from local music files (`config.py` `music_dir`, `db.py` SQLite at
  `~/.clickwheel/`), and the Plex/Apple Music sync tools read playlists _out
  of that local store_. Divorced from the Mac, there's little left worth
  calling.
- **Multi-user:** impossible as a single cloud service. Each user's library
  index and iPod are physically bound to _their own_ Mac (the iPod is a
  USB-mounted volume — `clickwheel/ipod/`, vendored iOpenPodv2, reads/writes
  the binary iTunesDB on `/Volumes/IPOD`). "Multi-user clickwheel" can only
  mean "each person runs this same tunnel recipe on their own Mac." There is
  no shared instance that can serve two libraries. (This is the opposite of
  the sibling `bibliocommons-mcp`, which _is_ going multi-user — because its
  data lives on BiblioCommons' servers, not the user's machine.)

The tunnel approach keeps every tool working, needs zero data re-architecture,
and degrades gracefully: iPod tools just return "iPod not connected" from the
phone exactly as they do locally today (see `find_ipod` in
`clickwheel/ipod/__init__.py`). You queue playlist edits from anywhere; they
apply to the device next time it's docked. **The one real cost: the Mac must
be awake and online.** For a desktop music tool that's acceptable.

## How attaching actually works (corrected — this is not phone-first)

You **cannot add a custom connector from the Claude iOS/Android app.** Per
Anthropic's docs, custom connectors are added on **claude.ai (web) or Claude
Desktop**; the mobile app then _uses_ connectors already added there. So the
flow is: add `clickwheel.fm` as a custom connector on claude.ai in a desktop
browser → complete auth there (a full browser, not a mobile webview, which is
the easy place for the OAuth round-trip) → it shows up and works in the iOS
app. Verification on the phone tests _use_, not _adding_.

Plan tiers are a non-issue: custom connectors are available on **Free, Pro,
Max, Team, and Enterprise** (Free is capped at one connector; on Team/Enterprise
only an Owner can add one for the org). No paid tier is required to attach.

## Why the mobile app couldn't use it before

The only transport was stdio (`clickwheel/mcp/server.py`,
`mcp.run(transport="stdio")`), so the server could only run as a local
subprocess of a desktop MCP client. claude.ai/mobile attach only to a **remote
MCP server reachable over the public internet** speaking **Streamable HTTP**.
Step 1 below gives it exactly that, with the server still running on _this_
Mac behind a tunnel. (SSE is the deprecated transport; we target Streamable
HTTP.)

## Approach

### 1. Streamable HTTP entry point (DONE — keeps stdio)

`mcp` is the official `modelcontextprotocol/python-sdk`. Clickwheel uses its
MCP 2 `MCPServer` API (`mcp.server.MCPServer`), pinned to `mcp>=2.0,<3`; the
instance lives in `clickwheel/mcp/_runtime.py`, and tools register on import.
Transport configuration is passed directly to `mcp.run(...)`, as required by
the 2.x API.

The endpoint supports both protocol eras on the same URL:

- MCP 2026-07-28 clients use `server/discover`. Streamable HTTP requests are
  stateless, so they need no initialize request, session ID, or sticky routing.
- Older clients fall back to the legacy initialize/session flow. The legacy
  HTTP leg remains sessionful for compatibility.

`clickwheel/mcp/server.py:main()` now switches transport (stdio stays the
default — local Claude Code/Desktop are unchanged):

- `clickwheel-mcp` (no args) → stdio, unchanged.
- `clickwheel-mcp serve --http` (or `CLICKWHEEL_MCP_TRANSPORT=http`) →
  Streamable HTTP **bound to `127.0.0.1:8000/mcp`** by default. Override with
  `--host`/`--port`/`--path` or `CLICKWHEEL_MCP_HOST`/`_PORT`/`_PATH`. It binds
  loopback only — the Cloudflare Tunnel is the sole ingress; the server never
  listens on a public interface (a non-loopback bind logs a warning).

Transport selection is unit-tested (`tests/test_mcp_transport.py`) and the real
HTTP entry point is smoke-tested end to end in both modes: modern
`server/discover` negotiates MCP 2026-07-28, and legacy initialization
negotiates MCP 2025-11-25. Both paths list the clickwheel tools. Stdio is tested
the same way.

MCP Apps is registered through the stable `io.modelcontextprotocol/ui`
extension API and modern discovery advertises its MIME types. Legacy clients
still receive the core text and structured tool results, but the legacy
initialize schema cannot advertise the modern extension; those hosts may use
text-only fallback until they support discovery.

The existing rules held while doing this:

- **Logging stays stderr-only** (CLAUDE.md rule #13). stdout is the wire
  protocol for the stdio path; `_setup_logging()` is unchanged.
- **Tools still wrap `actions.py`** (rule #11) — this was a transport addition
  only; no tool code changed.
- **No autoscan** (rule #9) — already correct for the MCP surface; remote
  calls serve cached SQLite, same as local chat.
- **Destructive gating is annotation-based** (corrected rule #12). The tools do
  **not** call `Context.elicit()` and have no `confirm` param — every mutating
  tool carries `destructiveHint=true` and compliant clients surface a native
  Allow/Deny prompt. So the old open question "does `Context.elicit()`
  round-trip to mobile?" is **moot**. The real thing to confirm on the phone is
  whether the claude.ai/mobile client honors `destructiveHint` with an
  Allow/Deny prompt (it should — it's a standard annotation). There is no
  server-side bypass to fail open on.

### 2. Expose via Cloudflare Tunnel + Access (owner-owned)

- Install `cloudflared`, create a named tunnel, route `clickwheel.fm` (apex,
  or a hostname on it) → `http://127.0.0.1:8000`. Cloudflare provides the
  public DNS + TLS; nothing is port-forwarded on the home network.
- **Auth: a plain self-hosted Cloudflare Access application — verified.** (This
  supersedes an earlier draft that recommended "Access for SaaS / OIDC.") A
  self-hosted Access app over `clickwheel.fm` is all that's required: Cloudflare
  Access natively serves the MCP OAuth challenge and discovery metadata, so the
  Claude connector authenticates with **zero OAuth code, no OIDC app, no Claude
  redirect URL, and no client ID/secret**. Confirmed against the live endpoint:
  a no-auth request to `/mcp` returns
  `www-authenticate: Cloudflare-Access resource_metadata="…/.well-known/cloudflare-access-protected-resource/mcp"`,
  and that metadata advertises `authorization_servers: [<team>.cloudflareaccess.com]`.
  Use the built-in One-time PIN identity (email code) and a policy allowing your
  email only. Steps in [`deploy/README.md`](deploy/README.md) §3. Because the
  connector is added in a desktop browser, the OAuth round-trip runs in a real
  browser, not a mobile webview.
- **Connector icon — verify before doing the favicon dance.** The server
  already advertises a protocol-level icon (`icons=[SERVER_ICON]`, an inlined
  base64 SVG in `_runtime.py`). If claude.ai renders the connector from that
  MCP `icons` field, the favicon workaround is unnecessary. If it instead
  derives the icon from the domain favicon (Google's favicon service, keyed off
  the apex), then serve a `clickwheel.fm` `/favicon.ico` **and** add an Access
  **bypass** policy for `/favicon.ico` and `/.well-known/*` so the
  _unauthenticated_ crawler can fetch them — otherwise Access gates the whole
  hostname and the icon never resolves. Expect up to a day of crawl/cache lag.
  The distinct apex (`clickwheel.fm` vs the sibling's `getbiblio.app`) is what
  makes the two connectors show different icons.

### 3. Keep it running (launchd, owner-owned)

The server and `cloudflared` must survive logout/reboot:

- Run `cloudflared` as a managed service (`cloudflared service install`) or a
  `launchd` LaunchAgent plist.
- Run `clickwheel-mcp serve --http` as a `launchd` LaunchAgent (`KeepAlive`,
  `RunAtLoad`). Log to a file under `~/.clickwheel/` or `~/.local/log/`.
- Modern MCP 2026-07-28 HTTP requests are stateless and need no affinity.
  Legacy clients retain their session against this single process, so they also
  avoid cross-instance affinity problems. Request-scoped
  `notifications/progress` continues to work in both modes.
- Mac-awake requirement: consider `caffeinate` or a Power Settings tweak so the
  machine doesn't sleep the tunnel. Document this for the owner.

## Tool behavior from mobile (set expectations)

- **Library + playlist tools** (read + mutation): fully work — they hit local
  SQLite. Build/edit playlists from your phone anytime.
- **Plex / Apple Music / Last.fm** tools: work whenever the Mac can reach
  those services (Plex on the LAN is reachable since the server runs _on the
  LAN_).
- **iPod tools:** work **only when the iPod is docked** to the Mac. Undocked,
  they return the same "not connected" error as locally — by design. Queue the
  intent; dock later; re-issue.
- **`delete_apple_music_playlist`:** macOS AppleScript via Music.app on the
  Mac — works (the Mac is doing it), just like locally.

## Effort

- MCP 2 migration + dual-era HTTP/stdio compatibility: **done in-repo.**
- Cloudflare Tunnel + Access for SaaS OIDC: ~0.5–1 day (mostly Cloudflare
  dashboard + DNS).
- launchd plumbing: ~0.5 day.
- Verifying destructive-gating + the connector OAuth attach against the real
  mobile client: variable; this is where surprises hide.

## Open questions

- **Does claude.ai/mobile honor `destructiveHint` with an Allow/Deny prompt?**
  Replaces the old elicitation question (the code never used `elicit()`). Should
  work — it's a standard annotation — but confirm on the device.
- **Connector icon source** — protocol `icons` field vs domain favicon (see
  step 2). Determines whether the favicon/Access-bypass work is needed.
- **Keeping the Mac awake** without leaving it wide open — power settings vs
  `caffeinate` vs accepting "only when I'm at my desk."
- **MCP Apps / inline UI bundles** (`docs/mcp/bundles.md`): do the iframe
  bundles render in the mobile client, or is it text-only fallback? Not a
  blocker (graceful fallback exists) but worth confirming.

## Dependencies / blockers

- `clickwheel.fm` registered (done), pointed at Cloudflare DNS.
- A Cloudflare account with Zero Trust (Access) enabled.
- ~~SDK migration~~ — done (`mcp>=2.0,<3`, MCPServer API).
- ~~No code blockers~~ — transport shipped; remaining work is all
  Cloudflare/launchd on the owner's machine.

## Verification (owner-owned — cannot be fully done in-repo)

The in-repo ceiling is met: transport resolution is unit-tested and the local
Streamable HTTP endpoint passes both modern stateless discovery and legacy
session initialization, followed by `tools/list`. The rest needs the owner, on
the phone, against the live tunnel after publishing and restarting the service:

1. ✅ **(done, in-repo)** `clickwheel-mcp serve --http --port <p>` then clients
   against `http://127.0.0.1:<p>/mcp` — MCP 2026-07-28 discovery and MCP
   2025-11-25 legacy initialization both list tools. (`npx
@modelcontextprotocol/inspector` works too.)
2. Bring up the tunnel; confirm `https://clickwheel.fm` reaches the server and
   Access challenges as expected.
3. **On a desktop browser:** add `clickwheel.fm` as a custom connector on
   claude.ai, complete the Access-for-SaaS OAuth flow, list tools, run
   `library_stats` and `search_tracks`.
4. **On the phone:** confirm the connector (added on web) is usable — run
   `library_stats` / `search_tracks` from the iOS app.
5. With the **iPod docked**: run `get_ipod_contents` from the phone; confirm a
   destructive tool (e.g. `sync_playlist_to_ipod`) surfaces a confirmation
   (Allow/Deny) and completes.
6. With the **iPod undocked**: confirm iPod tools fail gracefully ("not
   connected"), not with a crash or a hang.
7. Confirm the connector icon renders for `clickwheel.fm` (allow a day),
   distinct from the bibliocommons connector — and note whether it came from
   the MCP `icons` field or the favicon (closes that open question).
