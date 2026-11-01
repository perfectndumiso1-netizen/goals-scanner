> **Current update:** [Four-picture match posts](FOUR_PICTURE_MATCH_POSTS.md) supersedes the two-picture format, six-league-only selection and winner question below. New posts include recent H2H and home/away form, broader evidence-led selection, and natural form/trend captions. Historical posts and reservations are unchanged.

> **Latest owner update:** [Morning Advisor and separate video accumulators](MORNING_ADVISOR_AND_VIDEO_RESULTS.md) supersedes the 07:30 fixtures bulletin with published Bet Advisor 1X2 picks, adds one 06:00 video recap with independent accumulator sections, and uses the selected **Mr 2 Odds** logo on future pictures. The nine two-picture match targets remain. Older timetable/branding descriptions below are historical.

# Nine match packages per day

Supersedes the six league-specific feature slots and old 08:30/results,
19:30/story and 23:00/finals opportunities. The owner requested nine distinct
matches, two pictures per match, and accepted hourly 08:00–16:00 SAST targets.
The separately requested **07:30 combined fixtures bulletin is preserved**.

## Timetable (SAST)

| Time | Content |
|---|---|
| 07:30 | One combined fixtures bulletin covering the six approved leagues |
| 08:00 | Match 1: comparison + recent-results pictures, one feed post |
| 09:00 | Match 2: same two-picture format |
| 10:00 | Match 3 |
| 11:00 | Match 4 |
| 12:00 | Match 5 |
| 13:00 | Match 6 |
| 14:00 | Match 7 |
| 15:00 | Match 8 |
| 16:00 | Match 9 |

Nine match posts means **18 pictures**, not 18 separate feed posts. Together with
the fixture bulletin the maximum is ten editorial posts. There is also an
explicit nine-feature cap. Existing published/reserved/unknown history still
counts on deployment day; it is never reset to make room for a new timetable.

These are target windows, not guaranteed delivery times. The first match may
wait until at least 08:15 after a 07:30 bulletin because the existing 45-minute
minimum feed gap remains. The unchanged watchdog checks at :13/:33/:53, and
match slots retain a +50-minute backup. Fixtures have a 07:50 backup, before
the first match window. Latest active slot takes priority at 08:00; no missed
bulletin or old results/story backlog is flooded into the nine match windows.
GitHub cron itself can still be delayed/missed; no independent scheduler has
been configured by this change.

## Fixture selection and facts

- Same six approved countries/leagues only. No live feed, odds or predictions.
- One distinct safely upcoming fixture per match slot, kickoff more than ten
  minutes away; immutable fixture topic/key and same-day slot dedupe remain.
- Earlier safe kickoffs are preferred. Remaining places are reserved for
  eligible leagues not yet represented when otherwise they would be crowded
  out. Empty leagues do not force an invented fixture or prevent other leagues
  filling the nine target opportunities.
- The target is **nine distinct matches**, never a guarantee when complete
  verified samples/fixtures/quota are unavailable. A day with fewer valid matches
  produces fewer posts plus recorded reasons, not filler.
- One expensive candidate per preparation attempt. A factually unusable fixture
  is noted in the day's cache so it cannot starve every later slot. Temporary
  network/quota/cooldown failures do not silently switch fixture/provider/key.
- Comparison uses the same five completed same-league/season, all-venue matches
  per club as before. The recent-results card reuses **these exact samples**.
- Recent rows include real opponent names, date, H/A, team goals/opponent goals,
  and derived W/D/L, newest first. **Team score first**, including away matches,
  is explicit. No extra API calls for the second picture and no guessed results.
- Existing sample cross-checks, upcoming detail verification, shared 100/day UTC
  budget, cooldowns and conservative crash quota holds stay in effect. Broader
  league coverage may use more of that same budget; it is not increased.
- Approved first-card crests/player-photo rules and picture-only branding remain.
  Second card uses real registered club crests, with no provider/check footer.
  Caption retains at most three factual bullets plus relevant hashtags/question.

## Two-photo publication safety

1. Render both pictures; bind **both ordered SHA-256 hashes** and the verified
   snapshot to one reservation. Missing/tampered/swapped/removed second pictures
   block publishing; no single-picture fallback.
2. Save the existing durable reservation artifact.
3. A dedicated `stage` step uploads both photos with **published=false**. It does
   not call `/feed` and creates no public feed post. Known returned photo IDs
   remain in the checkpoint, including any orphan IDs from incomplete staging.
4. Save a separate **media-staged artifact containing both IDs**. The feed step
   requires successful media checkpoint upload and explicit `--media-checkpoint`.
5. Create **one** Page feed post with the caption and both attached media IDs in
   comparison/results order. Never post two independent public photo posts.
6. Read back Page post ID, exact caption, published flag and both attachment IDs
   in order. Missing, partial, reordered or unavailable attachment read-back
   retains an uncertain reservation—not a false success or another upload.

An acknowledged staging failure is different from an uncertain feed creation:
the staging function can only issue unpublished `/photos` requests, never a
`/feed` request. It can cancel that **unpublished-only** attempt and permit a
bounded fresh preparation, retaining known orphan IDs without auto-delete. This
cannot duplicate a public feed post. A process killed without such phase proof
remains unresolved. Any uncertain final feed POST or failed post-send read-back
is still **unknown, no blind resend**. Existing operator reconciliation remains.

Positive watchdog/operator reconciliation for packages must verify both known
media IDs, not just the caption. When evidence is missing it alerts rather than
claiming delivery. The same maximum three attempts/backoff, unknown blocks and
expiry safeguards apply. Monitoring can migrate schedules without resetting
old attempts, publication history, quota or ambiguous evidence; positively
reconciled older-schedule posts stop producing stale alerts.

## Scope and validation

Legacy factual builders remain as regression-tested compatibility code, not
additional active publication slots. No scanner/Reel/Android/model/music,
credentials, API-account fallback, provider rights, storage or unrelated feed
changes. No change claims new live API access or visual licences.

Offline tests cover all nine slot boundaries, preserved bulletin/cooldown,
league coverage, distinct fixtures, nine-match/ten-total caps, no-extra-call
recent results, away orientation, strict render facts, both-picture hashes,
unpublished upload bodies, durable media gate, one feed creation, partial
failures, no blind resend, read-back shapes/order and watchdog migration.
Actual Graph permissions and two-photo display still require live acknowledgement
and verification. No synthetic test post, existing-post edit, Reel reupload or
workflow dispatch is authorised merely to test this template change. Prior
manual workflow dispatch returned 403; do not bypass that restriction.
