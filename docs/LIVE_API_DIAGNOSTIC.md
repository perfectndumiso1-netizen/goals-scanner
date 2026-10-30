> **Current source: staged Highlightly.** All API-Sports slots are disabled following the owner’s confirmation that the accounts are suspended. Highlightly is selected for read-only verification; live publishing remains blocked until its access/coverage gates are approved. Earlier account-selection/activation descriptions below are historical. See [HIGHLIGHTLY_LIVE_FEED.md](HIGHLIGHTLY_LIVE_FEED.md).

> **Approved account selection:** the owner confirmed that API-Sports permits this same project to use the two independent active backup accounts while the original account is suspended. The original slot is now disabled, not queried or removed. Diagnostic mode checks the two approved accounts through `/status` only; see the update below.

# Read-only live API/key diagnostic

The owner requested a diagnostic after production run 41115785226 reported only a generic credentials/account-authorisation rejection. That generic report did not prove a key was damaged, identify the blocking slot, or establish which backups were tried. Do not infer those facts from the old message.

## Run safely

Actions → **Facebook meaningful live events (24h)** → **Run workflow**, select a NEW run on `main`:

- `diagnostic=true`
- `publish=false`
- `preview=true`
- `bootstrap=false`

The diagnostic input defaults false, so normal schedules/other feeds are unchanged. Selecting diagnostic mode skips content preparation, reservations and Facebook publishing even if someone also selects publish. The diagnostic step receives only the GitHub read token and three API key slots; no Facebook token/Page ID is passed. It does not import or call Page publishing operations.

The normal independent feed concurrency group serialises it with publishing. It restores the existing **production** namespace and refuses missing-ledger bootstrap. It exercises fresh `/status` checks for each eligible approved account through the same provider validation and failover policy. No global fixture read occurs in diagnostic mode. Request accounting and cooldown updates are saved back through the existing final checkpoint; match snapshots, pending events, unknown sends, post IDs and history are not reset or advanced. No extra paid service, synthetic score, image upload, Reel operation or Page call is involved.

## Safe output

The job emits an `API DIAGNOSTIC — NO FACEBOOK REQUESTS` notice, a job summary and `api-diagnostic.json` in its existing public planning artifact. The notice can be inspected through GitHub's check annotations without downloading raw logs or signed artifacts.

Per slot (`API_FOOTBALL_KEY`, `API_FOOTBALL_KEY_1`, `API_FOOTBALL_KEY_2`), it reports only:

- Whether a nonempty credential is configured and the slot is authorised.
- Whether an HTTP attempt actually occurred (not an assumption that every backup was used).
- Fixed endpoint names (`status` for this account-only audit), closed failure categories, HTTP status number when applicable, and authentication-fallback eligibility.
- Whitelisted error-field **names**, e.g. `token`, `ip` or `parameters`; unknown field names become `other` and are never echoed.
- Which approved slots succeeded and their verified allocation, provider usage and remaining request counts. No actual match scores are presented as a demonstration post.

Provider messages, raw responses, actual credentials/fingerprints, account names/emails, request headers and signed URLs are never included. Recognised categories include `authentication_rejected`, `mixed_authentication_rejection`, `ip_access_restriction`, `account_suspended`, `account_access_restriction`, `plan_or_coverage_rejection`, `rate_or_quota_rejection`, `parameter_rejection`, `transport_or_invalid_response`, and credential/account cooldown skips.

## Interpretation

A diagnostic workflow can complete successfully while the report says `outcome=blocked`: that means safe diagnosis completed, not provider authentication or Facebook publication succeeded. Require `outcome=verified_read_only` and both approved successful slots to confirm their real verified API responses. `facebook_requests` is always zero.

Authentication rejection and quota exhaustion can follow existing configured failover. IP restrictions, account suspension/blocking, plan/parameter failures, ordinary minute rate limits, network and unrelated server errors do **not** cause attempts intended to bypass provider restrictions. The diagnostic does not force every slot to be probed after such a policy stop; slots not attempted are explicitly shown as such. Look at the final attempt/category before deciding whether provider configuration needs attention.

A diagnostic does not establish/update the live event baseline. To resume normal posts, start a NEW run on `main` with diagnostic false, publish true, preview false, bootstrap false. Existing freshness, source/rights, master-variable, meaningful-event, image, quota and duplicate-send protections still apply.

## Dispatch permissions and validation

After merging the diagnostic input, the agent can attempt the explicit read-only dispatch. If GitHub again returns `403 Resource not accessible by integration`, report the denial accurately and use the owner phone UI above. Do not claim a diagnostic ran, retry unchanged, ask for key values, create a hidden push trigger, or bypass the integration's permissions.

Offline validation before this account-selection update: **956 tests passed, 1 skipped, 8 subtests passed**; focused diagnostic/event/stadium suite **115 passed**. New tests cover secret/unknown-field redaction, restricted first-slot stops, eligible second-slot fallback, all rejected/missing slots, zero Page calls, durable quota updates with unchanged unknown-send history, wrong branch/missing ledger refusal and workflow diagnostic isolation. Real provider diagnosis is confirmed only by an observed Actions run and its report, not these mocked tests.


## Approved independent accounts update

The owner explicitly confirmed provider permission for this project to use `API_FOOTBALL_KEY_1` and `API_FOOTBALL_KEY_2` while `API_FOOTBALL_KEY` is suspended. Production configuration now sets the original slot's `authorised=false`; it is not read for requests, retried, reset or deleted. Its `primary` quota group and prior usage remain intact. Normal live monitoring starts with `_1`, with `_2` as the configured independent fallback under the existing quota/authentication policy. This records owner attestation, not an independently audited provider permission document.

Diagnostic mode now makes **one fresh `/status` request per approved configured account**, not a global fixture request. It reports both approved accounts' safe verification outcomes and available quota metadata; the disabled original is explicitly labelled `disabled` and `http_attempted=false`. It never fetches fixtures, advances event baselines, renders images or contacts Facebook. If an approved account returns a NEW IP/account restriction, the diagnostic still stops: the suspension/access checks were not relaxed. Missing credentials, exhausted quotas and permitted authentication failures retain the existing policy and safe accounting.

Only two allocations are currently eligible: **200 gross requests/day**, not 300. Five-minute polling all day would require at least 288, before overhead/other consumers, so the existing quota-aware skips remain necessary. No extra allocation was created and no budget/history was reset.

Validation of this update: **969 passed, 1 skipped, 8 subtests passed** (full suite); **128 passed** (focused account/diagnostic/event/stadium tests). Production-file tests prove the disabled original is excluded, approved order/fallback, restriction stops, one fresh status request per approved account, final permitted response acceptance without a 101st call, and unchanged disabled history/unknown sends. These are offline tests, not evidence that either live account has yet passed the new diagnostic.
