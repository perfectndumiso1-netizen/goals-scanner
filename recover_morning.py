"""Recover a missed morning edition from today's already-published Advisor.

Runs the existing verifier/renderers/delivery lanes, without a 60-day rescan,
changing published selections, deleting a sent-slot marker or weakening quality gates.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import advisor_tracking
import scanner

SAST = ZoneInfo("Africa/Johannesburg")


def run(now=None):
    now = (now or datetime.now(SAST)).astimezone(SAST)
    today = now.date().isoformat()
    report = {"date": today, "edition": "morning", "status": "not_sent", "deliveries": {}}
    output = Path(os.getenv("VIDEO_RECOVERY_REPORT", "tmp/morning-recovery/result.json"))
    def finish(code, status, message):
        report.update(status=status, message=message)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        annotation = "error" if code else "notice"
        # Messages contain only our own diagnostics and public delivery IDs, never tokens or exceptions.
        print(f"::{annotation}::{message}", flush=True)
        if os.getenv("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as target:
                target.write("## Morning video recovery\n\n" + message + "\n\n```json\n" + json.dumps(report, ensure_ascii=False, indent=2) + "\n```\n")
        return code
    _, state = scanner._telegram_state(now)
    if "morning" in (state.get("briefing_slots") or {}).get(today, []):
        return finish(0, "already_delivered", "Morning edition is already recorded as delivered today. Nothing resent.")
    try:
        payload = json.loads(scanner.APP_FILE.read_text(encoding="utf-8"))
        generated = datetime.fromisoformat(str((payload.get("meta") or {}).get("generated")))
        generated = generated.replace(tzinfo=SAST) if generated.tzinfo is None else generated.astimezone(SAST)
    except (OSError, ValueError, TypeError):
        return finish(1, "blocked", "Today's published Advisor data is missing or invalid. No video sent.")
    if generated.date() != now.date() or not timedelta(0) <= now - generated <= timedelta(hours=6):
        return finish(1, "blocked", "Published Advisor is not fresh enough for today's recovery. Run the scanner first; no stale video sent.")
    if scanner.reel_mod is None:
        return finish(1, "blocked", "Video renderer could not be imported. No video sent.")
    pool = advisor_tracking.selections(payload)
    used = {(str(p.get("home") or ""), str(p.get("away") or ""))
            for p in (state.get("briefing_history") or {}).get(today, [])}
    picks, dropped = scanner.reel_mod.video_picks(pool, used=used, fx_dir=scanner.APP_FILE.parent / "fx", now=now)
    report.update(source_generated=generated.isoformat(), candidates=len(pool), verified_card=len(picks), dropped=dropped)
    print(f"::notice::Morning recovery: {len(pool)} published candidates; {len(picks)} selections in the verified card; {len(dropped)} exclusions.", flush=True)
    if len(picks) < 5:
        return finish(1, "blocked", "Fewer than five verified Advisor matches fit the required combined-odds range. No padding, no video sent. Exclusion reasons are in the recovery report.")
    old_force, old_edition = os.environ.get("FORCE_DAILY_REEL"), os.environ.get("DAILY_REEL_EDITION")
    os.environ["FORCE_DAILY_REEL"] = "true"
    os.environ["DAILY_REEL_EDITION"] = "morning"
    originals = {"telegram": scanner.send_telegram_video, "facebook": scanner.facebook_mod.publish}
    if scanner.yt_mod is not None:
        originals["youtube"] = scanner.yt_mod.publish_shortlist
    if scanner.drive_mod is not None:
        originals["drive"] = scanner.drive_mod.handoff
    def telegram(*args, **kwargs):
        ok = originals["telegram"](*args, **kwargs)
        report["deliveries"]["telegram"] = {"delivered": bool(ok)}
        print(f"::notice::Morning video Telegram delivery: {'confirmed' if ok else 'not confirmed'}.", flush=True)
        return ok
    def facebook(*args, **kwargs):
        result = originals["facebook"](*args, **kwargs)
        report["deliveries"]["facebook"] = {"status": result.status, "reel_id": result.video_id}
        print(f"::notice::Morning Facebook Reel: {result.status}; ID {result.video_id or 'none'}.", flush=True)
        return result
    def youtube(*args, **kwargs):
        result = originals["youtube"](*args, **kwargs)
        report["deliveries"]["youtube"] = {"delivered": bool(result), "id": result.get("id") if isinstance(result, dict) else None}
        return result
    def drive(*args, **kwargs):
        result = originals["drive"](*args, **kwargs)
        report["deliveries"]["drive"] = {"handed_off": bool(result)}
        return result
    scanner.send_telegram_video = telegram
    scanner.facebook_mod.publish = facebook
    if "youtube" in originals:
        scanner.yt_mod.publish_shortlist = youtube
    if "drive" in originals:
        scanner.drive_mod.handoff = drive
    try:
        scanner.maybe_send_daily_reel({}, now)
    finally:
        scanner.send_telegram_video = originals["telegram"]
        scanner.facebook_mod.publish = originals["facebook"]
        if "youtube" in originals:
            scanner.yt_mod.publish_shortlist = originals["youtube"]
        if "drive" in originals:
            scanner.drive_mod.handoff = originals["drive"]
        for key, value in (("FORCE_DAILY_REEL", old_force), ("DAILY_REEL_EDITION", old_edition)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    _, after = scanner._telegram_state(now)
    if "morning" not in (after.get("briefing_slots") or {}).get(today, []):
        return finish(1, "not_delivered", "No successful morning delivery was recorded. See renderer logs and recovery artifacts; not claiming success.")
    return finish(0, "delivered", "Morning edition delivered through at least one configured lane. Per-lane confirmations are recorded in this report; a Drive handoff alone is not a confirmed YouTube publication.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", help="Dated push-trigger request file")
    args = parser.parse_args(argv)
    if args.request:
        request = json.loads(Path(args.request).read_text(encoding="utf-8"))
        if request.get("date") != datetime.now(SAST).date().isoformat() or request.get("edition") != "morning":
            print("::notice::Recovery request is not for today's morning edition; nothing sent.")
            return 0
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
