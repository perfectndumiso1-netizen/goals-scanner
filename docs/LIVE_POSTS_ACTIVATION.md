> **Current source: staged Highlightly.** All API-Sports slots are disabled following the owner’s confirmation that the accounts are suspended. Highlightly is selected for read-only verification; live publishing remains blocked until its access/coverage gates are approved. Earlier account-selection/activation descriptions below are historical. See [HIGHLIGHTLY_LIVE_FEED.md](HIGHLIGHTLY_LIVE_FEED.md).

> **Current selected accounts:** `API_FOOTBALL_KEY` is disabled after the provider suspension report. The owner specifically confirmed that this project may use the independent `_1` and `_2` accounts while it is suspended. Monitoring now starts with `_1`, with `_2` as fallback; active gross capacity is 200/day. See [LIVE_API_DIAGNOSTIC.md](LIVE_API_DIAGNOSTIC.md). Historical three-account capacity descriptions below are superseded by that selection.

# Real live-post activation and renamed key slot — 30 October 2026

The owner explicitly requested committing the changes, triggering **real Facebook posts**, using each of the three independently authorised Free allocations at **100 requests/day**, and switching when an allocation actually runs out. This supersedes the initial dry-only gate and the event monitor's 90+10 reserve. The legacy provider/prediction/Reel budgets and all Reel/Android schedules remain unchanged.

## Current configuration

- `event_monitor.publish_enabled=true` (previously false).
- `event_monitor.daily_request_budget=100`, `daily_request_reserve=0`: up to the provider-verified allowance, never beyond it.
- `credential_revision="3"`: reverify corrected/renamed credentials without resetting existing account usage, snapshots, reservations or post IDs.
- Slots, in priority order: `API_FOOTBALL_KEY` → `primary`; **`API_FOOTBALL_KEY_1`** → `backup-1`; `API_FOOTBALL_KEY_2` → `backup-2`.
- Both numbered slots use an underscore: `API_FOOTBALL_KEY_1` and `API_FOOTBALL_KEY_2`. The older unseparated spellings are no longer read. No GitHub secret is deleted or its value read/copied into source.
- The owner has confirmed provider permission and an independent allowance for each slot. The existing rights, active-Free-plan, main-branch, Page credential, repository `FACEBOOK_FEED_PUBLISH`, durable-checkpoint, image-hash, content-expiry and unknown-send protections remain mandatory.

## Failover and capacity

The owner subsequently requested: **if the first key fails authentication, try the second**. This is a separate, explicit change from the earlier quota-only rule. `authentication_failover_permitted=true` now allows a confirmed credential rejection (structured token/key/authentication error or an unrestricted HTTP 401 challenge) to try the next configured, independently authorised allocation. If that credential is rejected too, the third is tried. Every backup must still pass its own active Free-plan and account-usage checks before fixture data is used. An authentication response is not proof that a saved key was damaged.

Each rejected credential gets a six-hour per-slot cooldown; subsequent polls skip it and use the next authorised slot rather than retrying it every five minutes. Exhaustion is not fabricated from an authentication response, including a misleading zero-remaining header. Revision 3 re-verifies the previous revision's stored failure once, then applies the new fallback policy. Existing account usage, confirmed snapshots and Facebook reservations are not reset. State records the last successful **slot name**, never its value.


A successful 100th provider request is used normally. When its daily remaining header becomes zero, the next request uses the next authorised allocation. Daily quota errors or verified `/status` usage reaching the account's actual limit also permit failover. Exhausted allocations are remembered through the UTC day, rather than repeatedly probed. Renaming a credential does not reset the account's usage.

Network failures, parameter/plan errors, unrelated 5xx, generic 403 responses, IP restrictions, account suspension/blocking and ordinary per-minute 429s do not switch keys. These are not treated as another credential to try in order to bypass access controls. A local conservative request-attempt count alone is not proof that the provider's daily allocation is exhausted: authoritative usage/remaining data or a documented daily quota response is required. Daily accounting resets at 00:00 UTC / 02:00 SAST.

The confirmed gross allocation is **3 × 100 = 300/day**. Continuous five-minute global monitoring needs **288 live requests/day**, leaving only **12** for account checks, calendars and terminal-detail batches, before other applications' use. This is much closer than 270 but is **not** a guarantee of uninterrupted all-day coverage: terminal refreshes can exceed the remaining headroom. No request is made beyond a verified per-account daily limit and no paid service is introduced.

## Real-post rules

The existing stadium-style picture and meaningful-event-only captions remain in force. No synthetic/reference score is eligible for production. First retrieval establishes a baseline, not a flood of old goal/card alerts. A subsequent fresh goal/score change, HT/FT, verified red card or significant status transition can produce a real consolidated Page photo post. No live matches/change, unavailable provider, unresolved old send, or stale data means skip — not a fabricated demonstration post.

A real run is not proof of a real post: require a returned Page post ID and successful Graph content verification before reporting publication. An unacknowledged timeout retains the reservation; never blindly resend.

## Requested trigger and phone-only fallback

After the reviewed change is merged to `main`, attempt the normal manual dispatch:

```sh
gh workflow run facebook-live.yml --ref main -f publish=true -f preview=false -f bootstrap=false
```

If GitHub returns `403 Resource not accessible by integration`, report that exact limitation. Do not claim a dispatch/post, retry unchanged, solicit credentials, reset the ledger, add a hidden push trigger, or use an unrelated old Reel/photo test to force a post.

The owner can run the same workflow in GitHub's phone UI:

1. Actions → **Facebook meaningful live events (24h)** → **Run workflow**.
2. Branch **main**; `publish=true`; `preview=false`; `bootstrap=false`.
3. Inspect the safe planning report. The first production event-monitor observation may only baseline; later five-minute runs publish meaningful changes. Keep bootstrap false for the existing production ledger.
4. If it reports dry-run despite the configuration, the existing repository variable `FACEBOOK_FEED_PUBLISH` must be `true`. Do not expose Page/API tokens in reports or chat.

The existing five-minute UTC cron remains `*/5 * * * *`; GitHub scheduling is best effort, not an exact timer. Trigger/post outcome must be reported from observed GitHub/Graph results, not inferred from the configuration.

## Validation

`python -m pytest leagues/tests tests tennis/tests -q`: **939 passed, 1 skipped, 8 subtests passed**. Event replay coverage now includes the full hundredth request followed by renamed-backup use, actual-status exhaustion, failed-attempt counts not causing failover, three-account exhaustion, exact workflow secret mapping, disabled-gate regression and durable primary-budget preservation. The stadium/crest tests and earlier duplicate/unknown-send protections remain passing.

Authentication fallback validation additionally covers first-to-second and first/two-to-third transitions, cached rejection skipping, HTTP 401, missing quota headers on rejected fixture requests, no false quota exhaustion, all-three-rejected failure, permission opt-out, policy-revision usage preservation, and no IP/account/plan/parameter-error switching. No new live run or Page post is inferred from these offline tests. A new owner-started run must select `main`; re-running an old workflow run may still execute the old commit.
