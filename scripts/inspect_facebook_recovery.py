"""Read-only inspection of an existing recovery run. Never calls Meta or delivery code.

Only safe, known publisher diagnostics and selected MP4 metadata are reported.
Raw logs, signed storage URLs and GitHub credentials are never printed/uploaded.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def github_download(repo, endpoint, destination, token):
    """Use the token only on api.github.com, never on the signed storage request."""
    opener = build_opener(NoRedirect())
    request = Request(f"https://api.github.com/repos/{repo}/{endpoint}", headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "PlayReport-read-only-investigation"})
    try:
        response = opener.open(request, timeout=60)
    except HTTPError as error:
        if error.code not in (301, 302, 303, 307):
            raise RuntimeError(f"GitHub API HTTP {error.code}") from None
        location = error.headers.get("Location", "")
        url = urlsplit(location)
        host = url.hostname or ""
        if url.scheme != "https" or not (host.endswith(".blob.core.windows.net") or host.endswith(".githubusercontent.com")):
            raise RuntimeError("Unexpected GitHub storage host; refusing credential forwarding") from None
        # A new Request with NO Authorization header; redirects still disabled.
        response = opener.open(Request(location), timeout=180)
    with response, Path(destination).open("wb") as target:
        shutil.copyfileobj(response, target, length=1024*1024)


def safe_evidence(log):
    """Whitelisted facts only, not raw exception/log lines (which might contain URLs)."""
    facts = []
    for line in log.splitlines():
        built = re.search(r"reel built (briefing-[a-zA-Z0-9_.-]+) \[(16:9|9:16)\] \(([0-9.]+)s, ([0-9]+) KB\)", line)
        if built:
            facts.append({"event": "render_complete", "file": built[1], "aspect": built[2],
                          "duration_seconds": float(built[3]), "size_kb": int(built[4])})
        if "Facebook 9:16 Reel render failed; Telegram will continue" in line:
            facts.append({"event": "portrait_render_failed"})
        if "Facebook Reel publishing failed for " not in line:
            continue
        file = re.search(r"publishing failed for ([a-zA-Z0-9_.-]+):", line)
        fact = {"event": "facebook_failure", "file": file[1] if file else "unknown"}
        http = re.search(r"HTTP (\d{3})(?:, Graph code (\d+))?(?:, subcode (\d+))?; check Page access", line)
        if http:
            fact.update(http_status=int(http[1]), graph_code=int(http[2]) if http[2] else None,
                        graph_subcode=int(http[3]) if http[3] else None)
        elif "set both FACEBOOK_PAGE_ACCESS_TOKEN and a numeric FACEBOOK_PAGE_ID" in line:
            fact["reason"] = "missing Page token or invalid/missing numeric Page ID (local preflight; no Meta request)"
        elif "only inspected 9:16 portrait video" in line:
            fact["reason"] = "portrait dimension/stream inspection failed before upload"
        elif "9:16 Reel render is missing" in line:
            fact["reason"] = "portrait file missing; landscape fallback blocked"
        elif "invalid Reel session or untrusted upload URL" in line:
            fact["reason"] = "start response failed session/upload-URL validation"
        elif "previous byte transfer was interrupted or ambiguous" in line:
            fact["reason"] = "ambiguous previous transfer; retry blocked"
        elif "during processing/publication" in line:
            fact["reason"] = "Meta reported a processing/publication error"
        elif "publication still pending" in line:
            fact["reason"] = "Meta publication still pending after polling"
        elif "network, inspection, file or response error" in line:
            fact["reason"] = "generic network/file/response exception; original code discarded details"
        else:
            fact["reason"] = "publisher failure; unclassified details deliberately omitted"
        facts.append(fact)
    return facts


def inspect_video(path):
    process = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,sample_aspect_ratio:stream_tags=rotate:stream_side_data=rotation",
        "-of", "json", str(path)], capture_output=True, text=True, timeout=60, check=True)
    meta = json.loads(process.stdout)
    return {"file": path.name, "bytes": path.stat().st_size, "streams": meta.get("streams", []),
            "duration_seconds": float((meta.get("format") or {})["duration"])}


def inspect_archive(archive, output):
    videos, receipts = [], []
    wanted = {"briefing-16x9.mp4", "briefing-9x16-reel.mp4"}
    with zipfile.ZipFile(archive) as source:
        for item in source.infolist():
            name = Path(item.filename).name
            if name in wanted:
                path = Path(output) / name  # Never use the archive's path (zip-slip protection).
                with source.open(item) as data, path.open("wb") as target:
                    shutil.copyfileobj(data, target, 1024*1024)
                videos.append(inspect_video(path))
            elif name.endswith(".facebook-upload.json") and item.file_size < 65536:
                data = json.loads(source.read(item))
                receipts.append({key: data.get(key) for key in ("kind", "phase", "video_id", "sha256")})
    return videos, receipts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text())
    repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GH_READ_TOKEN"]
    run, job, artifact = (str(request[key]) for key in ("run_id", "job_id", "artifact_id"))
    if not all(re.fullmatch(r"[1-9]\d*", value) for value in (run, job, artifact)):
        raise SystemExit("Invalid diagnostic IDs")
    output = Path("tmp/facebook-investigation")
    output.mkdir(parents=True, exist_ok=True)
    raw = Path("tmp/facebook-investigation-private")
    raw.mkdir(parents=True, exist_ok=True)
    report = {"source_run": run, "source_job": job, "source_artifact": artifact,
              "read_only": True, "publishing_attempts": 0}
    try:
        logs = raw / "job.log"
        github_download(repo, f"actions/jobs/{job}/logs", logs, token)
        report["log_evidence"] = safe_evidence(logs.read_text(encoding="utf-8", errors="replace"))
    except Exception as error:
        report["log_fetch_error"] = type(error).__name__  # Never expose a signed URL or raw exception.
    try:
        media = raw / "recovery.zip"
        github_download(repo, f"actions/artifacts/{artifact}/zip", media, token)
        report["videos"], report["receipts"] = inspect_archive(media, raw)
    except Exception as error:
        report["media_inspection_error"] = type(error).__name__
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("::notice::Read-only Facebook investigation: " + json.dumps(report, separators=(",", ":")), flush=True)
    with open(os.environ.get("GITHUB_STEP_SUMMARY", str(output / "summary.md")), "a") as target:
        target.write("## Read-only Facebook recovery investigation\n\n```json\n" + json.dumps(report, indent=2) + "\n```\n")
    # Never include raw logs, storage archives or extracted videos in the diagnostic artifact.
    shutil.rmtree(raw)
    if report.get("log_fetch_error") and report.get("media_inspection_error"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
