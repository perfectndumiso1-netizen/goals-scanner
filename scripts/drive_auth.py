#!/usr/bin/env python3
"""One-time Google Drive authorisation — produces the refresh token the handoff runs on.

A service account cannot write into a personal My Drive ("Service Accounts do not have storage quota"), so the
scan acts **as you** instead. Run this once on your own computer:

    export GDRIVE_CLIENT_ID='...apps.googleusercontent.com'
    export GDRIVE_CLIENT_SECRET='...'
    python scripts/drive_auth.py

It opens Google's consent screen in your browser, catches the redirect on http://127.0.0.1:8766/, exchanges the
code and prints a **refresh token**. Put the three values into the repository's secrets as `GDRIVE_CLIENT_ID`,
`GDRIVE_CLIENT_SECRET` and `GDRIVE_REFRESH_TOKEN` (plus `GDRIVE_FOLDER_ID`) — nothing is pasted into a file.

Scope asked for: `https://www.googleapis.com/auth/drive.file` — the app may only see and manage the files it
creates itself and the folders you hand it. It cannot read the rest of your Drive.

The OAuth client can be the same "Desktop app" client the YouTube poster uses; only the refresh token differs,
because each token carries the scopes it was granted.

Headless machine (no browser)? Add `--manual`, open the printed URL anywhere, then paste back the full redirect URL.
"""
from __future__ import annotations

import argparse
import os
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

SCOPE = "https://www.googleapis.com/auth/drive.file"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
PORT = 8766                     # 8765 belongs to scripts/yt_auth.py, so both can run without clashing
REDIRECT = f"http://127.0.0.1:{PORT}/"


def auth_url(client_id: str, redirect: str = REDIRECT) -> str:
    q = {
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",          # a refresh token, not just an hour-long access token
        "prompt": "consent",               # force the refresh token even on a re-run
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(q)}"


def exchange(client_id: str, client_secret: str, code: str, redirect: str = REDIRECT) -> dict:
    r = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect,
    }, timeout=60)
    r.raise_for_status()
    return r.json()


def _code_from(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("http"):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
        return (q.get("code") or [""])[0]
    return raw


def wait_for_code(url: str, state: str) -> str:
    """Serve one request on the loopback redirect and return the code Google sent back."""
    box: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server API
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            box["code"] = (q.get("code") or [""])[0]
            box["state"] = (q.get("state") or [""])[0]
            done = bool(box["code"])
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<h2>PlayReport Drive authorisation</h2>"
                + (b"<p>Done. You can close this tab and go back to the terminal.</p>" if done
                   else b"<p>Google did not return a code. Close this tab and try again.</p>")
            )

        def log_message(self, *_a):  # keep the terminal clean
            return

    srv = HTTPServer(("127.0.0.1", PORT), Handler)
    t = threading.Thread(target=srv.handle_request, daemon=True)
    t.start()
    webbrowser.open(url)
    t.join(timeout=300)
    srv.server_close()
    if not box.get("code"):
        raise SystemExit("No authorisation code arrived. Re-run, or use --manual.")
    return box["code"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="One-time Google Drive authorisation for the PlayReport handoff.")
    ap.add_argument("--manual", action="store_true", help="print the URL and ask for the redirect URL back")
    ap.add_argument("--client-id", default=os.getenv("GDRIVE_CLIENT_ID") or os.getenv("YT_CLIENT_ID") or "")
    ap.add_argument("--client-secret", default=os.getenv("GDRIVE_CLIENT_SECRET") or os.getenv("YT_CLIENT_SECRET") or "")
    args = ap.parse_args(argv)
    if not (args.client_id and args.client_secret):
        print("Set GDRIVE_CLIENT_ID and GDRIVE_CLIENT_SECRET first (a Google Cloud 'Desktop app' OAuth client).")
        return 2
    url = auth_url(args.client_id)
    print("\nOpen this URL and sign in with the Google account that owns the Drive folder:\n")
    print(url + "\n")
    if args.manual:
        raw = input("Paste the full redirect URL (or just the code) here: ").strip()
        code = _code_from(raw)
    else:
        code = wait_for_code(url, "")
    body = exchange(args.client_id, args.client_secret, code)
    refresh = body.get("refresh_token")
    if not refresh:
        print("Google returned no refresh_token. Remove the app's access at https://myaccount.google.com/permissions "
              "and run this again — a token issued without `prompt=consent` cannot be refreshed.")
        return 1
    print("\nAdd these to the repository's Actions secrets:\n")
    print(f"GDRIVE_CLIENT_ID={args.client_id}")
    print(f"GDRIVE_CLIENT_SECRET={args.client_secret}")
    print(f"GDRIVE_REFRESH_TOKEN={refresh}")
    print("GDRIVE_FOLDER_ID=<the folder id from its URL>")
    print("\nThen check the whole path with:  python drive_handoff.py check")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
