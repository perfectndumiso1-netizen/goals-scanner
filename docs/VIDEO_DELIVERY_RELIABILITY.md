# Three video editions with independent channel delivery — November 1 repair

## What the evidence actually showed

- Manual morning recovery **41279577739** (06:08:07 UTC / 08:08:07 SAST):
  published `morning_recovery.json` records Telegram delivered, Facebook failed
  with no Reel ID, YouTube off. Exact five filmed picks were recorded at
  08:09 SAST. A green run meant **one lane**, not successful Facebook delivery.
- The data branch's November 1 edition history has only `morning`. Noon/evening
  have no recorded edition. This does not establish the exact noon selection
  failure: that scanner's raw logs could not be downloaded from this sandbox.
- The Facebook recovery queue was empty, despite the morning failure. The
  manual workflow lacked `FACEBOOK_AUTOMATION=1` and did not register its artifact
  into the ordinary Facebook-only queue. It therefore missed the normal bounded
  Page-identity/recovery wrapper. This is a wiring defect, **not proof** of the
  exact Meta rejection reason. Retained artifact **13073275385** still contains
  that run's recovery media; don't create a new upload without inspecting its
  saved receipt/phase. Sandbox log download failed; no Meta error code inferred.
- Evening scanner **41322605127** started 17:42 SAST, after the existing evening
  automatic window. The independent timer first successfully dispatched at
  19:05 SAST, also outside all video windows. It cannot retroactively cover today.
- Editorial run **41313074544** confirmed a Facebook post, then failed its audit
  because earlier slots match02–match05 expired without delivery. Watchdog
  **41313310299** repeated those incidents. These red workflows were not evidence
  that every later post had failed. No retroactive burst of expired posts is safe.

## Production wiring in this change

The existing filename `recover-morning.yml` is retained so installed timer/App
permissions and bookmarked URLs keep working. Its display name is now
**Advisor videos (three editions + recovery)**.

- Automatic mode (`edition=auto`) runs only **05:00–07:19, 11:00–12:19 and
  16:00–17:19 SAST**. Cloudflare ticks every five minutes and admits this workflow
  at most every ten minutes inside those windows, before admitting a full scan.
  GitHub also has bounded backup crons inside the same windows.
- Manual default remains `morning`. Named noon/evening recovery is explicit, not
  automatic catch-up or relabelling of yesterday. Existing dated historical push
  requests remain date-guarded.
- This is video-only work from a same-day published Advisor, at most six hours
  old; no 60-day rescan first. Existing stats/H2H verification, five-to-eight
  matches, card odds, upcoming kickoff, distinct filmed manifests, music/no voice,
  exact native portrait/landscape renderers and no-filler rules remain unchanged.
- Automatic mode does not enable force and rechecks its window/date after
  preparation. An expired start is safely skipped. Shared `goals-scan` mutex and
  unchanged edition markers prevent scanner/recovery overlap and TG resends.
- `FACEBOOK_AUTOMATION=1` now uses the existing bounded Page identity check and
  same-session retry wrapper. No new permissions, credentials or quota bypass.
- Existing Facebook-only saved recovery runs first, without rerendering or
  Telegram resend. Failed media/session sidecars are uploaded, **then** their
  manifest/artifact ID is registered, **then** delivery state is persisted even
  if a requested channel failed. Upload failure does not erase delivered markers.
- A recorded delivered lane still blocks rerendering. Facebook failures are
  resumed only from their saved artifact/hash/receipt via the ordinary queue.
  Unknown transfer/finish phases are not reset or blindly resent.
- The report returns nonzero `partially_delivered` if an enabled Telegram or
  Facebook lane is not confirmed, even when another lane succeeded. It preserves
  the successful marker. No workflow-level success is used as Facebook proof.

## Rollout / verification

After merge, let the existing Cloudflare Git build deploy the new target list;
confirm the four runtime secrets and existing DO namespace were preserved. No new
App permissions, service, key rotation or storage migration is needed.

At the next window check the automatic `recover-morning.yml` run plus its
`morning_recovery.json` report (legacy filename; actual `edition` is in JSON).
Require Telegram acknowledgement and separately Facebook uploaded status / Reel
ID. If Facebook remains failed, inspect the retained same-session artifact and
safe publisher error codes before further action. The previous failed morning
artifact has NOT been automatically imported or resent by this change.

No missed-edition alerts outside existing workflow failures are added here.
A stale source, insufficient qualifying matches or actual Meta rejection still
blocks delivery. Scheduling is independently clocked, not guaranteed exact-time
posting. Morning results, 07:30 1X2 and nine 08–16 two-picture slots retain their
existing feed ledger, expiry, quotas and clock; the now-working external watchdog
covers future slots, not expired ones. Live/community/card/weekly remain paused.
