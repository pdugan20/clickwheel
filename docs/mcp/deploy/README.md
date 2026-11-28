# Deploy: clickwheel remote access (runbook)

Concrete steps to put the `serve --http` transport behind a Cloudflare Tunnel so
the Claude apps (including iOS) can reach it. It touches your Mac, your
Cloudflare account, and your devices.

Artifacts in this dir:

- `cloudflared-config.example.yml`: tunnel ingress config template
- `fm.clickwheel.mcp-http.plist`: LaunchAgent for the MCP HTTP server

**Hostname architecture:** the MCP endpoint is served on the **`mcp.clickwheel.fm`**
subdomain. The bare apex **`clickwheel.fm`** is _not_ served by the tunnel — a
Cloudflare Redirect Rule sends it to the docs site (`docs.clickwheel.fm`). So
Cloudflare Access, the tunnel ingress, and `--allowed-host` all key off
`mcp.clickwheel.fm`. (Earlier revisions ran the MCP server on the apex itself;
that's been split so the apex is free for the docs redirect — see issue #72.)

The examples use `mcp.clickwheel.fm`. Replace it (and the `<USER>` / `<TUNNEL>` /
`<UUID>` placeholders) with your own values.

## 1. Run the server over HTTP (local sanity)

```bash
pipx inject clickwheel 'clickwheel[mcp]'   # if not already
# --allowed-host is REQUIRED for the tunnel: the SDK's DNS-rebinding
# protection rejects the public Host header with HTTP 421 otherwise.
# Omit it for purely local testing (127.0.0.1 is always allowed).
clickwheel-mcp serve --http --allowed-host mcp.clickwheel.fm   # binds 127.0.0.1:8000/mcp
# in another shell:
curl -s http://127.0.0.1:8000/favicon.ico -o /dev/null -w '%{http_code}\n'   # 200
npx @modelcontextprotocol/inspector        # point at http://127.0.0.1:8000/mcp
```

`--allowed-host` can also be set via `CLICKWHEEL_MCP_ALLOWED_HOSTS=mcp.clickwheel.fm`
(comma-separated). If Claude's requests ever get a 403, add its origin with
`--allow-origin https://claude.ai` / `CLICKWHEEL_MCP_ALLOWED_ORIGINS`.

## 2. Cloudflare Tunnel

```bash
brew install cloudflared
cloudflared tunnel login                   # opens a browser, authorizes your CF account
cloudflared tunnel create clickwheel       # prints a UUID + creds file path
cp docs/mcp/deploy/cloudflared-config.example.yml ~/.cloudflared/config.yml
# edit ~/.cloudflared/config.yml: tunnel name/UUID, credentials-file path
cloudflared tunnel route dns clickwheel mcp.clickwheel.fm
cloudflared tunnel run clickwheel          # foreground test
```

With both the server and tunnel running, `https://mcp.clickwheel.fm/mcp` should reach
the server (you will get Access-challenged once step 3 is in place).

## 3. Auth: Cloudflare Access (self-hosted app + Managed OAuth)

A self-hosted Access app gates the endpoint, and **Managed OAuth** (a per-app
toggle) is what lets the Claude connector authenticate: it adds OAuth dynamic
client registration (RFC 7591) plus PKCE. Without it you get the `ofid_...`
"couldn't register" error. The connector URL is `https://mcp.clickwheel.fm/mcp`
(no portal, no SaaS-OIDC app, no manual client ID/secret).

In the Cloudflare Zero Trust dashboard
([one.dash.cloudflare.com](https://one.dash.cloudflare.com) → **Access controls →
Applications**):

1. Enable Zero Trust if prompted (**Free** plan; team name is account-wide, keep
   the auto-assigned one).
2. **Add an application → Self-hosted.**
3. **Destinations → Public hostnames:** subdomain `mcp`, Domain `clickwheel.fm`,
   blank path (protects the `mcp.clickwheel.fm` host). Do **not** gate the bare
   apex — it redirects to the docs site and must stay un-gated.
4. **Access policies → Create new policy:** name `Only me`, Action **Allow**,
   Include Selector **Emails** = your email. Save and attach.
5. Identity: built-in **One-time PIN** (email code); leave "Accept all available
   identity providers" on.
6. **Enable Managed OAuth** (toggle in the app settings, marked "Beta"). Then
   under **Allowed redirect URIs → + Add URI**, add exactly:
   `https://claude.ai/api/mcp/auth_callback`
   (Leave "Allow localhost/loopback clients" on.) This redirect URI is required;
   without it DCR registers but authorization is rejected with the `ofid_...`
   "Authorization with the MCP server failed" error.
7. Save the application.

Verify (unauthenticated): `curl -sI https://mcp.clickwheel.fm/mcp` returns `401`/`302`
toward your `<team>.cloudflareaccess.com` login, and
`curl -s https://mcp.clickwheel.fm/.well-known/oauth-authorization-server` returns
JSON containing a `registration_endpoint` (proof Managed OAuth/DCR is live).

### `ofid_` error cheat-sheet

- **"couldn't register with ... sign-in service"**: Managed OAuth not enabled (no
  DCR endpoint). Do step 6.
- **"Authorization with the MCP server failed ... credentials and permissions"**:
  the redirect URI is missing (add `https://claude.ai/api/mcp/auth_callback`), or
  Cloudflare "Block AI bots"/Bot Fight Mode is dropping Claude's requests (zone →
  Security → Bots → off, or allow IP range `160.79.104.0/21`).

## 4. Connector favicon (nothing to do)

The little icon Claude shows next to the connector comes from Google's favicon
service keyed off the **root domain** (`clickwheel.fm`) — _not_ the `mcp.`
connector host. Since the apex now 301-redirects to `docs.clickwheel.fm` (step
2's Redirect Rule), Google follows the redirect and caches the **docs site's**
favicon (the clickwheel mark, configured in Mintlify) for `clickwheel.fm`. So
the connector icon is correct with **no extra work** — no favicon serving on the
MCP server, no Access bypass.

This is why the MCP server no longer serves `/favicon.ico` and there's no
`clickwheel-favicons` bypass app: both were only needed back when the connector
ran on the apex behind Access. Google's favicon cache can lag a day or more
after the redirect goes live, so expect a delay before the icon updates.

(The MCP handshake still advertises the mark via the `icons=[SERVER_ICON]` field
— a base64 SVG inlined in `clickwheel/mcp/_runtime.py` — which is independent of
the Google-favicon connector-list icon.)

## 5. Keep it running (launchd)

```bash
cp docs/mcp/deploy/fm.clickwheel.mcp-http.plist ~/Library/LaunchAgents/
# edit <USER> + the clickwheel-mcp path
mkdir -p ~/.local/log
launchctl load -w ~/Library/LaunchAgents/fm.clickwheel.mcp-http.plist

# For a NEW deployment without an existing cloudflared service:
sudo cloudflared service install
```

The existing deployment uses the user LaunchAgent
`~/Library/LaunchAgents/fm.clickwheel.cloudflared.plist`, with `RunAtLoad` and
`KeepAlive`, running `/opt/homebrew/bin/cloudflared`. It is not managed by
`brew services`. Keep using that LaunchAgent; do not install a second service.

Decide on keep-awake: `caffeinate -s` under launchd, a Power Settings tweak, or
accept "only reachable when the Mac is awake."

### Pause remote access and keep local Clickwheel

The tunnel was intentionally paused on October 26, 2026. Local Clickwheel and
the Codex connection remain available. Keep the LaunchAgent and tunnel
configuration so remote access can be restored later.

To pause this deployment as the LaunchAgent's owning user:

```bash
launchctl disable "gui/$(id -u)/fm.clickwheel.cloudflared"
launchctl bootout "gui/$(id -u)/fm.clickwheel.cloudflared"
```

`disable` prevents automatic startup on later logins; `bootout` stops and
unloads the current service, including its `KeepAlive` behavior. Leave
`fm.clickwheel.mcp-http` running. Do not delete the tunnel, change DNS or Access
policies, or remove credentials to pause remote access.

Verify that the service is unloaded, its former PID has exited, and
`cloudflared tunnel info clickwheel` reports no active connectors. Then run
the local MCP initialization check below and `library_stats` through Codex.
An unauthenticated public `401` may still come from Cloudflare Access while
the tunnel is stopped; it does not mean the origin is reachable.

Only when remote access is wanted and restoration is authorized, enable and
load the preserved service again:

```bash
launchctl enable "gui/$(id -u)/fm.clickwheel.cloudflared"
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/fm.clickwheel.cloudflared.plist"
```

Check the installed version before restoring service, then perform the tunnel
and remote-connector verification below. `kickstart` alone does not restore
a service that has been unloaded and disabled.

### Update and restart cloudflared

For the operator maintaining the existing Apple Silicon Mac deployment: run
these steps on that Mac as the user who owns the LaunchAgent. Confirm the
upgrade and brief remote-access interruption are authorized before starting.
This procedure updates cloudflared and restarts only its LaunchAgent.

1. Record the installed version and the executable currently running:

   ```bash
   /opt/homebrew/bin/cloudflared --version
   cloudflared_pid=$(launchctl list | awk '$3 == "fm.clickwheel.cloudflared" {print $1}')
   test -n "$cloudflared_pid" && test "$cloudflared_pid" != "-"
   lsof -a -p "$cloudflared_pid" -d txt -Fn |
     sed -n '\|^n/opt/homebrew/Cellar/cloudflared/|s/^n//p'
   ```

   Expect a numeric PID and a path containing the running version. Stop if the
   LaunchAgent is absent or the executable belongs to a different installation.
   Updating the Homebrew symlink alone does not replace a running process.

2. Upgrade only cloudflared to the latest stable Homebrew release:

   ```bash
   HOMEBREW_NO_INSTALL_CLEANUP=1 HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK=1 \
     /opt/homebrew/bin/brew upgrade cloudflared
   /opt/homebrew/bin/cloudflared --version
   ```

   These options retain the previous keg and skip dependent-package upgrades.
   Check the current [Homebrew formula](https://formulae.brew.sh/formula/cloudflared)
   and [Cloudflare releases](https://github.com/cloudflare/cloudflared/releases).
   For the October 2026 [eMudhra advisory](https://blog.cloudflare.com/emudhra-certificate-compromise/),
   Cloudflare specifies at least 2026.10.2. Homebrew stable was 2026.10.3 when
   this procedure was verified on October 26, 2026; use newer stable fixes when
   available. Stop if the upgrade fails or the installed version remains below
   the required fixed release.

3. Restart the existing LaunchAgent:

   ```bash
   launchctl kickstart -k "gui/$(id -u)/fm.clickwheel.cloudflared"
   ```

   Remote requests may briefly disconnect. Leave `fm.clickwheel.mcp-http`
   running. Repeat step 1: the PID must change, and the executable path must
   contain the upgraded version. Run that exact executable with `--version`
   to confirm it. Do not substitute `brew services restart cloudflared`.

4. Verify tunnel readiness and active connections:

   ```bash
   curl --fail --silent --show-error --max-time 10 \
     http://127.0.0.1:20241/ready -o /dev/null -w 'readiness HTTP %{http_code}\n'
   curl --fail --silent --show-error --max-time 10 \
     http://127.0.0.1:20241/metrics |
     awk '/^cloudflared_tunnel_ha_connections / || /^cloudflared_tunnel_request_errors /'
   /opt/homebrew/bin/cloudflared tunnel info clickwheel
   ```

   Expect readiness `200`, active connections (normally four), and the new
   version in the authenticated tunnel-info result. The current deployment
   uses metrics port `20241`; if unavailable, inspect the process's listening
   ports with `lsof -a -p "$cloudflared_pid" -iTCP -sTCP:LISTEN -Pn` before
   retrying. A running PID alone is not a health check.

5. Verify the local MCP protocol and the public authentication gate:

   ```bash
   curl --fail --silent --show-error --max-time 10 \
     -H 'Content-Type: application/json' \
     -H 'Accept: application/json, text/event-stream' \
     --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"clickwheel-read-only-health","version":"1.0"}}}' \
     http://127.0.0.1:8000/mcp -o /dev/null -w 'local MCP HTTP %{http_code}\n'
   curl --silent --show-error --max-time 15 \
     https://mcp.clickwheel.fm/mcp -o /dev/null -w 'public MCP HTTP %{http_code}\n'
   ```

   Expect local initialization `200`. An unauthenticated public request should
   receive `401` or an Access login redirect (`302`); that verifies the gate,
   not an authenticated request to the origin. Complete the remote check by
   calling `library_stats` through the existing authenticated remote connector
   at `https://mcp.clickwheel.fm/mcp`. A local/stdio tool call does not prove
   remote access. If the connector requires reconnection, report remote
   verification as incomplete and use its normal OAuth sign-in flow; do not
   extract tokens or weaken Access to make the check pass.

6. Check for additional tunnels and connectors through the signed-in Cloudflare
   dashboard where account access permits. The read-only CLI fallback is:

   ```bash
   /opt/homebrew/bin/cloudflared tunnel list
   ```

   Use `tunnel info` for each in-scope tunnel to inspect connector versions.
   Record the account coverage and any dashboard sign-in gap. This does not
   establish coverage of other accounts or authorize restarting other connectors.

Keep credentials, authentication files, environment values, raw process
arguments, and unfiltered service/log dumps out of verification reports. If
the updated tunnel cannot connect, check readiness and targeted error messages;
do not disable TLS verification or Access, or silently roll back below a
security fix.

## 6. Add the connector + verify

1. On **claude.ai in a desktop browser** (you can't add connectors from the
   phone): Settings → Connectors → Add custom connector → `https://mcp.clickwheel.fm/mcp`.
   Complete the Cloudflare Access OAuth flow. List tools.
2. Run `library_stats` + `search_tracks` on web.
3. On the **phone**: the connector now appears, run the same tools.
4. **iPod docked**: `get_ipod_contents`; try `sync_playlist_to_ipod` and confirm
   the Allow/Deny prompt appears and it completes.
5. **iPod undocked**: confirm iPod tools fail gracefully ("not connected").
