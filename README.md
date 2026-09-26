# ⚽ Goals Scanner

Automatic football scanner that runs **three times a day** (07:00 / 12:00 / 17:00 South African time) on GitHub
Actions and sends everything to Telegram — no servers, no API keys, and it runs while your computer is off.

Every run:

* **Goals shortlists** — Over 1.5, Over 2.5, Both Teams To Score, from a backtested and calibrated model (v2).
* **Extra markets** — 1X2 / double chance, team goals, **corners** and **cards** probabilities (backtested, v3).
* **Sportybet prices** — real prices for every match found at Sportybet (ZA), a price check against the fair
  price, and Sportybet corners / cards / half-time corner prices for the parlay matches.
* **3 parlays** with combined odds between **2.70 and 3.50**, legs only from markets with real prices
  (1X2, double chance, Over/Under 2.5), each maximising calibrated probability × price — recorded and graded.
* **Delivery** — Telegram message + **PDF full report** + **PDF parlay dossier** (full data sheet and recent
  headlines for every parlay match); Markdown + CSV committed here; a weekly performance digest on Mondays.

<!-- SCAN:START -->
### Latest scan — Saturday 26 September 2026 (17:01 SAST)

23 fixtures scanned · window Sat 16:56 → Sun 17:01 SAST · [open full report](reports/2026-09-26.md)

**Over 1.5 goals** — 5 pick(s)

| Kick-off | Match | Competition | Final prob. | Rating |
|---|---|---|---|---|
| Sun 27 Sep 01:30 | **Philadelphia Union v Orlando City** | USA · MLS | 88% | ⭐⭐ |
| Sun 27 Sep 01:30 | **CF Montreal v FC Cincinnati** | USA · MLS | 85% | ⭐ |
| Sun 27 Sep 04:30 | **San Jose Earthquakes v Portland Timbers** | USA · MLS | 85% | ⭐ |
| Sun 27 Sep 01:30 | **Charlotte v Chicago Fire** | USA · MLS | 84% | ⭐ |
| Sun 27 Sep 02:30 | **Seattle Sounders v Minnesota United** | USA · MLS | 84% | ⭐ |

**Over 2.5 goals** — 10 pick(s)

| Kick-off | Match | Competition | Final prob. | Rating |
|---|---|---|---|---|
| Sun 27 Sep 01:30 | **Philadelphia Union v Orlando City** | USA · MLS | 70% | ⭐⭐⭐ |
| Sun 27 Sep 01:30 | **CF Montreal v FC Cincinnati** | USA · MLS | 65% | ⭐⭐ |
| Sun 27 Sep 04:30 | **San Jose Earthquakes v Portland Timbers** | USA · MLS | 64% | ⭐⭐ |
| Sun 27 Sep 01:30 | **Charlotte v Chicago Fire** | USA · MLS | 64% | ⭐ |
| Sun 27 Sep 02:30 | **Seattle Sounders v Minnesota United** | USA · MLS | 63% | ⭐ |
| Sun 27 Sep 02:30 | **Nashville SC v Toronto FC** | USA · MLS | 62% | ⭐ |
| Sun 27 Sep 01:30 | **New York Red Bulls v St. Louis City** | USA · MLS | 60% | ⭐ |
| Sun 27 Sep 03:30 | **Real Salt Lake v New England Revolution** | USA · MLS | 60% | ⭐ |
| … | _2 more in the full report_ | | | |

**Both teams to score** — 10 pick(s)

| Kick-off | Match | Competition | Final prob. | Rating |
|---|---|---|---|---|
| Sun 27 Sep 01:30 | **Philadelphia Union v Orlando City** | USA · MLS | 68% | ⭐⭐⭐ |
| Sun 27 Sep 01:30 | **CF Montreal v FC Cincinnati** | USA · MLS | 66% | ⭐⭐⭐ |
| Sun 27 Sep 04:30 | **San Jose Earthquakes v Portland Timbers** | USA · MLS | 65% | ⭐⭐ |
| Sun 27 Sep 02:30 | **Seattle Sounders v Minnesota United** | USA · MLS | 65% | ⭐⭐ |
| Sun 27 Sep 01:30 | **Charlotte v Chicago Fire** | USA · MLS | 64% | ⭐⭐ |
| Sun 27 Sep 01:30 | **New York Red Bulls v St. Louis City** | USA · MLS | 63% | ⭐ |
| Sun 27 Sep 03:30 | **Real Salt Lake v New England Revolution** | USA · MLS | 63% | ⭐ |
| Sun 27 Sep 02:30 | **FC Dallas v Los Angeles FC** | USA · MLS | 63% | ⭐ |
| … | _2 more in the full report_ | | | |

**Parlays (run 17:00, Sportybet)** — see [dossier](reports/2026-09-26-parlays.md)

1. @ **2.75** (P 37%): Guadalajara Chivas v Queretaro — Home or draw (1X) @ 1.17; Charlotte v Chicago Fire — Home win @ 2.35
2. @ **3.24** (P 30%): CF Montreal v FC Cincinnati — Home win @ 2.75; Houston Dynamo v Sporting Kansas City — Home or draw (1X) @ 1.18
3. @ **3.48** (P 28%): Philadelphia Union v Orlando City — Home or away (12) @ 1.18; Real Salt Lake v New England Revolution — Away win @ 2.95

**Tracker**

| Market | Settled | Hits | Hit rate | Last 30 days | Pending | Avg odds | Flat-stake return |
|---|---|---|---|---|---|---|---|
| Over 1.5 goals | 0 | 0 | – | – | 10 | – | – |
| Over 2.5 goals | 0 | 0 | – | – | 16 | – | – |
| Both teams to score | 0 | 0 | – | – | 14 | – | – |

### Parlay ledger

_No settled parlays yet — 15 pending (graded automatically once the results are in)._

<!-- SCAN:END -->

---

## 📱 PlayReport — the Android app

**Download:** [PlayReport.apk (latest)](https://github.com/perfectndumiso1-netizen/goals-scanner/releases/latest/download/PlayReport.apk)
— on the phone allow "install from unknown sources" when asked. If you still have the old *Goals Scanner* app
installed, uninstall it first (PlayReport is a new package). From then on the app updates itself: it checks for new
versions, downloads them and asks for one confirmation tap to install.

The app has no server of its own: it reads `data/app/latest.json`, the day files (`data/app/days/`), the team files
(`data/app/teams/`), the reports and the ledgers published by each scan, so it always shows exactly what the last scan
produced. Tabs: **Home** (the three safest trebles, top safest bets, shortlists, next kick-offs), **Bets** (safest
bets with probability / price / market filters, trebles, every market at ≥ 70 %, parlays, shortlists), **Live**
(scores, minute and scorers for every tracked match from Livescore.com's public feed, with a live verdict per bet),
**Matches** (search + sort; tap any match for a Sofascore-style page: overview, every market with model vs Sportybet
view, side-by-side team stats, season table position, head-to-head; tap any team name for its season page with splits,
last matches and the league table) and **Days** (60 days of history: every match with the final score and how the
picks, safest bets, trebles and parlays did). Menu: full analysis, parlay dossier, performance ledgers, settings.
Notifications: new analysis after each run, goals in tracked matches (with the scorer — within ~15 min when the app is
closed, instantly while the app is open) and app updates.
Every push to `android/` rebuilds the APK on GitHub Actions and publishes it on the Releases page.

## What you get every run

| File | Contents |
|---|---|
| `reports/YYYY-MM-DD.md` | Full report of the latest run that day: parlays, shortlists, Sportybet price check, every fixture with 1X2 / team goals / corners / cards, expandable per-match stats, trackers |
| `reports/YYYY-MM-DD-parlays.md` | Parlay dossier: each parlay, then the complete data sheet of every match involved + recent headlines (context only) |
| `reports/YYYY-MM-DD.csv` | Every fixture, every number (incl. corners / cards expectations and Sportybet prices) |
| `reports/latest.md` | Always the newest report |
| `data/tracker.csv` | Every shortlisted match, auto-settled once the result is in |
| `data/parlays.csv` | Every parlay proposed, auto-graded (won / lost / void) with the legs, odds and model probability |
| `data/safe_bets.csv`, `data/safe_accas.csv` | Every safest bet (≥ 70 % on both the model and the de-margined Sportybet view, price ≥ 1.30) and every safest treble, auto-graded |
| `data/app/days/`, `data/app/teams/` | Day-by-day history (60 days: scores, bets, grades) and season stats per league (table, splits, form) for the app |
| Telegram | Summary message, the full report as PDF, the parlay dossier as PDF, Monday weekly digest |
| `backtest/` | The evidence: `RESULTS.md` (goals model), `MARKETS_RESULTS.md` (corners, cards, 1X2, value finder), `PARLAY_EXPERIMENT.md` (parlay construction) |

## Coverage

38 competitions, all from the free [football-data.co.uk](https://www.football-data.co.uk) feeds:

* **England** Premier League, Championship, League One, League Two, National League
* **Scotland** Premiership, Championship, League One, League Two
* **Germany** Bundesliga, 2. Bundesliga · **Italy** Serie A, Serie B · **Spain** La Liga, Segunda
* **France** Ligue 1, Ligue 2 · **Netherlands** Eredivisie · **Belgium** Pro League · **Portugal** Primeira Liga
* **Turkey** Süper Lig · **Greece** Super League
* **Extra leagues** (no over/under odds in the feed, model only; no corners / cards data): Argentina, Austria,
  Brazil, China, Denmark, Finland, Ireland, Japan, Mexico, Norway, Poland, Romania, Russia, Sweden, Switzerland, USA (MLS)

## How it works

### Goals model (v2 — backtested on 52,000 matches)

1. **Team-form model.** Goals scored/conceded over the last two seasons, normalised by league average,
   time-weighted (a match 120 days ago counts half) and *strongly* shrunk towards league average (K = 40).
2. **Market-implied expected goals.** Where the feed publishes odds, the Over/Under 2.5 price fixes the expected
   total and the 1X2 prices fix the home/away split. Final expected goals are **90% market / 10% model**.
3. **Probabilities** for Over 1.5 / Over 2.5 / BTTS come from a Dixon-Coles-adjusted Poisson score matrix.
4. **Shortlist rule:** final probability ≥ threshold, ranked, max 15 per market.

| Market | Shortlist ≥ | ⭐⭐ ≥ | ⭐⭐⭐ ≥ | Backtest hit-rate 2025/26–26/27 (picks) |
|---|---|---|---|---|
| Over 1.5 | 84% | 87% | 90% | 87% · ⭐⭐ 88% · ⭐⭐⭐ 95% (903) |
| Over 2.5 | 60% | 64% | 68% | 67% · ⭐⭐ 71% · ⭐⭐⭐ 77% (1,675) |
| BTTS | 60% | 63% | 66% | 64% · ⭐⭐ 65% · ⭐⭐⭐ 71% (1,831) |

### Extra markets (v3 — `backtest/MARKETS_RESULTS.md`)

* **1X2 / double chance:** score matrix blended 10/90 with the sharp market (Betfair Exchange, else market
  average), de-margined with the *power* method, which fixes the favourite-longshot bias (favourites were
  under-estimated by 3–5 points with plain proportional de-margining). Where Sportybet prices a match, the fair
  probability is the average of the feed's reference price and Sportybet's own price, because the feed prices
  can be a few days old.
* **Team goals:** straight from the score matrix (calibrated within ~2 points).
* **Corners:** team corners for/against, league-normalised, time-decayed, shrinkage K = 40, negative-binomial
  totals. Calibrated within ~2 points on the 8.5–11.5 lines; beats the league-average baseline.
* **Cards:** same construction (K = 20) plus a **referee factor** where the referee is published (UK leagues);
  calibrated within ~2 points on the 3.5–5.5 lines.
* **Half-time corners:** no free historical data exists, so there is **no model** — Sportybet's price is shown
  for information only. **Squad values** are not used (no free, legal source; they are already priced into the odds).

### Parlays (`backtest/PARLAY_EXPERIMENT.md`)

Each run builds up to 3 parlays from matches kicking off before the next run (the whole 24 h window if fewer
than 4 priced matches are left). Legs: 1X2, double chance, Over/Under 2.5 at **real Sportybet prices** (feed
averages if Sportybet is unreachable). The builder maximises **calibrated probability × price** inside the
2.70–3.50 band, 2–4 legs, distinct matches. Backtest 2023–26 on real prices:

| Construction | Win rate | Return per unit |
|---|---|---|
| Highest-probability legs (naive) | 28–33% | −10% (train) / −24% (test) |
| **Max expected return, power de-margin (used)** | 30–33% | **−4% (train) / −13% (test)** |

**Read that twice:** a parlay at ~3.0 must win 1 in 3 just to break even, and the bookmaker margin compounds
across legs. Expect roughly one winning parlay in three and a negative long-run return. The ledger in the report
shows the real record. This is a research tool, not income.

### Sportybet prices and value

Prices come from Sportybet's public web feed (South Africa site by default, `SPORTY_CC`). They are used for
payouts and the price check only — **they never enter the probability model**. A positive edge means Sportybet
pays more than the fair price; in the backtest, positive edges on Over 2.5 at the best available price returned
about +3%, at average prices −7% — so value exists but is thin. A leg flagged "price moved" means Sportybet
disagrees strongly with the reference price: check team news before trusting it.

### Headlines

The parlay dossier lists up to four recent headlines per team from Google News RSS (no sign-up). They are
context for you to read — injuries, suspensions, manager changes — and are deliberately **not** fed into the
model, so unverifiable inputs cannot break it.

## Setup (once, ~5 minutes)

1. Create a GitHub repository and upload these files, keeping the folder structure.
2. Open the **Actions** tab and enable workflows if asked.
3. **Goals scan (3x daily) → Run workflow** to run it immediately.
4. It now runs at 07:00, 12:00 and 17:00 South African time (05:00 / 10:00 / 15:00 UTC).

If the commit step fails with a permissions error: **Settings → Actions → General → Workflow permissions →
"Read and write permissions"** → Save.

### Telegram

1. In Telegram, message **@BotFather** → `/newbot` → copy the bot token.
2. Message your new bot once, then open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the chat id.
3. Repo **Settings → Secrets and variables → Actions** — add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

Each run then sends the summary message, the PDF report and the PDF parlay dossier.

## Customising

Edit the `env:` block in `.github/workflows/daily-scan.yml` (no code changes needed):

| Variable | Default | Meaning |
|---|---|---|
| `TIMEZONE` / `TZ_LABEL` | `Africa/Johannesburg` / `SAST` | Timezone for all displayed times and the scan window |
| `RUN_HOURS` | `7,12,17` | Scheduled run hours (local) — keep in sync with the `cron:` line (UTC = SAST − 2) |
| `WINDOW_HOURS` | `24` | Scan matches kicking off within this many hours of the run |
| `MIN_P_O15` / `MIN_P_O25` / `MIN_P_BTTS` | `0.84` / `0.60` / `0.60` | Shortlist probability thresholds |
| `MAX_PICKS` | `15` | Max picks per market |
| `PARLAYS_PER_RUN` | `3` | Parlays built per run |
| `PARLAY_MIN_ODDS` / `PARLAY_MAX_ODDS` | `2.70` / `3.50` | Combined-odds band |
| `SPORTY_CC` | `za` | Sportybet country site (`za`, `ng`, `gh`, `ke`, `ug`, `tz`, `zm`) |
| `SPORTYBET` / `NEWS` / `PDF` | `1` | Set to `0` to switch a feature off |
| `LEAGUES` | _(all)_ | Restrict to some competitions, e.g. `E0,SP1,I1,D1,F1` |

Run it locally with `pip install -r requirements.txt && python scanner.py` (`SCAN_NOW="2026-09-26 12:00"`
simulates a run time).

## Notes & limits

* All times are South African time (SAST). Fixtures appear in the feed a few days ahead; each run lists matches
  kicking off inside the next 24 hours, and builds parlays for the matches before the next run.
* GitHub schedules can start up to ~30 minutes late at busy times. GitHub pauses schedules in repositories with no
  activity for 60 days — the commits from every run keep this one active.
* Sportybet's feed is unofficial; if it changes or blocks the runner, the scanner falls back to the feed's
  average prices and says so in the report.
* Teams with too little history (usually newly promoted from a division outside the feed) are shown with ⚠️ and
  never shortlisted or used in parlays.
* This is statistical information, not advice. Past hit-rates do not guarantee future results.
