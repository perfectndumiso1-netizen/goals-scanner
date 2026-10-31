# Highlightly: verified factual Facebook live feed

## Current state

The owner confirmed that the API-Sports accounts are suspended, requested Highlightly for the Facebook score feed, and said `HIGHLIGHTLY_API_KEY` was added to GitHub Actions Secrets. All three API-Sports slots are now `authorised=false`. Secrets and existing quota/post/unknown-send history are neither deleted nor reset. They are not fallback candidates for Highlightly.

`score_source=highlightly` selects the adapter. Following the observed full diagnostic below, **`highlightly.verification_only=false` and `account_coverage_verified=true` now enable the verified factual source**, subject to the existing publication/master-variable, window, quota, freshness, baseline/meaningful-event, reservation and unknown-send guards. Adding a secret or passing offline tests alone never established this verification. No Facebook post is claimed by activation. No credentials are retrieved locally or printed.

Only the factual live-score/event feed changes. Android, predictions/odds, results, Reels, music, Telegram, other provider clients and their accounts are not migrated. The legacy `provider` section remains for its existing adapter, not as evidence that Highlightly access has been verified.

## Verify safely from a phone

GitHub → Actions → **Facebook meaningful live events (08:00–24:00 SAST)** → **Run workflow**, a NEW run on `main`:

- `diagnostic=true`
- `publish=false`
- `preview=true`
- `bootstrap=false`

The diagnostic now selects Highlightly, not any API-Sports account. It reads **all of today's match-list pages**, within the same ten-page safety bound and daily allowance, validating BASIC/FREE plan, quota headers, complete pagination, unique IDs, HTTP timestamps and parseable factual observations. When a usable observation exists, it reads **one matching detail** and verifies the fixture/team/kickoff identity and documented event-array schema. It reports only safe categories, counts and coverage metadata, never team/player data or provider messages. It does **not** fetch highlights/video, odds, predictions or Page data, and it does not advance live-event baselines or enable publishing. Require `coverage=complete_day`, `match_detail_verified=true`, `ready_for_activation=true` and `outcome=verified_read_only` before considering activation. An empty usable sample cannot verify the detail endpoint and never sets ready. Every page and detail request counts against the same allowance.

The existing production concurrency lock and production state namespace remain. The attempted request is counted even on errors and persisted through the final checkpoint, alongside the untouched original ledger. No bootstrap/reset is permitted. The diagnostic step has no Facebook credentials.

Read `API DIAGNOSTIC — NO FACEBOOK REQUESTS` in the check notice or job summary. The mode is `read_only_highlightly_diagnostic`, with `slot=HIGHLIGHTLY_API_KEY`. Require real verified access and suitable coverage before changing the two activation gates. A green workflow with `outcome=blocked` is not successful API validation. Agent dispatch previously returned 403; use the owner UI, not hidden triggers or repeated forbidden dispatches.

## Adapter behavior after explicitly verified activation

- Direct Football API only: `https://soccer.highlightly.net`, authenticated using `x-rapidapi-key` from `HIGHLIGHTLY_API_KEY`. No RapidAPI host, alternate hosts, redirects, key rotation or automatic return to API-Sports.
- Only `/matches` and `/matches/{id}` are permitted. Daily lists use SAST date/timezone and documented pagination. Up to ten 100-row pages per poll; page limits, changing totals, duplicate IDs, truncated pages, invalid plans, stale timestamps, quota/network/access errors block the observation instead of claiming a complete matchday. Account-wide usage from headers can reduce the local balance.
- At most two detail requests per poll, round-robin across active matches with missing tracked matches first. Details verify exact fixture/team/kickoff identity. They supply goal/scorer/red-card events only when present and validated. This is bounded coverage, not a promise that every worldwide card is captured. Missing detail data is not fabricated.
- Match states, current score and shootout score are separate. Missing score values never become zero; ambiguous/unknown phases are not guessed. Unavailable HT/FT period scores stay unknown. Added-time event strings are parsed only when documented; match-clock added time is not invented. Only supported genuine goals and red cards enter the existing change detector; missed penalties/VAR reviews are not goals.
- Provider fixture IDs are namespaced as `highlightly:<id>`. Old API-Sports matches/events/reservations remain in place, not relabelled, resent or sent to Highlightly's detail endpoint. New matches establish a baseline, without announcing earlier goals. Only fresh subsequent meaningful changes can produce the existing consolidated stadium image/caption. Old pending events cannot leak into new-source posts.
- API-Sports team IDs/CDN crests are NOT used for Highlightly teams: optional crests are omitted rather than showing the wrong real badge. Arbitrary logo URLs and videos are not downloaded.
- Reservation/checkpoint/hash/expiry/unknown-send/acknowledgement/Graph-ID verification protections remain unchanged. Restoring data is not a post, and Graph acknowledgement is not proof of public audience visibility.

## Quota and scheduling

The selected free allowance is **100 requests per UTC day**, shared with other uses of this Highlightly Football subscription. Each page/detail/failed attempt consumes local budget. A valid final permitted response is accepted; no 101st request is made. Changing the key does not reset usage. Only the Highlightly daily counter rolls at UTC midnight; access cooldowns survive midnight and old provider/post history remains untouched.

The owner restored **08:00 inclusive to 24:00 exclusive SAST** coverage. Outside that window normal live polling, preview preparation and live-score sends are blocked (event IDs do not bypass the send check, including a midnight crossing during Page credential verification). The existing GitHub `*/5` schedule is unchanged; out-of-window invocations do not read match APIs. Explicit read-only diagnostics remain available independently of the publishing window. Within the window, this adapter defaults to **20-minute minimum polling**, with strict budget skips; pagination/details may exhaust the allowance earlier. This is NOT guaranteed 24-hour global coverage. Five-minute polling alone needs 288 requests/day before details/pagination. No paid subscription is purchased or silently enabled; non-100 allocations/non-Free plans are refused in this integration.

## Provider terms and factual-only scope

Official references reviewed 30 October 2026:

- https://highlightly.net/football-api/documentation/ — direct host, authentication, subscription distinctions.
- https://highlightly.net/football-api/documentation/matches/ — date query, score/state meanings, pagination.
- https://highlightly.net/football-api/documentation/getting-started/pagination/ — plan wrapper and quota headers.
- https://highlightly.net/football-api/documentation/docs.json — documented match detail array, events, states and score fields (v8.2.7). Examples are schema fixtures, never live evidence.
- https://highlightly.net/football-api/ — free Basic 100/day.
- https://highlightly.net/terms/ — §§6–7 allow data use/distribution but prohibit API pass-through, competing database extraction, quota circumvention and use supporting gambling/betting operations. Visual rights remain the user's responsibility. A football-data subscription is not a license to download/repost videos or unrestricted commercial logos.

This integration excludes betting/prediction use. The owner must ensure the actual Page/use complies with Highlightly's terms; this is not an independently audited license or legal assurance. If the intended use supports betting operations, obtain provider clarification/permission rather than repurposing this factual adapter.

## Offline validation

Full suite: **1,010 passed, 1 skipped, 8 subtests passed**. Focused Highlightly/diagnostic/event/account/stadium suite: **169 passed**, including **40 Highlightly tests**. Cases cover direct authentication, redaction, all error attempts counted, quota/final-request/UTC/cooldown boundaries, complete pagination and partial refusal, verified events, separate IDs/crests, identity mismatch, baseline/no-minute-only behavior, terminal detail confirmation, unchanged unknown-send guards, staged activation gates and durable zero-Facebook diagnostic state. These are mocked tests, not proof that the live Highlightly subscription has yet been verified.


## Observed diagnostic and restored window (30 October 2026)

Owner-triggered run [41129451774](https://github.com/perfectndumiso1-netizen/goals-scanner/actions/runs/41129451774), on the merged Highlightly adapter, reported `verified_read_only` at 23:14:03 SAST. Direct Free access and the first match-list page passed: allocation 100, requests 1, remaining 99; 100 rows read, 97 usable observations, 284 total rows, `coverage=first_page_only`, Facebook requests **0**. This confirms a real response, not complete-day pagination, detail endpoint verification or publication. Activation gates remain unchanged pending those remaining checks.

The owner then explicitly restored the 08:00–24:00 SAST window. Sixteen-hour five-minute polling alone needs **192 requests/day**, still above 100 before pagination/details. The observed 284-row day requires three 100-row pages for each complete-day sweep; shorter coverage therefore does not guarantee five-minute global updates, or even continuous 20-minute full-day coverage on this allowance. Quota stops remain enforced; no paid plan or extra account is enabled.

Window-change validation: **1,021 passed, 1 skipped, 8 subtests passed** (full suite); **136 passed** (focused window/Highlightly/event/diagnostic suite). New boundary tests cover SAST/UTC 07:59, 08:00, 23:59 and midnight; preview/direct polls outside coverage; no Page reconciliation outside coverage while keeping the production namespace; event-ID sends and a midnight crossing during credential verification. These tests do not replace the remaining live-provider coverage checks.


## Full pre-publication diagnostic update

The previous run 41129451774 verified only page one; it did not establish complete pagination or match-detail access. The owner subsequently requested triggering a Facebook post. Rather than bypass the unchanged activation gates or dispatch a normal run known to be blocked, the diagnostic now checks complete pagination plus one validated detail. On a 284-row day that means three list reads and one detail read, subject to actual remaining quota and current match availability. This is not an observed new run or a post; the existing first-page result remains the only real verification until the owner starts the updated diagnostic. The 08:00–24:00 SAST live window, production namespace, all unknown-send records, and disabled suspended accounts remain unchanged. A passing offline test or `ready_for_activation` diagnostic does not automatically flip config or publish.

Full-diagnostic update validation: **1,028 passed, 1 skipped, 8 subtests passed** (full suite), **75 passed** (focused Highlightly/diagnostic/window tests). New cases verify all 284 synthetic rows plus one detail, incomplete-page/identity/event-schema/network/quota failures, no false readiness for empty days, unchanged baselines/unknown sends, and no automatic activation. No new real-provider run or Facebook post is asserted by these tests.


## Verified activation — 31 October 2026

The owner requested Facebook publication, then started the updated full diagnostic. Observed [run 41164360718](https://github.com/perfectndumiso1-netizen/goals-scanner/actions/runs/41164360718), job 124428598336, at **05:26:13 SAST** returned:

- `outcome=verified_read_only`, `reason=verified_full_match_list_and_detail`
- `coverage=complete_day`, 868 rows across 9 pages, 61 usable observations
- `match_detail_verified=true`, `ready_for_activation=true`
- allocation 100, accounted requests 10, remaining 90
- **Facebook requests 0**

This is now real complete-list/detail verification, superseding the earlier first-page-only result. The owner had already requested enabling and triggering publication after successful verification. Only the two source activation switches are changed; `verification_reference` records the safe run evidence. No quota/history reset, provider-account re-enabling, baseline bootstrap, schedule/interval change or duplicate-send bypass occurs.

For a new owner-triggered normal run on `main`, use **diagnostic=false, publish=true, preview=false, bootstrap=false**. Only within **08:00–24:00 SAST** can it fetch and prepare live observations. A first live poll establishes a baseline, without announcing historical goals. Subsequent fresh meaningful changes may create a reserved/verified post, subject to all existing master, Graph and policy gates. Config activation, workflow success and API verification are not a Facebook post. Require an acknowledged and verified Graph ID before claiming publication. Read-only diagnostics can still be requested without posting, independently of the coverage window.

The observed 868-row day costs **9 list requests per complete sweep**, before up to 2 detail calls. With 90 remaining at diagnostic time, at most eight such 11-call sweeps fit if totals and other usage stay unchanged. Thus the configured 20-minute minimum does not guarantee updates throughout the full 16-hour window: quota exhaustion may stop reads earlier. The 100/day limit is unchanged; no extra keys or paid plan are introduced. The quota counter rolls at midnight UTC, not on activation, credential replacement or workflow start.

Activation validation: **1,033 passed, 1 skipped, 8 subtests passed** (full suite), **162 passed** (focused activation/Highlightly/diagnostic/window/account/event tests). Production-file tests verify the two activated source gates, the existing time window/request bounds, continued exclusion of all suspended accounts, and baseline-before-change behavior. Historical staging tests explicitly select staging rather than asserting it is still production. Send-failure regression tests now use a fixed in-window clock so midnight/window protections are not inadvertently bypassed or wall-clock dependent. This validation is not evidence of a new Facebook run or post.
