"""Apple Music integration helpers — pure functions consumed by actions.py.

This module owns the mechanical work of talking to Apple Music: JWT
developer-token signing, the Music User Token auth dance (a tiny local
HTTP server that serves a MusicKit-JS page and catches the redirect),
and thin REST helpers for the catalog/library probes the doctor uses.
It deliberately raises bare exceptions; `actions.py` is the layer that
catches them and re-raises typed ClickwheelError variants so the CLI
and MCP surface can present consistent errors.

The `pyjwt[crypto]` package is an optional extra (`pip install
'clickwheel[applemusic]'`). Importing this module without it is fine;
only the JWT helpers actually touch pyjwt.
"""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Apple Music's REST root. Same host for catalog and library endpoints;
# /v1/catalog/... is public-catalog-scoped, /v1/me/... requires both
# the developer token AND a Music User Token.
API_ROOT = "https://api.music.apple.com"


class AppleMusicExtraMissingError(RuntimeError):
    """Raised when pyjwt[crypto] isn't installed."""


class AppleMusicConfigInvalidError(ValueError):
    """Raised for a malformed apple_music config block."""


class AppleMusicAuthFailedError(RuntimeError):
    """Raised when the user-token auth dance didn't yield a token."""


class AppleMusicHTTPError(RuntimeError):
    """Wrapper for non-2xx responses from api.music.apple.com.

    Carries the status code and the response body (if any) so the
    doctor can surface Apple's error detail without callers needing
    to know the urllib exception shape.
    """

    def __init__(self, status: int, body: str, url: str) -> None:
        excerpt = body[:200] or "(empty body)"
        super().__init__(f"Apple Music returned HTTP {status} for {url}: {excerpt}")
        self.status = status
        self.body = body
        self.url = url


def _import_jwt() -> Any:
    """Import pyjwt lazily so the rest of clickwheel doesn't pay the
    cryptography cost. Re-raises as AppleMusicExtraMissingError with a
    pip install command in the message.
    """
    try:
        import jwt  # PyJWT

        return jwt
    except ImportError as exc:
        raise AppleMusicExtraMissingError(
            "pyjwt is not installed. Install the optional extra:\n"
            "  pip install 'clickwheel[applemusic]'  (or `pipx inject clickwheel "
            "'clickwheel[applemusic]'` if you installed with pipx)"
        ) from exc


def read_private_key(path: str | Path) -> str:
    """Read a MusicKit .p8 private key, expanding ~ in the path.

    Returns the PEM string. Raises FileNotFoundError or
    AppleMusicConfigInvalidError if the file isn't a PEM private key.
    """
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f".p8 key file not found: {p}")
    text = p.read_text()
    if "BEGIN PRIVATE KEY" not in text:
        raise AppleMusicConfigInvalidError(
            f"{p} doesn't look like a PEM private key (no 'BEGIN PRIVATE KEY' "
            "marker). Re-download the .p8 from developer.apple.com."
        )
    return text


def generate_developer_token(
    key_pem: str,
    key_id: str,
    team_id: str,
    ttl_seconds: int = 180 * 24 * 3600,
) -> str:
    """Sign a MusicKit developer token (JWT, ES256).

    Apple caps token lifetime at 180 days; we default to that ceiling
    so the token's good for as long as possible without re-signing.
    Callers that want shorter tokens (e.g. CI tests) can pass
    `ttl_seconds`.
    """
    jwt = _import_jwt()
    now = int(time.time())
    payload = {"iss": team_id, "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(payload, key_pem, algorithm="ES256", headers={"kid": key_id})


def _request_json(
    url: str,
    *,
    headers: dict[str, str],
    method: str = "GET",
    data: bytes | None = None,
    timeout: float = 10.0,
) -> dict:
    """Minimal JSON HTTP helper. Returns the decoded body or raises
    AppleMusicHTTPError with status + body."""
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8")
        except Exception:
            pass
        raise AppleMusicHTTPError(exc.code, body, url) from exc


def verify_developer_token(token: str, storefront: str = "us") -> dict:
    """Round-trip the developer token against the catalog search
    endpoint. Returns the first hit if any. Raises AppleMusicHTTPError
    on auth failure or network problems.

    A 401 here typically means the key behind `kid` was revoked on
    developer.apple.com, or the signature doesn't match the kid header.
    """
    url = f"{API_ROOT}/v1/catalog/{storefront}/search?term=nirvana&types=songs&limit=1"
    body = _request_json(url, headers={"Authorization": f"Bearer {token}"})
    songs = body.get("results", {}).get("songs", {}).get("data", [])
    return songs[0] if songs else {}


def verify_user_token(dev_token: str, user_token: str, storefront: str = "us") -> dict:
    """Round-trip a Music User Token against /v1/me/storefront.

    Returns the user's storefront record (which carries the
    authoritative country code Apple thinks the user is in). Raises
    AppleMusicHTTPError on 401/403 (user token expired or rejected) or
    if the dev token itself isn't accepted.
    """
    return _request_json(
        f"{API_ROOT}/v1/me/storefront",
        headers={
            "Authorization": f"Bearer {dev_token}",
            "Music-User-Token": user_token,
        },
    )


def detect_icloud_music_library(
    dev_token: str, user_token: str, storefront: str = "us"
) -> bool:
    """Probe whether iCloud Music Library is on for this user.

    Strategy: hit /v1/me/library/songs?limit=1. If we get a 200 with a
    songs array (even empty), iCML is on. If Apple returns 403
    "USER_LIBRARY_DISABLED" (or similar), it's off. Other failures
    propagate as AppleMusicHTTPError.
    """
    try:
        _request_json(
            f"{API_ROOT}/v1/me/library/songs?limit=1",
            headers={
                "Authorization": f"Bearer {dev_token}",
                "Music-User-Token": user_token,
            },
        )
        return True
    except AppleMusicHTTPError as exc:
        # 403 typically signals iCML disabled. We don't trust the body
        # message format (it varies); the status is the load-bearing
        # signal. 401 would be an auth problem, not an iCML problem —
        # let that re-raise.
        if exc.status == 403:
            return False
        raise


# ---------------------------------------------------------------------------
# Music User Token auth dance
# ---------------------------------------------------------------------------


_AUTH_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>clickwheel — Apple Music auth</title>
<style>
  body {{ font: 16px/1.5 -apple-system, system-ui, sans-serif; max-width: 36rem;
         margin: 4rem auto; padding: 0 1rem; color: #222; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 0.5rem; }}
  button {{ font: inherit; padding: 0.6rem 1rem; background: #fa233b; color: #fff;
            border: 0; border-radius: 6px; cursor: pointer; }}
  button:disabled {{ background: #ccc; cursor: not-allowed; }}
  .status {{ margin-top: 1.5rem; padding: 0.75rem 1rem; border-radius: 6px;
             background: #f4f4f4; }}
  .ok {{ background: #d6f5d6; }}
  .err {{ background: #fde2e2; }}
  code {{ background: #f4f4f4; padding: 0.1rem 0.3rem; border-radius: 3px; }}
</style>
</head>
<body>
<h1>clickwheel — Apple Music authorization</h1>
<p>
  Click below to sign in with your Apple ID. clickwheel will receive a
  Music User Token so it can create and read playlists on your behalf.
  This window will close automatically when authorization completes.
</p>
<button id="auth-btn" disabled>Loading MusicKit…</button>
<div id="status" class="status">Waiting for MusicKit to load…</div>

<script src="https://js-cdn.music.apple.com/musickit/v3/musickit.js"
        data-web-components async></script>
<script>
const DEV_TOKEN = {dev_token_json};
const APP_NAME  = "clickwheel";
const APP_BUILD = {build_json};

document.addEventListener("musickitloaded", async () => {{
  try {{
    await MusicKit.configure({{
      developerToken: DEV_TOKEN,
      app: {{ name: APP_NAME, build: APP_BUILD }},
    }});
    const btn = document.getElementById("auth-btn");
    const stat = document.getElementById("status");
    btn.disabled = false;
    btn.textContent = "Authorize with Apple Music";
    stat.textContent = "MusicKit ready. Click the button to sign in.";

    btn.addEventListener("click", async () => {{
      btn.disabled = true;
      btn.textContent = "Authorizing…";
      try {{
        const userToken = await MusicKit.getInstance().authorize();
        stat.className = "status ok";
        stat.innerHTML = "Authorized. Sending token back to clickwheel… "
                       + "you can close this window once it confirms.";
        const r = await fetch("/callback", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ user_token: userToken }}),
        }});
        if (r.ok) {{
          stat.innerHTML = "Done. Token saved. You can close this window.";
        }} else {{
          stat.className = "status err";
          stat.textContent = "clickwheel rejected the token (HTTP " + r.status + ").";
        }}
      }} catch (e) {{
        stat.className = "status err";
        stat.textContent = "Authorization failed: " + (e && e.message || e);
        btn.disabled = false;
        btn.textContent = "Try again";
      }}
    }});
  }} catch (e) {{
    const stat = document.getElementById("status");
    stat.className = "status err";
    stat.textContent = "MusicKit.configure failed: " + (e && e.message || e);
  }}
}});
</script>
</body>
</html>
"""


def _pick_free_port() -> int:
    """Bind a socket to 127.0.0.1:0 to let the kernel pick a free
    ephemeral port, then close it. Tiny race window but fine for a
    one-shot interactive flow."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class AuthServerResult:
    user_token: str | None
    error: str | None


def run_user_token_auth(
    dev_token: str,
    *,
    build: str,
    port: int | None = None,
    timeout_seconds: float = 300.0,
    open_browser: bool = True,
) -> AuthServerResult:
    """Run the local MusicKit-JS auth dance.

    Spins up an HTTP server on 127.0.0.1, opens the user's browser to
    it, waits for the browser to POST the user token back to /callback.
    Returns the captured token (or an error string explaining what went
    wrong), then shuts the server down.

    `timeout_seconds` is the upper bound on how long we wait for the
    user. The browser is opened best-effort — if the open fails, the
    URL is still surfaced via the returned result so the user can
    paste it manually.
    """
    if not dev_token:
        raise AppleMusicAuthFailedError(
            "developer token is empty; can't run user-token auth without it."
        )

    selected_port = port if port is not None else _pick_free_port()
    result = AuthServerResult(user_token=None, error=None)
    done = threading.Event()

    html = _AUTH_HTML.format(
        dev_token_json=json.dumps(dev_token),
        build_json=json.dumps(build),
    )

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # noqa: N802  (stdlib API)
            # Silence the default per-request stderr logging; we route
            # through the module logger instead.
            logger.debug("auth-server: " + fmt, *args)

        def do_GET(self):  # noqa: N802
            if self.path in ("/", "/index.html"):
                payload = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):  # noqa: N802
            if self.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length else ""
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                result.error = "callback body wasn't valid JSON"
                done.set()
                return
            token = body.get("user_token")
            if not token:
                self.send_response(400)
                self.end_headers()
                result.error = "callback body missing 'user_token'"
                done.set()
                return
            result.user_token = token
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            done.set()

    server = HTTPServer(("127.0.0.1", selected_port), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{selected_port}/"
    logger.info("Apple Music auth server listening at %s", url)

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception as exc:
            logger.debug("webbrowser.open failed: %s", exc)

    try:
        completed = done.wait(timeout=timeout_seconds)
        if not completed:
            result.error = (
                f"Timed out after {int(timeout_seconds)}s waiting for the "
                "browser to complete the MusicKit auth flow."
            )
    finally:
        server.shutdown()
        server.server_close()

    return result
