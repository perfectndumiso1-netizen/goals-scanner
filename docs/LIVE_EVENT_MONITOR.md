> **Verified Highlightly activation (31 October 2026):** full owner-triggered diagnostic 41164360718 verified all 868 list rows/9 pages plus one match detail, with 90 requests remaining and zero Facebook requests. The factual source is now enabled within **08:00–24:00 SAST**, subject to existing baseline/event, quota, master-variable and publication safeguards. This supersedes earlier staged/blocked notes below; activation is not a post. See [HIGHLIGHTLY_LIVE_FEED.md](HIGHLIGHTLY_LIVE_FEED.md).

> **Coverage restored:** normal live-score reads/posts are restricted to **08:00–24:00 SAST**, not 24-hour coverage. Highlightly’s first-page diagnostic passed; full pagination/detail coverage and activation remain pending. See [HIGHLIGHTLY_LIVE_FEED.md](HIGHLIGHTLY_LIVE_FEED.md).

> **Current source: staged Highlightly.** All API-Sports slots are disabled following the owner’s confirmation that the accounts are suspended. Highlightly is selected for read-only verification; live publishing remains blocked until its access/coverage gates are approved. Earlier account-selection/activation descriptions below are historical. See [HIGHLIGHTLY_LIVE_FEED.md](HIGHLIGHTLY_LIVE_FEED.md).

> **Current account selection:** the suspended original `API_FOOTBALL_KEY` is disabled without deleting its secret or history. The owner specifically confirmed provider permission to use the two independent approved backups for this project while it is suspended. Active order is `_1 → _2`, with 200 gross/day, not 300. Historical three-account descriptions below are superseded; see [LIVE_API_DIAGNOSTIC.md](LIVE_API_DIAGNOSTIC.md).

> **Current activation and key names:** see [LIVE_POSTS_ACTIVATION.md](LIVE_POSTS_ACTIVATION.md). The owner has now requested real publishing and full 100/day per authorised allocation; this supersedes the earlier dry-only/90+10 settings below.

# PlayReport ZA: meaningful live events, 24-hour schedule

This is the current live-monitor specification. It supersedes the ten-minute periodic posts, app-only coverage, daytime window and old live caption described in earlier live-score documents. Results, predictions, Android, Reels and their schedules are unchanged.

## Activation status and scheduler

- Workflow: **Facebook meaningful live events (24h)**, `.github/workflows/facebook-live.yml`.
- UTC cron: **`*/5 * * * *`**, every five minutes throughout the day/night. SAST has no daylight-saving change.
- The live job calls the existing isolated feed engine. It no longer depends on scanner completion or checks out scanner data. Existing repository/ref concurrency and durable pre-send reservations remain. No workflow was removed and no Reel schedule changed.
- **Current live configuration:** `event_monitor.mode = "events"`, `enabled = true`, **`publish_enabled = true` (owner-requested activation)**. A scheduled request for publishing cannot override this gate, even if the existing repository publish variable is true. Dry-run state uses the existing dry namespace, never the production ledger.
- Manual dry monitoring: Actions → this workflow → Run workflow → `publish=false`, `preview=true`, `bootstrap=false`. Repeated executions restore the dry ledger, establish baselines, then report meaningful changes. An initial observation intentionally produces no retrospective goal/card bulletin.
- Do not enable automatic posting until a real-provider dry run/checkpoint has been reviewed. After that review, change only `event_monitor.publish_enabled` to true in a reviewed change. Existing config/master-variable/source-rights gates must also pass. Real sends are restricted to `main`. **Do not bootstrap/reset the existing production ledger.** Its unresolved attempts still block new sends.
- `enabled=false` disables event monitoring; it does not fall through into periodic posting. The explicit `mode="legacy"` option exists only for older-adapter regression/rollback investigation, not the requested production mode.

GitHub cron is best effort: configured five-minute scheduling is not proof of five-minute execution or a delivery SLA. No new real provider run or Facebook post is implied by offline tests.

## Critical Free-plan capacity limit

Five-minute global live requests for 24 hours require **288 requests/day minimum**, before account checks, calendars and terminal confirmation. This cannot fit a Free account's **100/day**, or the standing **90 operational / 10 reserve** limit. Three keys alone do **not** establish three allowances; the separate account allocations were subsequently explicitly confirmed by the owner. Even three 90-call operational ceilings total only **270**, below the **288 minimum** plus overhead. Quota-only failover also does not rotate at the local reserve, so this is not a promise of 270 usable polls or all-day coverage.

The transport verifies an active Free allocation, counts failed requests, honours reported account usage and remaining quota (including other consumers), enforces at most 90 operational requests per configured authorised account allocation, and stops at the reserve. It preserves the latest good observations and pending events when quota/network/coverage is unavailable, but **does not post cached scores as fresh updates**. Daily accounting/exhaustion resets at **00:00 UTC / 02:00 SAST**.

Typical costs:

| Operation | API requests |
| --- | ---: |
| Account verification | 1 per selected slot per UTC day |
| Global `fixtures?live=all` | 1 per active five-minute poll; events are embedded |
| Optional SAST fixture calendar | roughly 4/day at most when idle, cached six hours and refreshed on local date change |
| Confirm disappearing tracked matches | at most 1 additional request/poll, up to 20 IDs per request |
| Separate goal/card event calls | **0** |
| Separate match statistics calls in event mode | **0** |

Known-empty periods back off to the next cached kickoff or at most 60 minutes, with hourly global discovery so an incomplete calendar is not treated as proof that nothing can be playing. A restricted calendar does not block the plan-permitted global live endpoint. **An unexpected new/rescheduled match can therefore be discovered late while idle.** Active tracked games use five-minute polling while quota permits. At the ceiling, runs safely skip until reset; all-day five-minute data coverage is not available with this allocation. No paid service or quota-bypassing key cycling has been added.

## Secret slots and lawful failover

Read through existing GitHub Secrets, in order:

1. `API_FOOTBALL_KEY`
2. `API_FOOTBALL_KEY_1`
3. **`API_FOOTBALL_KEY_2`**

The requested spelling `API_FOOTBALL_KEY 2` contains a space and is not a valid GitHub Actions secret name. Set the third slot with the valid name above in GitHub's Secrets UI; never send its value in chat. No existing secrets are removed, renamed by this code, or copied into config, state, posts or artifacts. State contains slot names and quota-group accounting only, not key values or key fingerprints.

The owner has separately confirmed independent authorised allowances: `API_FOOTBALL_KEY` maps to `primary`, `API_FOOTBALL_KEY_1` to `backup-1`, and `API_FOOTBALL_KEY_2` to `backup-2`. Preserve the existing `primary` accounting; do not reset it. If keys share an account in a future setup, they must instead share a quota group. The first configured, authorised slot is used. Network errors, malformed/invalid requests, plan failures, IP/account restrictions, unrelated 5xx and ordinary minute-rate 429s **never** cause key switching. Credential failures back off; when correcting/replacing secrets, also bump the non-secret `credential_revision` to force re-verification.

The owner confirmed on **30 October 2026** that the provider permits failover between independently authorised allocations. That attestation is recorded and `failover_permitted=true`. The owner also explicitly confirmed that **each of the three keys has an independently authorised allowance**, so the backup groups are now mapped separately. This is an owner attestation, not an independently audited provider account record. Code permits quota failover when all of these hold (confirmed authentication rejections additionally follow the owner-enabled policy in [LIVE_POSTS_ACTIVATION.md](LIVE_POSTS_ACTIVATION.md)):

- The provider has explicitly authorised the specific alternative account allocation for this use; do not create multiple Free accounts to increase the limit.
- `failover_permitted=true` and `permission_reference` contains a non-secret reference to the owner's confirmation of that provider permission.
- The backup slot is explicitly authorised and belongs to a **different, genuinely independently authorised** quota group. Relabelling keys does not grant permission.
- The primary has documented daily exhaustion: a daily quota rejection / daily-remaining-zero 429, or verified allocation usage reaching its actual daily limit. A local 90-call reserve is **not** a failover trigger.
- The backup itself passes active Free-plan and account-usage checks. Each group retains its own reserve. Exhausted groups are not probed repeatedly before UTC reset.

## Detection, freshness and coverage

`fixtures?live=all` discovers every in-progress competition exposed by the authorised plan, without the retired app/team/country/daytime filters. Embedded Goal and verified Red Card/second-yellow-dismissal events are normalised; missed penalties and ordinary yellow cards are not goal/red alerts. Provider coverage is not a guarantee of access to every league/season.

For each fixture ID the ledger retains teams, current score/minute/status, source event identities, observed time and a transition sequence. A first observation baselines existing goals/cards. Minute-only, unchanged score/state, repeated raw events, scorer enrichment, stale HTTP timestamps, out-of-order minutes/source observations and obvious status regressions do not produce another event. A frozen in-play clock is not indefinitely re-labelled fresh. Overnight kickoffs remain eligible.

Meaningful changes include score increases/corrections, HT/FT (including AET/PEN), verified red cards, shoot-out score changes and significant phase/status transitions such as postponed, cancelled, abandoned, interrupted or suspended. A match disappearing from the live list is **not** inferred finished: fetch fresh details for its ID. Only outstanding tracked/pending IDs are refreshed, in batches of 20, with a 15-minute per-ID terminal-check backoff and fair advancement to the remaining IDs. Once a final is confirmed and its events published, historical finals are not fetched again. Outstanding publication retries may require a fresh final confirmation before being sent.

Scorers and actual event minutes appear only when supplied consistently by the provider. A scoreboard change without reliable event metadata says **Score updated**, with the current verified match clock separately labelled as status; it does not invent a goal time/player. Unknown scores remain unknown, not 0–0. Rescheduled postponed/cancelled fixtures can retain their identity without inventing a score.

## One consolidated bulletin and one picture

All currently eligible pending events are consolidated into **one** candidate, grouped by competition; unchanged matches are excluded, not used as padding. The provider's 20-ID terminal batch limit does not restrict the bulletin to 20 changed matches. Text exceeding the bounded 60,000-character guard is withheld for inspection rather than silently dropping matches or sending extra posts.

Caption format:

```text
PLAYREPORT ZA | LIVE SCORES

LIVE MATCH UPDATES
[verified source observation time] SAST

[Competition]
[Home] [actual score] [Away]
[Verified event details, if available]
Status: [actual status and available clock]

Scores are updated when meaningful match events occur.

#PlayReportZA #LiveScores
```

The existing native Page photo publisher uploads an original 1080×1350 JPEG highlighting exactly one changed match from the bulletin. It uses the current verified score, not a prediction or synthetic fixture. A confirmed cancellation/postponement/abandonment with no score gets an honest status panel, never a fabricated 0–0. The image now follows the owner's stadium/crest/central-score template in the existing portrait format; see [LIVE_SCORE_TEMPLATE.md](LIVE_SCORE_TEMPLATE.md). Only actual team-ID provider crests may be added when available; they are optional, not invented replacements. The existing local stadium asset is reused and no paid graphics service or extra football-data endpoint is introduced. Render/hash/expiry checks still fail closed.

## Persistence and failed Facebook sends

The existing artifact storage, namespace, checkpoint-before-mutation, content/image hashes and shared feed lock remain in use. State adds:

- `live_event_ledger.matches`: confirmed snapshots, observation times, known provider event identities and transition sequence.
- `live_event_ledger.events`: detected time, change details, pending/reserved/unknown/published/simulated/expired state and confirmed Page post ID.
- Last successful API retrieval and **actual** successful Facebook publication timestamps; simulations never claim Facebook success.
- `event_api`: UTC per-account usage, exhausted/cooldown state and per-slot verification metadata.
- `event_monitor_cache`: next poll, optional upcoming calendar, source retrieval times and bounded terminal-check retry metadata.

A non-mutating credential-verification failure safely returns the event to pending with a 15-minute retry backoff. Pending content is rebuilt only from freshly re-observed match state. Pending events older than six hours expire rather than being posted later as new live news. Published/simulated event details are kept seven days; unreferenced match snapshots are pruned after two days. Unresolved publication evidence is never automatically discarded.

The pre-uploaded reservation is marked unknown before any Page mutation. Network timeout, acknowledgement ambiguity or verification failure **does not** release it for blind resend. A returned post ID is stored before verification; the next publish-enabled prepare may **GET/verify the existing post hash**, then mark it published without a replacement POST. No-ID ambiguity or an interrupted reserved run requires the existing operator reconciliation workflow/Page inspection. Exactly-once remote delivery cannot be promised when Meta returns no acknowledgement/idempotency token; this system chooses no blind duplicates over automatic resend.

Global live coverage needs more state than the old 512 KiB bound. The same storage backend now enforces a **16 MiB bound at both write and restore**, failing before publication if the reservation would not be restorable. Published historical reservations compact redundant snapshots/event lists; unresolved evidence, keys, hashes and post IDs survive. No production checkpoint is reset or migrated to a new namespace.

## Verification and limits

Offline replay tests cover initial retrieval, unchanged/minute ticks, goals/scorers, multiple changed matches including >20, HT/FT, reds/duplicates/enrichment, status-only artwork, overnight kickoffs, missing matches, 20-ID terminal batches, empty-calendar discovery, quota/shared limits, explicitly permitted quota failover, forbidden error failover, UTC reset, restart/pending identity, safe pre-mutation retry, ambiguous-send blocking, acknowledged-ID read-only recovery, disabled publication gates and checkpoint size.

Local synthetic preview images/captions are **not real results and were not sent to Facebook**. A real GitHub/provider dry-run and current Page permission/audience verification still need to be observed before activation. Existing Actions dispatch permission failures are not retried unchanged or presented as successful runs. No physical Android test is implied; those files and prediction/Reel features were not changed.

Provider reference: https://api-sports.io/documentation/football/v3 (`live=all`, embedded events, `ids` batch ≤20). Rights/publication approval already recorded for the existing source remains required; separate API-account failover authorisation has not been presumed.

Local validation (30 October 2026): `python -m pytest leagues/tests tests tennis/tests -q` — **939 passed, 1 skipped, 8 subtests passed**. The event replay file contains **68 tests**. Secret scan covers **287 tracked files**, with no credential patterns. The 1080×1350 synthetic JPEG was rendered and visually inspected locally, not uploaded.
