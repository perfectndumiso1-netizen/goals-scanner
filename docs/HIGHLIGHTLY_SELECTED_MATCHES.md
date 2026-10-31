# Highlightly selected-match operations

## Approved scope

On 31 October 2026 the owner chose selected coverage from:

| Key | Competition | Required country |
| --- | --- | --- |
| `psl` | South African PSL | South Africa |
| `laliga` | LaLiga | Spain |
| `epl` | Premier League | England |
| `bundesliga` | Bundesliga | Germany |
| `ligue1` | Ligue 1 | France |
| `seriea` | Serie A | Italy |

The configured cap is **five distinct fixtures per SAST day**, not five simultaneous slots that are reused after FT. This is a new automatic selection, not the historical paused 6–7-fixture watchlist. No manually invented teams, app-prediction selection, paid service or new credentials are involved.

Competition aliases are exact after case/accent/punctuation normalisation and require the matching country. Similar-name cups, second divisions, youth/women's leagues and other countries are not selected. Unknown aliases fail closed; no worldwide fallback. Actual provider coverage/aliases are not newly proven by synthetic tests. Fewer than five qualifying fixtures means fewer than five selections, including zero on an empty day.

## How the roster is chosen

1. During **08:00 inclusive–24:00 exclusive SAST**, obtain a complete, verified daily schedule using the existing list transport (at most ten 100-row pages). Retain only selected fixture **metadata**, not cached publishable scores.
2. Consider fixtures with a verified NS/live phase, a kickoff on this SAST day inside the coverage window, and no more than six hours since kickoff. Future NS fixtures are retained even when the score normalizer would discard them.
3. Fill available slots with PSL first when eligible. Prefer representation across the six leagues, with European priority rotating deterministically by day. Within each league prefer fewer overlapping kickoffs, then proximity to the current time and deterministic kickoff/ID ordering. Six eligible leagues cannot all fit into five slots.
4. Persist the chosen identities/kickoffs in `highlightly_watchlist` in the **existing checkpoint/production namespace**. Finished/cancelled/unresolved slots are not replaced. Newly discovered PSL fixtures cannot displace an already full roster.
5. Permit a second complete catalog attempt normally at least eight hours after a successful scan. There are **at most two attempts/day**, including failures. A failed first attempt can retry after one hour (also subject to the poll interval); failures retain the previous roster and stop that cycle. Skip an optional rediscovery if its estimated pages would consume the last available detail allowance. No partial scan is committed.
6. A rediscovery may fill unused slots or retime an existing target before a confirmed live observation; it does not replace selected identities. Midday watchlist-settings changes fail closed until operator review or the next SAST day rather than resetting selection/counters.

The first complete scan can still be expensive. Newly added/rescheduled fixtures can be missed or delayed between scans. A full five-match roster stays full even if one match becomes unavailable.

## Refresh and event safety

- Keep the existing **20-minute minimum cycle**, with at most **two details/cycle**. Poll only due selected fixtures, oldest attempt first; a failed/unusable fixture advances its attempt time so it cannot permanently starve the others. Stop further requests in a cycle after a provider/access/network error.
- A detail must have fresh HTTP/source time (existing **180-second** bound) and match the selected namespaced ID, home/away IDs and names, competition/country and kickoff. Explicit PST/CANC observations may supply a rescheduled kickoff; an unexplained live kickoff change is rejected.
- The first accepted sample for each selected fixture establishes that roster's baseline. Existing snapshots/pending/unknown-send evidence is preserved. Crossing from an older global snapshot cannot announce historical goals: events newly created on that baseline are expired explicitly, and pre-baseline pending events are excluded from selected bulletins.
- Only subsequent fresh, accepted, meaningful score/HT/FT/status/shootout/verified goal/red-card changes can form a bulletin. Minute-only/unchanged observations do not publish. Rejected stalled/regressive observations are not reported as accepted fresh samples. Cached catalog phase/score/clock, absence and wall-clock passage never produce a goal, zero score, kickoff or terminal state.
- Stop routine detail reads after an explicitly confirmed terminal observation. More than six hours after kickoff marks the target **unresolved**, never FT. Reaching midnight, quota/cooldown limits or losing a fixture also never implies FT.
- Pending-event and send-time guards restrict selected posts to this day's roster and approved league identities. Old global/nonselected prepared score posts are cancelled before Page access. Existing reservations, content/image hashes, expiry/window checks, locks, unknown-send/manual-review blocks and Graph acknowledgement/verification remain.
- Caption label: **SELECTED MATCH UPDATES**, retaining PLAYREPORT ZA branding, SAST, the existing closing line and hashtags. No unrelated layout, Android, predictions, Reels, results or editorial scheduling changes.

## Budget and timing: promises we do not make

The same **100 requests/UTC day**, provider-reported balance, failed-attempt accounting, shared-use limits and cooldowns remain. Reserve stays **0**, a valid 100th response is accepted, and no 101st request is made. Key changes do not reset quota. Daily Free-plan verification is required after UTC rollover before details; cached metadata cannot bypass it. Midnight UTC is 02:00 SAST, outside normal coverage.

At the historical 868-row size, two complete catalogs cost 18 requests. Five fixtures at an **assumed eight detail reads each** cost another 40. This **58-request illustration** excludes failures, extra reads, other account use and diagnostics. There is no eight-read hard cap; delays/extra time/unknown phases can need more. The quota guard—not that illustration—is authoritative.

With five simultaneous targets and two funded detail slots every 20 minutes, a fixture can wait **up to about 60 minutes** for its next turn, longer with failures/cooldowns or exhausted quota. Staggered games can improve that. This is neither every-goal coverage nor guaranteed HT/FT or five-minute/per-match 20-minute updates. Late fixtures may not reach FT before the 24:00 boundary.

## See the real selected fixtures from a phone

Open the normal **Facebook meaningful live events (08:00–24:00 SAST)** Actions run on `main`:

- Job summary: **Selected live watchlist**.
- Check notice: **SELECTED LIVE WATCHLIST**.
- Existing feed artifact now also includes **`live-watchlist.json`** (`tmp/facebook-feed/live-watchlist.json` in the job).

These show public teams, competition, SAST kickoff, confirmed phase if observed, attempts and degraded/unresolved problems. They contain no cached score, key values, raw provider errors or account PII. A list is only actual once the production scan has committed it. Outside the window/no scan/failed scan can legitimately show an empty roster; do not fabricate a fixture to fill it.

The explicit read-only diagnostic additionally previews a candidate roster without committing it or changing baselines. It still spends real API quota; routine re-diagnostics are unnecessary. Its `coverage=complete_day` describes complete schedule pagination, **not worldwide publishing coverage**. Agent dispatch previously returned 403; use the owner UI if dispatch is needed, without bypasses. No bootstrap/reset or forced posting.

A workflow success, roster artifact or source verification is not a post. Only an acknowledged and subsequently verified Graph ID establishes a confirmed send; public audience visibility is a separate question.

## Implementation and validation

`facebook_feed/highlightly_watchlist.py` contains the bounded metadata/selection/polling logic. `highlightly.py` routes selected mode; `event_monitor.py` scopes events/captions; `cli.py` validates configuration, surfaces the roster and enforces send scope. The existing reusable workflow only adds the roster artifact, with no cron/permissions changes. One previous-day public roster summary is retained; existing event/post/quota history is not reset.

The selected-mode suite uses **synthetic transport only**, including actual-config routing, country/alias exclusions, future metadata, PSL/European rotation, cap/no-recycling, identity/retiming, partial catalogs/failures, fair queue, UTC/SAST boundaries, plan/cooldown/quota admission including the valid 100th response, stale/stalled observations, baseline transition from global mode, unknown-history preservation, read-only diagnostics, phone-summary artifacts and cancelling old unselected reservations before Page access. Full validation results are recorded with the implementation change. No live provider or Facebook request is part of these tests; actual teams, source coverage, savings and publication remain unclaimed until separately observed.

Local pre-rollout validation: **52 selected-mode tests passed; full repository suite 1,111 passed, 1 skipped, 8 subtests passed**. Credential scan: **301 tracked files, clean**; staged whitespace/diff checks clean. These are offline results, not deployment, current quota or posting evidence.
