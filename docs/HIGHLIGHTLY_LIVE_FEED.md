# Highlightly: staged factual Facebook live feed

## Current state

The owner confirmed that the API-Sports accounts are suspended, requested Highlightly for the Facebook score feed, and said `HIGHLIGHTLY_API_KEY` was added to GitHub Actions Secrets. All three API-Sports slots are now `authorised=false`. Secrets and existing quota/post/unknown-send history are neither deleted nor reset. They are not fallback candidates for Highlightly.

`score_source=highlightly` selects the new adapter. **`highlightly.verification_only=true` and `account_coverage_verified=false` deliberately block normal live polling/publication pending observed real-provider verification.** Adding a secret or passing offline tests does not prove subscription coverage or create a Facebook post. No credentials are retrieved locally or printed.

Only the factual live-score/event feed changes. Android, predictions/odds, results, Reels, music, Telegram, other provider clients and their accounts are not migrated. The legacy `provider` section remains for its existing adapter, not as evidence that Highlightly access has been verified.

## Verify safely from a phone

GitHub → Actions → **Facebook meaningful live events (08:00–24:00 SAST)** → **Run workflow**, a NEW run on `main`:

- `diagnostic=true`
- `publish=false`
- `preview=true`
- `bootstrap=false`

The diagnostic now selects Highlightly, not any API-Sports account. It performs one read of today's `/matches` first page, validates the documented BASIC/FREE plan, 100/day quota headers, envelope/pagination, HTTP timestamp and parseable factual observations. It reports only fixed safe categories, request counts and coverage metadata. It does **not** fetch highlights/video, odds, predictions, Page data or match details; it does not advance live-event baselines or enable publishing. If `coverage=first_page_only`, this read has not verified the complete day. Zero usable observations are reported honestly and are not proof of live-score coverage.

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
