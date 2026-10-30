# Facebook live-score activation — 30 October 2026

## Evidence and permission boundary

The owner requested live Facebook publishing and explicitly selected **“Yes, permission confirmed”** when asked whether the applicable API-Football data-publication permissions cover the Page, including any required rights-holder permissions. This is the owner's confirmation, **not independent legal verification and not a claim that an API key grants publication rights**. API-Football's [terms](https://www.api-football.com/terms) distinguish API access from publication permission.

The replacement-key tests provide separate technical evidence:

- [Preflight 41072417420](https://github.com/perfectndumiso1-netizen/goals-scanner/actions/runs/41072417420): the coverage catalogue returned current competition/statistics coverage. Catalogue coverage alone does not prove account entitlement to live fixtures.
- [Live preview 41072704384](https://github.com/perfectndumiso1-netizen/goals-scanner/actions/runs/41072704384): generated a fresh app-covered score candidate (`status: dry_run`). Existing code requires actual normalized fixtures, exact app club-side/kickoff matching and source freshness before producing that candidate. Facebook reservation and mutation steps were skipped.

Accordingly, **only the API-Football provider's `rights_confirmed` and `account_coverage_verified` flags are now true**. Account verification means a real qualifying app-matched fixture test succeeded, not that every app league, fixture or supplemental stat is universally accessible. Missing/restricted/ambiguous/stale data continues to skip. Extra-stat availability in the actual preview was not independently inspected. The unofficial app-source approvals remain false; no automatic source fallback is introduced.

## Preserved scope and safety

- Only `results` and `live` are authorised; unrelated community/cards/weekly/late roundups stay paused.
- Score checks at ten-minute intervals, 08:00–23:59 SAST. Overnight kickoffs excluded entirely; no midnight carry-over.
- One shared 90-request/day operational cap; optional stats use the same budget, max six attempts/day/two fixtures per eligible update. No paid service or increased quota.
- Three new score posts/day, existing 60-minute new-post cooldown. Editing remains off. Score/stat ticks do not trigger extra posts.
- Same Page credentials, exact app matching/freshness, expiry, source revalidation, hash/read-back, reservation and unknown-send protections.
- Existing three video editions/Telegram, supplied music, caption/cover rules, model/markets and Android APK unchanged.
- If either provider approval is revoked, scheduled preparation blocks before provider/Page access. Send also rechecks source/type approvals.

## Existing production history — do not bootstrap/reset

Read-only artifact metadata showed an existing main/live namespace `pr-feed-state-3106028d38475832-`, including latest checkpoint `pr-feed-state-3106028d38475832-40988588586-1-main-final` (30 October 01:54:52 UTC) and earlier reconciled checkpoints. Existence alone does not prove the contents are healthy or every reservation resolved. Restore and validate that ledger normally. A failed restore must block, never reset. **Leave `bootstrap` false.** Do not clear history just because a publication is blocked.

## Owner-side publishing switch

The session cannot read/change `FACEBOOK_FEED_PUBLISH` (GitHub integration HTTP 403). This is a repository **Actions variable**, not the API secret. The current value is unverified.

On a phone, open [Actions variables](https://github.com/perfectndumiso1-netizen/goals-scanner/settings/variables/actions). Create or edit:

- Name: `FACEBOOK_FEED_PUBLISH`
- Value: `true`

Do not modify or share `API_FOOTBALL_KEY`, `FACEBOOK_PAGE_ACCESS_TOKEN` or `FACEBOOK_PAGE_ID` values. No credential value was read or printed by this session.

Once this activation is merged and the master variable is true, eligible scheduled jobs may publish. To request the first fresh live update manually, use [Facebook feed engine](https://github.com/perfectndumiso1-netizen/goals-scanner/actions/workflows/facebook-feed-run.yml), start a **new** run on `main` with `kind=live`, `publish=true`, `preview=false`, `bootstrap=false`. This is an actual publication request, not another dry run. Normal eligibility/cooldowns/caps may still skip it. Starting a new run regenerates current data; do not resend a saved draft/caption as a live update.

## Verification after the first attempt

A successful workflow badge alone is not enough. Inspect its safe annotations/report to distinguish `skipped`, `reserved`, `published`, `unknown`, credential errors and expired content. A successful mutation needs a post ID plus caption read-back; public-audience visibility/business-verification remains a separate owner/non-role check. If a mutation is ambiguous or the token fails, inspect the Page and reconcile the exact reservation; never blindly bootstrap, clear the ledger or create a replacement post.

No Facebook publication was executed directly by the agent while preparing this activation. The master variable, first live Page send/read-back and public visibility remain unverified until an actual publication run is inspected.
