# Current League Coverage — Audit (2026-09-29)

Audit of exactly what the football scanner currently collects, from the code and the live `data`
branch (verified by cloning `data` on 2026-09-29). No guessing: every list below is copied from
`scanner.py` or counted from the published files.

## 1. How the system collects data (three providers, one model)

| Provider | What it supplies | Key | Dynamic? |
|---|---|---|---|
| **football-data.co.uk** | Historical results + upcoming fixtures + bookmaker odds for a fixed set of divisions (`fixtures.csv`, `new_league_fixtures.csv`, per-season CSVs) | none (public CSV) | No — a fixed set of files |
| **Livescore.com public app feed** | **Every football match worldwide** (all countries, domestic leagues, second/third divisions, cups, continental, women's, youth) — the "world spine" (`worldfeed.py` → `livescore.py`) | none (public JSON) | **Yes** — competitions ("stages") appear/disappear on the daily feed and are discovered automatically |
| **Sportybet** (public site) | Prices only — a comparison layer, **never a model input** (data-first rule) | none | Yes (scraped per run) |
| **Google News RSS** | Headlines for context only — **never a model input** | none | Yes (per team) |

The prediction model's history pool is built in `scanner.py:main()` as the concatenation of:
1. `main_all` — football-data main divisions (hard-coded list, below);
2. `extra_all` — football-data "extra" country files (hard-coded list, below);
3. `world_all` — the **Livescore worldwide archive** (`archive.results_frame(...)`), i.e. every
   competition the world feed has played.

**The model is generic**: it predicts any fixture in the scan window as long as the teams have
history in that pool. Coverage therefore grows automatically as the world archive accumulates
seasons of any competition — no code change per league.

## 2. Hard-coded league lists (exact, from `scanner.py`)

### `MAIN_LEAGUES` — 22 divisions (football-data division codes → country, name)

| Code | Country | Competition |
|---|---|---|
| E0 | England | Premier League |
| E1 | England | Championship |
| E2 | England | League One |
| E3 | England | League Two |
| EC | England | National League |
| SC0 | Scotland | Premiership |
| SC1 | Scotland | Championship |
| SC2 | Scotland | League One |
| SC3 | Scotland | League Two |
| D1 | Germany | Bundesliga |
| D2 | Germany | 2. Bundesliga |
| I1 | Italy | Serie A |
| I2 | Italy | Serie B |
| SP1 | Spain | La Liga |
| SP2 | Spain | Segunda División |
| F1 | France | Ligue 1 |
| F2 | France | Ligue 2 |
| N1 | Netherlands | Eredivisie |
| B1 | Belgium | Pro League |
| P1 | Portugal | Primeira Liga |
| T1 | Turkey | Süper Lig |
| G1 | Greece | Super League |

→ 12 countries, 22 codes (E0–EC, SC0–SC3, D1/D2, I1/I2, SP1/SP2, F1/F2, N1, B1, P1, T1, G1 = 22 entries).

These 22 divisions also define where **corner and card statistics** come from football-data
(the `markets.CountModel` corner/card models; elsewhere, corners/cards come from the Livescore
match-statistics archive once `WORLD_COUNT_MIN_N` (5) matches with stats exist per team).

### `EXTRA_LEAGUES` — 16 countries (country name in `new_league_fixtures.csv` → file code)

Argentina (ARG), Austria (AUT), Brazil (BRA), China (CHN), Denmark (DNK), Finland (FIN),
Ireland (IRL), Japan (JPN), Mexico (MEX), Norway (NOR), Poland (POL), Romania (ROU),
Russia (RUS), Sweden (SWE), Switzerland (SWZ), USA (USA).

(These are the football-data "new league" files: their top divisions only.)

### `SEED_STAGES` — 52 pre-seeded Livescore stages (environment-overridable)

`england/premier-league, england/championship, spain/laliga, spain/laliga-2, italy/serie-a,
germany/bundesliga, germany/2-bundesliga, france/ligue-1, france/ligue-2, portugal/primeira-liga,
scotland/scotland-premiership, turkey/super-lig, switzerland/super-league, greece/super-league,
poland/ekstraklasa, ukraine/premier-league, romania/liga-1, croatia/1st-league,
denmark/superliga, norway/eliteserien, sweden/allsvenskan, finland/veikkausliiga,
austria/bundesliga, belgium/belgian-pro-league-2025, israel/premier-league,
ireland/league-of-ireland-premier-division, wales/cymru-premier, south-africa/premiership,
egypt/premier-league, morocco/botola-pro, algeria/ligue-1-2025, nigeria/npfl,
ghana/premier-league, tanzania/premier-league, botswana/premier-league, brazil/serie-a,
argentina/liga-profesional-clausura, chile/primera-division, colombia/primera-a-clausura,
uruguay/primera-division-clausura, paraguay/division-profesional-clausura,
peru/primera-division-clausura, ecuador/serie-a, venezuela/primera-division-clausura,
usa/major-league-soccer-2026, mexico/liga-mx-apertura, japan/j-league-2025,
iran/persian-gulf-pro-league, saudi-arabia/saudi-professional-league, qatar/qatar-stars-league,
indonesia/super-league, australia/northern`

Purpose: guarantee continuous archiving (full current season + `BACKFILL_SEASONS`=2 earlier
seasons) for the biggest competitions, so their pages are rich before auto-discovery catches up.
They are a **seed, not a limit** — discovery (below) adds every other stage it sees.

## 3. Dynamic discovery (the part that makes coverage worldwide)

`scanner.py:main()` (world spine block) on **every 30-minute run**:

1. `worldfeed.fetch_window()` — pulls **every football match** on the scan window days from the
   public feed (all countries, all competitions, incl. women's/youth/friendlies).
2. **Stage discovery** — every stage (competition) seen on the window days *and* two days back
   is added to the refresh priority list, plus every already-archived stage (kept fresh between
   matchdays) and the 52 seeds. New stages get priority 0 (in-window stages refresh first).
3. `archive.refresh()` — for each stage within its 6-hour freshness window, fetch the stage's
   whole current season (time budget `BUDGET_S`=150 s, so a slow feed never blocks the run).
4. `archive.backfill(seasons=2, budget 45 s)` — earlier seasons for eligible stages.
5. `archive.refresh_stats(budget 75 s, max 400 requests)` — match statistics (corners, cards,
   half-time) for recent finished matches, capped per run.
6. `archive.save()` — persistent JSON per stage under `data/ls/stages/` on the `data` branch.

**One bad stage never kills the scan**: every stage fetch is individually try/excepted, and the
whole world block is best-effort (a failure logs and continues).

## 4. Current published coverage (live `data` branch, counted 2026-09-29)

`data/app/leagues/index.json` — **284 competitions in 78 country/competition labels**
(261 with a standings table, 23 knockout/cup without one):

- 23 England · 21 Germany · 14 Italy · 14 UEFA Nations League · 13 Norway · 12 AFCON Qualification
  · 12 Sweden · 10 Spain · 9 CONCACAF Nations League · 9 Denmark · 9 Euro U21 2027 · 7 Argentina ·
  6 Bolivia · 6 Finland · 6 Mexico … (full list: every entry in `index.json`, grouped by country)
- Includes women's (UEFA Women's Champions League, Women's Euro U17), youth (Euro U17/U21),
  continental (UEFA/CONCACAF Nations League, AFCON Qualification), friendlies, and domestic
  leagues across Europe, Africa, the Americas and Asia.

Model history pool (what the prediction engine actually sees): the 22 main divisions + 17 extra
countries from football-data **plus** the entire Livescore archive (`world_all`) — i.e. all 284
stages' accumulated results.

## 5. IDs / identity

- **football-data**: division codes (E0, SP1, …) + file codes (ARG, JPN, …) — stable.
- **Livescore**: `Ccd`/`Scd` stage codes (e.g. `south-africa/premiership`) + **numeric team IDs**
  (`home_id`/`away_id`) — team history is keyed by the provider team id where present; display
  uses names. App badges (`data/app/badges.json`) map team name → Livescore crest image path.
- App fixture id: `date|country|home|away` (`appdata.fixture_id`); live matches: `live:<eid>`.

## 6. Allowlists / blocklists / filters (exact)

| Filter | Where | Effect |
|---|---|---|
| `LEAGUES` env var | `scanner.py` CONFIG | Optional restriction to specific football-data codes — **not set** in the workflow (full coverage) |
| `SEED_STAGES` | CONFIG | Pre-seed 52 stages for continuous archiving (a floor, not a ceiling) |
| `WORLD=1` | scan.yml env | World spine on — every competition on the feed |
| `WORLD_COUNT_MIN_N=5` | CONFIG | Corner/card *counts* outside main leagues need 5 matches with stats per team (N/A otherwise) |
| `_MIN_TEAMS=4` | leagues.py | A standings table is published only with ≥4 teams in league format |
| `MIN_N=5` / `MIN_VENUE_N=4` | trends.py | Trend lines are suppressed (not zero-filled) under 5 matches |
| `settings.leagues = 'major'\|'all'` | app (user setting) | Display filter only — "Major leagues" vs "Every competition" in the Bets boards |
| No country/region blocklist | — | The world spine has **no** region filter; cups, women's, youth and friendlies are all in |

Minimum-history requirement of the model (existing, **not to be changed**): a team's sample is
scored by `quality._score_sample` — ≥20 matches = 1.0, 10–19 = 0.8, 5–9 = 0.55, 1–4 = 0.3,
0 = 0 (no prediction); recent-weighted evidence <4 caps the score at 0.3. Data-quality
components (completeness, recency, consistency, …) drive the confidence label, never a silent
exclusion.

## 7. Scheduling

- `scan.yml` — every 30 minutes (GitHub cron); full-report runs at 07:00/12:00/17:00 SAST.
- 24-hour fixture window (`WINDOW_HOURS`); stage refresh ≤ every 6 h; budgets: 150 s stage
  refresh / 45 s backfill / 75 s statistics / 400 stats requests per run.
- State (archive + app data) lives on the `data` branch, restored and republished every run.

## 8. Gaps found by this audit (what the worldwide-coverage task must add)

1. **No machine-readable competition status registry** — there is no per-competition
   `Country|Competition|Provider ID|Season|Fixtures|Historical Data|Stats Quality|Eligible|Reason`
   dashboard with statuses (ACTIVE / ELIGIBLE / INSUFFICIENT_HISTORY / …). *(Step 8)*
2. **No per-league trend block** in the league browser (league averages, O0.5–O3.5, BTTS,
   H/D/A, clean sheets, last-5/10/season windows, change vs season). *(Req 12, 24–26)*
3. **Team pages lack the requested trend windows** (last 5/10/20, season, previous season,
   attack/defence/form split in one trend block). *(Req 13, 25)*
4. **News exists but only in the Telegram/PDF parlay dossier** — not in the app, not per-fixture.
   The Match Center has no News tab. *(Req 16–19)*
5. **Match Center tabs**: Overview/Markets/Trends/Stats/H2H/Data/Line-ups exist, but there is no
   dedicated **Form** tab (both teams' recent matches), no **Table** tab (league standings), and
   no **News** tab. *(Req 15)*
6. **League Center tabs**: Table/Results/Fixtures exist; no **Trends**, **Teams** or **News**
   tabs, and no status/eligibility line. *(Req 22)*
7. **Global search** covers fixtures (Matches tab) and leagues (Leagues tab) separately; there is
   no single search across clubs + leagues + countries + fixtures. *(Req 29)*
8. **No coverage reports** (`CURRENT_LEAGUE_COVERAGE.md` / `WORLDWIDE_LEAGUE_COVERAGE.md`). *(Steps 1, 11)*

Everything else the 33-point spec asks for (worldwide discovery, caching, rate limits, budgets,
N/A rules, stable IDs, auto-scan, one-league-failure-isolation) **already exists** in
`worldfeed.py` / `scanner.py` / `leagues.py` / `appdata.py`.
