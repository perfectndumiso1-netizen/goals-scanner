"""Deliver an in-window edition or explicitly recover a named Advisor video.

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



def refresh_h2h(pool, now):
    """Repair missing contextual H2H from genuine provider archive, never change a published pick/price."""
    import shortlist_reel
    import reel_verify
    import worldfeed
    import quality
    wanted, details = {}, {}
    for pick in pool:
        try:
            kickoff = datetime.fromisoformat(str(pick.get("kickoff")))
            kickoff = kickoff.replace(tzinfo=SAST) if kickoff.tzinfo is None else kickoff.astimezone(SAST)
        except (ValueError, TypeError):
            continue
        if kickoff <= now:
            continue
        path = scanner.APP_FILE.parent / "fx" / (shortlist_reel._fx_key(pick) + ".json")
        try:
            detail = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        problems = reel_verify.stats_problems(pick, detail, now=now)
        if not problems or any("head-to-head" not in reason for reason in problems):
            continue
        div = str(detail.get("div") or "")
        if not div.startswith("LS:") or "/" not in div:
            continue
        stage = div[3:]
        wanted[stage] = 100
        details[path] = (detail, stage)
    if not wanted:
        return {"refreshed_fixtures": 0}
    archive = worldfeed.Archive(scanner.LS_DIR)
    outcome = archive.backfill(wanted, now, seasons=2, budget_s=90, max_requests=24)
    archive.save()
    refreshed = 0
    for path, (detail, stage) in details.items():
        home, away = reel_verify._norm(detail.get("home")), reel_verify._norm(detail.get("away"))
        meetings = {}
        for event_id, record in (archive.load(stage).get("events") or {}).items():
            try:
                stamp, _, h, _, a, hg, ag, _, _ = record
                when = datetime.strptime(str(stamp), "%Y%m%d%H%M")
                if when >= now.replace(tzinfo=None) or when < now.replace(tzinfo=None) - timedelta(days=1100):
                    continue
                if (reel_verify._norm(h), reel_verify._norm(a)) not in ((home,away),(away,home)):
                    continue
                if hg is None or ag is None or int(hg) != float(hg) or int(ag) != float(ag) or min(int(hg),int(ag)) < 0:
                    continue
                match = {"date": when, "home": h, "away": a, "hg": int(hg), "ag": int(ag),
                         "league": archive.load(stage).get("league") or detail.get("league") or "",
                         "source_event_id": str(event_id)}
                meetings[(when.date(), h, a, int(hg), int(ag))] = match
            except (ValueError, TypeError):
                continue
        rows = sorted(meetings.values(), key=lambda m:m["date"], reverse=True)[:10]
        if len(rows) <= len(detail.get("h2h") or []):
            continue
        updated = dict(detail, h2h=[{**m,"date":m["date"].strftime("%Y-%m-%d")} for m in rows],
                       h2h_meta=quality.h2h_evidence(rows,now),
                       h2h_refreshed={"source":"Livescore stage archive", "stage":stage,"at":now.isoformat()})
        path.write_text(json.dumps(updated,ensure_ascii=False,separators=(",", ":")),encoding="utf-8")
        refreshed += 1
    outcome["refreshed_fixtures"] = refreshed
    print(f"::notice::Historical-data repair: {outcome['added']} genuine archived results added; {refreshed} fixture H2H records refreshed. Published picks/prices unchanged.",flush=True)
    return outcome


def run(now=None, edition="morning", clock=None):
    # Explicit editions are operator recovery; auto never forces a missed window.
    clock = clock or ((lambda: now) if now is not None else (lambda: datetime.now(SAST)))
    now = clock().astimezone(SAST)
    automatic = edition == "auto"
    if automatic:
        edition = scanner._reel_slot(now)
    today = now.date().isoformat()
    report = {"date": today, "edition": edition, "status": "not_sent", "deliveries": {}}
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
                target.write("## Advisor video delivery\n\n" + message + "\n\n```json\n" + json.dumps(report, ensure_ascii=False, indent=2) + "\n```\n")
        return code
    if edition is None and automatic:
        return finish(0, "outside_window", "No automatic video edition is due; nothing forced or resent.")
    if edition not in ("morning", "noon", "evening"):
        return finish(1, "blocked", "Unknown video edition; no mutation attempted.")
    _, state = scanner._telegram_state(now)
    if edition in (state.get("briefing_slots") or {}).get(today, []):
        return finish(0, "already_delivered", "Edition already has a recorded delivery lane. No rerender or Telegram resend; Facebook-only recovery uses the saved queue, not this marker as proof of Facebook delivery.")
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
    report["history_refresh"] = refresh_h2h(pool, now)
    used = {(str(p.get("home") or ""), str(p.get("away") or ""))
            for p in (state.get("briefing_history") or {}).get(today, [])}
    picks, dropped = scanner.reel_mod.video_picks(pool, used=used, fx_dir=scanner.APP_FILE.parent / "fx", now=now)
    report.update(source_generated=generated.isoformat(), candidates=len(pool), verified_card=len(picks), dropped=dropped)
    print(f"::notice::Video {edition}: {len(pool)} published candidates; {len(picks)} selections in the verified card; {len(dropped)} exclusions.", flush=True)
    if len(picks) < 5:
        return finish(1, "blocked", "Fewer than five verified Advisor matches fit the required combined-odds range. No padding, no video sent. Exclusion reasons are in the recovery report.")
    old_force, old_edition = os.environ.get("FORCE_DAILY_REEL"), os.environ.get("DAILY_REEL_EDITION")
    os.environ["FORCE_DAILY_REEL"] = "false" if automatic else "true"
    os.environ["DAILY_REEL_EDITION"] = edition
    expected = {"telegram": bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")),
                "facebook": scanner.facebook_mod.requested()}
    report["expected_lanes"] = expected
    originals = {"telegram": scanner.send_telegram_video, "facebook": scanner.facebook_mod.publish}
    if scanner.yt_mod is not None:
        originals["youtube"] = scanner.yt_mod.publish_shortlist
    if scanner.drive_mod is not None:
        originals["drive"] = scanner.drive_mod.handoff
    def telegram(*args, **kwargs):
        ok = originals["telegram"](*args, **kwargs)
        report["deliveries"]["telegram"] = {"delivered": bool(ok)}
        print(f"::notice::Video {edition} Telegram delivery: {'confirmed' if ok else 'not confirmed'}.", flush=True)
        return ok
    def facebook(*args, **kwargs):
        result = originals["facebook"](*args, **kwargs)
        report["deliveries"]["facebook"] = {"status": result.status, "reel_id": result.video_id}
        print(f"::notice::Video {edition} Facebook Reel: {result.status}; ID {result.video_id or 'none'}.", flush=True)
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
        delivery_now = clock().astimezone(SAST)
        if automatic and (delivery_now.date() != now.date() or scanner._reel_slot(delivery_now) != edition):
            return finish(0, "window_expired", "Automatic video window expired during preparation; no forced catch-up or upload.")
        scanner.maybe_send_daily_reel({}, delivery_now)
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
    if edition not in (after.get("briefing_slots") or {}).get(today, []):
        return finish(1, "not_delivered", "No successful edition delivery was recorded. See renderer logs and recovery artifacts; not claiming success.")
    missing = [lane for lane, enabled in expected.items() if enabled and not (
        report["deliveries"].get(lane, {}).get("status") == "uploaded" if lane == "facebook"
        else report["deliveries"].get(lane, {}).get("delivered"))]
    if missing:
        report["unconfirmed_lanes"] = missing
        return finish(1, "partially_delivered", "Video delivery is PARTIAL: a configured channel is unconfirmed. Keep delivered-lane markers; use saved Facebook-only recovery, never rerender or resend Telegram.")
    return finish(0, "delivered", "Edition delivered through at least one configured lane. Per-lane confirmations are recorded in this report; a Drive handoff alone is not a confirmed YouTube publication.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", help="Dated push-trigger request file")
    parser.add_argument("--edition", choices=["auto", "morning", "noon", "evening"], default="morning")
    args = parser.parse_args(argv)
    if args.request:
        request = json.loads(Path(args.request).read_text(encoding="utf-8"))
        if request.get("date") != datetime.now(SAST).date().isoformat() or request.get("edition") != "morning":
            print("::notice::Recovery request is not for today's morning edition; nothing sent.")
            return 0
    return run(edition=args.edition)


if __name__ == "__main__":
    raise SystemExit(main())
