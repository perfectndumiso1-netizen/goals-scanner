# Scheduled football editorial: live coverage paused

## Owner-approved plan (31 October 2026)

Replace the Highlightly live feed with ten **scheduled editorial opportunities**, not ten guaranteed stories. The owner selected **pre-match comparisons** explicitly during implementation. All times are SAST (UTC+2):

| Time | Slot |
| --- | --- |
| 07:30 | One combined fixtures post, all six leagues |
| 08:30 | Yesterday's confirmed results |
| 10:00 | South African PSL pre-match comparison |
| 11:00 | Premier League pre-match comparison |
| 12:00 | LaLiga pre-match comparison |
| 13:00 | Serie A pre-match comparison |
| 14:00 | Bundesliga pre-match comparison |
| 15:00 | Ligue 1 pre-match comparison |
| 19:30 | Distinct, explicitly dated goal/incident story from yesterday's results |
| 23:00 | Newly confirmed evening finals |

The six featured slots are **one hour apart in the schedule**. GitHub scheduled jobs are not an exact-time delivery service; delays are possible. Each slot expires after 45 minutes; no overnight/missed-slot catch-up or backlog flood. Existing scanner, prediction, Android, Reel, Telegram, music and unrelated workflow schedules are untouched. The earlier standalone feed `results` kind is replaced by the new 08:30 bulletin, avoiding a duplicate 08:00 results post.

## Live pause and state safety

- `live.enabled=false`, `event_monitor.enabled=false`, `publish_enabled=false`.
- `facebook-live.yml` has **no cron**, and its job only runs explicit read-only diagnostics. It cannot trigger a normal live publication.
- `authorized_kinds=[editorial]`: old live/roundup/results preparations are no longer authorised to send. Keys, verification evidence, quota usage, suspended API-Sports exclusions, event/post/unknown-send history are preserved.
- Keep the **same production checkpoint namespace**, 16 MiB cap, restore checks and reusable workflow concurrency mutex. No bootstrap/reset, branch/data migration or new paid service.
- Existing unresolved reserved/unknown publications block new editorial API preparation and sending until the existing inspection/reconciliation procedure resolves them. Do not blindly resend or mark an uncertain post absent.

## Pictures and captions

The owner-supplied comparison image is a **layout reference only**, not a source of its example statistics or crests. `comparison_graphic.py` renders deterministic typography using the existing stadium asset and bundled fonts: 1080×1350, dark background, teams, competition/date/time, side-by-side numeric table. No image-generation service, invented player image, arbitrary crest download or third-party logo reuse.

**PLAYREPORT ZA branding is allowed on pictures only.** Captions and hashtags contain no personal brand. Every post has relevant league/football tags; featured/story captions also include sanitised team tags. No `#PlayReportZA` or other branded hashtag.

Comparison pictures contain **only stats, labels, match date/kickoff and sample period**—no trend paragraphs or engagement question. Captions carry **up to three verified facts/trends**, an explicit sample scope/date range, a neutral comment question (no public source/assessment footer). Native Facebook polls are **not enabled/supported by the existing publisher**; the caption uses “Your pick: home, draw or away? Comment below.” This is engagement, not a prediction, odds or betting recommendation.

## Verified pre-match statistics, not unsupported premium fields

Select one distinct, still-upcoming fixture in the slot's league from today's complete schedule. Require at least ten minutes until kickoff and re-read its match detail before using it; postponed, rescheduled, changed-ID/team/competition or already-started fixtures fail closed. A day without an eligible fixture is a visible skip, not a fake match or an unapproved league.

For each side use **exactly five most recent completed league matches in the same league and season**, all venues, within 180 days and before both the post and target kickoff. No cross-season/cup mixing, inferred finals or missing-to-zero conversion. Extra-time/shootout samples need editorial scope review and are withheld rather than silently treating shootout wins as ordinary league wins.

The initial card rows are derived directly from those results:

- Goals scored and conceded.
- Goals scored/conceded per game (total ÷ five, two decimal places).
- Clean sheets and wins.

No unverified SofaScore ratings, big chances, possession, expected goals, shots, player rankings, injuries, odds or probabilities are used. This uses already documented/previously account-verified `/matches` and `/matches/{id}` routes rather than claiming new Basic-plan statistics access.

**Double check before rendering:** obtain two independently requested, complete league-season catalogs; validate country/league/season/IDs/pagination; require each side's chosen five records to match across both reads. Additionally check each team's newest sampled result against its detail, and verify the upcoming fixture against its detail. Any conflict blocks the entire card before image creation. Caption facts are calculated from that same evidence.

This is explicitly a **same-provider cross-check**, not proof from an independent publisher or a guarantee that the provider itself is correct. Both sample date ranges are disclosed; the samples need not cover identical calendar dates. No historical H2H/streak claim is made beyond the verified sample.

## Fixtures, results and story

The 07:30 post is one combined text bulletin grouped into PSL, EPL, LaLiga, Serie A, Bundesliga and Ligue 1, with SAST kickoffs and explicit provider phases. Only after a complete catalog can a section say no fixtures are listed. No per-league fixture posts.

Results include only explicit Finished/Finished-after-extra-time/Finished-after-penalties records with known scores and past kickoffs, never missing/active/postponed records. Shootout winner/score is not guessed from the current score. The evening post excludes results already included in an earlier results bulletin.

The 19:30 story reuses yesterday's verified result catalog and fetches current match detail, avoiding an extra worldwide scan. Its date is explicit. A featured/story fixture is not reused for another story. It includes at most three selected, validated goal/red-card incidents, not a purported complete commentary. Goal-event counts must reconcile to both final scores; malformed/duplicate/own-goal attribution or missing incidents block the story rather than guessing. If there is no distinct supported story, skip it.

## Quota and publishing

`editorial.Source` reuses the existing Highlightly transport and **same shared `highlightly_api` state**: 100 requests per UTC day, valid 100th accepted, no 101st, provider-reported remaining, failed-attempt accounting, freshness checks, Free-plan validation, UTC rollover and cooldown preservation. Only documented match routes; no key/account/provider fallback. A complete catalog is at most the configured ten 100-row pages. Paginated partial results never replace a complete cache or produce a bulletin.

Illustration, **not a promised cost**: three nine-page day catalogs = 27; six league histories read twice at four pages each = 48; six upcoming-fixture details plus twelve latest-result details = 18; one story detail = 1. Total **94** before failures/other account use. Actual season/page sizes vary, shared usage may leave less, and quota guards can skip late slots. A small synthetic ten-slot replay uses 34 requests; that does **not** establish production cost or coverage.

Daily metadata/evidence caches are bounded and cleared at SAST day rollover without clearing quota or post history. They contain whitelisted factual fields only, not the provider's predictions/news/highlights. Schedule caching is not live-score observation.

Editorial policy allows up to ten distinct daily slots, with 45-minute minimum feed spacing to tolerate scheduled-run delays. This deliberately overrides the legacy two-ordinary-post cap, 120-minute interval and Reel quiet windows **for this explicitly approved editorial schedule only**. Legacy kinds keep their policy. A successful/ambiguous daily slot cannot choose another fixture on rerun; immutable key/topic/caption hashes also dedupe repeated stories.

The reusable workflow still saves a durable reservation **before** Page mutation. All comparison images are hashed into the reservation and checked before Page access. Plans expire in at most five minutes and comparisons before kickoff; send rechecks expiry after credential verification. Publication requires config/source approval, existing repository master variable, `main`, a matching run-owned checkpoint and unchanged reservation. Unknown outcomes are saved and never blindly resent. A verified Graph ID is required before claiming a confirmed send; workflow success is not publication or public-audience proof.

## Operation and current evidence

New workflow: **Facebook scheduled football (10 factual slots)**, `facebook-editorial.yml`, using the existing feed engine/secrets. Manual dispatch defaults `publish=false`, does not bypass slot timing or initialise a new ledger. Existing read-only diagnostics remain available; they spend quota and should not be repeatedly triggered to force posts.

Review the normal feed summary/report and `facebook-feed-preview-editorial-*` artifacts for captions, pictures and safe skip reasons. If there is no existing production checkpoint, restoration fails or unknown sends exist, inspect/recover using existing procedures—do not bootstrap blindly.

Local validation: **53 new editorial tests**; full repository **1,164 passed, 1 skipped, 8 subtests passed**. Tests cover every slot, hourly map, live pause, cross-check disagreements, source/date/identity/period restrictions, captions/hashtags, no filler, day/unknown-history preservation, complete pagination/Free plan, valid 100th/no 101st, synthetic ten-slot replay, deterministic rendering, run-owned reservation/image hash and tamper refusal. Historical live test fixtures now explicitly opt into their retired configuration; production pause is tested separately.

No authenticated provider request, workflow dispatch, Facebook mutation, actual selected fixture, verified post or independently sourced statistical accuracy was observed during implementation. Offline tests do not establish account quota remaining, actual aliases/coverage or ten publishable stories every day.

Provider terms remain factual-only; do not repurpose this data for odds/predictions or betting-support use. The existing source-rights approval is owner-attested, not an independently audited licence or permission to repost videos/logos.


## Presentation correction after first published card

The owner requested removing provider/source attribution and assessment/check timestamps from both pictures and captions. These labels are now omitted from comparison graphics and all scheduled-editorial captions, including fixtures, results and incident stories. Actual match dates, kickoff times and sample-period/date-range labels remain to avoid misrepresenting the data. Internal verification metadata, evidence, cross-checks, quotas, publication hashes and history are unchanged. This changes future content only; it does not edit, delete or repost the already-published Orlando Pirates–Kaizer Chiefs card.
