# Highlightly schedule-cache and targeted-refresh assessment

**Historical assessment — 31 October 2026, before the scope decision. Production was unchanged during this assessment.** No score-provider calls, key access, Facebook operations, state resets, schedule changes or account changes were made for this assessment. The offline calculator and tests are not imported by the feed or its workflows.

## Subsequent owner decision

After receiving this assessment, the owner approved selected coverage from PSL, LaLiga, EPL, Bundesliga, Ligue 1 and Serie A, capped at five matches/day. The separate implementation is documented in [selected-match operations](HIGHLIGHTLY_SELECTED_MATCHES.md). The assessment below preserves the evidence and modelling at the earlier decision point; its “decision required”/“unchanged” statements describe that stage, not the later configuration. The eight-reads-per-match estimate is **not an implemented hard limit**.

## Bottom line

Caching the daily schedule is technically feasible and can remove repeated nine-page downloads. However, each documented match-detail request covers **one match**. It is a substantial saving for a small selected set, **not a solution for frequent worldwide updates under 100 requests/day**.

No live-only list filter, multi-ID detail batch, larger-than-100 match-list page, push stream or free request exemption was established in the reviewed documentation. Do not invent `live=all`, comma-separated IDs, a 1,000-row page or no-cost conditional requests based on other providers' APIs. A return type of array for `/matches/{id}` is not evidence of batch input support. Provider clarification could change this assessment; no undocumented parameters were probed.

**Recommendation:** keep the existing production behavior until the user chooses the trade-off. For frequent updates to a deliberately limited set, build an opt-in metadata-cache/targeted scheduler. For unchanged worldwide scope, favour bulk reads with quota-aware pacing across the window; targeting every live fixture can be more expensive than the current bulk approach. Neither option promises five-minute worldwide coverage.

## Evidence reviewed

### Repository

- `facebook_feed/highlightly.py`: `page()` requests today's SAST list at 100 rows/page; `matches()` validates complete pagination; every normal `poll()` downloads it again before up to two detail requests.
- `Highlightly.detail()` already uses a provider-namespaced single ID and validates a detail/event response. The prior owner-triggered full diagnostic actually verified this endpoint.
- `observation()` is an observation normalizer, **not a schedule cache parser**. It discards many future/distant fixtures under the live freshness/kickoff checks. Reusing only its returned values as the calendar would lose the very future matches a scheduler needs.
- `highlightly_monitor_cache` currently holds timing/cursor metadata, not a complete persistent daily kickoff catalog. The event ledger is not a full future schedule either.
- `Highlightly.request()` counts attempts, honours account-wide quota headers/cooldowns, and requires a verified Free plan before details. `plan_verified_at` is cleared on UTC-day rollover; a cached schedule must not bypass the new day's account/plan validation.
- The existing production checkpoint/namespace and concurrency lock can persist a bounded catalog without a new paid service or app/backend migration, but this has **not** been implemented or tested live.
- Live operation remains 08:00 inclusive to 24:00 exclusive SAST. Source freshness, baseline suppression, meaningful changes, unknown-send blocking and verified Graph acknowledgements remain mandatory.

### Prior observed provider evidence (not a new query)

Owner-triggered diagnostic [41164360718](https://github.com/perfectndumiso1-netizen/goals-scanner/actions/runs/41164360718) at 05:26:13 SAST on 31 October reported 868 rows, 9 pages, 61 **usable observations**, a verified detail and 90 remaining requests. **61 usable observations does not mean 61 concurrently live matches.** The report does not expose the full kickoff distribution/concurrency trace. Ninety is a historical observed balance used as a model input, not a newly checked current balance.

### Official provider documentation

Reviewed 31 October 2026:

1. [Match-list reference](https://highlightly.net/football-api/documentation/matches/): date/timezone and league/country/team filters, paginated general scores/status; a list read already contains current scores. The provider describes one-minute list refresh, not a guaranteed application polling SLA.
2. [OpenAPI specification](https://highlightly.net/football-api/documentation/docs.json), match routes (v8.2.7 in the previously reviewed reference): list `limit` maximum 100; `/matches/{id}` takes one numeric path ID and returns detailed match/events. No live-only/multi-ID parameter is declared on these routes in the reviewed spec.
3. [Pagination and quota headers](https://highlightly.net/football-api/documentation/getting-started/pagination/): each page spends quota; account-wide remaining/limit headers must still govern reads.

No authenticated API call was made, and no undocumented API behavior, endpoint reliability, timing distribution, or permission expansion is claimed.

## Reproducible request-cost model

Run without credentials or network:

```sh
python scripts/analyze_highlightly_budget.py --rows 868 --remaining 90
python scripts/analyze_highlightly_budget.py --rows 868 --remaining 100
```

Inputs below are **illustrative assumptions**, not a new production plan:

- Half-open 08:00–24:00 window = 960 minutes, 48 starts at a 20-minute interval (last 23:40, not midnight).
- 868 list rows = 9 requests per complete catalog.
- Two catalog scans per day (e.g. 08:00 and 16:00) = 18 requests.
- Ten requests of hypothetical planning headroom for errors/other usage. **Production reserve remains 0; this assessment changes neither the 100th-request allowance nor any configured budget.**
- Eight detail reads per selected match, **including** baseline/terminal reads in that allowance. This is a cost assumption, not a guarantee that eight reads reach FT or catch every event. Delays, extra time, suspensions, schedule changes and failures can require more. A 20-minute poll can also miss a short HT interval.

### Current full-list demand if every cycle runs

| Work over 16 hours | Requests |
| --- | ---: |
| 48 full list sweeps, 9 pages each | 432 |
| Those sweeps plus the current maximum 2 detail reads each | Up to 528 |

The second row is a ceiling under the assumed fixed row/page count and successful eligible cycles, not an observed bill. Actual quota guards stop much sooner. Fewer active fixtures reduce detail calls, not the nine-page list cost.

### Cached catalog + selected match costs

| Selected matches/day | Catalog requests | Detail requests at 8/match | Planning headroom | Total model demand | Fits an input balance of 90? |
| --- | ---: | ---: | ---: | ---: | --- |
| 2 | 18 | 16 | 10 | 44 | Yes |
| 7 | 18 | 56 | 10 | 84 | Yes |
| 8 | 18 | 64 | 10 | 92 | No |
| 12 | 18 | 96 | 10 | 124 | No |

With a fresh **100-request input**, the same arithmetic fits up to 9 matches at 8 reads each (`18 + 72 + 10 = 100`). With the historical **90-request input**, it fits up to 7 (`18 + 56 + 10 = 84`). These are aggregate capacity examples, not reliable live-match or post counts. Do not silently replace the requested worldwide scope with this limited selection.

### Why targeting can also be worse

On an individual refresh, fetching A live matches by ID costs A requests. The current 868-row bulk list costs 9 before optional details. Targeting only 2 matches costs 2; targeting 20 costs 20. However, bulk list scores and per-match details do not provide identical event coverage: the current extra two detail calls cover only a subset of matches.

Daily affordability is not cadence. With at most two targeted requests every 20 minutes and round-robin selection:

| Concurrent selected matches | Time for one full round, **if every slot is funded** |
| --- | ---: |
| 1–2 | 20 minutes |
| 5 | 60 minutes |
| 8 | 80 minutes |
| 12 | 120 minutes |

The two-per-cycle ceiling itself would cost 96 detail requests over the full window, before catalogs/headroom, so it cannot be funded continuously under this example. Refreshing one match every 20 minutes throughout the window costs `18 + 48 + 10 = 76`; refreshing two costs `18 + 96 + 10 = 124`. A small number of matches at staggered kickoff times may fit far better than the same number playing concurrently.

### Worldwide alternative: slower but spread across the window

Keeping worldwide list sweeps at up to 11 calls each permits eight complete sweeps from the historical 90-request balance (`8 × 11 = 88`) if the page count stays nine and usage elsewhere does not change. Those sweeps could be budget-paced over the 16-hour window, roughly one every two hours, instead of consuming the balance in the early morning. That preserves broad score discovery but materially delays updates; red-card/scorer detail remains limited. This is an option, **not a production scheduling change made here**.

## Implementation requirements if targeted mode is approved

1. **Explicit scope choice first.** Worldwide scope remains the standing request. Do not re-enable the old 6–7-match watchlist, pick leagues/teams, or narrow to the app's fixtures without approval. Any selected-match mode must be labelled as selected coverage, not global live coverage.
2. **Separate bounded metadata cache.** Validate/cache today's IDs, team identity, competition, aware SAST kickoff and fetch time from raw schedule rows, including future NS fixtures. Do not use cached score/phase/clock as publishable observations. Preserve the existing production ledger and namespaces, quota usage, unknown sends and immutable post history.
3. **Atomic complete catalog.** Publish a replacement catalog only after all pages pass identity/schema/pagination checks. On failure retain old metadata with an explicit degraded/stale flag; do not call it a complete current day. Bound size/day retention and checkpoint growth. Nine-page discovery remains nine billable requests.
4. **Due-time + fair queue.** Use cached kickoffs to enqueue due fixtures, but never infer kickoff, FT, postponement or cancellation from the clock or absence. Remove a match from routine polling only on an appropriate explicit provider observation, or visibly mark it unresolved when a bound/budget prevents more checks. Rotation of active fixtures must not starve behind continually missing fixtures. Preserve protected pending/unknown events.
5. **Daily permission/plan verification.** Perform a validated fresh list/plan check after UTC rollover before serving detail reads. A partial page can establish account plan metadata, not catalog completeness. If it is followed by a complete scan, count/reuse that page only within a compatible fresh, validated snapshot; otherwise budget the extra request explicitly.
6. **Quota-aware scheduling and failure accounting.** Respect local and provider-reported budgets, other consumers, Retry-After and cross-midnight cooldowns. Pre-budget complete catalog reads using a conservative estimate, stop safely on quota exhaustion, and count every actual page/detail/failed attempt. Never reset usage or introduce new account/key rotation.
7. **Fresh, identity-checked detail observations.** Details provide score/status/events together, so do not duplicate a list read for each tracked fixture. Validate provider-namespaced fixture ID, teams, kickoff, phase, goals and supported incident fields. A new source sample establishes a baseline; cached metadata must not generate goal/HT/FT events. Maintain actual per-observation source timestamps, the existing 180-second freshness bound, image hashes, send-time window/expiry and acknowledged/verified Graph IDs.
8. **Rediscovery trade-off visible.** Most kickoff activations can be discovered from the initial complete catalog. Fixtures added/retimed after that scan can be missed or late until rediscovery. Two scans eight hours apart can mean almost eight hours of delay for a newly added fixture; caching is not real-time global discovery.
9. **Replay before rollout.** Simulate sparse and busy days, simultaneous kickoffs, added fixtures, changed identities, UTC/SAST boundaries, NS delays, partial scans, unknown/extra-time statuses, red cards, explicit finals, provider errors, stale bodies and ambiguous sends. Report worst revisit gap, targets omitted, missed deadlines, costs and degraded coverage—not just average request savings. Use a read-only owner-approved diagnostic later if fresh provider evidence is required; no secret values in reports.

## Decision required before any production change

- **Selected matches:** potentially much cheaper and faster per selected fixture; accept narrower coverage and approve how matches are chosen. Aggregate 7–9-match examples are not selection or delivery guarantees.
- **Worldwide scores:** keep broad scope, but accept much slower quota-paced sweeps on this allowance. A documented more efficient bulk/live endpoint or larger authorised quota would be needed for frequent global coverage.

No choice is assumed in this assessment. The current Highlightly adapter, production config, app, workflows and publishing behavior remain unchanged.

## Assessment validation

The offline calculator has **26 passing tests** covering page boundaries (including an empty query), half-open window counts, budget/headroom arithmetic, concurrency/revisit estimates, extra-time read assumptions, input validation and reproducible CLI output. Full repository suite: **1,059 passed, 1 skipped, 8 subtests passed**. These validate deterministic modelling and existing regressions, not actual source timing, production savings or a new score/API response. Only this report, the standalone calculator and its tests were added; production files are unchanged.
