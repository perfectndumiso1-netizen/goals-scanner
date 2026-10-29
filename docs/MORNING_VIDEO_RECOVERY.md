# Missed video editions and recovery

## Scheduling fix

Daily editions are due at 08:00 and 16:00 Africa/Johannesburg. GitHub scheduled
runs are best-effort and can arrive hours late. The morning edition remains due
from 08:00 until 15:59; the evening edition remains due from 16:00 until midnight.
A subsequent scan retries a quality-gated or failed edition, but the existing
`data/app/telegram_state.json` `briefing_slots` marker prevents reposting an
edition that has already succeeded through any delivery lane. The scanner uses
the current clock at delivery time, rather than the start time of a long scan.
No previous-day edition is automatically backfilled or relabelled as today's.

## Immediate morning recovery

`Recover morning Advisor video` runs the same verification, renderers, music,
recap, selection rules and delivery functions as the normal scanner, without
re-running 60 days of fixture discovery. It reads the existing data branch and
requires a same-day Advisor publication no more than six hours old. It does
not clear delivery markers or lower the five-match/combined-odds/statistics/
recent-H2H checks. It forces the **morning** edition, including yesterday's full
filmed-selection recap, even if an operator explicitly requests it after 16:00.

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
