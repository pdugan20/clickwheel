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

## 3. Auth — Cloudflare Access for SaaS (OIDC)

In the Cloudflare Zero Trust dashboard:

1. **Settings → Authentication**: add an identity provider (Google / GitHub /
   one-time PIN).
2. **Access → Applications → Add → SaaS → OIDC**. App name `clickwheel`.
3. Redirect URL: `https://claude.ai/api/mcp/auth_callback`.
4. **Policy**: allow your email only.
5. Save; copy the **Client ID + Client Secret** — you may need them in the
   connector's _Advanced settings_ on claude.ai.

> Use **Access for SaaS (OIDC)**, not a _self-hosted_ Access app. The SaaS-OIDC
> app makes Cloudflare the OAuth authorization server, which is what the Claude
> connector's OAuth flow expects. A self-hosted app only shows a browser SSO
> login the connector won't complete cleanly.

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
