#!/usr/bin/env python3
"""
One-time X (Twitter) OAuth 2.0 PKCE login.

Uses X_OAUTH2_CLIENT_ID / X_OAUTH2_CLIENT_SECRET from .env.
Opens a browser, then saves:
  X_OAUTH2_ACCESS_TOKEN
  X_OAUTH2_REFRESH_TOKEN
to .env

Note: video media upload still prefers OAuth 1.0a (API Key + Access Token).
OAuth 2.0 is excellent for tweets/replies and confirms the app works.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

AUTH_URL = "https://twitter.com/i/oauth2/authorize"
TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
REDIRECT_URI = os.getenv("X_OAUTH2_REDIRECT_URI", "http://127.0.0.1:8790/callback")
SCOPES = "tweet.read tweet.write users.read offline.access"


def _set_env(key: str, value: str) -> None:
    path = ROOT / ".env"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    line = f"{key}={value}"
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    if pattern.search(text):
        text = pattern.sub(line, text)
    else:
        text = text.rstrip() + "\n" + line + "\n"
    path.write_text(text, encoding="utf-8")


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def main() -> None:
    client_id = os.getenv("X_OAUTH2_CLIENT_ID") or os.getenv("X_CLIENT_ID") or ""
    client_secret = os.getenv("X_OAUTH2_CLIENT_SECRET") or os.getenv("X_CLIENT_SECRET") or ""
    if not client_id:
        print("Missing X_OAUTH2_CLIENT_ID in .env")
        sys.exit(1)

    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(16)
    result: dict[str, str] = {}

    parsed = urllib.parse.urlparse(REDIRECT_URI)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8790
    path = parsed.path or "/callback"

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            qs = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(qs)
            if "code" in params:
                result["code"] = params["code"][0]
                result["state"] = params.get("state", [""])[0]
                body = b"<html><body><h2>X auth OK — you can close this tab.</h2></body></html>"
                self.send_response(200)
            else:
                body = b"<html><body><h2>Missing code</h2></body></html>"
                self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):  # noqa: A003
            return

    server = HTTPServer((host, port), Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    auth_params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = AUTH_URL + "?" + urllib.parse.urlencode(auth_params)
    print("Opening browser for X login…")
    print("If it does not open, visit:\n", url)
    print()
    print("IMPORTANT: In the X developer portal, set Callback URI / Redirect URL to exactly:")
    print(" ", REDIRECT_URI)
    webbrowser.open(url)
    thread.join(timeout=180)
    server.server_close()

    if not result.get("code"):
        print("No auth code received (timeout or cancel).")
        sys.exit(1)
    if result.get("state") != state:
        print("State mismatch — aborting.")
        sys.exit(1)

    data = {
        "code": result["code"],
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": verifier,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    auth = None
    if client_secret:
        auth = (client_id, client_secret)

    r = httpx.post(TOKEN_URL, data=data, headers=headers, auth=auth, timeout=30)
    print("token status", r.status_code)
    if r.status_code >= 400:
        print(r.text[:500])
        sys.exit(1)
    tok = r.json()
    access = tok.get("access_token", "")
    refresh = tok.get("refresh_token", "")
    if not access:
        print("No access_token in response", tok)
        sys.exit(1)

    _set_env("X_OAUTH2_ACCESS_TOKEN", access)
    if refresh:
        _set_env("X_OAUTH2_REFRESH_TOKEN", refresh)
    print("Saved X_OAUTH2_ACCESS_TOKEN" + (" + REFRESH" if refresh else ""))

    me = httpx.get(
        "https://api.x.com/2/users/me",
        headers={"Authorization": f"Bearer {access}"},
        params={"user.fields": "username,name"},
        timeout=30,
    )
    print("me", me.status_code, me.text[:300])
    if me.status_code == 200:
        u = me.json().get("data") or {}
        print(f"SUCCESS logged in as @{u.get('username')} ({u.get('name')})")
    print("Done.")


if __name__ == "__main__":
    main()
