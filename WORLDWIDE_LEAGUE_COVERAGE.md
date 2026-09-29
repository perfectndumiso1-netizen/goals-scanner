# Worldwide league coverage — PlayReport v1.9 (data-coverage upgrade)

_Generated 2026-09-29 (SAST). This document is the final report of the data-coverage upgrade:
more competitions, more data quality, more on-screen context — with the prediction model
**frozen and byte-identical for the same input**._

## 1. What changed (and what did not)

| Layer | Before | Now |
|---|---|---|
| Competitions tracked by the scanner | 52 seeded Livescore stages + 22 main + 16 extra football-data feeds (≈ 90, with overlap) | **Every competition on the public Livescore feed + the football-data feeds — 323 in the registry, 284 published to the app** |
| Per-competition data-quality status | none (the model silently used whatever the feed had) | **Machine-readable registry** — `data/app/leagues/status.json` + human dashboard `STATUS.md`, one row per competition with status, reason, season, history depth, stats quality, eligibility |
| League browser (app) | Table / Results / Fixtures | Table · **Trends** · Results · Fixtures · **Teams** · **News** + per-league **data-quality status line** |
| Match Center (app) | Overview / Markets / Trends / Stats / H2H / Data / Line-ups | + **Form** (both clubs' recent results), + **Table** (full standings, both clubs highlighted), + **News** (fixture, home team, away team) |
| Team page | Overview / Matches / Table | + **Trends** (last 5 / 10 / 20 / season / previous season) |
| Search | fixtures only | **global**: fixtures + leagues + clubs |
| News | none in the app (a dead dossier hook only) | per-fixture + per-league headlines from Google News, **context only — never a model input** |
| Prediction model | — | **Untouched.** Half-life, shrinkage, attack/defence, venue adjustment, Dixon-Coles, xG, probabilities, calibration, market comparison, EV and thresholds are exactly as before. Same input ⇒ same output (verified by hash, §9). |

## 2. Coverage numbers

### Registry (scanner side, `coverage.py`)

| Metric | Value |
|---|---|
| Competitions discovered | **323** (285 Livescore stages + 38 football-data feeds) |
| Countries | **80** |
| Eligible (model sample ≥ 5 archived matches for ≥ half the teams) | **271** |
| Status split | 318 ACTIVE · 0 UPCOMING · 4 FINISHED · 1 DATA_ERROR |

"Eligible" reuses the model's own sample tiers (`quality._score_sample`: 5 matches → moderate,
10 → good, 20 → strong). The model keeps predicting on thinner samples too — it never used to
stop — but those leagues are now *labeled* (small-sample evidence chips on every selection) and
marked `not model-eligible` in the registry instead of failing silently.

### Published to the app (league browser)

| Metric | Value |
|---|---|
| Competitions published (index + detail) | **284** (every Livescore stage with archived matches) |
| With a standings table | 261 (knockout/round formats correctly have none — a bracket is not a table) |
| Countries in the browser | 78 |

### Latest production window (run of 2026-09-29 19:41 SAST)

| Metric | Value |
|---|---|
| Fixtures in the 24 h window | **147** (10 main-feed, 137 world-spine, 0 extra-feed in window) |
| Competitions represented | 61 |
| Priced by Sportybet ZA | 76 |
| Enough data (data_ok) | 93 |
| Flagged ⚠️ low data (shown, predicted with small-sample labels, **excluded from shortlists**) | 54 |

## 3. How competitions are discovered (provider-driven, no hard-coded whitelist)

1. **Discovery** — `worldfeed` pulls the public Livescore day feed; every `ccd/scd` (competition)
   that appears is a candidate. Seeded stages (`SEED_STAGES`) are only *priorities* for history
   backfill — they are not the coverage boundary.
2. **Archival** — each stage keeps an incremental event archive (`data/ls/stages/<key>.json`):
   current season + backfilled earlier seasons merged into one event map, plus per-match
   statistics, a `stats_probe` (does this provider publish stats at all?) and a `backfill`
   record (`season: count`, `season: -1` = fetch failed). No season is downloaded twice —
   only new matches are fetched per run (incremental, no re-downloading unchanged history).
3. **Quality assessment** — `coverage.assess_stage()` grades every archived competition:
   status (ACTIVE / UPCOMING / FINISHED / DATA_ERROR), season label from the most recent result
   (July–June convention, or calendar year for calendar-year countries), history depth,
   stats quality (share of the last 30 finished matches with statistics, and whether the
   provider publishes stats at all), and eligibility against the model's own sample tiers.
4. **Inclusion** — every competition with archived matches is analysed with the same frozen
   model and published to the app. Quality gates what gets *shortlisted* (the existing
   low-data rules), never what gets *seen*.
5. **Isolation** — one bad API response, one corrupt stage file or one failed query is caught,
   logged and skipped; it can never kill the worldwide scan (per-competition try/except in
   `coverage.build`, `leagues.build`, `worldfeed.refresh`, and per-query in the news cache).

## 4. The machine-readable status registry

`data/app/leagues/status.json` (rebuilt every scan; also rendered as `STATUS.md`):

```
Country | Competition | Provider | Provider ID | Season | Fixtures (window) |
Historical matches (+ earlier seasons) | Stats quality (n/N, provider-publishes) |
Teams | Eligible | Status | Reason
```

Statuses: `ACTIVE` · `UPCOMING` · `FINISHED` · `DATA_ERROR`. Examples from the current data:

- **South Africa · Premiership** — 2026-27 · 57 archived · stats 25/30 (83%) · ACTIVE · **eligible**
- **AFCON Qualification · Group A** — 2026-27 · 15 current + 12 from 2024-25 backfill · ACTIVE
- **A competition whose provider answers "no stats" 8+ times** — stats quality
  "provider publishes none" (corners/cards stay N/A everywhere for it — never zero-filled)

The registry is a **report, not an input**: nothing in it feeds the model.

## 5. Trend engine (data-driven, N/A-never-zero)

`leagues._window_trend` / `leagues.league_trends` / `teamstats._trend_window` compute, per
competition and per team, from **published results only**:

- average goals · Over 0.5 / 1.5 / 2.5 / 3.5 · BTTS · home/draw/away win share ·
  home & away goals · clean sheets · failed to score · average corners & cards
  (corners/cards only over the matches that actually carry statistics — `n/N` shown)
- windows: **Last 5 / 10 / 20 / Season / Previous season** (teams: L5/L10/L20/season/previous)
- change detection, e.g. "Last 10 vs season: avg goals −0.18 · Over 2.5 −13.3 pp" —
  **descriptive only**, explicitly labelled as not a betting recommendation
- **minimum window sizes** (5 matches for league windows, 3 for team windows) — thinner
  windows render **N/A**. Nothing is estimated, interpolated, zero-filled or substituted.

Standings tables are computed from **current-season events only** — backfilled earlier seasons
stay available in Results/Trends and can no longer pollute a live table.

## 6. Match Center, League Center, search

- **Match Center tabs**: Overview · **Form** (last 10 of both clubs, all competitions, with
  venue splits and last-10 points/goals) · Markets · Trends · Stats · **Table** (full
  standings with both clubs highlighted + each club's home/away record) · H2H · **News** ·
  Data · Line-ups.
- **League Center tabs**: Table · **Trends** (the full trend table + change block) · Results ·
  Fixtures · **Teams** (knockout: teams seen in the archive; table leagues: the table) ·
  **News**. Every league page shows its **data-quality status** (active / model-eligible /
  insufficient history / no published stats / finished / data error) from the registry.
- **Global search**: the Matches search box now surfaces matching **leagues** (from the league
  index) and **clubs** (from the window's fixtures and already-loaded team pages) above the
  fixture list.
- **Stable ID chain**: country → competition (`LS:<country-code>/<competition-code>`) →
  season (from the latest result) → team (provider team name inside that competition) →
  fixture (`date|country|home|away`). Team pages are keyed by the same division key the model
  pool uses, so league → team → match links always resolve to the right club (identity by
  provider ID, never by fuzzy name matching; crests fall back to a neutral badge, never a
  wrong club's icon).

## 7. News — sources and rules

- **Source**: Google News RSS (headline index of BBC, Reuters, ESPN, Sky, Goal.com, club/league
  sites, etc.). No scraping, no paywall bypass, no full-article copying. Each item shows
  **headline · source · publication date · link**; tapping opens the original.
- **Freshness**: items are bucketed **last 24 h → 3 d → 7 d** (7-day search window) and the
  bucket is displayed.
- **Match-specific**: three queries per fixture — `"home" AND "away"` (previews, line-ups,
  team news), and one per team. Leagues get their own query plus their top teams.
- **Hard rule: news is information only.** It is rendered in the app and stored in the fixture
  detail, and nothing in the model, market, EV or selection code reads it. A news-driven model
  feature would require separate backtesting before it could exist.
- **Caching**: on-disk TTL cache (`data/news_cache.json`, 6 h TTL) with a per-run request
  budget (90 queries). Half-hourly runs therefore cost at most 90 RSS requests; a failed
  fetch keeps the previous (stale) entries and retries next run — an outage never publishes
  "no news", and never kills the scan.

## 8. Performance, caching, isolation

| Item | Value |
|---|---|
| Average scan time (last 12 production runs) | **≈ 3.5 min** (range 3.3–4.8 min) |
| Livescore stats budget | 75 s / 400 match-stat requests per run (unchanged) |
| News budget | 90 RSS queries per run, 6 h TTL (new) |
| Incremental history | season archives merge — only new matches fetched; backfill per stage once |
| Duplicates removed | the world spine only adds fixtures the football-data feeds did not already match to a live event (match index dedup, per run) |
| API failures | per-competition and per-query try/except; a failure is logged and skipped, never fatal (the current production `data_check` shows 0 errors) |
| Model output for identical input | **byte-identical** (see §9) |

## 9. Model safety — the frozen model, proven

The upgrade touched only presentation and the data *layer around* the model. Proof:

1. **Backtest replay** of the production parameters (half-life 120 d, K=40, venue K=20,
   Dixon-Coles ρ=−0.05, market-xG weight 0.9) on the current dataset:
   - `backtest/predictions.pkl` md5 **`e4d979781fa7781f2b5a44b0a48f851b`** — identical to the
     pre-upgrade baseline.
   - Backtest report `bt_before.md` vs `bt_after.md`: **identical except the timestamp line**.
2. **Existing test suite**: 18/18 passed (2 pre-existing + 16 new offline tests covering the
   registry statuses, N/A trend behaviour, news cache TTL/budget/failure semantics,
   per-competition isolation, registry survival and the stable ID chain).
3. **No model input changed**: the pool build, the half-life/shrinkage/venue/Dixon-Coles code,
   the market comparison, EV and the shortlist thresholds are unmodified; news/status/trends
   are written to separate JSON fields the model never reads.

## 10. The 12 metrics (REQ 10)

| # | Metric | Value |
|---|---|---|
| 1 | Countries discovered | **80** (registry) |
| 2 | Competitions discovered | **323** (285 Livescore + 38 football-data) |
| 3 | Eligible competitions | **271** |
| 4 | Fixtures discovered (last 24 h window) | **147** (61 competitions, 24 countries) |
| 5 | Fixtures processed | **147** (all analysed by the frozen model; 76 priced by Sportybet) |
| 6 | Rejections for insufficient data | **54** flagged ⚠️ low data → excluded from shortlists (shown + predicted with small-sample labels) |
| 7 | Rejections for unsupported stats | corners/cards stay **N/A** for competitions whose provider publishes no stats (e.g. most AFCON qualifiers); no zero-fill |
| 8 | API failures (last run) | 0 fatal; per-competition isolation active (corrupt files/failed queries skipped & logged — covered by test) |
| 9 | Duplicates removed | world spine adds only unmatched fixtures (match-index dedup per run) |
| 10 | Average scan time | **≈ 3.5 min** |
| 11 | API requests used (per run) | ≤ 400 match-stats (75 s budget) + ≤ 90 news RSS (6 h TTL) + day/season feed pages |
| 12 | Model outputs identical for same input | **Yes — md5 of predictions.pkl identical to the pre-upgrade baseline; report identical modulo timestamp** |

## 11. Limitations (stated, not hidden)

- **Livescore is the spine.** Coverage = what the public feed publishes, plus football-data's
  main/extra files. A competition that leaves the feed leaves the app next scan.
- **Stats coverage varies.** Corners/cards exist only where the provider publishes them
  (shown as N/A otherwise); the stats probe distinguishes "provider publishes none" from
  "collecting in progress".
- **Backfill depth.** Earlier seasons are backfilled for the seeded priorities (2 seasons /
  45 s budget); the "previous season" trend window is N/A until the archive reaches back that
  far.
- **News is 7-day-window headlines** from a public index — not full articles, not guaranteed
  for every small club; freshness is shown, never assumed.
- **Registry is a report.** It labels quality; it does not gate the model (which has its own,
  unchanged sample rules).

## 12. Endpoints used (all public, no keys)

| Purpose | Endpoint |
|---|---|
| Fixtures/results (main) | `football-data.co.uk/mmz4281/<season>/<DIV>.csv` |
| Fixtures/results (extra) | `football-data.co.uk/new/<CODE>.csv` |
| Live spine / stage archive | Livescore public day & scoreboard endpoints (no API key) |
| Headlines | `news.google.com/rss/search?q=…` (7-day window, per team / per fixture) |
| Prices | Sportybet public event endpoints (ZA) |
