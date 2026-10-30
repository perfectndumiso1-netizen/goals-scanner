# Three daily videos, separate morning results, app-covered Facebook scores

> **Subsequent score update:** API-FOOTBALL is now the selected (still approval-gated) Facebook source, with 10-minute checks during 08:00–24:00 SAST and optional emoji-labelled statistics. See [LIVE_SCORE_STATS.md](LIVE_SCORE_STATS.md). Earlier app-source/five-minute descriptions below are rollout history, not the current score configuration.

## Current owner request and implemented scope (30 October 2026)

Return to three videos per day at the previous times; Telegram plus Facebook only; move video warnings to an animated bottom footer instead of a full-screen disclaimer; remove yesterday's results from videos; publish those results separately each morning; prepare live-score updates for the matches covered by the app.

### Video calendar — SAST / UTC+2

The historical scanner immediately before commit `14f45670d17747b8c438157f50900e2f84ccd83b` confirms these original windows:

| Edition | SAST target | Accepted window |
|---|---|---|
| Morning | 05:00 | 05:00–07:19 |
| Noon | 11:00 | 11:00–12:19 |
| Evening | 16:00 | 16:00–17:19 |

`video_schedule.py` is the shared source for scanner routing and workflow preparation. The existing half-hour scanner cron, full-report hours (07/12/17), mutex and persisted per-day/per-edition receipts remain. GitHub scheduling is best effort, not exact-time delivery. An edition is skipped rather than padded when fewer than five verified distinct matches form a qualifying card. A forced edition still cannot resend an already-receipted slot. Adding noon does not reset morning/evening history or re-upload existing Reels.

Telegram retains one 16:9 video per edition; Facebook gets its separately rendered native 9:16 cut. Facebook failure cannot replace that cut with a landscape upload or block Telegram. Portrait covers remain the exact filmed matches only. The existing reservation/receipt/recovery and upload-before-cleanup paths are unchanged. YouTube and Drive switches are now off in the scheduled scanner and manual morning recovery, matching the requested two delivery channels. The locked supplied music, no narration, market rules, statistics/H2H verification, slow evidence holds, card odds target and non-repeating match selection are unchanged.

### Video presentation

- No full-screen disclaimer slide.
- No results/recap slide in any edition, even if an older caller passes `recap=True`. Compatibility arguments and standalone historical rendering helpers remain, but the video builder never includes those cards.
- One continuous readable ticker is applied to the assembled picture before the unchanged music mux. It does not reset at each match/slide. Pillow renders the text; FFmpeg crops/scrolls it, requiring no drawtext plugin or new production dependency. Portrait chart/record bounds and the progress bar reserve space above the footer so it does not cover the statistical rows.
- The fixed **18+** label remains visible. The moving text preserves statistical-information/not-advice, responsible-staking, no-guarantee, price-change and all-legs-must-win information. This implements the owner's alternative moving-footer format, not a claim that warnings are legally unnecessary.
- The Telegram caption no longer repeats the full warning or recap. Exact Facebook title/date/hashtag formatting remains unchanged.

## Separate Facebook morning results

The existing `facebook-roundup.yml` workflow is repurposed to **Facebook morning video results**, at **08:00 SAST / 06:00 UTC**. It requests the new `results` content type, not an additional late-night roundup. A two-hour tolerance and deterministic yesterday-date key permit delayed scheduling without a duplicate edition.

It reads only the published `data/app/telegram_state.json` filmed history and `data/advisor_ledger.json`. Filmed markets/prices stay original; the ledger supplies settlement. All filmed selections appear, including losses, voids and unsettled selections, with no winning-only sample or fallback to a current shortlist. Duplicate filmed lines are removed; suspicious cards over 24 distinct lines fail closed. Goal scorelines are explicitly labelled **FT goals**, so they are never represented as corner totals. Missing history/stale publication yields a skip, not fabricated results.

A read-only dry run against the actual published 29 October filmed history produced all five selections: **4 won, 1 lost**, no void/unsettled selections. This is draft evidence, **not a Facebook publication receipt**. The original filmed prices, including the losing selection, are retained.

## App-covered score integration — prepared, NOT verified live publishing

`score_source: app` selects a separate `AppScores` adapter for the same public Livescore date endpoint/UTC+2 and user agent as Android. It is explicit, not a fallback from API-FOOTBALL or an invented API subscription. No new service/account/payment is added. The existing API-FOOTBALL path and its independent rights/free-budget guards remain.

The adapter requires:

- A recent app publication; exact published Livescore event ID, fixture date, club sides and kickoff agreement. Different/unmatched aliases are skipped rather than fuzzily guessed. Other leagues/events cannot enter simply because they appear in the source feed.
- A fresh HTTP Date (180-second maximum source age), valid phase and nonnegative integer scores. Unknown/missing values, ambiguous penalty finals, oversized/malformed responses and failed requests are skipped.
- Persistent poll/cooldown metadata; no relabelling an expired cached score as live. HTTP 429/503 cooldowns persist. The existing frozen-clock suppression remains.

The selected score workflow polls at most every **five minutes** via `*/5 * * * *`; this is **not** a phone event stream or 20-second app refresh. Active app-covered fixtures are prioritised, bounded to **30 per combined update**. This is a coverage universe, not a guarantee every fixture is listed simultaneously. A one-goal change is significant for this source; unchanged snapshots/clock-only ticks do not create posts. Overnight fixtures can remain eligible for 12 hours after kickoff. Original score safety caps remain **three new score posts/day** and **60-minute new-post cooldown**. Automatic editing stays **off** until a real same-app edit/read-back test is approved and passes. Therefore this is not yet an every-goal Facebook service.

### Activation gates that remain unresolved

1. Repository variable **`FACEBOOK_FEED_PUBLISH=true`** is still required alongside JSON and an explicit workflow publish request. The session receives **HTTP 403 Resource not accessible by integration** for repository variable/secret settings, so its value cannot be verified/set here. No secret value was requested/read/exposed.
2. A missing production ledger still requires an inspected first-run bootstrap. A restore failure never resets history; ambiguous attempts still block repeat publication. Do not bootstrap to bypass an unknown attempt.
3. `app_scores.rights_confirmed` and `app_scores.coverage_verified` remain **false**. A shared public endpoint or successful HTTP response does not establish redistribution rights or verified coverage. They must not be flipped merely to make a job green. Scheduled live preparation safely reports the missing approvals without a live reservation/bootstrap or Facebook request; an explicit read-only preview/preflight remains available for validation.
4. Page/business-verification restrictions and public-audience visibility have not been remotely resolved. A future API success alone must not be advertised as non-role/public visibility proof.

Only **`results` and `live`** are authorised by the current JSON. Community, weekly, card and late roundup publishing remain paused, including if someone combines Publish + Preview manually. These source/type gates are checked before prepare and again at send. Results can run without the unapproved live provider, but still require the master variable, intact ledger and Page permissions. No morning-results or live-score Facebook publication was performed as a test.

## Validation

- Full suite: **759 passed, 1 skipped, 8 subtests passed** (80.72 seconds).
- New offline tests cover original schedule/timezone, complete filmed results/original prices, stale/missing history, date-key idempotency, requested-kind limits, independent source approvals, exact app-ID/name/date matching, malformed scores/statuses, stale HTTP dates, persisted rate-limit cooldown, unchanged/single-goal updates, moving-footer filter and send-time approval revalidation.
- Real FFmpeg smoke tests: **1920×1080** and **1080×1920**, three seconds each. Both completed with exact duration, a changing ticker region, stable fixed 18+ region (allowing normal H.264 compression noise), and silent picture. The unchanged music pipeline is separately regression-tested. These synthetic background clips are encoder tests, not filmed-match deliveries.
- Read-only real morning-results draft as described above. Real public score-feed/coverage and Facebook create/edit integration checks remain outstanding; offline synthetic tests do not prove them.
- Existing action-lock dependency lists still match: no new action or workflow file was added. Only scanner/presentation invariant hashes were re-pinned for the explicit request; publisher, music, verification and insight hashes remain locked.
- No Android asset/native/version/build-release changes. Existing APK remains 1.6.87; this is a server/video automation change, not an APK release. Its old in-app schedule description will need updating in a future requested app release.

## Changed files

Production: `video_schedule.py`, `scanner.py`, `shortlist_reel.py`, `facebook_feed/app_scores.py`, `facebook_feed/{cli,content,policy}.py`, `config/facebook-feed.json`; existing workflows `scan.yml`, `recover-morning.yml`, `facebook-feed-run.yml`, `facebook-live.yml`, `facebook-roundup.yml`.

Regression updates: `tests/test_video_return.py`, `tests/test_reel.py`, `tests/test_morning_recovery.py`, `tests/test_advisor_video.py`, `tests/test_archive_restore.py`, `tests/test_facebook_feed.py`, `tests/test_facebook_feed_safety.py`, `tests/test_facebook_one_match_test.py`, `tests/test_facebook_reel_presentation.py`, `tests/test_facebook_render_routing.py`, `tests/test_rebrand.py`, `tests/fixtures/facebook-feed-reel-invariants.json`.

Docs: this file and the current-scope note in `docs/FACEBOOK_FEED_AUTOMATION.md`. Downloaded snapshots, dev dependencies and encoder smoke media remain ignored under `tmp/` / `.venv/`.
