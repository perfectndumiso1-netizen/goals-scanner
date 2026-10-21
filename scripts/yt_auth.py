#!/usr/bin/env python3
"""One-time YouTube authorisation — produces the refresh token the poster runs on.

Run this on your own computer once (not in CI):

    export YT_CLIENT_ID='...apps.googleusercontent.com'
    export YT_CLIENT_SECRET='...'
    python scripts/yt_auth.py

It opens Google's consent screen in your browser, catches the redirect on http://127.0.0.1:8765/, exchanges the
code and prints a **refresh token**. Put the three values into the repository's secrets as `YT_CLIENT_ID`,
`YT_CLIENT_SECRET` and `YT_REFRESH_TOKEN` — you do not need to paste anything into a file.

Scope asked for: `https://www.googleapis.com/auth/youtube` (upload, read status, update and delete — the probe
deletes its own test clip). The account you sign in with must own the channel you want to post to.

Headless machine (no browser)? Add `--manual`, open the printed URL anywhere, then paste back the full redirect URL.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

import youtube_post as yt  # noqa: E402

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
PORT = 8765
REDIRECT = f"http://127.0.0.1:{PORT}/"


def auth_url(client_id: str, redirect: str = REDIRECT) -> str:
    q = {
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join(yt.SCOPES),
        "access_type": "offline",          # a refresh token, not just an hour-long access token
        "prompt": "consent",               # force the refresh token even on a re-run
        "include_granted_scopes": "true",
    }
    return f"{AUTH_URL}?{urllib.parse.urlencode(q)}"


def exchange(client_id: str, client_secret: str, code: str, redirect: str = REDIRECT) -> dict:
    r = requests.post(yt.TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect,
    }, timeout=60)
    if r.status_code >= 400:
        raise SystemExit(f"token exchange failed ({r.status_code}): {r.text[:400]}")
    return r.json()


def wait_for_code(port: int = PORT, timeout: float = 300.0) -> str:
    """Catch the one redirect Google sends back and hand its `code` to the main thread."""
    holder: dict[str, str] = {}
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):                                    # noqa: N802 - stdlib API
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" in qs:
                holder["code"] = qs["code"][0]
                body = b"Authorised. You can close this tab and go back to the terminal."
            else:
                holder["error"] = qs.get("error", ["no code in the redirect"])[0]
                body = b"Authorisation was cancelled. Close this tab."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            done.set()

        def log_message(self, *_args):                       # keep the terminal quiet
            pass

    srv = HTTPServer(("127.0.0.1", port), Handler)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        if not done.wait(timeout):
            raise SystemExit("timed out waiting for the browser redirect — re-run, or use --manual")
    finally:
        srv.shutdown()
    if holder.get("error"):
        raise SystemExit(f"authorisation failed: {holder['error']}")
    return holder["code"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Authorise the PlayReport YouTube poster")
    ap.add_argument("--manual", action="store_true", help="no local browser: print the URL and paste the redirect back")
    ap.add_argument("--no-browser", action="store_true", help="print the URL but do not try to open a browser")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args(argv)

    client_id = (os.getenv("YT_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("YT_CLIENT_SECRET") or "").strip()
    if not (client_id and client_secret):
        print("Set YT_CLIENT_ID and YT_CLIENT_SECRET first (Google Cloud → APIs & Services → Credentials → "
              "OAuth client ID → Desktop app).", file=sys.stderr)
        return 2

    redirect = REDIRECT if args.port == PORT else f"http://127.0.0.1:{args.port}/"
    url = auth_url(client_id, redirect)
    print("\n1) Open this URL and sign in with the Google account that owns the channel:\n")
    print(url + "\n")
    if not args.no_browser and not args.manual:
        webbrowser.open(url)

    if args.manual:
        back = input("2) Paste the whole redirect URL (or just the code) and press Enter:\n> ").strip()
        if "code=" in back:
            code = urllib.parse.parse_qs(urllib.parse.urlparse(back).query).get("code", [""])[0]
        else:
            code = back
        if not code:
            print("No code found in that URL.", file=sys.stderr)
            return 2
    else:
        print("2) Approve the access. Waiting for the redirect…")
        code = wait_for_code(args.port)

    tok = exchange(client_id, client_secret, code, redirect)
    refresh = tok.get("refresh_token")
    if not refresh:
        print("\nNo refresh_token came back. Remove the app's access at https://myaccount.google.com/permissions "
              "and run this again (Google only issues a refresh token on a fresh consent).", file=sys.stderr)
        return 2

    # Prove it actually works before printing anything to copy.
    try:
        creds = yt.Creds(client_id, client_secret, refresh)
        token = yt.access_token(creds)
        info = yt.channel_info(token)
        scopes = yt.token_scopes(token)
    except Exception as exc:                                  # noqa: BLE001 - show the reason, do not crash
        print(f"\nThe token was issued but the channel check failed: {exc}", file=sys.stderr)
        info, scopes = {}, []

    print("\n3) Add these three repository secrets (Settings → Secrets and variables → Actions):\n")
    print(f"YT_CLIENT_ID={client_id}")
    print(f"YT_CLIENT_SECRET={client_secret}")
    print(f"YT_REFRESH_TOKEN={refresh}\n")
    if info:
        print(f"Channel: {info.get('title')} ({info.get('id')}) · {info.get('subscribers'):,} subscribers · "
              f"{info.get('videos'):,} videos")
    print("Scopes: " + (" ".join(scopes) if scopes else "(could not read)"))
    if "https://www.googleapis.com/auth/youtube" not in scopes:
        print("Warning: the token does not carry the full `youtube` scope — the probe will not be able to delete "
              "its test clip. Re-run this script and approve the consent screen fully.", file=sys.stderr)
    print("\nNext: `python youtube_post.py probe` — it uploads a 3-second clip and tells you whether this project "
          "can publish publicly or needs YouTube's audit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
