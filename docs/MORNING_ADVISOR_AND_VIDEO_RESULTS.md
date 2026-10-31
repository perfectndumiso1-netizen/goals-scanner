# Morning Advisor bulletin, separate video accumulators and image branding

Owner requested (and selected **one post with separate accumulator sections**):
- Results for the videos, each video treated as its own accumulator.
- Replace the fixtures bulletin with all 1X2 selections shown on Bet Advisor.
- Replace remaining public image wordmarks with **Mr 2 Odds** and the selected logo.

## Production targets (SAST)

| Time | Content |
|---|---|
| 06:00 | One previous-day video-results post, separate labelled accumulator per recorded video |
| 06:20 | Backup for that same results post, not another report |
| 07:30 | **1X2 Predictions of the Day** from the published Bet Advisor, replacing fixtures |
| 07:50 | Same-slot predictions backup |
| 08:00–16:00 | Existing nine hourly distinct-match targets, two pictures per match |

Results prepare only in 06:00–06:44:59, to leave at least 45 minutes before 07:30.
The explicit results-only morning allowance supersedes the generic ordinary-feed
quiet window for this one requested recap; unrelated feeds stay paused. Results
have a separate one-post/day cap, immutable date topic and the same unknown-send
and 45-minute spacing protection. Maximum is one recap + ten editorial posts,
not a results post per video. No backfill flood if a morning window was missed.
Actual GitHub scheduling/delivery times are not guaranteed.

## Bet Advisor 1X2 only — no factual-source betting reuse

`advisor_predictions` reads only scanner-published `data/app/latest.json` from a
read-only checkout of the existing `data` branch. It uses the same visible-section
selection extraction as Bet Advisor: recommendation groups (six displayed rows),
high-confidence list (five today), and displayed value/strong sections (five each).
Same selections are deduped; it does not pull extra picks from the separate 1X2
board/shortlist, invent selections, rerun the model or change its thresholds.

Copy every qualifying visible **H/D/A** selection and its original published
odds, represented as **1/X/2**. Require today's fresh publication, real identities,
finite original price >=1.16, finite original probability, today's kickoff more
than ten minutes away. Already-started picks are not future predictions. Invalid
upcoming 1X2 evidence blocks the bulletin instead of publishing a partial set.
No text truncation that silently drops selections; empty board means no filler.
Caption has the date, matches, kickoff times, original choices/odds and a brief
18+/no-guarantee reminder. No branded captions/hashtags added.

**Never import or request Highlightly data for this betting bulletin.** The
factual builder explicitly refuses this slot; CLI routes to the local Advisor
reader first. Published snapshots carry immutable `published-bet-advisor`
provenance. Only that known slot uses a zero provider-request admission; it does
not read/reset/debit factual quota or let a match slot escape the existing hard
100/day cap/cooldown. Send-time source approval checks recognize the independent
Advisor source, not Highlightly's factual-use approval. The nine factual match
packages remain unchanged and cannot be used as betting/video evidence.

The posting workflow display name and watchdog exact-name completion subscription
are changed together. The watchdog also follows completion of the morning-results
workflow and can positively reconcile a known/unknown results receipt; it never
blindly recreates one.

## Each actual filmed edition is one accumulator

After successful rendering, require the exact `build_meta.json` pick list to be
an unchanged subset of verified candidates, 5–8 distinct selections. Use those
actual filmed selections for history/metadata, not the earlier candidate pool.
The portrait manifest must match the landscape card exactly; on mismatch retain
the landscape delivery and block the mismatched portrait, never upload a cropped
landscape fallback. No music, dimensions, timing or upload/delete protection is
weakened. Existing delivery acknowledgements/slot dedupe remain.

Store an append-only `briefing_editions[day][morning|noon|evening]` manifest with
stable ID, original prices, exact picks, recorded timestamp and hash alongside
the backward-compatible flat history. Preserve the manifests across midnight,
with the same seven-day history horizon. Never overwrite a recorded edition with
a later winning line. The app's single-selection record/model remains unchanged.

Recap the manifest's exact legs against the existing Advisor settlement ledger,
including losses, voids and pending legs. Conflicting ledger records or wrong
countries do not become a win. Each labelled video is graded independently:
- Any lost leg => **LOST**, zero return on a one-unit example stake.
- Otherwise any pending/unconfirmed leg => **PENDING**, no final payout claimed.
- All void => **VOID**, one-unit stake returned.
- All hit/void, with at least one hit => **WON**; void legs count at 1.00.

Use original filmed prices with decimal multiplication, not replacement ledger
prices or a sum of singles. Show original combined odds, void-adjusted odds when
relevant, and explicitly hypothetical return/profit **per 1-unit stake**. Missing
original prices do not produce invented combined odds/payouts. No all-day mega-
accumulator, cherry-picked winning video or combined cross-video result.

## Important legacy limitation (including the old 2026-10-31 record)

The live saved history checked during implementation held 11 selections and
`morning/noon` slot names, **but no per-video membership**. The `data` branch has
amended/squashed history; earlier source file versions were not available through
its normal commit history. Action log downloads were unavailable in this sandbox.
A count of 11 and two edition names is not evidence for a 5+6 or 6+5 split.

Therefore older unassigned selections are disclosed under **OLDER VIDEO GROUPING
UNAVAILABLE**, with their original per-leg status, but **no accumulator outcome or
combined odds**. They are not called one big accumulator and are never guessed
into video groups. Exact historical groups require original video/manifest proof.
Future successfully recorded editions use the new exact manifests. Deploying new
code cannot retroactively manufacture the missing boundaries for tomorrow's recap.

## Mr 2 Odds imagery

Use existing owner-selected `assets/reel/logo.png` (exported from
`assets/branding/mr-2-odds-logo.png`) and a **MR 2 ODDS** wordmark in a dedicated
header box. Apply to comparison, recent-results, portrait video cover and generic/
legacy score artwork, without covering club players, team names or statistics.
No new generated logo, no public reupload/edit of old posts. App identity,
credentials/environment variable names, state namespaces and legacy data keys
remain unchanged. No Android/scanner model, market, probability or music changes.

Validation is offline. Synthetic layout previews contain blank values and are not
Facebook posts or evidence of live delivery. Merging/successful tests do not prove
Facebook visibility; require existing Graph acknowledgement and read-back. No
workflow dispatch, live provider call, YouTube enablement or test post is part of
this change.
