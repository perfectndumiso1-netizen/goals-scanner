"""YouTube auto-poster for Mr 2 Odds videos — probe, upload, check, publish, delete.

The videos are already built and sent to Telegram each day; this module is the second delivery lane. It talks to
the YouTube Data API directly with `requests` (no google-api-python-client, so the hashed requirements stay as they
are) and it is deliberately conservative:

* **Nothing runs unless the three credentials are set** (`YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`) *and*
  `YT_UPLOAD` is switched on. A scan on a repository with no YouTube secrets behaves exactly as before.
* **`probe` is the first thing to run, not `upload`.** An unaudited Google Cloud project gets its uploads *locked*
  as private — the call succeeds, the video is invisible, and it cannot be appealed or flipped by hand; the only fix
  is re-uploading through an audited client. `probe` uploads a three-second test clip as unlisted, reads back the
  privacy YouTube actually gave it, and deletes it. If it comes back private, the project needs the audit (or a
  third-party verified uploader) and this module is not ready to publish.
* **Metadata never promotes a bookmaker.** Betting content on YouTube is age-restricted and may only point at
  Google-certified gambling services, so titles, descriptions and tags carry the analysis and the 18+ line — no
  operator names, no affiliate or deep links.
* **One video per slot at most, and the slot is opt-in.** `YT_SLOTS` (default `morning`) decides which of the day's
  shortlist videos go up; the match breakdown has its own switch (`YT_UPLOAD_BREAKDOWN`, default on). Daily
  near-identical uploads are what YouTube's inauthentic-content policy targets, so the default is two a day, not six.

Commands (all read the same env):

    python youtube_post.py info                      # who am I, what scopes does the token have, how many subs
    python youtube_post.py probe                     # upload a 3s clip unlisted, report + delete  ← run this first
    python youtube_post.py upload FILE [options]     # publish a video (uses FILE.json metadata when present)
    python youtube_post.py status VIDEO_ID           # actual privacy/upload status
    python youtube_post.py publish VIDEO_ID          # flip a private video to public
    python youtube_post.py delete VIDEO_ID           # remove a video

One-time authorisation lives in `scripts/yt_auth.py` (loopback OAuth, prints the refresh token).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import requests

log = logging.getLogger("scanner")

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"

# `youtube` covers insert + update + delete, so a probe can clean up after itself and a locked upload can be
# inspected. `youtube.upload` alone would be enough to publish but leaves junk behind.
SCOPE = "https://www.googleapis.com/auth/youtube"
SCOPES = [SCOPE]

CATEGORY_SPORTS = "17"
PRIVACY = ("public", "unlisted", "private")

DISCLAIMER = (
    "Statistical information, not betting advice. 18+ only. Never bet money you cannot afford to lose — "
    "there is no such thing as a sure bet."
)
TAGS = ["football stats", "football analysis", "over 1.5 goals", "corners", "bookings", "match preview"]
TITLE_MAX = 100
DESC_MAX = 4600          # bytes, under the API's 5000 ceiling


class YTError(RuntimeError):
    """A YouTube API call failed. The message is safe to log."""


# ------------------------------------------------------------------ credentials

@dataclass(frozen=True)
class Creds:
    client_id: str
    client_secret: str
    refresh_token: str

    def __repr__(self) -> str:                      # never print secrets into a log
        return f"Creds(client_id={'set' if self.client_id else 'missing'}, refresh_token=<hidden>)"


def creds_from_env() -> Creds | None:
    cid = (os.getenv("YT_CLIENT_ID") or "").strip()
    secret = (os.getenv("YT_CLIENT_SECRET") or "").strip()
    refresh = (os.getenv("YT_REFRESH_TOKEN") or "").strip()
    if not (cid and secret and refresh):
        return None
    return Creds(cid, secret, refresh)


def configured() -> bool:
    """True when the channel credentials are present. Never raises."""
    return creds_from_env() is not None


def enabled() -> bool:
    """`YT_UPLOAD=1` plus credentials: the scan only posts when both say yes."""
    return _truthy(os.getenv("YT_UPLOAD")) and configured()


def _truthy(v: str | None) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def slots() -> set[str]:
    """Which shortlist videos go to YouTube (default: the morning one). `YT_SLOTS=morning,noon,evening` for all."""
    raw = os.getenv("YT_SLOTS", "morning")
    return {s.strip().lower() for s in raw.split(",") if s.strip()}


def slot_allowed(slot: str) -> bool:
    return str(slot or "").strip().lower() in slots()


def breakdown_enabled() -> bool:
    return _truthy(os.getenv("YT_UPLOAD_BREAKDOWN", "1"))


def default_privacy() -> str:
    p = (os.getenv("YT_PRIVACY") or "public").strip().lower()
    return p if p in PRIVACY else "public"


# ------------------------------------------------------------------ http plumbing

def _request(method: str, url: str, **kw) -> requests.Response:
    """Single seam for tests: every call in this module goes through here."""
    kw.setdefault("timeout", 120)
    return requests.request(method, url, **kw)


def _json(resp: requests.Response, what: str) -> dict:
    if resp.status_code >= 400:
        raise YTError(f"{what} failed ({resp.status_code}): {resp.text[:400]}")
    try:
        return resp.json()
    except ValueError as exc:
        raise YTError(f"{what} returned non-JSON: {resp.text[:200]}") from exc


def access_token(creds: Creds) -> str:
    """Exchange the long-lived refresh token for an access token."""
    resp = _request("POST", TOKEN_URL, data={
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "refresh_token": creds.refresh_token,
        "grant_type": "refresh_token",
    })
    body = _json(resp, "token refresh")
    tok = body.get("access_token")
    if not tok:
        raise YTError(f"token refresh returned no access_token: {body}")
    return str(tok)


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def token_scopes(token: str) -> list[str]:
    """Scopes actually granted (a refresh token made before we asked for `youtube` will be narrower)."""
    try:
        resp = _request("GET", "https://oauth2.googleapis.com/tokeninfo", params={"access_token": token})
        body = _json(resp, "tokeninfo")
    except YTError:
        return []
    return str(body.get("scope") or "").split()


def channel_info(token: str) -> dict:
    resp = _request("GET", f"{API}/channels", params={"part": "snippet,statistics", "mine": "true"},
                    headers=_headers(token))
    items = _json(resp, "channels.list").get("items") or []
    if not items:
        raise YTError("this Google account has no YouTube channel")
    ch = items[0]
    sn, stats = ch.get("snippet") or {}, ch.get("statistics") or {}
    return {
        "id": ch.get("id"),
        "title": sn.get("title"),
        "country": sn.get("country"),
        "subscribers": int(stats.get("subscriberCount") or 0),
        "videos": int(stats.get("videoCount") or 0),
        "views": int(stats.get("viewCount") or 0),
    }


# ------------------------------------------------------------------ metadata

def clean(text: str, limit: int) -> str:
    """YouTube rejects `<` and `>` in titles/descriptions, and caps both."""
    out = str(text or "").replace("<", "(").replace(">", ")")
    out = " ".join(out.split())
    if len(out.encode("utf-8")) <= limit:
        return out
    cut, size = [], 0
    for word in out.split():
        size += len(word.encode("utf-8")) + 1
        if size > limit:
            break
        cut.append(word)
    return " ".join(cut).rstrip(" ,.;:-")


def _odds(x: dict) -> str:
    try:
        return f"{float(x.get('odds')):.2f}"
    except (TypeError, ValueError):
        return ""


def _pick_line(x: dict) -> str:
    home, away = str(x.get("home") or "").strip(), str(x.get("away") or "").strip()
    label = str(x.get("label") or x.get("sel") or "").strip()
    odds = _odds(x)
    line = f"{home} v {away} — {label}" if label else f"{home} v {away}"
    return f"{line} ({odds})" if odds else line


def description_for_shortlist(day: str, picks: list[dict], *, recap: str = "") -> str:
    lines = [f"Today's shortlist for {day}: the matches Mr 2 Odds rates, and why each one made the list.",
             "Over 1.5 total goals, team goals, corners and bookings only. Every selection is a single — "
             "no accumulators."]
    if recap:
        lines.append(clean(recap, 400))
    body = "\n".join(f"• {_pick_line(p)}" for p in (picks or [])[:20])
    if body:
        lines += ["", "On the card:", body]
    lines += ["", DISCLAIMER]
    return clean("\n".join(lines), DESC_MAX)


def description_for_breakdown(day: str, matches: list[dict], *, credits: str = "") -> str:
    lines = [f"Match breakdown for {day}: recent form, home and away splits, head to head, team news and the pick "
             f"for each game — explained from the numbers, revealed at the end of each match."]
    names = [f"{m.get('home')} v {m.get('away')}" for m in (matches or [])[:10]]
    if names:
        lines += ["", "This episode:", "\n".join(f"• {n}" for n in names)]
    if credits:
        lines += ["", clean(credits, 900)]
    lines += ["", DISCLAIMER]
    return clean("\n".join(lines), DESC_MAX)


def title_for(day: str, n: int, *, kind: str = "shortlist", label: str = "") -> str:
    if kind == "breakdown":
        return clean(f"Match Breakdown | {n} games, form, team news and the pick | {day}", TITLE_MAX)
    tail = f" | {label}" if label else ""
    return clean(f"Football Shortlist | Over 1.5, corners & bookings | {day}{tail}", TITLE_MAX)


def tags() -> list[str]:
    """Under the 500-character total budget, including separators."""
    out, size = [], 0
    for t in TAGS:
        if size + len(t) + 1 > 480:
            break
        out.append(t)
        size += len(t) + 1
    return out


def meta(*, kind: str, day: str, items: list[dict], recap: str = "", credits: str = "", label: str = "") -> dict:
    """The sidecar written next to a built video; also the primary argument to `upload`."""
    desc = (description_for_breakdown(day, items, credits=credits) if kind == "breakdown"
            else description_for_shortlist(day, items, recap=recap))
    return {
        "kind": kind,
        "title": title_for(day, len(items or []), kind=kind, label=label),
        "description": desc,
        "tags": tags(),
        "categoryId": CATEGORY_SPORTS,
        "madeForKids": False,
    }


def write_meta(video: Path, m: dict) -> Path:
    """`briefing-16x9.mp4` → `briefing-16x9.mp4.json`, so the upload step never rebuilds wording."""
    video = Path(video)
    side = video.with_suffix(video.suffix + ".json")
    side.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
    return side


def read_meta(video: Path) -> dict:
    video = Path(video)
    side = video.with_suffix(video.suffix + ".json")
    if not side.exists():
        return {}
    try:
        data = json.loads(side.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


# ------------------------------------------------------------------ upload

def _metadata(m: dict, privacy: str, publish_at: str | None) -> dict:
    snippet = {
        "title": clean(m.get("title") or "", TITLE_MAX) or "Mr 2 Odds",
        "description": clean(m.get("description") or "", DESC_MAX),
        "tags": [clean(t, 60) for t in (m.get("tags") or TAGS)][:30],
        "categoryId": str(m.get("categoryId") or CATEGORY_SPORTS),
    }
    status: dict = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": bool(m.get("madeForKids", False)),
    }
    if publish_at:
        status["privacyStatus"] = "private"          # YouTube only schedules a video that is private
        status["publishAt"] = publish_at
    return {"snippet": snippet, "status": status}


def upload_video(path: Path, meta: dict, *, creds: Creds | None = None, privacy: str | None = None,
                 publish_at: str | None = None, token: str | None = None) -> dict:
    """Resumable upload, one request for the bytes (our files are ~5–10 MB).

    Returns `{"id", "privacy", "requested", "locked", "status"}`. `locked` is the signal that the Cloud project is
    unaudited: YouTube accepted the upload but pinned it private and it cannot be appealed — re-upload via an
    audited client (or the web) or finish the audit.
    """
    path = Path(path)
    if not path.exists():
        raise YTError(f"video not found: {path}")
    privacy = (privacy or default_privacy()).lower()
    if privacy not in PRIVACY:
        raise YTError(f"privacy must be one of {PRIVACY}, got {privacy!r}")
    if publish_at and privacy != "private":
        privacy = "private"                          # scheduling always goes through private first
    creds = creds or creds_from_env()
    if creds is None and not token:
        raise YTError("YouTube credentials are not configured (YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN)")
    token = token or access_token(creds)
    body = _metadata(meta, privacy, publish_at)
    size = path.stat().st_size

    init = _request(
        "POST", f"{UPLOAD_URL}?uploadType=resumable&part=snippet,status",
        headers={**_headers(token), "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Length": str(size), "X-Upload-Content-Type": "video/mp4"},
        data=json.dumps(body),
    )
    if init.status_code >= 400:
        raise YTError(f"upload start failed ({init.status_code}): {init.text[:400]}")
    location = init.headers.get("Location") or init.headers.get("location")
    if not location:
        raise YTError("upload start returned no Location header")

    with path.open("rb") as fh:
        sent = _request("PUT", location, headers={**_headers(token), "Content-Type": "video/mp4",
                                                 "Content-Length": str(size)}, data=fh)
    got = _json(sent, "upload")
    vid = got.get("id")
    if not vid:
        raise YTError(f"upload returned no video id: {str(got)[:300]}")
    actual = str((got.get("status") or {}).get("privacyStatus") or "")
    result = {
        "id": vid,
        "privacy": actual,
        "requested": privacy,
        "locked": bool(privacy in ("public", "unlisted") and actual == "private"),
        "status": got.get("status") or {},
        "title": (got.get("snippet") or {}).get("title"),
    }
    log.info("YouTube: uploaded %s → https://youtu.be/%s (requested %s, got %s)", path.name, vid, privacy, actual)
    if result["locked"]:
        log.warning("YouTube: video %s came back PRIVATE although %s was requested — the API project is not audited. "
                    "Locked uploads cannot be appealed or made public by hand; re-upload via an audited client or "
                    "the YouTube site, or finish the audit. See `python youtube_post.py probe`.", vid, privacy)
    return result


def video_status(video_id: str, *, creds: Creds | None = None, token: str | None = None) -> dict:
    token = token or access_token(creds or creds_from_env())
    resp = _request("GET", f"{API}/videos", params={"part": "status,snippet", "id": video_id},
                    headers=_headers(token))
    items = _json(resp, "videos.list").get("items") or []
    if not items:
        raise YTError(f"video {video_id} not found on this channel")
    it = items[0]
    return {"id": it.get("id"), "status": it.get("status") or {},
            "privacy": (it.get("status") or {}).get("privacyStatus"),
            "title": (it.get("snippet") or {}).get("title")}


def set_privacy(video_id: str, privacy: str, *, creds: Creds | None = None, token: str | None = None) -> dict:
    """Flip a video's visibility. Works for ordinary private videos, not for ones locked by an unverified project."""
    if privacy not in PRIVACY:
        raise YTError(f"privacy must be one of {PRIVACY}")
    token = token or access_token(creds or creds_from_env())
    body = {"id": video_id, "status": {"privacyStatus": privacy}}
    resp = _request("PUT", f"{API}/videos?part=status", headers={**_headers(token),
                    "Content-Type": "application/json; charset=UTF-8"}, data=json.dumps(body))
    got = _json(resp, "videos.update")
    return {"id": got.get("id"), "privacy": (got.get("status") or {}).get("privacyStatus")}


def delete_video(video_id: str, *, creds: Creds | None = None, token: str | None = None) -> bool:
    token = token or access_token(creds or creds_from_env())
    resp = _request("DELETE", f"{API}/videos", params={"id": video_id}, headers=_headers(token))
    if resp.status_code >= 400:
        raise YTError(f"delete failed ({resp.status_code}): {resp.text[:300]}")
    return True


# ------------------------------------------------------------------ probe

def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def probe_clip(dest: Path, *, seconds: float = 3.0) -> Path:
    """A tiny black-and-silent clip — long enough for YouTube to accept it, useless enough to delete after."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [_ffmpeg(), "-y",
           "-f", "lavfi", "-i", f"color=c=black:s=640x360:r=30:d={seconds}",
           "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
           "-shortest", "-t", f"{seconds}", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "64k", str(dest)]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0 or not dest.exists():
        raise YTError(f"could not build the probe clip:\n{r.stdout[-800:]}")
    return dest


def probe(*, work: Path | None = None, keep: bool = False) -> dict:
    """Can this project publish? Upload a 3 s clip as unlisted, read back the real privacy, then delete it."""
    creds = creds_from_env()
    if creds is None:
        raise YTError("YouTube credentials are not configured (YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN)")
    token = access_token(creds)
    info = channel_info(token)
    scopes = token_scopes(token)
    work = Path(work) if work else Path(tempfile.mkdtemp(prefix="yt-probe-"))
    clip = probe_clip(work / "probe.mp4")
    try:
        res = upload_video(clip, {
            "title": "Mr 2 Odds API probe", "description": "Automatic upload check. Deleting this clip.",
            "tags": ["probe"], "categoryId": "22", "madeForKids": False,
        }, token=token, privacy="unlisted")
        # Re-read from the API: the upload response is the best source, but a second look catches a delayed lock.
        if not res["locked"]:
            time.sleep(2)
            try:
                again = video_status(res["id"], token=token)
                res["privacy"] = again.get("privacy") or res["privacy"]
                res["locked"] = res["privacy"] == "private"
            except YTError as exc:
                log.info("YouTube: could not re-read probe status (%s)", exc)
        res.update({"channel": info, "scopes": scopes, "clip": str(clip)})
        if not keep:
            try:
                delete_video(res["id"], token=token)
                res["deleted"] = True
            except YTError as exc:
                res["deleted"] = False
                res["delete_error"] = str(exc)
        return res
    finally:
        if not keep:
            try:
                clip.unlink()
            except OSError:
                pass


def report(res: dict) -> str:
    """Human answer to 'will this project publish, or do I need the audit?'."""
    if res.get("locked"):
        return ("LOCKED — the API project is not audited. YouTube accepted the upload and pinned it private; that "
                "cannot be appealed or changed by hand. Either finish the audit, upload through the YouTube site, or "
                "post via a verified third-party tool.")
    if res.get("privacy") in ("public", "unlisted"):
        return f"OK — uploads can publish ({res.get('privacy')}). This project needs no audit."
    return f"UNEXPECTED — requested unlisted, YouTube reports {res.get('privacy')!r}."


# ------------------------------------------------------------------ scan hooks

def publish_shortlist(video: Path, *, day: str, picks: list[dict], recap: str = "", slot: str = "morning") -> dict | None:
    """Called by the scan after a shortlist video is built. Returns the upload result, or None when skipped."""
    if not enabled() or not slot_allowed(slot):
        return None
    m = meta(kind="shortlist", day=day, items=picks, recap=recap, label=slot.title())
    write_meta(video, m)
    return upload_video(video, m)


def publish_breakdown(video: Path, *, day: str, matches: list[dict], credits: str = "") -> dict | None:
    if not enabled() or not breakdown_enabled():
        return None
    m = meta(kind="breakdown", day=day, items=matches, credits=credits)
    write_meta(video, m)
    return upload_video(video, m)


# ------------------------------------------------------------------ cli

def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mr 2 Odds YouTube auto-poster")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("info", help="channel identity, granted scopes and audience")
    p_probe = sub.add_parser("probe", help="upload a 3s clip unlisted and report whether it can publish")
    p_probe.add_argument("--keep", action="store_true", help="leave the clip on the channel (private/unlisted)")

    p_up = sub.add_parser("upload", help="upload a video")
    p_up.add_argument("file")
    p_up.add_argument("--title")
    p_up.add_argument("--description")
    p_up.add_argument("--tags", help="comma separated")
    p_up.add_argument("--privacy", choices=PRIVACY, default=None)
    p_up.add_argument("--publish-at", help="ISO 8601 e.g. 2026-10-22T05:30:00Z")

    p_st = sub.add_parser("status")
    p_st.add_argument("video_id")

    p_pub = sub.add_parser("publish", help="make a private video public")
    p_pub.add_argument("video_id")
    p_pub.add_argument("--privacy", choices=PRIVACY, default="public")

    p_del = sub.add_parser("delete")
    p_del.add_argument("video_id")

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.cmd == "info":
        token = access_token(creds_from_env())
        info = channel_info(token)
        print(json.dumps({**info, "scopes": token_scopes(token)}, indent=2))
        return 0
    if args.cmd == "probe":
        res = probe(keep=args.keep)
        print(json.dumps({k: v for k, v in res.items() if k != "status"}, indent=2))
        print("\n" + report(res))
        return 0 if not res.get("locked") else 2
    if args.cmd == "upload":
        path = Path(args.file)
        m = read_meta(path)
        if args.title:
            m["title"] = args.title
        if args.description:
            m["description"] = args.description
        if args.tags:
            m["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
        m.setdefault("title", title_for(time.strftime("%a %d %b")))
        m.setdefault("description", DISCLAIMER)
        res = upload_video(path, m, privacy=args.privacy, publish_at=args.publish_at)
        print(json.dumps({k: res[k] for k in ("id", "privacy", "requested", "locked")}, indent=2))
        return 0 if not res["locked"] else 2
    if args.cmd == "status":
        print(json.dumps(video_status(args.video_id), indent=2))
        return 0
    if args.cmd == "publish":
        print(json.dumps(set_privacy(args.video_id, args.privacy), indent=2))
        return 0
    if args.cmd == "delete":
        delete_video(args.video_id)
        print(f"deleted {args.video_id}")
        return 0
    return 1


if __name__ == "__main__":                                   # pragma: no cover
    try:
        sys.exit(_main())
    except YTError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
