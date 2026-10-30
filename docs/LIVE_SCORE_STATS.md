# API-Football live score checks and optional statistics

## Current scope

The owner selected API-Football's 100-request/day account, ten-minute checks, no coverage from midnight to 08:00 SAST, and emoji-labelled extra statistics where available. This updates only the isolated Facebook feed. The existing app/backend, prediction markets/formulas, three video windows, music, Telegram delivery and Android APK remain unchanged.

**Implemented is not activated:** the selected source is now `api-football`, but both provider rights and account-coverage approval switches remain false. No key, real provider response, rights approval, Page publication or public visibility was obtained/verified in this change. Do not paste a key in chat or commit one. The reusable workflow already reads the repository secret `API_FOOTBALL_KEY` into the preparation step only; direct API-Sports authentication stays in the `x-apisports-key` header, never a URL. There is no RapidAPI or unofficial fallback.

## Hours, matching and polling

- GitHub cron `*/10 6-21 * * *` = every ten minutes from **08:00 through 23:50 SAST**. Cron remains best effort. Runtime guards also reject delayed jobs after midnight, including previews. Send rechecks the time both before any Page request and immediately before mutation.
- Matches kicking off **00:00–07:59 SAST are excluded entirely**, including if still playing after 08:00. Coverage stops at midnight for late matches. The window is an allowed interval, not a promise of 96 successful polls or uninterrupted coverage after quota exhaustion.
- Read only the fresh existing app publication (12-hour maximum). Require known kickoff, same-day permitted kickoff, and an actual kickoff within the previous 270 minutes. This is a bounded possible-in-play window, not an invented live status: the provider must still report a validated status/score. No future/overnight fixtures or absent/stale publication means no fixture API request.
- One day's fixture request is shared across matches. Club sides and kickoff instant must match **exactly after basic name normalization** to one app fixture. Ambiguous duplicates, wrong sides, different kickoffs and unverified club aliases are skipped. No editorial big-league/rivalry filter can expand or narrow that app universe. Only matched normalized fixtures enter the persisted provider cache; an updated app publication revalidates cache identity.
- Already published full-time fixtures stop triggering polling. When the three-new-post/day cap is reached and editing is off, scheduled polling also stops to conserve the allowance. Explicit read-only preview/preflight is still possible within its safety gates.
- A separate last-attempt marker enforces the polling interval even after failed requests or after the five-minute freshness TTL expires. Old scores are never rejuvenated just because ten-minute polling is configured. HTTP source Date, impossible elapsed/status checks and frozen-clock suppression remain. Retry-After cooldown is persisted; no immediate retries.

## Request budget — optional stats are not free extra calls

All API calls (status verification, fixtures, statistics, coverage checks, failed calls) share a **90-request/day hard local ceiling**, retaining ten of the stated 100 requests as a safety reserve. The budget uses the provider's UTC day, respects reported account usage/remaining headers and rejects paid/inactive plans. Other uncontrolled consumers of the same key can affect its actual allowance.

Additional statistics require `fixtures/statistics?fixture=<provider ID>`: **one extra request per fixture**. They are therefore fetched only after a provisional verified score post passes the unchanged posting policy:

- Maximum **two fixtures with stats per update**.
- Maximum **six statistics attempts per UTC day**, including failures; all six also count inside the shared 90-call ceiling.
- Leave the last two operational requests available for fixture checking, rather than using them on optional stats.
- Reuse only identity-matched fresh stats (maximum five-minute HTTP/cache age); never reuse expired stats on error or budget exhaustion.
- No optional call for an unchanged score, feed cooldown/daily cap, missing team IDs, or NS/postponed/cancelled fixture.

Consequently fewer than 90 fixture polls may fit: a daily status call, six stats calls and a coverage call leave at most 82 fixture calls inside the conservative operational budget. Skipping irrelevant hours/matches saves calls. There is no promise that a free plan provides current-season/live/statistics coverage; an empty or restricted response produces a skip, never an older-season substitute.

## Post presentation

Score/status icons: **⚽** score-centre heading, **🔴** in play, **⏸️** half-time/break/interruption, **🏁** final, **📅** scheduled/postponed/cancelled.

Optional verified pairs, explicitly **home–away**, each with a statistics snapshot time:

| Field | Label |
|---|---|
| Corners | 🚩 Corners |
| Yellow/red cards | 🟨 Yellow cards / 🟥 Red cards |
| Possession | 📊 Possession |
| Shots on target | 🎯 Shots on target |
| Total shots | 🥅 Total shots |
| Fouls | ⚠️ Fouls |
| Offsides | 🚫 Offsides |

Both exact provider team IDs and names must match. Unknown/duplicate metrics, nulls, booleans, negatives, noninteger counts and malformed percentages are omitted, not turned into zero. Possession must be a pair of valid percentage values summing to 100 within one point of rounding. Actual reported zero remains zero. No derived possession, inferred corners/cards, historical substitutes, xG guesses or new betting markets are added.

Stats are supplemental: failure/unsupported coverage omits extras but retains a fresh verified score. Snapshot metadata participates in the prepared reservation/hash/read-back. Expiry respects the oldest source timestamp; source changes between preparation and send cancel the plan rather than borrowing another provider's approval.

A score/status change can generate an update (including a one-goal change), subject to the existing **three-new-posts/day** and **60-minute new-post cooldown**. Routine clock ticks, possession/corner/card-only changes do **not** create extra posts. Editing stays **off** pending a real same-app Page edit/read-back test. Ten-minute data checks are not a ten-minute Facebook posting service.

## Activation still required

1. Securely configure/verify `API_FOOTBALL_KEY` through repository Actions secrets, never chat/source code.
2. Validate this exact Free account's current-season league/live/statistics coverage against the app fixtures and confirm permitted Facebook redistribution. Only evidence can justify the two provider approval switches. The independent app-source switches remain false.
3. Verify `FACEBOOK_FEED_PUBLISH`, Page publishing permissions/public visibility and the durable production ledger. A missing ledger requires inspected bootstrap, never a blind reset. Previous access to repository variable settings returned 403; this change does not claim that permission is resolved.
4. Only results/live remain authorised. Community/cards/weekly/late roundups stay paused. No extra test Reel, Page post, manual production dispatch or API-key read was performed.

## Offline validation

- **804 passed, 1 skipped, 8 subtests passed** in the complete Python suite (81.01 seconds).
- **45 new synthetic tests** cover SAST/UTC boundaries, overnight kickoffs, stale/missing app coverage, exact/ambiguous mapping, cache filtering, request/stat quotas, interval after failure, correct zero/null handling, bad/duplicate team metrics, possession validation, fresh/expired stats, HTTP cooldowns, emojis, no stats-only spam, no optional spending during feed cooldown, source changes before send, midnight send cancellation and already-reported finals/post-cap polling skips.
- Existing renderer/music/model/publisher invariants remain untouched. These tests do not establish real account access, redistribution permission or successful/public Facebook publication.


## First saved-key preflight (30 October 2026)

The owner manually ran [41071073984](https://github.com/perfectndumiso1-netizen/goals-scanner/actions/runs/41071073984) on `main` after saving the secret. GitHub reports workflow success, **not provider validation success**. Its API-readable annotation says `preflight` was skipped because the provider returned errors; no scores were used. The specific error was deliberately suppressed by the original adapter. The missing-secret error did not occur, but this establishes only that a nonempty secret was loaded, not that the key is valid or the Free plan is accessible. The Facebook mutation/reservation steps were skipped.

The adapter now maps known provider error keys to static safe categories (credentials/account authorisation, IP restriction, request allowance, plan/season access, parameters, unknown), and labels only known endpoints. It never echoes provider error text, unknown keys, credentials, account details or arbitrary endpoints. Existing failure gates/budgets remain unchanged. A repeat read-only `preflight` can distinguish the next action without exposing the key. Do not enable publishing or mark coverage/rights approved based on a green workflow badge.

Automatic dispatch from this session is blocked with GitHub integration HTTP 403; the owner must start the repeat test from the workflow page with `kind=preflight`, `publish=false`, `preview=true`, `bootstrap=false`. Logs/artifact storage are not reachable from the sandbox; the safe workflow annotation can be retrieved through the GitHub API. No attempt was made to read the secret value.
