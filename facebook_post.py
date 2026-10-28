"""Stream PlayReport videos to a Facebook Page, without logging credentials.

Uses only the standard library so the existing one-shot briefing workflow needs no
new dependencies. A returned video ID means Facebook accepted the published upload;
Facebook may still be processing it. Never delete the source here. Failures keep a
recovery copy outside Git/state; Actions uploads that directory as an artifact.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

log = logging.getLogger("scanner")
ROOT = Path(__file__).resolve().parent
GRAPH_VERSION = "v25.0"
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class UploadResult:
    status: str  # disabled, uploaded, failed
    video_id: str | None = None


def requested() -> bool:
    """Partial configuration is a failed upload, not permission to delete a video."""
    return bool(os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or os.getenv("FACEBOOK_PAGE_ID"))


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as video:
        for chunk in iter(lambda: video.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def _receipt(path: Path) -> Path:
    return path.with_name(path.name + ".facebook-upload.json")


def published_id(path: Path) -> str | None:
    """Reuse only a receipt for this exact file's bytes and the configured Page."""
    try:
        info = json.loads(_receipt(path).read_text(encoding="utf-8"))
        if (info.get("page_id") == os.getenv("FACEBOOK_PAGE_ID", "").strip()
                and re.fullmatch(r"\d+", str(info.get("video_id", "")))
                and path.is_file() and info.get("sha256") == _digest(path)):
            return str(info["video_id"])
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the bearer token to a redirect target.
        return None


class _VideoBody:
    """Known-length multipart body; urllib/http.client sends chunks, not a RAM-sized video."""
    def __init__(self, path: Path, caption: str):
        self.path = path
        self.boundary = "PlayReport" + uuid.uuid4().hex
        parts = []
        for name, value in (("title", (caption.splitlines() or ["PlayReport ZA football briefing"])[0][:100]),
                            ("description", caption[:5000]), ("published", "true")):
            parts.append(f'--{self.boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8"))
        parts.append(f'--{self.boundary}\r\nContent-Disposition: form-data; name="source"; filename="PlayReport.mp4"\r\nContent-Type: video/mp4\r\n\r\n'.encode("ascii"))
        self.prefix = b"".join(parts)
        self.suffix = f"\r\n--{self.boundary}--\r\n".encode("ascii")
        self.size = len(self.prefix) + path.stat().st_size + len(self.suffix)

    def __iter__(self):
        yield self.prefix
        with self.path.open("rb") as video:
            for chunk in iter(lambda: video.read(CHUNK_SIZE), b""):
                yield chunk
        yield self.suffix


def _retain(path: Path, reason: str) -> UploadResult:
    # No API response bodies or exception strings: either can echo an access token.
    log.error("Facebook publishing failed for %s: %s. Original video retained; Telegram will still be attempted.", path.name, reason)
    try:
        directory = Path(os.getenv("VIDEO_RECOVERY_DIR") or ROOT / "tmp" / "video-recovery")
        directory.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^a-zA-Z0-9_-]", "_", path.stem)[:80]
        recovery = directory / f"{stem}-{_digest(path)[:20]}.mp4"
        if not recovery.exists():
            shutil.copy2(path, recovery)
        log.error("Facebook recovery video saved: %s (download the workflow's video-recovery artifact).", recovery)
    except OSError:
        log.error("Could not save Facebook recovery copy; original remains at %s. Preserve it before the runner exits.", path)
    return UploadResult("failed")


def publish(path: Path, caption: str = "") -> UploadResult:
    """Publish once per exact file/Page on this runner; never retry an ambiguous POST.

    Authentication is a bearer header over HTTPS, never a URL/query string or
    logged request. Missing both secrets preserves the old Telegram-only behavior.
    A partial/invalid configuration fails closed for cleanup, but not Telegram.
    """
    path = Path(path)
    if not requested():
        return UploadResult("disabled")
    token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
    page = os.getenv("FACEBOOK_PAGE_ID", "").strip()
    if not token or not re.fullmatch(r"\d+", page):
        return _retain(path, "set both FACEBOOK_PAGE_ACCESS_TOKEN and a numeric FACEBOOK_PAGE_ID")
    try:
        if not path.is_file() or path.stat().st_size == 0:
            return _retain(path, "video file is missing or empty")
    except OSError:
        return _retain(path, "cannot read video file")
    previous = published_id(path)
    if previous:
        log.info("Facebook: already accepted this video as %s; not uploading it again.", previous)
        return UploadResult("uploaded", previous)
    try:
        digest = _digest(path)
        body = _VideoBody(path, str(caption or ""))
        req = Request(
            f"https://graph-video.facebook.com/{GRAPH_VERSION}/{page}/videos",
            data=body, method="POST",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": f"multipart/form-data; boundary={body.boundary}",
                     "Content-Length": str(body.size)},
        )
        # No blind retry: a timeout can happen after Facebook accepted the post.
        with build_opener(_NoRedirect()).open(req, timeout=600) as response:
            info = json.loads(response.read(65536).decode("utf-8"))
        video_id = str(info.get("id", "")) if isinstance(info, dict) else ""
        if not re.fullmatch(r"\d+", video_id) or "error" in info:
            return _retain(path, "Facebook returned no valid video ID; check the Page/token permissions and video requirements")
        receipt = _receipt(path)
        temp = receipt.with_suffix(".tmp")
        temp.write_text(json.dumps({"video_id": video_id, "page_id": page, "sha256": digest}), encoding="utf-8")
        temp.replace(receipt)
        log.info("Facebook: video accepted for PlayReport ZA (video ID %s); Facebook may still be processing it.", video_id)
        return UploadResult("uploaded", video_id)
    except HTTPError as exc:
        try:
            error = json.loads(exc.read(65536)).get("error", {})
            code, subcode = error.get("code"), error.get("error_subcode")
            # Only numeric error identifiers are safe to reflect into logs.
            codes = ", Graph code " + str(int(code)) if code is not None else ""
            codes += ", subcode " + str(int(subcode)) if subcode is not None else ""
        except (ValueError, TypeError, AttributeError, OSError):
            codes = ""
        return _retain(path, f"HTTP {exc.code}{codes}; check Page access, token expiry, pages_manage_posts permission and video limits")
    except Exception:  # Facebook failure must never prevent the existing Telegram send.
        return _retain(path, "network, file or response error; publication may be ambiguous, check the Page before retrying")
