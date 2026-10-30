# Android local caching and performance report

## Scope and preservation

The existing app (currently branded **Mr 2 Odds**, with legacy PlayReport identifiers) remains a Kotlin Android shell around bundled HTML/CSS/JavaScript in a WebView. This is an incremental data-access change, not a native UI rewrite.

- GitHub remains the backend: the configured repository's `data` branch under `data/app/` and `reports/`.
- Existing Livescore endpoints remain the live-data source; no new backend, account, subscription or service.
- `com.playreport.app`, signing configuration, branding/assets, navigation, model identifiers, prediction algorithms/formulas and published JSON formats are unchanged.
- Existing tickets, favourites and preferences stay in their current localStorage/SharedPreferences stores.
- **No automated workflow file is changed.** The existing connected 15-minute `playreport-check` WorkManager task is reused. Its notification paths are preserved.
- No production dependency or Gradle/version change. Room/Coil/DataStore would add migrations or UI integration not warranted by this existing WebView architecture. Android's built-in SQLite is appropriate for whole JSON snapshots and cache metadata; it does not replace the published data models.

## 1. Inspection: architecture and bottlenecks

`MainActivity.kt` loads bundled assets using `WebViewAssetLoader`; JavaScript calls its asynchronous native `fetch` bridge on a four-thread executor. `Net.kt` uses `HttpURLConnection`. Data is indexed/normalised by `core.js`, then consumed by `views.js`, `pages.js`, `leagues.js` and existing supporting modules. `CheckWorker.kt` already polls a small GitHub heartbeat and handles notifications.

Main resources and models:

| Resource | Existing consumers/models |
|---|---|
| `data/app/latest.json` | Home, matches, predictions, shortlists, advisor, search; `meta`, fixture IDs, selection tuples, `safe`, `history`, `tracked` |
| `data/app/fx/<sha1(id)[:12]>.json` | Match analysis, team samples, H2H, trends; exact fixture identity |
| `data/app/days/YYYY-MM-DD.json` | Historical fixtures, results, final scores and stored statistics, archived bets |
| `data/app/teams/<division-slug>.json` | Team profiles, statistics and existing table models |
| `data/app/teams/teams-index.json` | Global team search |
| `data/app/leagues/index.json`, `fixtures.json`, competition files | League browser, worldwide fixtures, standings, results and trends |
| `data/app/badges.json` | Existing team-name-to-image-path map |
| `reports/YYYY-MM-DD.md` | Full analysis/archive |
| Existing Livescore date/statistics/lineup/incident APIs | Live tab, match page and notifications |

Problems found:

1. Timestamp cache-busters repeatedly downloaded unchanged GitHub files; the native bridge exposed no HTTP validators.
2. League index, global fixture index and team-index paths could wait for network before consulting persistent fallback data.
3. Session-memory shortcuts could keep details/teams/league data indefinitely without checking freshness.
4. Secondary localStorage was limited to roughly 600 KB and shared the WebView's small quota. The active namespace was `pr_d:`, but pruning/size/clear still targeted obsolete `pr_c:` entries.
5. Large latest snapshots were copied into synchronous localStorage; native preference fallback was restricted to smaller payloads.
6. Repeated entry points could overlap live requests, repeat parsing and repaint entire views even when data had not changed.
7. Reports were effectively session-only; live request failure could clear the all-live list. Offline/freshness state was not consistently visible.

Home already had a cached-start path. This change does **not** claim that every existing startup was network-first, or that all screens are hundreds of times faster.

## 2. Implemented architecture

```text
Existing screens/models
       │ getJson / loadData / loadDetail / loadDay / loadTeams
       ▼
resource-cache.js — cache-first repository
       ├─ bounded parsed-object memory cache
       ├─ asynchronous native bridge → JsonCache.kt → SQLite
       ├─ conditional background GET → existing Net.kt / GitHub or existing live provider
       └─ changed/status events → existing models → coalesced relevant-screen repaint

Existing connected WorkManager checker
       └─ PublishedSync.kt → conditional tiny heartbeat
                          → version check / changed latest snapshot
                          → same SQLite database
```

The database stores complete **validated resource snapshots**, keyed by canonical URL, plus ETag, Last-Modified, last check, last content change, published version and byte count. A separate bounded table persists request cooldowns, including failures with no cached body. Transactions replace snapshots atomically; there is no cross-date fixture merge or recreation of prediction IDs.

Android database reads/writes and network requests use the existing executor/worker, never synchronous UI-thread database operations. The browser test/preview fallback uses asynchronous IndexedDB; it is not a new backend.

Existing validated `pr_latest` and `pr_d:` records migrate on demand. The durable copy is checked first; legacy entries are removed only after successful persistence. Failed migration preserves both usable in-memory data and the legacy copy. New data no longer requires serialising the large snapshot into localStorage on every refresh.

Limits: 32 MB downloaded JSON database budget, 8 MB per resource, bounded negative-cache metadata; parsed repository memory bounded by entry count and payload size, and bounded detail/team/day/report mirrors. Oldest-checked non-primary resources are evicted under pressure; the primary latest snapshot is protected. User settings and tickets are not evicted. Explicit clear-data also invalidates pending writes.

## 3. Synchronisation and consistency

- Canonical URLs remove only the old `t` cache-buster; date, division, fixture hashes, repository/branch, timezone and provider query parameters retain their identity.
- A saved resource is returned immediately. When due, background revalidation starts while it remains visible.
- ETag is preferred, otherwise Last-Modified. A `304` touches freshness metadata only; an identical `200` reuses the parsed object and does not rewrite the body or trigger a full repaint.
- Changed valid content replaces the snapshot atomically and updates its existing model. Full repaints are coalesced and limited to relevant views, preserving scroll/search focus and avoiding navigation animations for background updates.
- Foreground requests have single-flight deduplication and a two-request queue. Native HTTP also deduplicates identical request signatures across callers. Live-refresh entry points share one processing flight.
- Timeouts remain bounded: native connect/read 15/30 seconds, bridge guard 50 seconds; browser fetch 20 seconds.
- Network/5xx failures receive at most one immediate retry after one second, then exponential cooldown (30 seconds up to 15 minutes). Permanent errors and malformed data are not blindly retried.
- `403`/`429` respect rate-limit reset / Retry-After (bounded to 24 hours), impose at least 15 minutes' cooldown, and suppress the queued burst for that origin. Android cooldowns survive process restarts. Manual refresh does not bypass rate limiting.
- The existing worker conditionally reads the tiny heartbeat. If the publication version matches the saved latest snapshot, no full download is needed; otherwise it conditionally warms the same database. On resume, the UI can adopt this shared snapshot without downloading it again.
- Connectivity callbacks, online events and resume/visibility events restart appropriate checks. Network-error cooldowns can be released on reconnection; server rate limits remain respected.
- Validation rejects malformed/missing essential latest fields, duplicate fixture/selection IDs, wrong fixture hash/teams, wrong archive date, wrong division/league identity and regressive publication versions. Empty or invalid replacements do not erase useful cached content; legitimately empty optional league fixture lists remain allowed.
- Cached live scores retain their actual last-check age and are explicitly labelled when stale/offline. Failed live refreshes do not empty previously useful scores or turn old cached events into new goal notifications.

## 4. Default freshness rules

Refresh intervals are configurable in the repository policies; these are revalidation intervals, **not deletion deadlines**. Stale useful information remains available with clear status.

| Data | Default revalidation |
|---|---|
| Latest fixtures/predictions | 5 minutes; publication changes invalidate match-detail freshness |
| Worldwide league fixtures | 10 minutes |
| Match analysis | 15 minutes, or sooner after a new latest publication |
| League index/standings/results | 30 minutes |
| Team statistics/global team index | 6 hours |
| Recent day files and current/recent reports | 5 minutes |
| History/reports older than 3 days | 24 hours, allowing late corrections |
| Badge path map | 7 days |
| Live provider data | 20–30 seconds, respecting the existing live refresh setting and active-view scheduling |
| App closed | Existing connected WorkManager opportunity, approximately every 15 minutes; heartbeat + latest snapshot only |

Image binaries continue using WebView's existing HTTP disk cache, server cache headers and lazy loading, now with asynchronous image decoding. Image retention is not guaranteed after OS cache eviction; initials remain the existing offline fallback. No Coil migration or external-image downloading service is introduced.

The discreet status line distinguishes downloaded/saved data, refresh due, failed refresh and offline use, with last-check time. The main publication timestamp is shown separately, with a warning when its source publication is more than an hour old. Cached live scores are not labelled as confirmed-current scores.

## 5. Testing and measured results

### Automated checks completed locally

- **730 Python tests passed**, 1 existing skip, 8 subtests passed (`leagues/tests`, `tests`, `tennis/tests`). This includes a wrapper for the JavaScript regressions; no workflow modification was needed.
- **25 JavaScript cache regressions passed** (`node --test android/cache_test.cjs`).
- Host SQLite schema/metadata/primary-key checks passed. These are SQL contract checks, not Android instrumentation.
- Real Chromium harness passed against the bundled UI and read-only GitHub publication snapshots, with **zero uncaught JavaScript errors**.

| Requested scenario | Result/evidence |
|---|---|
| First install, empty cache | One network request creates the snapshot; no-data offline state does not loop requests |
| First successful download | Validated body and validators persist; models render |
| Reopen with cache | Real IndexedDB/browser reopen: **180 ms** in the recorded run |
| Repeated screen switching | Five matches/bets/home cycles: **0 additional latest-data requests** |
| Slow internet | Stale data returned before the pending response; changed content arrives automatically |
| Offline | Cached latest, match details, team statistics, day results and league details restored without requests |
| Connectivity restored | Revalidation resumes; changed snapshots update existing models |
| Unchanged GitHub data | Conditional header verified; 304 preserves screen DOM/object/body; identical 200 avoids reparsing/rewriting |
| Updated GitHub data | Changed publication reaches the existing screen without reopening it |
| Failures/rate limits | Bounded retry, persistent cooldown, origin queue suppression and no cache loss verified |

### Before/after controlled comparison

The harness loads the old bundled assets from baseline commit `49196874736afdcb980438bae465d0721e9937c3` and the changed assets, using the same saved league index and an artificial **2,000 ms** response delay:

- Previous cached league-index load: **2,009 ms**.
- New cache-first league-index load: **4 ms**.
- Cached whole-app browser reopen: **180 ms**.

These are local Chromium measurements with simulated network latency, not Android device/battery/scroll-FPS benchmarks and not a claim about every screen. Re-runs varied slightly (cached league approximately 4–7 ms). The primary win is eliminating network wait from saved-screen opening and avoiding unchanged downloads/renders.

### Android validation status

Local Java/Gradle/Android SDK/emulator are unavailable. The unchanged existing `Build Android app` pull-request validation job compiles `assembleDebug` and runs `testDebugUnitTest` without publishing a release. Its result will be recorded here once available. No physical-device or emulator offline/Doze/scrolling/battery measurement is claimed.

## 6. Files changed/created

Created:
- `android/app/src/main/assets/www/resource-cache.js` — repository, policies, validation integration hooks, queue/deduplication/backoff, browser IndexedDB fallback.
- `android/app/src/main/java/com/playreport/app/JsonCache.kt` — shared, bounded transactional SQLite cache and cooldowns.
- `android/app/src/main/java/com/playreport/app/PublishedSync.kt` — conditional heartbeat and snapshot warming in the existing worker.
- `android/cache_test.cjs` — deterministic repository regressions.
- `android/cache_browser_test.cjs` — optional real-browser integration and before/after harness.
- `tests/test_android_local_cache.py` — existing test-suite entrypoint, syntax and SQL/bridge contract checks.
- `docs/ANDROID_LOCAL_CACHE.md` — this inspection/architecture/test/limitations report.

Modified:
- `android/app/src/main/assets/www/core.js` — existing loader integration, migrations, identity guards, model updates, freshness status and correct legacy pruning namespace.
- `android/app/src/main/assets/www/app.js` — validated legacy boot and shared-cache adoption on resume.
- `android/app/src/main/assets/www/leagues.js` — cache-first existing league/fixture/detail loaders.
- `android/app/src/main/assets/www/pages.js` — persistent reports and existing clear-data action.
- `android/app/src/main/assets/www/views.js` — deduplicated live refresh, preserved failed-refresh data and stale-score handling.
- `android/app/src/main/assets/www/index.html` — load repository before existing core.
- `android/app/src/main/assets/www/app.css` — small status-line spacing only.
- `android/app/src/main/java/com/playreport/app/MainActivity.kt` — asynchronous cache/conditional-fetch bridge and connectivity callback.
- `android/app/src/main/java/com/playreport/app/Net.kt` — conditional headers, metadata, bounded reads and shared request deduplication.
- `android/app/src/main/java/com/playreport/app/CheckWorker.kt` — invoke heartbeat/snapshot helper, preserving notification paths and scheduling.

## 7. Remaining limitations / release gate

- Native build validation and a device/emulator pass are distinct from browser and host-SQL tests. Check Android connectivity/rotation, database eviction, low-storage behaviour, offline process restart and prolonged Doze on a phone before release.
- WorkManager is best-effort and Android may defer it; this is not an always-running live-score service. Closed-app warming downloads latest only, not every team/league or the whole backend archive.
- A never-downloaded resource cannot be shown offline. Useful history is retained until explicit clear, OS data removal, or cache-budget eviction.
- SQLite stores original snapshot bodies to preserve flexible existing formats, not a new queryable football-domain schema. Parsing a newly loaded/changed JSON body still occurs in JavaScript; repeated unchanged bodies are not reparsed.
- Browser preview persistence uses its browser quota; the 32 MB eviction guarantee is the Android SQLite implementation.
- No production release is published or version bumped by this work. Backend compatibility is verified with the existing public JSON format and tests; signed APK/device verification remains a separate release gate.

## Reproduce

```sh
node --test android/cache_test.cjs
python -m pytest leagues/tests tests tennis/tests -q
```

The optional browser harness needs developer-only `playwright-core` and `@sparticuz/chromium` (installed under ignored `tmp/android-test-tools`, not in the APK), and read-only snapshots in `tmp/android-fixtures/`: `latest.json`, `leagues-index.json`, optionally `detail.json`, `teams.json`, `league.json`, `day.json` for its first fixture/league. Supply `ANDROID_CACHE_FIXTURES` / `ANDROID_TEST_MODULES` to use another directory. No production secrets are required. Run `node android/cache_browser_test.cjs`. Outputs/screenshots stay under ignored `tmp/`; no generated publication data or large datasets belong in Git.
