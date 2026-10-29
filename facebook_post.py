"""Publish only verified 9:16 Facebook Page Reels; never ordinary /videos posts.

Standard-library, streamed start/upload/finish/status flow. Credentials are headers,
redirects are forbidden, and failures retain the source plus a recovery artifact.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

log = logging.getLogger("scanner")
ROOT = Path(__file__).resolve().parent
GRAPH_VERSION = "v25.0"
CHUNK_SIZE = 1024 * 1024
STATUS_ATTEMPTS = 12
STATUS_INTERVAL = 5
KIND = "facebook_reel_9x16"


@dataclass(frozen=True)
class UploadResult:
    status: str  # disabled, uploaded (publishing complete), failed (includes pending)
    video_id: str | None = None


def requested() -> bool:
    return bool(os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN") or os.getenv("FACEBOOK_PAGE_ID"))


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as video:
        for chunk in iter(lambda: video.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def _receipt(path: Path) -> Path:
    return path.with_name(path.name + ".facebook-upload.json")


def _read_receipt(path: Path) -> dict:
    try:
        info = json.loads(_receipt(path).read_text(encoding="utf-8"))
        if (info.get("kind") == KIND and info.get("page_id") == os.getenv("FACEBOOK_PAGE_ID", "").strip()
                and re.fullmatch(r"[1-9]\d*", str(info.get("video_id", "")))
                and path.is_file() and info.get("sha256") == _digest(path)):
            return info
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return {}


def published_id(path: Path) -> str | None:
    info = _read_receipt(Path(path))
    return str(info["video_id"]) if info.get("phase") == "published" else None


def _save(path: Path, info: dict, phase: str):
    info["phase"] = phase
    receipt = _receipt(path)
    temp = receipt.with_suffix(".tmp")
    temp.write_text(json.dumps(info), encoding="utf-8")
    temp.replace(receipt)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward credentials to another host.


class _VideoBody:
    """Raw file iterator for rupload; no multipart encoding and no whole-file RAM copy."""
    def __init__(self, path: Path):
        self.path = path
        self.size = path.stat().st_size

    def __iter__(self):
        with self.path.open("rb") as video:
            for chunk in iter(lambda: video.read(CHUNK_SIZE), b""):
                yield chunk


def dimensions(path: Path) -> tuple[int, int] | None:
    """Inspect the actual stream, never trust a filename or caller's width/height."""
    probe = shutil.which("ffprobe")
    if probe:
        result = subprocess.run([probe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                                 "stream=width,height,sample_aspect_ratio:stream_tags=rotate:stream_side_data=rotation",
                                 "-of", "json", str(path)], capture_output=True, text=True, timeout=30)
        if result.returncode:
            return None
        streams = json.loads(result.stdout).get("streams") or []
        if not streams:
            return None
        stream = streams[0]
        rotation = float((stream.get("tags") or {}).get("rotate") or 0)
        rotation += sum(float(s.get("rotation") or 0) for s in stream.get("side_data_list", []))
        if rotation % 360 or stream.get("sample_aspect_ratio") not in (None, "N/A", "1:1", "0:1"):
            return None
        return int(stream["width"]), int(stream["height"])
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            return None
    result = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=30)
    text = result.stderr
    if re.search(r"rotation of (?!0[. ])|rotate\s*:", text):
        return None
    size = re.search(r"Video:[^\n]*?\b(\d{2,5})x(\d{2,5})(?:[,\s\[])", text)
    if not size or re.search(r"SAR (?!1:1\b)\d+:\d+", text):
        return None
    return int(size[1]), int(size[2])


def retain_failure(path: Path, reason: str) -> UploadResult:
    path = Path(path)
    log.error("Facebook Reel publishing failed for %s: %s. Original video retained; Telegram will still be attempted.", path.name, reason)
    try:
        directory = Path(os.getenv("VIDEO_RECOVERY_DIR") or ROOT / "tmp" / "video-recovery")
        directory.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^a-zA-Z0-9_-]", "_", path.stem)[:80]
        recovery = directory / f"{stem}-{_digest(path)[:20]}.mp4"
        if not recovery.exists():
            shutil.copy2(path, recovery)
        if _receipt(path).exists():
            shutil.copy2(_receipt(path), _receipt(recovery))
        log.error("Facebook recovery video saved: %s (download the workflow's video-recovery artifact).", recovery)
    except OSError:
        log.error("Could not save Facebook recovery copy; original remains at %s. Preserve it before the runner exits.", path)
    return UploadResult("failed")


def _json(opener, request: Request) -> dict:
    with opener.open(request, timeout=600) as response:
        info = json.loads(response.read(65536).decode("utf-8"))
    if not isinstance(info, dict) or "error" in info:
        raise ValueError("invalid Graph response")
    return info


def _control(opener, endpoint, token, fields):
    return _json(opener, Request(endpoint, data=urlencode(fields).encode("utf-8"), method="POST",
                                headers={"Authorization": f"Bearer {token}",
                                         "Content-Type": "application/x-www-form-urlencoded"}))


def publish(path: Path, caption: str = "") -> UploadResult:
    """Publish a native Reel, failing closed on landscape/unknown dimensions.

    Persist progress before ambiguous requests. A later call resumes the same video ID
    or checks its status, rather than creating duplicate Reels. An old /videos receipt
    cannot masquerade as a successfully published Reel.
    """
    path = Path(path)
    if not requested():
        return UploadResult("disabled")
    token = os.getenv("FACEBOOK_PAGE_ACCESS_TOKEN", "").strip()
    page = os.getenv("FACEBOOK_PAGE_ID", "").strip()
    if not token or not re.fullmatch(r"[1-9]\d*", page):
        return retain_failure(path, "set both FACEBOOK_PAGE_ACCESS_TOKEN and a numeric FACEBOOK_PAGE_ID")
    try:
        if not path.is_file() or not path.stat().st_size:
            return retain_failure(path, "video file is missing or empty")
        size = dimensions(path)
        if not size or size[0] < 540 or size[1] < 960 or abs(size[0] / size[1] - 9 / 16) > 0.001:
            return retain_failure(path, "only inspected 9:16 portrait video (540x960 or larger) is allowed; no landscape fallback")
        info = _read_receipt(path)
        if info.get("phase") == "published":
            return UploadResult("uploaded", str(info["video_id"]))
        opener = build_opener(_NoRedirect())
        endpoint = f"https://graph.facebook.com/{GRAPH_VERSION}/{page}/video_reels"
        if not info:
            start = _control(opener, endpoint, token, {"upload_phase": "start"})
            video_id = str(start.get("video_id", ""))
            upload_url = str(start.get("upload_url", ""))
            url = urlsplit(upload_url)
            if (not re.fullmatch(r"[1-9]\d*", video_id) or url.scheme != "https"
                    or url.netloc != "rupload.facebook.com" or url.query or url.fragment
                    or not url.path.startswith("/video-upload/") or not url.path.endswith("/" + video_id)):
                return retain_failure(path, "invalid Reel session or untrusted upload URL; no credentials forwarded")
            info = {"kind": KIND, "video_id": video_id, "page_id": page, "sha256": _digest(path)}
            _save(path, info, "uploading")
            body = _VideoBody(path)
            uploaded = _json(opener, Request(upload_url, data=body, method="POST", headers={
                "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(body.size),
                "Content-Type": "application/octet-stream", "Content-Length": str(body.size)}))
            if uploaded.get("success") is not True:
                return retain_failure(path, "Reel byte transfer was not acknowledged")
            _save(path, info, "transferred")
        if info["phase"] == "uploading":
            return retain_failure(path, "previous byte transfer was interrupted or ambiguous; inspect the saved Reel ID before retrying")
        if info["phase"] == "transferred":
            _save(path, info, "finishing")
            finished = _control(opener, endpoint, token, {"upload_phase": "finish", "video_id": info["video_id"],
                "video_state": "PUBLISHED", "description": str(caption or "")[:5000],
                "title": (str(caption or "").splitlines() or ["PlayReport ZA"])[0][:100]})
            if finished.get("success") is not True:
                return retain_failure(path, "Reel publication was not acknowledged; inspect the saved Reel ID")
        for attempt in range(STATUS_ATTEMPTS):
            status = _json(opener, Request(f"https://graph.facebook.com/{GRAPH_VERSION}/{info['video_id']}?fields=status",
                                         headers={"Authorization": f"Bearer {token}"})).get("status") or {}
            if status.get("video_status") == "error" or any(
                    (status.get(phase) or {}).get("status") in ("error", "failed")
                    for phase in ("uploading_phase", "processing_phase", "publishing_phase")):
                return retain_failure(path, "Facebook rejected the Reel during processing/publication; inspect its saved ID and media requirements")
            if (status.get("publishing_phase") or {}).get("status") == "complete":
                _save(path, info, "published")
                log.info("Facebook: 9:16 Reel published for PlayReport ZA (video ID %s).", info["video_id"])
                return UploadResult("uploaded", str(info["video_id"]))
            if attempt + 1 < STATUS_ATTEMPTS:
                time.sleep(STATUS_INTERVAL)
        return retain_failure(path, "Reel publication still pending; source and session ID retained, no duplicate POST")
    except HTTPError as exc:
        try:
            error = json.loads(exc.read(65536)).get("error", {})
            code, subcode = error.get("code"), error.get("error_subcode")
            codes = ", Graph code " + str(int(code)) if code is not None else ""
            codes += ", subcode " + str(int(subcode)) if subcode is not None else ""
        except (ValueError, TypeError, AttributeError, OSError):
            codes = ""
        return retain_failure(path, f"HTTP {exc.code}{codes}; check Page access, token expiry, Reel permissions and media limits")
    except Exception:
        return retain_failure(path, "network, inspection, file or response error; inspect the saved Reel ID before retrying")
