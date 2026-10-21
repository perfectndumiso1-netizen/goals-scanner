"""Google Drive handoff — drop the finished video in a Drive folder, where a free Zapier Zap picks it up.

Publishing route (user's choice, 2026-10-21): the video is built here, copied into a Drive folder, and a two-step
Zapier Zap ("New File in Folder" → "Upload Video") hands it to YouTube. Zapier's free plan has no third step, so the
folder doubles as the permanent receipt log: nothing is moved or deleted afterwards.

Design notes
------------
* **Service account, not OAuth.** The scan runs unattended, so it authenticates as a Google service account
  (`GDRIVE_SA_JSON`) and uploads into a folder shared with that account's address as Editor (`GDRIVE_FOLDER_ID`).
* **Nothing happens unless it is switched on** (`DRIVE_HANDOFF=1` plus both secrets). A repository without them
  behaves exactly as before — the same rule the YouTube poster follows.
* **No new dependency.** The hashed requirements carry no crypto library, so the RS256 JWT is signed with plain
  integer maths from the standard library (PKCS#1 v1.5 + SHA-256). The key never leaves this process.
* **Resumable upload.** Google's multipart endpoint stops at 5 MB; a video is bigger, so the file goes up through
  one resumable request instead.
* **The title has no extension** and the mime type is `video/mp4`: that is what makes the Zapier→YouTube step upload
  a playable video rather than a file.

Commands (all read the same env):

    python drive_handoff.py info                 # is it configured, which folder, does the account see it
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


def configured() -> bool:
    return service_account() is not None and bool(folder_id())


def enabled() -> bool:
    """`DRIVE_HANDOFF=1` plus both secrets: the scan only hands off when everything says yes."""
    return _truthy(os.getenv("DRIVE_HANDOFF")) and configured()


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


def _json(resp: requests.Response, what: str) -> dict:
    if resp.status_code >= 400:
        raise DriveError(f"{what} failed ({resp.status_code}): {resp.text[:400]}")
    try:
        return resp.json()
    except ValueError as exc:
        raise DriveError(f"{what} returned non-JSON: {resp.text[:200]}") from exc


def access_token(sa: dict) -> str:
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
        raise DriveError(f"upload start failed ({start.status_code}): {start.text[:400]}")
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
    payload = (b"PlayReport Drive handoff dry run. " * 64)[:DRY_RUN_BYTES] if dry_run else path.read_bytes()
    mime = "text/plain" if dry_run else VIDEO_MIME
    if dry_run:
        name = f"{name} (dry run)"
    if token is None:
        sa = service_account()
        if sa is None:
            raise DriveError("GDRIVE_SA_JSON is missing or unusable")
        token = access_token(sa)
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
            notify(f"📤 YouTube handoff: {res.get('name')} → PlayReport/YouTube")
        except Exception:  # noqa: BLE001
            pass
    return res


# ------------------------------------------------------------------ cli

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Hand a finished PlayReport video to Google Drive for the YouTube Zap.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info", help="is it configured, and can the account see the folder")
    ck = sub.add_parser("check", help="dry run: a 2 KB stand-in through the whole path")
    ck.add_argument("--folder", default=None)
    up = sub.add_parser("upload", help="upload a video")
    up.add_argument("file")
    up.add_argument("--name", default=None)
    up.add_argument("--dry-run", action="store_true")
    up.add_argument("--folder", default=None)
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not configured():
        print("Drive handoff is NOT configured: set GDRIVE_SA_JSON and GDRIVE_FOLDER_ID.")
        return 2
    sa = service_account() or {}
    print(f"service account: {sa.get('client_email')}")
    print(f"folder id:       {folder_id() or '(unset)'}")
    try:
        token = access_token(sa)
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
        res = upload_video(Path("dry-run.mp4"), name="PlayReport handoff check", dry_run=True, token=token,
                           fid=getattr(args, "folder", None))
    else:
        res = upload_video(Path(args.file), name=args.name, dry_run=args.dry_run, token=token,
                           fid=getattr(args, "folder", None))
    print(f"{'dry-run file' if res.get('dry_run') else 'uploaded'}: {res['name']} -> {res.get('link') or res['id']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
