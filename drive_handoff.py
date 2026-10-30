"""Google Drive handoff — drop the finished video in a Drive folder, where a free Zapier Zap picks it up.

Publishing route (user's choice, 2026-10-21): the video is built here, copied into a Drive folder, and a two-step
Zapier Zap ("New File in Folder" → "Upload Video") hands it to YouTube. Zapier's free plan has no third step, so the
folder doubles as the permanent receipt log: nothing is moved or deleted afterwards.

Design notes
------------
* **Two ways to authenticate, your own account first.** A service account (`GDRIVE_SA_JSON`) only works when the
  folder lives in a Workspace Shared Drive, because a service account has no storage quota of its own — in a personal
  My Drive Google refuses the upload with *"Service Accounts do not have storage quota"*. So the preferred mode is
  **your own account** (`GDRIVE_CLIENT_ID` / `GDRIVE_CLIENT_SECRET` / `GDRIVE_REFRESH_TOKEN`, made once with
  `scripts/drive_auth.py`); the service account stays as a fallback for a Shared Drive. `GDRIVE_FOLDER_ID` is
  required either way, and `mode()` says which one is in use.
* **Nothing happens unless it is switched on** (`DRIVE_HANDOFF=1` plus credentials). A repository without them
  behaves exactly as before — the same rule the YouTube poster follows. The difference is that a switched-on but
  incomplete handoff is now **loud**: `describe()` names the missing secrets, and the scan sends that to Telegram
  once a day, so a misconfigured lane can never look like a working one again (it did for a whole day).
* **No new dependency.** The hashed requirements carry no crypto library, so the RS256 JWT is signed with plain
  integer maths from the standard library (PKCS#1 v1.5 + SHA-256). The key never leaves this process.
* **Resumable upload.** Google's multipart endpoint stops at 5 MB; a video is bigger, so the file goes up through
  one resumable request instead.
* **The title has no extension** and the mime type is `video/mp4`: that is what makes the Zapier→YouTube step upload
  a playable video rather than a file.

Commands (all read the same env):

    python drive_handoff.py info                 # configured? which account, which folder, can it add files?
    python drive_handoff.py diagnose             # exactly what is missing, without touching the network
    python drive_handoff.py check                # dry run: build a 2 KB stand-in and verify the whole path
    python drive_handoff.py upload FILE [--name NAME] [--dry-run]
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

import requests

log = logging.getLogger("scanner")

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/drive/v3"
UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"
SCOPE = "https://www.googleapis.com/auth/drive.file"   # only the files this app creates and the folders it is given
JWT_LIFETIME = 3600
VIDEO_MIME = "video/mp4"
DRY_RUN_BYTES = 2048


class DriveError(RuntimeError):
    """A Drive call failed. The message is safe to log (no secrets, no key material)."""


# ------------------------------------------------------------------ configuration

def _truthy(v: str | None) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def _env(*names: str) -> str:
    """First non-empty value among `names` — lets the Drive lane reuse the YouTube OAuth client when it is there."""
    for n in names:
        v = (os.getenv(n) or "").strip()
        if v:
            return v
    return ""


def service_account() -> dict | None:
    """The parsed service-account JSON from `GDRIVE_SA_JSON`, or None when it is absent or unusable."""
    raw = (os.getenv("GDRIVE_SA_JSON") or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict) or not (data.get("client_email") and data.get("private_key")):
        return None
    return data


def folder_id() -> str:
    return (os.getenv("GDRIVE_FOLDER_ID") or "").strip()


def user_creds() -> tuple[str, str, str] | None:
    """(client_id, client_secret, refresh_token) for acting **as you**, which is what a personal My Drive needs.

    A service account has no storage quota of its own, so Drive refuses uploads into a personal folder ("Service
    Accounts do not have storage quota"). Acting as the folder's owner avoids that entirely and needs no sharing.
    The OAuth client can be the same one the YouTube poster uses — only the refresh token is scope-specific.
    """
    cid = _env("GDRIVE_CLIENT_ID", "YT_CLIENT_ID")
    secret = _env("GDRIVE_CLIENT_SECRET", "YT_CLIENT_SECRET")
    refresh = _env("GDRIVE_REFRESH_TOKEN", "DRIVE_REFRESH_TOKEN")
    if not (cid and secret and refresh):
        return None
    return cid, secret, refresh


def mode() -> str:
    """'user' (your own account), 'service-account', or 'none'."""
    if user_creds() is not None:
        return "user"
    if service_account() is not None:
        return "service-account"
    return "none"


def configured() -> bool:
    return bool(folder_id()) and mode() != "none"


def enabled() -> bool:
    """`DRIVE_HANDOFF=1` plus credentials: the scan only hands off when everything says yes."""
    return _truthy(os.getenv("DRIVE_HANDOFF")) and configured()


def missing() -> list[str]:
    """The names of the settings that still have to be added, in the order they should be added."""
    out: list[str] = []
    if mode() == "none":
        out += ["GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN"]
    if not folder_id():
        out.append("GDRIVE_FOLDER_ID")
    return out


def status() -> dict:
    """Everything a log line or a Telegram message needs to explain why the handoff did or did not run."""
    on = _truthy(os.getenv("DRIVE_HANDOFF"))
    return {"switch_on": on, "mode": mode(), "folder": folder_id() or None,
            "configured": configured(), "enabled": on and configured(), "missing": missing()}


def describe() -> str:
    """One sentence, safe to show a person. Never contains key material."""
    st = status()
    if st["enabled"]:
        who = "your Google account" if st["mode"] == "user" else "the service account"
        return f"Drive handoff is ON — uploading as {who} into folder {st['folder']}"
    if not st["switch_on"]:
        return "Drive handoff is OFF (DRIVE_HANDOFF is not set to 1)"
    return ("Drive handoff is ON but NOT configured — missing " + ", ".join(st["missing"])
            + ". Videos will keep going to Telegram only.")


# ------------------------------------------------------------------ RS256 without a crypto library

def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _pem_to_der(pem: str) -> bytes:
    body = "".join(line.strip() for line in str(pem or "").splitlines()
                   if line.strip() and not line.strip().startswith("-----"))
    return base64.b64decode(body)


class _Reader:
    """Minimal DER walker: enough of ASN.1 to pull (n, e, d) out of a PKCS#8 or PKCS#1 RSA key."""

    def __init__(self, data: bytes):
        self.d, self.i = data, 0

    def take(self, n: int) -> bytes:
        out = self.d[self.i:self.i + n]
        if len(out) != n:
            raise DriveError("service-account key is truncated")
        self.i += n
        return out

    def tlv(self) -> tuple[int, bytes]:
        tag = self.take(1)[0]
        length = self.take(1)[0]
        if length & 0x80:
            n = length & 0x7F
            length = int.from_bytes(self.take(n), "big")
        return tag, self.take(length)

    def children(self) -> list[tuple[int, bytes]]:
        out, end = [], len(self.d)
        while self.i < end:
            out.append(self.tlv())
        return out


def _int_of(raw: bytes) -> int:
    return int.from_bytes(raw, "big")


def rsa_key(pem: str) -> tuple[int, int]:
    """(modulus, private exponent) from a PEM private key. Accepts PKCS#8 and PKCS#1."""
    der = _Reader(_pem_to_der(pem))
    outer = der.tlv()
    if outer[0] != 0x30:
        raise DriveError("not an RSA private key")
    parts = _Reader(outer[1]).children()
    if len(parts) == 3 and parts[1][0] == 0x30:           # PKCS#8: SEQ { version, AlgorithmIdentifier, OCTET STRING }
        inner = _Reader(parts[2][1])
        seq = inner.tlv()
        parts = _Reader(seq[1]).children()
    if not parts or parts[0][0] != 0x02:
        raise DriveError("not an RSA private key")
    # RSAPrivateKey ::= SEQ { version, n, e, d, ... }
    return _int_of(parts[1][1]), _int_of(parts[3][1])


_SHA256_DIGEST_INFO = bytes.fromhex("3031300d060960864801650304020105000420")


def sign_rs256(payload: str, pem: str) -> str:
    """Sign `payload` with RSASSA-PKCS1-v1_5 + SHA-256 (RFC 8017 §8.2), using only the standard library."""
    n, d = rsa_key(pem)
    k = (n.bit_length() + 7) // 8
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    encoded = _SHA256_DIGEST_INFO + digest
    if k < len(encoded) + 11:
        raise DriveError("service-account key is too small to sign with")
    em = b"\x00\x01" + b"\xff" * (k - len(encoded) - 3) + b"\x00" + encoded
    signature = pow(int.from_bytes(em, "big"), d, n)
    return _b64url(signature.to_bytes(k, "big"))


def assertion(sa: dict, *, scope: str = SCOPE, now: float | None = None) -> str:
    """The signed JWT that the service account trades for an access token."""
    issued = int(now if now is not None else time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": sa["client_email"],
        "scope": scope,
        "aud": sa.get("token_uri") or TOKEN_URL,
        "iat": issued,
        "exp": issued + JWT_LIFETIME,
    }
    signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}." \
                    f"{_b64url(json.dumps(claims, separators=(',', ':')).encode())}"
    return f"{signing_input}.{sign_rs256(signing_input, sa['private_key'])}"


# ------------------------------------------------------------------ http plumbing

def _request(method: str, url: str, **kw) -> requests.Response:
    """Single seam for tests: every call in this module goes through here."""
    kw.setdefault("timeout", 300)
    return requests.request(method, url, **kw)


def _explain(resp: requests.Response, what: str = "upload start") -> str:
    """A Drive failure as an operator can act on — the quota refusal above all, because it looks like a
    permissions problem and is not."""
    text = (resp.text or "")[:600]
    low = text.lower()
    if "storage quota" in low or "storagequotaexceeded" in low:
        return ("upload failed (403): a service account has no storage quota of its own, which is what Google "
                "reports for a folder in a personal My Drive. Use your own account instead: run "
                "scripts/drive_auth.py once and set GDRIVE_CLIENT_ID / GDRIVE_CLIENT_SECRET / "
                "GDRIVE_REFRESH_TOKEN, or move the folder into a Shared Drive. Raw: " + text[:240])
    if resp.status_code == 404:
        return (f"{what} failed (404): the folder is not visible to the {mode()} credentials. Share it with the "
                f"service account as Editor, or use your own account via scripts/drive_auth.py. Raw: " + text[:240])
    if resp.status_code == 401:
        return (f"{what} failed (401): the credentials were rejected — run scripts/drive_auth.py again. "
                f"Raw: {text[:240]}")
    return f"{what} failed ({resp.status_code}): {text[:400]}"


def _json(resp: requests.Response, what: str) -> dict:
    if resp.status_code >= 400:
        raise DriveError(f"{what} failed ({resp.status_code}): {resp.text[:400]}")
    try:
        return resp.json()
    except ValueError as exc:
        raise DriveError(f"{what} returned non-JSON: {resp.text[:200]}") from exc


def access_token(sa: dict | None = None) -> str:
    """An access token for whichever mode is configured: your own account first, then a service account."""
    creds = user_creds()
    if creds is not None:
        cid, secret, refresh = creds
        resp = _request("POST", TOKEN_URL, data={
            "client_id": cid, "client_secret": secret, "refresh_token": refresh,
            "grant_type": "refresh_token",
        })
        body = _json(resp, "user token refresh")
        tok = body.get("access_token")
        if not tok:
            raise DriveError("token refresh returned no access_token: the refresh token may belong to a deleted "
                             "OAuth client or have been revoked — run scripts/drive_auth.py again.")
        return str(tok)
    sa = sa or service_account()
    if sa is None:
        raise DriveError("no Drive credentials: set GDRIVE_REFRESH_TOKEN (preferred) or GDRIVE_SA_JSON")
    resp = _request("POST", sa.get("token_uri") or TOKEN_URL, data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion(sa),
    })
    body = _json(resp, "service-account token")
    tok = body.get("access_token")
    if not tok:
        raise DriveError(f"token exchange returned no access_token: {body}")
    return str(tok)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------ the handoff

def title_for(path: Path) -> str:
    """The Docker/Zapier title: the filename without its extension (a Zapier→YouTube step chokes on `.mp4`)."""
    return Path(path).stem


def folder_info(token: str, fid: str | None = None) -> dict:
    """Name, type and sharing of the target folder — proves the service account can actually see it."""
    fid = fid or folder_id()
    if not fid:
        raise DriveError("GDRIVE_FOLDER_ID is not set")
    resp = _request("GET", f"{API}/files/{fid}",
                    params={"fields": "id,name,mimeType,webViewLink,capabilities/canAddChildren",
                            "supportsAllDrives": "true"}, headers=_headers(token))
    body = _json(resp, "folder lookup")
    caps = body.get("capabilities") or {}
    return {"id": body.get("id"), "name": body.get("name"), "type": body.get("mimeType"),
            "link": body.get("webViewLink"), "can_add": bool(caps.get("canAddChildren"))}


def upload_bytes(token: str, payload: bytes, name: str, *, fid: str | None = None,
                 mime: str = VIDEO_MIME) -> dict:
    """Resumable single-request upload into the folder. Returns the created file's id, name and link."""
    fid = fid or folder_id()
    if not fid:
        raise DriveError("GDRIVE_FOLDER_ID is not set")
    meta = {"name": name, "mimeType": mime, "parents": [fid], "appProperties": {"source": "playreport"}}
    start = _request("POST", UPLOAD_URL, params={"uploadType": "resumable", "supportsAllDrives": "true",
                                                 "fields": "id,name,size,webViewLink"},
                     headers={**_headers(token), "Content-Type": "application/json; charset=UTF-8",
                              "X-Upload-Content-Type": mime, "X-Upload-Content-Length": str(len(payload))},
                     data=json.dumps(meta))
    if start.status_code >= 400:
        raise DriveError(_explain(start))
    location = start.headers.get("Location") or start.headers.get("location")
    if not location:
        raise DriveError("upload start returned no Location header")
    put = _request("PUT", location, headers={**_headers(token), "Content-Type": mime,
                                             "Content-Length": str(len(payload))}, data=payload)
    body = _json(put, "upload")
    return {"id": body.get("id"), "name": body.get("name") or name,
            "size": int(body.get("size") or len(payload)), "link": body.get("webViewLink")}


def upload_video(path: Path, *, name: str | None = None, dry_run: bool = False,
                 token: str | None = None, fid: str | None = None) -> dict:
    """Put a finished video in the Drive folder the Zap watches.

    `dry_run` sends a 2 KB stand-in text file instead of the video, so the whole path (auth, folder permissions,
    the Zap trigger) can be proven without publishing anything. The video itself is never modified or deleted.
    """
    path = Path(path)
    if not dry_run and not path.exists():
        raise DriveError(f"video not found: {path}")
    name = (name or title_for(path)).strip()
    if not name:
        raise DriveError("a Drive title is required")
    payload = (b"Mr 2 Odds Drive handoff dry run. " * 64)[:DRY_RUN_BYTES] if dry_run else path.read_bytes()
    mime = "text/plain" if dry_run else VIDEO_MIME
    if dry_run:
        name = f"{name} (dry run)"
    if token is None:
        if mode() == "none":
            raise DriveError("no Drive credentials — set GDRIVE_REFRESH_TOKEN (scripts/drive_auth.py) or GDRIVE_SA_JSON")
        token = access_token()
    out = upload_bytes(token, payload, name, fid=fid, mime=mime)
    out["dry_run"] = dry_run
    return out


def handoff(path: Path, *, dry_run: bool = False, notify=None) -> dict | None:
    """Scan hook: hand a finished video to the Zap, logging and reporting failures without ever raising.

    `notify` is the scanner's Telegram sender (a string argument); it is only used to say what happened.
    Returns the upload result, or None when the handoff is switched off.
    """
    if not enabled():
        return None
    try:
        res = upload_video(path, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001 - a Drive hiccup must never take the scan or the Telegram send down
        log.warning("Drive handoff skipped: %s", exc)
        if notify:
            try:
                notify(f"⚠️ YouTube handoff failed for {Path(path).name}: {exc}")
            except Exception:  # noqa: BLE001
                pass
        return None
    log.info("Drive handoff: %s → %s (%d KB)", res.get("name"), folder_id(), res.get("size", 0) // 1024)
    if notify:
        try:
            notify(f"📤 YouTube handoff: {res.get('name')} → Mr 2 Odds/YouTube")
        except Exception:  # noqa: BLE001
            pass
    return res


# ------------------------------------------------------------------ cli

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Hand a finished Mr 2 Odds video to Google Drive for the YouTube Zap.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("diagnose", help="what is configured and what is missing (no network)")
    sub.add_parser("info", help="which account, which folder, and can it add files")
    ck = sub.add_parser("check", help="dry run: a 2 KB stand-in through the whole path")
    ck.add_argument("--folder", default=None)
    up = sub.add_parser("upload", help="upload a video")
    up.add_argument("file")
    up.add_argument("--name", default=None)
    up.add_argument("--dry-run", action="store_true")
    up.add_argument("--folder", default=None)
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.cmd == "diagnose":
        st = status()
        print(f"switch:   {'on' if st['switch_on'] else 'off'}  (DRIVE_HANDOFF)")
        print(f"mode:     {st['mode']}")
        print(f"folder:   {st['folder'] or '(unset)'}  (GDRIVE_FOLDER_ID)")
        print(f"ready:    {'yes' if st['enabled'] else 'no'}")
        if st["missing"]:
            print("missing:  " + ", ".join(st["missing"]))
        print(describe())
        return 0 if st["enabled"] else 2

    if not configured():
        print("Drive handoff is NOT configured — " + describe())
        return 2
    if mode() == "user":
        print("account:         your own Google account (OAuth refresh token)")
    else:
        print(f"service account: {(service_account() or {}).get('client_email')}")
    print(f"folder id:       {folder_id() or '(unset)'}")
    try:
        token = access_token()
    except DriveError as exc:
        print(f"auth failed: {exc}")
        return 1
    try:
        info = folder_info(token, getattr(args, "folder", None))
    except DriveError as exc:
        print(f"folder check failed: {exc}")
        return 1
    print(f"folder:          {info['name']} ({info['type']}) · can add files: {info['can_add']}")
    if args.cmd == "info":
        return 0 if info["can_add"] else 1
    if args.cmd == "check":
        res = upload_video(Path("dry-run.mp4"), name="Mr 2 Odds handoff check", dry_run=True, token=token,
                           fid=getattr(args, "folder", None))
    else:
        res = upload_video(Path(args.file), name=args.name, dry_run=args.dry_run, token=token,
                           fid=getattr(args, "folder", None))
    print(f"{'dry-run file' if res.get('dry_run') else 'uploaded'}: {res['name']} -> {res.get('link') or res['id']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
