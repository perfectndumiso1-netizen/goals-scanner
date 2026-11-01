# Four-picture factual match posts

Owner-authorised update to the stats-picture packages, not Reels or the betting
model. Each new match post has one caption and four ordered 1080×1350 pictures:

1. Existing last-five league team comparison.
2. Existing recent league results with actual dates, opponents and scores.
3. Recent head-to-head league meetings, showing the actual historical home/away
   order and scores, newest first.
4. The home team's last five **home** league games alongside the away team's
   last five **away** league games. These are not their all-venue records relabelled.

The existing nine distinct-match opportunities (08:00–16:00 SAST), 07:30 Advisor
bulletin, spacing, source approvals, artifact namespace and expiry rules remain.
Previously published posts are not edited. Nine opportunities are not a guarantee
of nine sufficiently documented matches or of successful Facebook delivery.

## Data and selection

- Editorial-only exact country/competition matching now covers the original six
  leagues plus Netherlands, Portugal, Belgium, Turkey, Scotland, Austria,
  Switzerland, Denmark, Norway, Sweden, Poland, Czech Republic, Greece, Japan,
  South Korea, Brazil, Argentina, USA and Mexico. No country/league guessing or
  assumption that a subscription actually covers them. Australia is not added.
- The live watchlist, scanner league/market diet, Advisor, odds, thresholds,
  videos/music and credentials are unchanged.
- No prestige ranking or forced big-league representation. Prefer candidates
  with complete already repeat-verified histories, then the clearest five-game
  home/away points contrast, then goal-difference contrast. Ties/unknown evidence
  use safe kickoff and stable fixture ID, not the size of the league.
- This means **best supported among the evidence available within the quota**,
  not a claim that every world fixture has been researched or that a bookmaker
  favourite is known. Unassessed candidates are not assigned an invented score.
- Current-season last-five all-venue comparison still requires five games within
  180 days. The extra cards read the current and immediately previous league
  season only: up to five direct meetings within 730 days; exactly five games
  per required venue within 365 days. One verified recent meeting is sufficient;
  it is labelled as one meeting, never padded to five. Both seasons and date
  horizons appear on the extra cards; individual result dates remain visible.
- Every history is read twice through the existing complete, paginated `/matches`
  catalog. Completed records are compared canonically; unrelated live-score
  movement cannot fabricate or invalidate completed results. The newest match
  in each used group is cross-checked through the documented detail route.
  This remains a same-provider cross-check, not independent-source verification.
- Missing venue form, missing H2H, changed identities, missing scores, conflicting
  records, future results, and extra-time/shootout ambiguity fail closed. Never
  render guessed stats, substitute all-venue form for venue form, or downgrade a
  new four-picture package to two pictures. No second expensive candidate after
  a provider/budget/cooldown error; existing unavailable-fixture bookkeeping stays.

## Captions

Three natural, more detailed paragraphs summarise overall form and goals,
relative strength/weakness with the home/away context, and observed goal/H2H
trends. Conflicting overall and venue records are described as conflicting;
closely matched records do not produce an invented stronger side. No public
“sample”, source, checked or assessed labels. Captions retain actual kickoff and
recent meeting dates; all individual form dates are on the cards and in evidence.
Existing picture-only Mr 2 Odds branding and team/competition hashtags remain.

The closing engagement question is **“Which market looks strongest to you in this
match?”**, not a winner poll. It is audience engagement, not a generated tip,
price, probability or market ranking. No Highlightly data enters a betting model
or bookmaker-favourite computation. Highlightly's factual-only terms and the
existing owner-attested rights gates still apply; this update does not establish
provider permission for betting-support use or certify the Page's intended use.

## Publishing and quota safety

New preparations must contain all four graphics. Their ordered image hashes and
caption hash bind to one durable reservation. Upload all four as unpublished
photos, checkpoint each ID, persist the complete ID list, then create exactly one
feed post. Readback must prove the caption, published flag and **all four photo
IDs in order**. Partial uploads, missing fourth acknowledgements, expired work
and unknown feed outcomes cannot silently publish a partial album or replay it.

Unchanged legacy two-picture reservations remain verifiable/reconcilable using
their original hashes/IDs. They are not upgraded, reset or rendered as four.

The same shared Highlightly budget remains at 100 requests per UTC day, including
failures/pages/details. No 101st request, account/key fallback or reset. Two-season
reads can consume more requests than two-card posts, so preparation admission
holds up to `5 × max_pages + 6` requests for a match slot; normal checkpointed
preparation releases unused hold, whereas a crash conservatively retains it.
The transport still enforces provider remaining/cooldown/UTC rollover. There is
no new request made just to determine odds or scan all worldwide histories.

## Verification

Offline tests exercise all four rendered layouts, venue and H2H identities,
stronger-data selection outside the big leagues, caption grammar and balance,
complete four-photo Graph protocol/readback, partial fourth uploads, legacy
reconciliation, quota and reservation guards. These tests do not prove a real
Facebook album is visible. No test stats are sent to Facebook; actual publication
requires the existing scheduled path and positive Graph readback.
