# Approved football thumbnails, club crests and broader statistics

## Owner approval

The owner approved both preview layouts and requested broader statistics. This implementation changes future Facebook portrait video covers/opening frames and future football comparison pictures. It does not dispatch a publisher, replace a Facebook post, reupload an existing Reel, alter prediction selection, or reset publication state.

## Facebook video cover

`facebook_cover.render_matches()` now renders the approved 1080×1920 stadium template:

- Picture-only PLAYREPORT ZA branding.
- Prominent numerical total, e.g. **2.55**, followed by **Odds combined**.
- The exact filmed match list, in its existing order, with registered club crests where the pick's country and club identity match.
- The edition's SAST date and existing non-guarantee warning. No preview labels, invented matches, individual markets/prices, probabilities or source/assessment footer.

Every filmed pick must have a valid finite decimal price above 1. The displayed total uses the **same existing `video_card.combined_odds()` calculation and two-decimal formatting as the video's closing calculation**, rather than hard-coding the example or using the unfiltered input card. Rendering never changes the picks/model. Missing or invalid prices fail closed; historical recovery data without prices cannot fabricate a total.

The existing portrait build uses this generated cover as its first frame and saves `.cover.jpg`. Telegram/landscape presentation is not changed. Existing Meta preferred-thumbnail upload/read-back checks and ambiguous-attempt checkpoints remain untouched: an unconfirmed cover never causes a duplicate video upload. The artwork is implemented, but Meta can still reject thumbnail permissions or fail to confirm a preferred thumbnail; don't claim a Facebook cover change without its verification. No old Reel is reuploaded merely to replace its cover.

## Club logos

`club_crests.py` is a shared, offline registry backed by 129 local PNGs (approximately 3 MB) and a pinned provenance/hash manifest. South African clubs, including Orlando Pirates and Kaizer Chiefs, are included. European current and previous-season assets cover many clubs across the five approved leagues. This is not worldwide logo coverage.

Stats cards use the competition's verified country plus the exact observed club name. Covers use the actual pick's country and names. Explicit country-qualified aliases handle common provider spellings, not arbitrary numeric provider IDs. Missing/ambiguous/corrupt artwork is omitted, never replaced with a different real badge or the app logo. No extra Highlightly quota, arbitrary URL downloads or runtime SVG/native-library dependency is introduced. See `assets/club-crests/README.md` for provenance and rights caveats.

## Broader comparison pictures

The approved crest-led comparison layout is retained at 1080×1350 and extended to **ten readable rows**:

1. Goals scored.
2. Goals conceded.
3. Goals per game.
4. Goals conceded per game.
5. Clean sheets.
6. Wins.
7. Draws.
8. Losses.
9. Unbeaten matches (wins + draws).
10. Matches scored in (goals for > 0).

All use the **same five most recent verified completed matches in the same league/season, all venues**, not a mixture of samples or a fabricated season total. Draws/losses/unbeaten/scored-in are calculated directly from those known final scores, correctly handling home/away orientation and legitimate zeros. Sample size, cross-checks, freshness/identity checks, missing-data refusals, source gates and quotas are unchanged. There are **no additional provider calls** for these rows.

This does not promise possession, shots, corners, expected goals, big chances, ratings or league tables: their availability/definitions/plan coverage must first be verified. No factual Highlightly data is fed into the existing betting/prediction video selection; only static artwork utilities are shared.

Public captions retain at most three facts/trends, the engagement question and unbranded hashtags. Branding stays on pictures only. No public source or checked/assessed timestamp is restored. Actual match date/kickoff and sample-period labels remain. Internal evidence and immutable caption/image hashes are preserved.

## Validation

Full offline suite: **1,207 passed, 1 skipped, 8 subtests passed**; focused approved-artwork/editorial/Reel presentation suite: **108 passed**. New tests validate every pinned asset, exact country aliases, unknown/corrupt/path-rejected assets, correct combined totals, invalid-price rejection, all filmed names, 1/5/8-row cover fitting, ten-row statistics, mixed W/D/L samples, away orientation, real PSL crest placement and absence of source/assessment labels. Existing upload/unknown-send/recovery guards still pass.

No authenticated score-provider request, Facebook mutation, production fixture selection or newly verified Facebook thumbnail was performed for this implementation. Local rendering and passing tests are not a published post or a Meta thumbnail acknowledgement.
