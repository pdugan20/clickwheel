# Deploy: clickwheel remote access (runbook)

Concrete steps to take the in-repo work (the `serve --http` transport) live
behind a Cloudflare Tunnel so the Claude iOS app can reach it. This is the
owner-owned half — it touches your Mac, your Cloudflare account, and your
devices. The _why_ is in [`../remote-mobile-access.md`](../remote-mobile-access.md);
the phase/task status is in
[`../remote-mobile-access-tracker.md`](../remote-mobile-access-tracker.md).

Artifacts in this dir:

- `cloudflared-config.example.yml` — tunnel ingress config template
- `fm.clickwheel.mcp-http.plist` — LaunchAgent for the MCP HTTP server

Replace `<USER>` / `<TUNNEL>` / `<UUID>` placeholders with your values.

## 1. Run the server over HTTP (local sanity)

```bash
pipx inject clickwheel 'clickwheel[mcp]'   # if not already
# --allowed-host is REQUIRED for the tunnel: the SDK's DNS-rebinding
# protection rejects the public Host header with HTTP 421 otherwise.
# Omit it for purely local testing (127.0.0.1 is always allowed).
clickwheel-mcp serve --http --allowed-host clickwheel.fm   # binds 127.0.0.1:8000/mcp
# in another shell:
curl -s http://127.0.0.1:8000/favicon.ico -o /dev/null -w '%{http_code}\n'   # 200
npx @modelcontextprotocol/inspector        # point at http://127.0.0.1:8000/mcp
```

`--allowed-host` can also be set via `CLICKWHEEL_MCP_ALLOWED_HOSTS=clickwheel.fm`
(comma-separated). If Claude's requests ever get a 403, add its origin with
`--allow-origin https://claude.ai` / `CLICKWHEEL_MCP_ALLOWED_ORIGINS`.

## 2. Cloudflare Tunnel

```bash
brew install cloudflared
cloudflared tunnel login                   # opens a browser — authorizes your CF account
cloudflared tunnel create clickwheel       # prints a UUID + creds file path
cp docs/mcp/deploy/cloudflared-config.example.yml ~/.cloudflared/config.yml
# edit ~/.cloudflared/config.yml: tunnel name/UUID, credentials-file path
cloudflared tunnel route dns clickwheel clickwheel.fm
cloudflared tunnel run clickwheel          # foreground test
```

With both the server and tunnel running, `https://clickwheel.fm/mcp` should
reach the server (you'll get Access-challenged once step 3 is in place).

## 3. Auth — Cloudflare Access (self-hosted app + **Managed OAuth**)

Verified working May 2026. A self-hosted Access app gates the endpoint, and
**Managed OAuth** (a per-app toggle) is what lets the Claude connector
authenticate — it adds OAuth **dynamic client registration (RFC 7591)** + PKCE.
Without it you get the `ofid_…` "couldn't register" error. The connector URL
stays `https://clickwheel.fm/mcp` (no portal, no SaaS-OIDC app, no manual client
ID/secret).

In the Cloudflare Zero Trust dashboard ([one.dash.cloudflare.com](https://one.dash.cloudflare.com)
→ **Access controls → Applications**):

1. Enable Zero Trust if prompted (**Free** plan; team name is account-wide — keep
   the auto-assigned one).
2. **Add an application → Self-hosted.**
3. **Destinations → Public hostnames:** Domain `clickwheel.fm`, blank subdomain
   and path (protects the whole host).
4. **Access policies → Create new policy:** name `Only me`, Action **Allow**,
   Include Selector **Emails** = your email. Save + attach.
5. Identity: built-in **One-time PIN** (email code); leave "Accept all available
   identity providers" on.
6. **Enable Managed OAuth** (toggle in the app settings, marked "Beta"). Then
   under **Allowed redirect URIs → + Add URI**, add **exactly**:
   `https://claude.ai/api/mcp/auth_callback`
   (Leave "Allow localhost/loopback clients" on.) **This redirect URI is
   required** — without it DCR registers but authorization is rejected with the
   `ofid_…` "Authorization with the MCP server failed" error.
7. Save the application.

Verify (unauthenticated): `curl -sI https://clickwheel.fm/mcp` → `401`/`302`
toward your `<team>.cloudflareaccess.com` login, and
`curl -s https://clickwheel.fm/.well-known/oauth-authorization-server` returns
JSON containing a **`registration_endpoint`** (proof Managed OAuth/DCR is live).

### `ofid_` error cheat-sheet

- **"couldn't register with … sign-in service"** → Managed OAuth not enabled (no
  DCR endpoint). Do step 6.
- **"Authorization with the MCP server failed … credentials and permissions"** →
  the redirect URI is missing (add `https://claude.ai/api/mcp/auth_callback`),
  or Cloudflare **"Block AI bots"/Bot Fight Mode** is dropping Claude's requests
  (zone → Security → Bots → off, or allow IP range `160.79.104.0/21`).

## 4. Favicon bypass — **GATED on final favicon design**

> ⚠️ Don't do this step until the favicon art is locked (see tracker Phase 3).
> Google's favicon cache is sticky (~1 day+ lag); publishing a draft icon means
> living with it while the new one propagates.

Once the design is final and regenerated (`./scripts/generate-favicon.sh`):

In **Access → Applications**, add a **Bypass** policy (or a separate app with
Bypass) for paths `/favicon.ico`, `/apple-touch-icon.png`, `/favicon-32.png` so
Google's _unauthenticated_ crawler can fetch them. Without this, Access gates
the whole hostname and the icon never resolves.

Then verify the fetch is unauthenticated and that Google caches it (allow ~1 day):

```bash
curl -I https://clickwheel.fm/favicon.ico      # 200, no Access redirect
curl -sL "https://www.google.com/s2/favicons?domain=clickwheel.fm&sz=32" -o /tmp/cw.png
# md5 of /tmp/cw.png should DIFFER from the default globe (a nonexistent domain's response)
```

## 5. Keep it running (launchd)

```bash
cp docs/mcp/deploy/fm.clickwheel.mcp-http.plist ~/Library/LaunchAgents/
# edit <USER> + the clickwheel-mcp path
mkdir -p ~/.local/log
launchctl load -w ~/Library/LaunchAgents/fm.clickwheel.mcp-http.plist

# cloudflared as a managed service (simplest):
sudo cloudflared service install
```

Decide on keep-awake: `caffeinate -s` under launchd, a Power Settings tweak, or
accept "only reachable when the Mac is awake."

## 6. Add the connector + verify

1. On **claude.ai in a desktop browser** (you can't add connectors from the
   phone): Settings → Connectors → Add custom connector → `https://clickwheel.fm/mcp`.
   Complete the Cloudflare Access OAuth flow. List tools.
2. Run `library_stats` + `search_tracks` on web.
3. On the **phone**: the connector now appears — run the same tools.
4. **iPod docked**: `get_ipod_contents`; try `sync_playlist_to_ipod` and confirm
   the Allow/Deny prompt appears and it completes.
5. **iPod undocked**: confirm iPod tools fail gracefully ("not connected").
