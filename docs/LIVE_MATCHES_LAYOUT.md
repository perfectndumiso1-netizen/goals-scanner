# Compact Facebook live scoreboard

Owner requested the supplied screenshot's compact country/league/match structure, exactly **Live Matches SAST** as title, no owner/Page name, source or promotional caption, and up to ten league/football-keyword hashtags.

## Public presentation

- Exact first line: `Live Matches SAST` (no brand, date suffix or prefix emoji).
- Country flag where explicitly mapped (otherwise globe + actual country name), country and league heading once per group.
- Match minute/status, home club, actual goals, away club. Valid reported added time is shown only against regulation break minutes, not double-counted on a minute already advanced into stoppage time.
- Reported halftime scores where available. Second-half scores are derived only from validated actual goal totals minus halftime; extra-time/shootout goals are never labelled second half. Extra-time fixtures need a separate verified regulation-fulltime score before a second-half breakdown is printed.
- Compact rows of two labelled emoji stats, home–away: corners, yellow/red cards, shots on target, total shots, possession, goalkeeper saves, fouls and offsides. Null/missing/inconsistent values and unknown half scores are omitted, not replaced with zero or guesses.
- Up to seven unique league tags from leagues actually present, then relevant `#LiveScores #Football #FootballStats`, at most ten unique tags overall. Familiar country-specific league aliases are explicit; generic divisions/Premier leagues are country-qualified. These are relevant keywords, **not a claim of verified search volumes or trending rankings**. No unrelated leagues or guaranteed-win/betting tags.
- No printed name/brand/Page title, provider/source line, checked-time preamble, statistical disclaimer, engagement question, stats caption or promotional paragraph. Facebook itself will still display the Page identity in its native post UI; this change controls only the post's text.

This is text formatting of the existing post, not a copied screenshot, image upload, copied branding or an unlicensed sports logo. Existing results/roundup/video captions are outside this live-post formatting change.

## Data and safety unchanged

`score.halftime`, `score.fulltime` and reported added minutes are optional validated values from the same existing fixture response. Goalkeeper saves come from the same already-budgeted statistics response. **No additional endpoint/request, event/substitution/penalty-count inference or paid service** was added to reproduce the reference's denser metrics.

The old source/fetched/score/stat timestamps stay in internal metadata and continue to govern matching, freshness, expiry, immutable reservations and read-back. Same app fixtures/selection, ten-minute SAST schedule, request/stat budgets, original post caps/cooldowns and permission checks remain. Missing data produces a smaller block, not a weaker qualification policy.

No auto-edit, deletion, forced fresh post or reupload is done to restyle the already published post. Existing published scores still prevent an identical match snapshot from being reposted just because its formatting/half metadata changed. The layout applies to the next normally eligible live post; edits remain disabled.

## Validation

Full Python suite: **829 passed, 1 skipped, 8 subtests passed**. New synthetic offline presentation contracts verify grouping/title/no extra copy, country-qualified relevant hashtags with dedupe/ten-tag limit, missing/invalid stats, halftime/extra-time/stoppage distinctions, goalkeeper-saves parsing without extra requests, and no repost/edit caused by clock/format changes. Existing video/music/publisher invariants and production delivery safeguards remain unchanged. No new Facebook post was sent as a layout test.
