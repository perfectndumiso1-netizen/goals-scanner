> **Latest owner update:** [Morning Advisor and separate video accumulators](MORNING_ADVISOR_AND_VIDEO_RESULTS.md) supersedes the 07:30 fixtures bulletin with published Bet Advisor 1X2 picks, adds one 06:00 video recap with independent accumulator sections, and uses the selected **Mr 2 Odds** logo on future pictures. The nine two-picture match targets remain. Older timetable/branding descriptions below are historical.

> **Timetable update:** [Nine match packages](NINE_MATCH_PACKAGES.md) now replaces the six league-specific feature slots and old results/story slots with nine two-picture match targets at 08:00–16:00 SAST. The 07:30 combined-fixtures bulletin remains. Package publication adds durable unpublished-media staging and verifies both attachments; earlier single-image descriptions are historical.

# Editorial delivery watchdog

## What is automated

`facebook-watchdog.yml` wakes at minutes **13, 33 and 53**, plus after completion
of the normal scheduled-editorial workflow. It uses the **same feed mutex and
live artifact namespace**, never the scanner's data branch. Only `main` may run
production recovery. Manual dispatch defaults `publish=false` (no recovery job).

The scope is the approved ten factual **editorial/stats** opportunities. It does
not alter scanner/Reel schedules, video upload/recovery, music, Android, models,
paused live/community/card/weekly feeds, or photo/data rights gates. No Reel is
reuploaded by this watchdog. It is not a general self-repair system for every
repository workflow.

### Outcome-based journal

The live feed checkpoint includes a bounded `editorial_delivery` journal. It
starts with the current slot on deployment, not fictional failures for the
unmonitored morning. It detects slots that close without delivery even if the
primary trigger never ran. It does **not** publish expired slots, backfill a
queue of missed posts, or invent filler. Summaries retain seven days; immutable
publication history and unresolved reservations keep their existing retention.

A green preparation is **not** delivery. Only a ledger entry made `published`
by the existing Graph acknowledgement/read-back path, or a positive subsequent
hash read-back, counts as delivered. Reports distinguish:

- `delivered`: publication previously acknowledged and verified;
- `skipped`: no eligible/verified content or shared allowance exhausted;
- `waiting`: a temporary failure/backoff/cooldown;
- `verifying`: publication uncertain, read-only checks pending;
- `needs_attention`: bounded recovery exhausted, credentials/access blocked,
  unexplained preparation failure, missing durable state, or an expired slot.

## Bounded recovery

Every production editorial invocation through the shared engine now performs:

1. Restore the existing live checkpoint. Missing/corrupt/unreadable state blocks;
   **no automatic bootstrap, namespace/key revision or history reset**.
2. Attempt bounded positive reconciliation of unresolved editorial reservations.
3. Check current 60-minute slot, existing attempts, global unknowns, 45-minute
   feed spacing, account cooldown and shared quota. Check Page credential
   identity using GET **before spending football quota**.
4. Allocate a maximum of **three preparations per daily slot**, shared across
   primary, backup and watchdog invocations. Retry waits are 10 then 20 minutes;
   the next invocation after the wait may recover, not an exact-time promise.
5. Save an `-admitted` artifact **before provider preparation**. No admission
   upload success means no preparation. The CLI validates the same run, current
   slot, namespace and journal ownership; it does not restore an older state on
   top of that admission.
6. Rebuild current verified content. Existing factual/sample/fixture/price and
   expiry rules remain authoritative. A successful reservation is independently
   uploaded **before any Facebook mutation**, exactly as before.
7. Audit the resulting delivery ledger, send an intervention alert where needed,
   and upload the final journal even if preparation/sending failed.

Known transport failure may be retried within the slot. 429 respects the same
provider cooldown; 401/403 does not switch accounts or keep probing. Empty
schedules, missing verified samples and unsupported extra-time samples are
recorded skips, not fabricated cards. Changed/malformed identities are not
silently accepted on retry. Credentials/permissions requiring human repair are
reported, not bypassed.

### Quota safety after a killed runner

The existing shared **100/day UTC** allocation and valid 100th/no-101st transport
checks remain. Each durable admission temporarily debits a conservative maximum
of `3 * max_pages_per_poll + 3` requests (at most 33, clipped to remaining local
budget/header allowance): complete day catalog, two history catalogs and three
detail checks. A healthy preparation releases this hold **in memory only** and
uses the existing actual/header accounting. Its final checkpoint contains actual
usage. If preparation is killed before a final checkpoint, the saved hold remains
spent. A later run cannot reclaim it or erase potentially spent requests.

This can conservatively exhaust the local budget early after crashes; safety is
preferred over spending beyond the account allowance. UTC rollover still resets
only the provider's daily counters and preserves cooldowns. No extra account,
credential/key fallback or paid API subscription is added.

## No blind resend

- Uncertain POST or failed post-send verification keeps the reservation. A
  `retryable` GET error never makes a started POST safe to resend.
- An existing post ID receives an exact caption-hash/Page/published read-back.
- A lost acknowledgement without an ID may search **one bounded 100-post Page
  feed response**, restricted to reservation time -5/+15 minutes. Only one exact
  published Page-ID/caption-hash/time match is considered, followed by a separate
  hash read-back. Empty, truncated, inaccessible, conflicting or duplicate
  results **never prove absence** and never cancel a reservation.
- Read-back recovery has its own three-check limit/backoff per reservation and
  at most three unresolved entries are checked per invocation.
- A positive check marks the existing post delivered; no creation/edit request.
- Only explicit **local pre-mutation** credential-GET failure or content expiry
  can cancel a prepared attempt and allow a fresh bounded preparation. Ambiguous
  Facebook mutations are not converted into cancellations.
- Manual inspected-absence reconciliation remains available for unresolved cases.

## Alerts and operational limits

The existing `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` secrets are used only by the
audit step. No values are printed, copied, requested in chat or written to state.
A Telegram API `ok:true` is required before claiming notification acceptance.
This is API acceptance, not proof that a human read the message.

If Telegram is unavailable/fails, the watchdog's separate alert job creates or
updates **one marked GitHub issue** with `issues:write`. The publishing job keeps
`contents:read` / `actions:read`; the issue job has no Page/provider/Telegram
secrets and no publication state writes. It only checks out `main`, not the SHA
from a triggering workflow. The issue includes safe diagnoses and a workflow
link. GitHub notification preferences determine email/push visibility. Existing
issue bodies are updated, not an unlimited issue per failed run. Notification
metadata dedupes the same diagnosis set per SAST day. If both channels fail,
there is a failed workflow and an explicit failed-notification report—not a
claim that an alert was delivered. GitHub issues remain as incident records;
they are not automatically closed as proof of recovery.

The repository has issues enabled. During implementation the GitHub integration
returned **403** for secret-list access, so Telegram secret presence or live
alert delivery could not be verified. No permission bypass or credential
replacement was attempted.

Reports contain only fixed diagnoses, counts, attempt numbers, slot keys and run
links. No raw provider/Graph exceptions, token-bearing URLs, signed storage
links, credentials or API data enter alerts.

### Important: GitHub is still one failure domain

The periodic watchdog and workflow-completion wakeup are **both GitHub Actions**.
They recover from a missed primary run **when the watchdog itself starts**; they
cannot promise to detect/alert during a total Actions outage, disabled repository
Actions, or a runner that never starts. The configured cron is 72 short checks/day
plus completion wakeups and uses Actions capacity/minutes.

**No independent external scheduler is configured by this change.** That requires
an independently authenticated service/account. A chosen external scheduler can
call GitHub's authenticated workflow-dispatch API for `facebook-watchdog.yml`,
`ref=main`, `inputs.publish=true`, using a narrowly scoped GitHub App/service
identity managed in that scheduler's secret store. No token in a public URL or
public unauthenticated endpoint. Do not pretend the endpoint alone establishes
independent monitoring: failure to dispatch must itself trigger that service's
alert channel. No external account, paid purchase or new credential was created.

## Validation and delivery evidence

Failure-injection tests are offline and mock transport/Graph/Telegram/GitHub.
They cover missing ledgers, branch/config gates, slot expiry/midnight, bounded
attempts and delays, crash quota holds, 100th/no-101st, no-content skips,
pre-mutation-only retries, lost acknowledgements, failed read-back, positive
reconciliation, alert dedupe/failure and workflow permission/checkpoint order.

Tests/CI/merge/active workflow state are **not a confirmed Facebook post or a
verified live alert**. No synthetic test post or duplicate Reel is required.
