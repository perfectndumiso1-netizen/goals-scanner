> **Verified Highlightly activation (31 October 2026):** full owner-triggered diagnostic 41164360718 verified all 868 list rows/9 pages plus one match detail, with 90 requests remaining and zero Facebook requests. The factual source is now enabled within **08:00–24:00 SAST**, subject to existing baseline/event, quota, master-variable and publication safeguards. This supersedes earlier staged/blocked notes below; activation is not a post. See [HIGHLIGHTLY_LIVE_FEED.md](HIGHLIGHTLY_LIVE_FEED.md).

> **Coverage restored:** normal live-score reads/posts are restricted to **08:00–24:00 SAST**, not 24-hour coverage. Highlightly’s first-page diagnostic passed; full pagination/detail coverage and activation remain pending. See [HIGHLIGHTLY_LIVE_FEED.md](HIGHLIGHTLY_LIVE_FEED.md).

> **Current source: staged Highlightly.** All API-Sports slots are disabled following the owner’s confirmation that the accounts are suspended. Highlightly is selected for read-only verification; live publishing remains blocked until its access/coverage gates are approved. Earlier account-selection/activation descriptions below are historical. See [HIGHLIGHTLY_LIVE_FEED.md](HIGHLIGHTLY_LIVE_FEED.md).

> **Current account selection:** the suspended original `API_FOOTBALL_KEY` is disabled without deleting its secret or history. The owner specifically confirmed provider permission to use the two independent approved backups for this project while it is suspended. Active order is `_1 → _2`, with 200 gross/day, not 300. Historical three-account descriptions below are superseded; see [LIVE_API_DIAGNOSTIC.md](LIVE_API_DIAGNOSTIC.md).

> **Activation update:** [LIVE_POSTS_ACTIVATION.md](LIVE_POSTS_ACTIVATION.md) records the current renamed secret, 100/day allocations and explicit real-publishing request; the historical off/reserve notes below are superseded.

# Live score image: stadium template

The owner supplied a score-card reference on 30 October 2026 and requested that live-post images follow its style. The event-mode default is now `live.graphic_style="stadium"`; `classic` remains available for the older adapter/regression tests. Editorial/results/Reels/Android graphics and schedules are not changed.

## Layout

The template is adapted to the existing native Facebook **1080×1350 portrait** requirement rather than changing the delivery to a landscape video frame:

- Existing local `assets/reel/bg_stadium.jpg`, reused read-only under a dark navy overlay.
- Competition heading and restrained PlayReport ZA branding.
- Green live-clock/status pill, large white central score, actual provider crests on either side where available.
- Club names and green underline accents.
- Half-time score **only when verified and available**; no guessed 0–0.
- SAST **source-observation** date/time footer, not a copied reference timestamp or kickoff time.
- Accurate final/interruption labels, added time and penalty totals when supplied. An unknown score on a confirmed cancellation/postponement/abandonment remains a status panel, not fabricated goals.

`stadium_graphic.py` is a deterministic Pillow renderer, using the existing fonts/stadium artwork. It contains no network requests or fixture data hardcoded from the owner's attachment. Optional artwork is prepared before rendering. Long/unrenderable names fail closed; source numbers, nulls and unknown clocks are not filled with invented defaults. Existing image hash/reservation/expiry checks still apply before any Page mutation.

## Provider crests

When `live.crests_enabled=true`, the prepare phase attempts at most two public crest downloads for the image's selected match. `crest_cache.py` constructs the fixed provider CDN URL `https://media.api-sports.io/football/teams/{team_id}.png` from a validated numeric team ID. It never follows arbitrary provider/user URLs or sends an API key, Facebook credential, or authorisation header to that CDN. Redirects are blocked.

Only validated PNGs ≤512 KiB and ≤1024×1024 are accepted. The local disposable cache has a 30-day positive TTL, six-hour failure backoff and 512-file bound; fresh GitHub-hosted runners may need to fetch again because this cache is not added to the durable publication ledger or a new paid storage service. Each request has a four-second timeout. Missing/invalid/unavailable crests are omitted with neutral HOME/AWAY labels; no invented club badge or unrelated Page logo is substituted. The score card can still render accurately. Existing owner-confirmed publication rights remain the basis for using provider-supplied identity artwork; CDN availability alone is not independent rights verification.

No additional `/fixtures`, event, statistics, or account API call is needed for the design. Crest downloads are public media requests, not additional football-data endpoint requests. No paid API/graphics service or new dependency was added. Real CDN access was not exercised from the restricted local sandbox; transport behaviour was verified using offline mocked responses.

## Failover confirmation and account mapping

The owner's confirmation that the provider permits failover across independently authorised allocations is recorded in `event_monitor.permission_reference`, with `failover_permitted=true`. The owner separately confirmed **three independent authorised allowances**. Slots now map to `primary` (`API_FOOTBALL_KEY`), `backup-1` (`API_FOOTBALL_KEY_1`) and `backup-2` (`API_FOOTBALL_KEY_2`). Existing `primary` usage is preserved, not reset. If that allocation arrangement changes, keys sharing an allowance must be put back in the same group; permission alone must not be treated as a second allowance.

The existing quota-only conditions remain: documented daily exhaustion, plus the owner-enabled confirmed-authentication fallback in LIVE_POSTS_ACTIVATION.md; no switching for ordinary 429/network/IP-restriction/invalid-request/5xx errors, no rotation at the local 90-call reserve, active Free-plan verification and UTC reset. Actual Facebook publishing remains **off** pending the real-provider dry-run review; this image change does not activate posts.

## Preview and testing

The local reference-layout preview reuses the clubs/crests/score shown in the user's attachment **only as an unverified layout example**. It is watermarked `REFERENCE PREVIEW — UNVERIFIED SCORES — NOT PUBLISHED`. Crops and preview files live under ignored `tmp/stadium-preview/`, not production assets or the event ledger. No Page post/upload was made and the reference score was not treated as current API data.

Validation: `python -m pytest leagues/tests tests tennis/tests -q` — **939 passed, 1 skipped, 8 subtests passed**. The new stadium/crest suite contains **30 offline cases**, covering layout/date/clock/HT facts, status-only/null scores, real local PNGs, missing/unsafe crests, bounded positive/negative caching, exact credential-free CDN requests, invalid IDs/config and independent/shared quota safety. No physical Android, real-provider or real-Page delivery test is implied.
