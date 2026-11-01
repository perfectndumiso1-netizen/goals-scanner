# Missed video editions and recovery

## Scheduling fix

Current automatic windows are **05:00–07:19, 11:00–12:19 and
16:00–17:19 Africa/Johannesburg**, defined in `video_schedule.py`. GitHub cron
is best-effort; a wake-up outside a window does not automatically force a missed
edition. The existing `briefing_slots` markers prevent repeats after a recorded
successful lane. A Telegram success alone is not proof of Facebook publication.

See [Independent scheduling](INDEPENDENT_SCHEDULER.md) for the Cloudflare timer.
Repository code alone does not deploy or activate that external service.

## Immediate morning recovery

`Recover morning Advisor video` runs the same verification, renderers, music,
selection rules and delivery functions as the normal scanner, without
re-running 60 days of fixture discovery. It reads the existing data branch and
requires a same-day Advisor publication no more than six hours old. It does
not clear delivery markers or lower the five-match/combined-odds/statistics/
recent-H2H checks. It forces the **morning** edition only on explicit recovery, with no recap or
narration. Yesterday's results are a separate morning Facebook post. Even an
after-hours request must pass current source freshness and upcoming-match gates.

- From GitHub Actions (after merge): run **Recover morning Advisor video**.
- For the authorized 2026-10-29 recovery, the same session branch has a push
  trigger restricted to `config/morning-video-request.json`. The request date
  must equal today's SAST date, so later merges cannot revive an old request.
- The workflow shares the scanner's `goals-scan` concurrency lock; it never
  writes the data branch alongside another scanner or recovery run.
- Per-lane results and gate exclusions appear in the job summary and the
  `morning-video-recovery-<run>-<attempt>` artifact. Public Reel/YouTube IDs may
  appear; credentials must never be included.
- Delivery state is persisted even after a later upload fails. A successful
  Drive handoff is not a confirmed YouTube publication. A Telegram success is
  not a Facebook success. Failed Facebook media stays recoverable; no
  landscape fallback is allowed.

The catch-up fix only changes timing. It cannot guarantee an edition if fewer
than five distinct verified published selections fit the required card, if the
source publication is stale, or if platform credentials/media are rejected.

## Calendar-season archive repair

The 2026-10-29 recovery exposed an independent history-fetch bug: in July–December,
calendar-year backfill used the European season anchor and requested the current
year plus only one previous year. Old negative attempt labels also incorrectly
made a corrected request list look exhausted. Backfill now requests the previous
calendar years from `now.year`, and checks the actual requested labels rather
than the total count of remembered attempts.

Recovery tops up only candidates blocked solely by missing H2H, from the existing
provider's historical stage archive. It refreshes contextual H2H and its evidence
metadata, retaining source event IDs and the stage/retrieval time. It excludes
future/unscored/wrong-club meetings, deduplicates real results and never changes
published selections, odds or model probabilities. The normal verifier still
runs afterwards. The safe diagnostic report is also saved as
`data/app/morning_recovery.json` for phone-accessible inspection.
