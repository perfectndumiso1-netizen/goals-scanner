# Automatic video delivery tracking and failure alerts

## What this adds (and what it does not prove)

The scheduler clock was verified through actual GitHub dispatches on November 1.
That did not verify Facebook video publishing. This change adds ongoing,
per-edition channel evidence and Telegram failure alerts. It is not a claim that
an actual future Reel has already been published. No old match/video is resent
as part of deployment or monitoring activation.

No new account, secrets, permission scopes, database or routine Cloudflare checks
are needed. The existing Git-connected Worker build picks up the new target mode;
GitHub health backup crons use the same workflow as well.

## Evidence: existing data branch, separate from media delivery state

`data/app/video_delivery.json` is a versioned, atomic-write observation ledger.
It records each SAST date and morning/noon/evening edition, with **separate**
`telegram` and `facebook` statuses. Monitoring retention is eight calendar dates;
publication receipts, filmed accumulators, unknown-upload blocks and slot markers
are never reset or pruned by this module.

- Telegram confirmation requires the actual `sendVideo` JSON `ok=true` and a
  positive `message_id`; HTTP 200 alone is insufficient for this ledger.
- Facebook confirmation requires the existing publisher's `uploaded` result
  (publishing-phase complete) and a numeric Reel ID. A preferred-cover issue is
  separate from the acknowledged Reel publication.
- `attempting` is saved before each channel's mutation; failure or uncertainty
  becomes `unconfirmed`, not evidence that no post exists. An interrupted attempt
  becomes alertable after ten minutes. Observing does not cause a media retry.
- Confirmed evidence cannot be downgraded or overwritten with another identity.
- Legacy `briefing_slots`, a green workflow, Telegram success and a Facebook
  recovery reservation are NOT imported as Facebook confirmations.
- New failure manifests carry explicit edition/date metadata from the scoped
  rendering context. Facebook-only saved recovery can update only that edition,
  using the existing media digest/session checks. Older unassigned artifacts are
  not guessed into an edition. Telegram is not called by this recovery path.
- No captions, provider payloads, credentials, exception text, JWTs or signed URLs
  enter the observation ledger or alerts. Existing Telegram-video exception
  logging was narrowed to omit credential-bearing URLs/response details.

Scanner and dedicated video jobs both observe the same send function. Existing
successful-lane markers, cleanup, aspect ratios, render/quality rules and
same-session/unknown protections remain authoritative and unchanged. Even a
monitoring failure does not erase evidence or initiate a new upload.

## Detection and routing

The Worker now always checks `recover-morning.yml` first:

- **Inside a video window:** `edition=auto`, admitted at most every ten minutes.
  Existing 05:00–07:19, 11:00–12:19 and 16:00–17:19 SAST windows remain unchanged.
- **Outside a video window:** `edition=health`, admitted at most every fifteen
  minutes. This lightweight job does not install the renderer or call Facebook,
  any provider, `sendVideo`, the scanner, or media recovery. It can only inspect
  evidence and send a status message to Telegram.

GitHub backup cron wakes also route by the current clock. The route job computes
mode, then runs either the existing video job or the new standard-library-only
health job. All share the existing **goals-scan** mutex, including the scanner,
so they cannot overwrite each other's data-branch changes. Active/recent-run
checks and dispatch reservations in the Worker are unchanged.

Health planning runs after dedicated video/recovery work as well. It detects:

1. A source/quality blocked or partial-delivery outcome.
2. An explicitly unconfirmed/missing-config channel.
3. An interrupted attempt older than ten minutes.
4. An entire edition window ending without both channel confirmations, including
   when no render/upload job ran at all.

Monitoring begins at ledger activation. A window already in progress is covered;
expired pre-activation windows are not retrospectively turned into alerts or
fabricated acknowledgements. The current and previous SAST day are audited, so
an overnight wake-up still catches the preceding evening's missed window.

## Alert reservation and deduplication

At most **one incident alert per date/edition** is reserved. The message names the
edition and each channel's observed status, and explains that confirmed media
will not be resent. A blocked edition may later succeed; its tracker then becomes
`confirmed_both_channels` without generating repeated incident alerts.

The workflow deliberately separates:

1. Plan/reserve the incident locally.
2. **Commit/push the reservation to the data branch.** If this fails, do not send.
3. Send only reservations owned by this run ID **and attempt**.
4. Persist the Telegram alert acknowledgement, even if notification failed.

Before the request, the alert becomes `unknown`. Exceptions, parsing failures or
a timeout are never printed with token-bearing URLs, and an ambiguous alert is
not blindly sent again. A later run/attempt cannot replay another run's reserved
alert. Unconfirmed alert transport remains visible as a failed health check.
This favors avoiding duplicate alerts over guaranteed exactly-once messaging:
a crash after reservation but before send may leave an unsent reservation needing
attention. Do not reset it to force a retry. A resolved incident is not sent if
both channels were confirmed before notification.

The scanner now checkpoints restored state even if its main step fails, retaining
interrupted-attempt observations and existing recovery bookkeeping. Dedicated
video workflows already checkpoint partial-delivery state. No artifact checkpoint,
failed upload or stale source is treated as a successful public post.

## Where to see status / limits

Normal use does not require searching Cloudflare logs. GitHub health/video job
summaries show date/edition and the two channel statuses/receipt IDs. Telegram
receives deduplicated failure messages automatically when delivery needs attention.
The existing `morning_recovery.json` remains a per-run renderer report; the new
ledger is the cross-run source of channel evidence, including Facebook-only
reconciliation after the original Telegram send.

This monitor cannot send a Telegram alert when the bot/chat credentials are
invalid or Telegram rejects/is unavailable. That condition fails the health job
without exposing credentials. Nor can it execute alerts while both Cloudflare
and GitHub execution are unavailable. A heavy scanner can delay the shared mutex;
there is no exact-minute alert SLA or guarantee of three qualifying cards/day.
Insufficient verified picks, provider limits or actual Meta rejection remain
valid delivery blockers. No model, quota, audio, source-rights or permission gate
is loosened to make a dashboard green.

## Verification

Tests use temporary JSON ledgers, mock HTTP and synthetic IDs only. They cover
missed windows, timezone/day boundaries, activation, per-lane evidence,
monotonic receipts, partial success, interrupted attempts, crash/unknown alert
safety, run/attempt deduplication, saved-session Facebook reconciliation, workflow
checkpoint ordering, and the absence of media publishing in health-only jobs.
The bundled Worker runtime is still checked using generated RSA keys and local
mock GitHub responses. Real next-window Telegram and Facebook receipts are
required before claiming end-to-end live delivery.
