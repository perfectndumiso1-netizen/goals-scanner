# Ten-minute live updates with one score picture

## What happened

The owner reported no automatic score post after ten minutes. Read-only inspection established:

- The live workflow was active, but its latest scheduled run shown by GitHub was 30 October 08:32 UTC; no recent ten-minute schedule execution appeared in the run list. Workflow configuration alone was not evidence of regular execution.
- The production JSON still allowed only **three new score posts/day and a 60-minute new-post cooldown**, despite ten-minute provider polling. The formatter also required score/status changes, suppressing unchanged-score observations. Those settings could not meet the requested posting cadence.
- Manual feed run [41074088141](https://github.com/perfectndumiso1-netizen/goals-scanner/actions/runs/41074088141) had confirmed a live post with caption read-back. That does not prove later scheduled delivery or public audience visibility.
- The agent attempted an immediate real trigger with `publish=true`, `preview=false`, `bootstrap=false`; GitHub rejected dispatch with **HTTP 403 Resource not accessible by integration**. No replacement key/secret is needed for that permissions failure. No new post was triggered by that attempt.

The owner explicitly requested automatic posts every ten minutes and a picture highlighting one match score. This supersedes the old live-post frequency caps, not the API quota, overnight exclusion, source rights, freshness, duplicate/unknown-attempt safeguards or unrelated feed restrictions.

## Cadence and scheduler

- `publish_every_poll: true`, ten-minute publication cooldown, bounded to **90 new score posts/day**. In practice the shared 90 API-call cap is usually reached earlier because status/statistics/coverage calls consume the same budget.
- Fresh verified in-play observations can generate a new ten-minute-bucket update even if the goals are unchanged. The picture carries the observation time. Identical public text is allowed only in this periodic live mode; same reservation key and feed cooldown still block repeats. An all-final bulletin is not repeated unchanged.
- An unresolved live reservation/unknown attempt blocks another live creation pending inspection/reconciliation. Do not clear history to bypass it.
- Cron is shifted off the busy hour boundary to **08:03, 08:13 … 23:53 SAST** (`3-59/10 6-21 * * *` UTC).
- A successful completion of the existing **PlayReport scan (every 30 min)** also invokes the same feed engine as a fallback. Only own-repository `main` completions may do so; fork/other-branch/failing runs are rejected. The same concurrency, master switch, ten-minute provider interval and cooldown prevent duplicate sends from cron/fallback/manual overlap.
- GitHub cron is best effort and can be delayed/dropped. The scan-completion fallback improves recovery but is **not** an independent precise ten-minute timer. Absolute every-ten-minute delivery cannot be guaranteed by GitHub Actions, a finite free API quota, Page availability or a window without eligible live matches. A reliable external scheduler would need a separate agreed deployment; none was purchased/created here.

## Picture per live update

Each new live post must include an original **1080×1350 JPEG** showing exactly one verified match from that post's selected score snapshot. Prefer an in-play match. Text continues listing the other selected matches in the requested compact format, headed `Live Matches SAST` with up to ten relevant hashtags; no new brand/source/promotional caption is added.

Artwork shows the same match's clubs, actual score, league, status/minute, SAST source-observation time and optional verified stats. It is drawn locally with existing licensed Liberation fonts, gradients/pitch shapes; no external photos, club logos or extra provider requests. A synthetic design smoke test was rendered locally and is **not a real match or publication**. Long/unrenderable names fail closed rather than being silently truncated.

Live jobs now install the existing hash-locked Pillow feed dependency. The existing native Page `/photos` publisher sends the JPEG with the text in its caption. If rendering fails, the entire live update skips instead of falling back to text-only. The image SHA-256 is checkpointed with the reservation and rechecked before any Page request; missing/changed images cannot be published. Caption hash, source/expiry revalidation, unknown-send tracking and post-ID/caption read-back remain. A real new live-photo Page send has not been verified by the offline renderer/upload-lane tests.

The renderer routes through a separate live branch; existing editorial graphics, morning results, Telegram/Reels, original music and model/market rules are unchanged. This request is implemented for live-score posts, not unrelated paused content.

## Budget and ledger

The owner retains 100 requests/day, with a **90 shared operational-call ceiling** and ten requests reserve. Optional stats still max six attempts/day/two matches per eligible update. This change does not silently raise quotas or add a paid plan; there may not be enough calls to fill all 96 possible ten-minute daytime slots. Poll only eligible app coverage, stop overnight/when exhausted, and never substitute stale scores to fill a slot.

To keep high-frequency history within the existing 512-KiB restore bound, retain full latest published snapshot and compact older published snapshots to needed terminal-fixture identity/status evidence and remove their redundant live-only fixture-ID lists (not used for editorial dedupe). Preserve every reservation key/hash, picture hash, post ID and **all unresolved snapshots**. Score observations expire after six hours (beyond the 270-minute eligible match window). Existing production history is restored; bootstrap/reset is not authorised.

## Trigger and verification

The GitHub connection needs **Actions write/dispatch permission** to trigger a run directly. Until corrected, the owner can start a **new** [live workflow](https://github.com/perfectndumiso1-netizen/goals-scanner/actions/workflows/facebook-live.yml) on `main`, with `publish=true`, `preview=false`, `bootstrap=false`. This requests a genuine new post, not an extra test Reel. The repository variable `FACEBOOK_FEED_PUBLISH=true` remains mandatory.

Check the resulting report/annotation for a confirmed post ID and caption read-back—not just job success. A skip can mean no eligible match, pending unresolved attempt, interval, exhausted quota, stale source, image-render failure or Page permissions. Public audience visibility is still separate. No agent-initiated publication was confirmed in this task.

## Validation

Full suite before final diagnostic-message-only/picture-penalty-label adjustment: **841 passed, 1 skipped, 8 subtests passed**. Twelve new offline cadence/photo tests cover ten-minute/legacy cooldown, unchanged fresh observations, same-key and unknown-attempt guards, no unchanged-final repeats, one exact picture match, real JPEG render, long-name failure, repeated-history size bound, image-digest tampering before Page access, existing photo-upload handoff, trusted fallback guards and unsafe cap/photo configuration rejection. Legacy three-post tests explicitly select the old policy instead of weakening unrelated safeguards. No video/music/publisher invariant pins changed.
