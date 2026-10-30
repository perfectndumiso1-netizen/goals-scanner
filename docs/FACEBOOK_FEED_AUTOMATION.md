# PlayReport ZA: independent Facebook feed automation

## Status and activation boundary

**30 October: the owner paused all non-Reel Facebook posts.** Configuration is disabled/dry-run again. See [Reels-only caption and cover update](FACEBOOK_VISIBILITY_AND_COPY.md). The activation history below describes the earlier rollout, not current publication permission.

Editorial activation was requested on 29 October 2026: JSON is now `enabled:true`, `dry_run:false`. **Publishing is still gated by repository variable `FACEBOOK_FEED_PUBLISH=true` and an inspected first live-ledger bootstrap.** The agent received HTTP 403 when attempting to set that variable, so an owner must complete the phone steps below. Scores, roundups and editing remain off pending their account/rights/integration checks. This activation adds no Reel, changes no Telegram behaviour, and leaves the existing 08:00 / 16:00 SAST Reel pipeline unchanged. Text/photo posts use an independent package, workflows, concurrency group and artifact ledger. Existing scanner data is read only; no feed workflow pushes to its `data` branch.

Offline API contract/replay tests are **not** successful Facebook/API-FOOTBALL integration tests. Do not advertise verified live coverage, rights clearance, feed/photo creation or editing until the account-specific checks below have passed. No paid subscription is authorized.

## Calendar (South Africa has no DST)

| Content | SAST target | GitHub UTC cron | Limits |
|---|---|---|---|
| Community / analysis | Daily 12:15 | `15 10 * * *` | At most one/day |
| Teams to Watch This Week | Monday 10:15 | `15 8 * * 1` | Once/ISO week; 3–5 qualifying teams |
| Interesting Stats Match Card | Tue/Thu/Sat 18:15 | `15 16 * * 2,4,6` | At most three/week; skip thin evidence |
| Selected score centre | :07/:27/:47 | `7,27,47 * * * *` | Disabled; at most three NEW score/roundup posts combined/day |
| Combined results roundup | Daily 23:15 | `15 21 * * *` | At least two selected, uncovered finals; shares score cap |

All non-score features share a two-post/day ceiling and 120-minute minimum gap. Score posts have a 60-minute gap; edits have a separate 20-minute minimum. New ordinary posts avoid 07:30–08:45 and 15:30–16:45 SAST to give the existing Reels space. A two-hour scheduling tolerance accommodates modest Actions delays; later ordinary runs skip rather than publish an old edition. GitHub cron is best effort, not an exact-time guarantee. Workflow concurrency preserves one running and one pending job, not an unlimited queue; excess pending work may be superseded safely.

**Changing a time/poll frequency requires changing BOTH JSON settings and the corresponding workflow cron.** Increasing the JSON interval can reduce polling through caching; it does not reschedule GitHub. Daily/weekly caps are enforced in code as well as by deterministic edition keys.

## Editorial evidence and graphics

- Uses the existing published `data/app/latest.json`, matching `fx/<id>.json`, forward `days/<date>.json` and first-published Advisor ledger. No new unofficial Livescore polling is introduced.
- Rejects stale/future-generated snapshots, mismatched fixture/detail identities, unknown kickoff times, malformed/duplicate results, friendlies and thin samples. Exactly five **recorded competitive** results are labelled with the actual sample dates, competition scope and newest-first form. Mixed-competition samples are not labelled league-only. Source validation establishes archive consistency/recency, not independent certification by a league.
- Match cards require an evidenced angle plus five home/away venue results. Useful competitive H2H is optional, dated and explicitly historical. Goals are never called shots, wins never called unbeaten runs, and model probabilities are never used as historical results.
- Community modes rotate discussion, form, preview, honest prediction review, fact, debate and team-pattern development. A review includes losses, pending/void counts and its denominator, not just wins. Unsupported tactical/player claims are not generated.
- Weekly features list verified archive fixtures in the next 168 hours, SAST times, five-match statistics and a statistical selection reason. Conflicting dates for the same pairing cause the affected teams to be excluded; the system never chooses a rescheduled date arbitrarily. The archive may not be a complete schedule; this is not a claim of every fixture worldwide. If fewer than three teams qualify, skip.
- Community and single-match cards avoid fixture IDs already covered by those paths. Weekly overviews can legitimately mention a team subsequently covered in detail.
- Original 1080×1350 JPEGs use only code-drawn shapes/text and existing Liberation fonts under `assets/fonts/LICENSE-Liberation.txt`. No club badges, player photos or footage are downloaded. Text overflow skips the graphic instead of silently shrinking it illegibly. Full samples/source attribution accompany the image in its caption.
- `editorial_competitions: []` permits qualifying archive competitions. To restrict them, supply `{"country":"England","names":["Premier League"]}` entries. `live.competitions` separately controls scoreboard coverage.

## Provider research and limits (reviewed 29 October 2026)

**Chosen adapter: direct API-FOOTBALL / API-SPORTS Free account.** Official [pricing](https://www.api-football.com/pricing) lists $0, 100 requests/day and access to endpoints including fixtures/livescore/statistics, but explicitly limits seasons on Free. This is **not proof** a new account can read the current season or South African Premiership. Its [beginner guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide) documents `x-apisports-key`, the response/error/pagination envelope and daily/per-minute quota headers. API-SPORTS football information [3](https://api-sports.io/sports/football) states daily quota reset at 00:00 UTC.

- One batched SAST-date fixtures request covers the configured competitions, rather than one request per league/match. Twenty-minute cadence is 72 scheduled polls/day. Daily Free-plan checks, an occasional catalog probe and a roundup normally fit inside the local **90-request ceiling**, leaving headroom below 100. Manual tests/other consumers also spend the same key's allowance.
- Local usage, `/status.requests.current`, and the actual remaining daily quota header constrain spending across separate dry/live ledgers. `/status` must identify an active Free account before fixture/catalog calls. A paid account is rejected, not silently used. No upgrade, payment or fallback provider is attempted.
- A short cache prevents repeated calls in the same evidence window. Although the polling interval is 20 minutes, snapshots older than five minutes cannot be reused for publication. Missing/stale HTTP dates, provider errors, pagination, quota exhaustion, malformed statuses/scores, impossible elapsed time, implausibly old in-play statuses and frozen in-play observations cause skips. No automatic retry storm.
- HTTP response time is **not** a per-match last-updated guarantee. This API does not give this adapter an independently verified event freshness timestamp. Provider latency/season access must be observed on the actual account before activation. Twenty-minute polling can also miss HT or an intermediate score. Captions say **latest reported scores**, show the check time and explain periodic updates; this is not a second-by-second service.
- Selection is bounded: configured rivalries, manual fixture IDs, featured teams, knockout importance or a verified archive statistical story. Not every match qualifies. Competition aliases still need checking against the account response, especially SA Premiership.
- First KO/in-play, HT/FT and significant state changes are eligible, subject to limits. Minute ticks and an ordinary single-goal change do not create a new post. A two-goal aggregate change, lead reversal, penalties or status transition can justify one. Final-roundup dedup uses previously published final snapshots, not merely teams/date.

**Rights blocker:** the provider's [terms](https://www.api-football.com/terms) say an API subscription does not itself confer publication/commercial rights; the customer must verify the appropriate rights-holder permissions. The API is not a blanket license for social-media/betting publication. `provider.rights_confirmed` must remain false until reviewed/cleared. Source credit is included, but attribution alone does not resolve rights. Review the existing archive suppliers' usage terms too.

**Rejected as a free-live substitute:** [football-data.org pricing](https://www.football-data.org/pricing) explicitly labels the €0 scores/schedules delayed; its free-with-livescores product is €12/month. We have not established its delay length and do not silently relabel delayed data “live”. OpenLigaDB was not established as a reliable seven-competition replacement. No unofficial app score endpoint is used as fallback.

## Facebook integration

Reuses `FACEBOOK_PAGE_ID` and `FACEBOOK_PAGE_ACCESS_TOKEN`. The client validates identity, can derive the exact target Page token from an existing permitted user token in memory, and checks the derived identity again. Tokens remain in headers/memory, never URLs, captions, logs, state or artifacts. No video/Reel endpoints are called.

Official Meta [Pages posts guide](https://developers.facebook.com/docs/pages-api/posts/) documents:
- `POST /PAGE/feed` for text, and post-ID reads for verification;
- `POST /PAGE/photos` for photo publication;
- `POST /PAGE_POST` with `message` for editing, returning `success: true`;
- **only posts created using the same app can be edited**.

The [Page Photos reference](https://developers.facebook.com/docs/graph-api/reference/page/photos/) documents multipart `source`, `caption`, Page tokens, `pages_manage_posts`, `pages_read_engagement`, `pages_show_list` and the Page CREATE_CONTENT task. Other tasks/permissions/app review depend on your app setup; consult the guides rather than assuming Reel success proves feed access. The new client reuses the repository's existing Graph version without changing the Reel client. Creation/edit is considered confirmed only after GET returns the expected ID/message and `is_published: true`.

Editing is **off by default**. Keep it off until a real create → edit → read-back test succeeds for this Page/app. Failure never creates a replacement automatically. With editing off, meaningful combined updates may create a new post within the same strict three/day budget. A completed Reel test is not proof of these feed/photo/edit operations.

## Phone-only setup and staged activation

1. Review the PR and **Facebook feed upgrade dry-run validation** Actions run. Download its artifact on your phone: community/card/weekly captions, two JPEGs and `report.json`. Missing/thin evidence is allowed to skip, with a reason. This workflow never receives Facebook credentials and never sends a Facebook request.
2. After merging, workflows appear in GitHub → Actions. The editorial JSON is staged for activation, but the repository variable and first bootstrap are still required. Use **Facebook feed engine (isolated)** → Run workflow → choose `community`, `card` or `weekly`; leave Publish false and Preview true. Previews respect caps/quiet windows. The dedicated all-feature validation workflow is a history-isolated demonstration; normal dry runs simulate durable limits.
3. For score investigation only: create a **Free** API-FOOTBALL account at <https://dashboard.api-football.com/register> (no paid subscription). Find Account → My Access. GitHub repository → Settings → Secrets and variables → Actions → **New repository secret** → name `API_FOOTBALL_KEY`, paste the value there, not in chat or a file. Existing Page secrets do not need renaming. `github.token` supplies read-only artifact access automatically; no new GitHub PAT is needed.
4. Run engine `preflight`, Publish false, Preview true. This checks the account and catalog, **not** current-season live entitlement. Then run `live` previews around actual selected matches and `roundup` after at least two selected finals. Compare kickoff/HT/FT, goals, penalties, delays and all enabled competitions against authoritative match reports. Absence of a match today is not proof of entitlement or lack of coverage. Verify actual Free season access in the provider dashboard/Live Tester. Narrow competitions if needed.
5. Resolve source/publication rights and review actual drafts before changing activation flags. Confirm Page permissions, then perform a separately approved real text/photo creation and same-app edit/read-back test. Record the post IDs/outcomes. **These real integration checks are pending, not silently treated as passed.**
6. Approval has been received and JSON is already `enabled:true`, `dry_run:false`. On your phone, open repository **Settings → Secrets and variables → Actions → Variables → New repository variable**, name `FACEBOOK_FEED_PUBLISH`, value `true` (edit it if it already exists). The agent cannot set it because GitHub returned HTTP 403. Both settings and the workflow Publish request must agree; a flag alone cannot publish. Start with an inspected first run: engine, chosen kind, Publish true, Bootstrap true. Bootstrap must only initialize a genuinely absent live ledger **after checking the Page for previous attempts**. Use main for production; branch ledgers are deliberately separate. Subsequent scheduled runs restore the checkpoint and do not bootstrap.
7. Keep `live.enabled:false` until real provider tests, `provider.rights_confirmed:true` and `provider.account_coverage_verified:true` are justified. Keep `live.edit_existing:false` until the same-app edit test has passed. Enabling ordinary editorial features need not enable scores.
8. Emergency stop: set repository variable `FACEBOOK_FEED_PUBLISH=false` and/or JSON `dry_run:true`. This affects only new feed/photo/edit sends; it does not stop or change the two existing Reels. A mutation already in flight cannot be recalled by changing a variable.

Scheduled workflows run from the default branch only. New workflow dispatch buttons may not appear until their definitions reach that branch. Branch validation has a narrow token-free push trigger (`config/facebook-feed-dry-run.json`), so it does not need publishing activation or a scanner/Telegram rerun.

## Durable state, failure and recovery

State artifacts are namespaced by repository + branch + **dry/live**, filtered to the originating repository/branch, and validated for schema/size. The newest trusted artifact is authoritative. A download/API/parse failure blocks, never resets history. Restore searches up to 10,000 indexed artifacts and fails closed at that bound. Artifacts have 30-day retention; running the isolated feeds refreshes them. If all expire or are deleted, live operation blocks until explicit inspected bootstrap. Do not delete artifacts or bootstrap to bypass an unresolved attempt.

**Order:** restore → validate evidence/caps → reserve deterministic edition/topic → upload durable reservation artifact → send once → save returned ID → verify published contents → upload final ledger. Prepared plans expire within five minutes (or sooner at kickoff/source expiry), rechecked immediately before mutation, including after slow credential resolution. Content must match its reservation. Every new feature shares this feed mutex; none shares the Reel/scanner lock.

A timeout can mean Facebook accepted a post even if its reply was lost. Such entries stay `unknown`/`reserved`, count conservatively and block the same retry. Unresolved entries survive normal history pruning. Rerunning a job is not permission to resend. No system can make an ambiguous third-party mutation exactly-once without provider support; this implementation prefers a skipped post over a duplicate.

**Phone recovery:** inspect the Page and the latest `pr-feed-state-…` artifact, then Actions → **Facebook feed reservation recovery (no publishing)**, on the same production branch:
- Enter the exact unresolved key and existing `PAGE_POST` ID to confirm it. Recovery uses **GET only**, validates Page ownership, caption hash and published state, then saves the ledger. It never creates/edits a post.
- Only if you established the attempt did **not** publish: leave post ID empty, tick Cancel reservation and Confirm Page inspection. This clears the reservation in a new checkpoint, not the Page. Do not cancel an uncertain attempt; that could permit a later duplicate.
- A wrong ID/hash, network failure or missing state fails without resetting the ledger. Recovery works while feed publishing is disabled. Cancellation is an operator acknowledgement, not an automated proof of absence.

Do not run the old morning recovery or completed Reel retry as a feed test. Reel `1438401701204389` was already confirmed published; nothing here reuploads it.

## Tests and local commands (maintainers; phone users use Actions)

```sh
python -m pytest leagues/tests tests tennis/tests -q
python -m facebook_feed.cli preview --kind all --source PATH/data/app --work tmp/feed-review
python scripts/check_secrets.py
```

The branch dry-run also uploads a ledger on one Actions runner, restores it on another and asserts restoration; the second run refuses the already simulated daily edition.

The new suite covers evidence/sample validation; real image rendering; weekly interval/conflicting dates; rotation and honest losses; selection/state transitions; duplicate/cap/cooldown policy; stale/frozen data and provider failures; Free-plan/quota enforcement; feed/photo/edit request contracts; token redaction; ambiguous outcomes/restart protection; checkpoint restore/trust; expired/tampered plans; dry-run non-publication; and SHA-256 invariants for the untouched Reel workflow/renderer/publisher/music. Synthetic score replay tests do not establish actual live coverage. Real-data previews validate actual archive records but do not replace independent provider or Facebook integration tests.
