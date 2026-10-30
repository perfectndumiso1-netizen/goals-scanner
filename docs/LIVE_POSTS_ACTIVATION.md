# Real live-post activation and renamed key slot — 30 October 2026

The owner explicitly requested committing the changes, triggering **real Facebook posts**, using each of the three independently authorised Free allocations at **100 requests/day**, and switching when an allocation actually runs out. This supersedes the initial dry-only gate and the event monitor's 90+10 reserve. The legacy provider/prediction/Reel budgets and all Reel/Android schedules remain unchanged.

## Current configuration

- `event_monitor.publish_enabled=true` (previously false).
- `event_monitor.daily_request_budget=100`, `daily_request_reserve=0`: up to the provider-verified allowance, never beyond it.
- `credential_revision="2"`: reverify corrected/renamed credentials without resetting existing account usage, snapshots, reservations or post IDs.
- Slots, in priority order: `API_FOOTBALL_KEY` → `primary`; **`API_FOOTBALL_KEY_1`** → `backup-1`; `API_FOOTBALL_KEY2` → `backup-2`.
- `API_FOOTBALL_KEY1` (without the underscore before 1) is no longer the event monitor's backup slot. No GitHub secret is deleted or its value read/copied into source.
- The owner has confirmed provider permission and an independent allowance for each slot. The existing rights, active-Free-plan, main-branch, Page credential, repository `FACEBOOK_FEED_PUBLISH`, durable-checkpoint, image-hash, content-expiry and unknown-send protections remain mandatory.

## Failover and capacity

A successful 100th provider request is used normally. When its daily remaining header becomes zero, the next request uses the next authorised allocation. Daily quota errors or verified `/status` usage reaching the account's actual limit also permit failover. Exhausted allocations are remembered through the UTC day, rather than repeatedly probed. Renaming a credential does not reset the account's usage.

Network failures, credentials/parameter errors, unrelated 5xx and ordinary per-minute 429s do not switch keys. A local conservative request-attempt count alone is not proof that the provider's daily allocation is exhausted: authoritative usage/remaining data or a documented daily quota response is required. Daily accounting resets at 00:00 UTC / 02:00 SAST.

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

`python -m pytest leagues/tests tests tennis/tests -q`: **922 passed, 1 skipped, 8 subtests passed**. Event replay coverage now includes the full hundredth request followed by renamed-backup use, actual-status exhaustion, failed-attempt counts not causing failover, three-account exhaustion, exact workflow secret mapping, disabled-gate regression and durable primary-budget preservation. The stadium/crest tests and earlier duplicate/unknown-send protections remain passing.
