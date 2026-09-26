# ⚽ Goals Scanner

Automatic daily scan of football fixtures for the **goals markets** — Over 1.5, Over 2.5 and Both Teams To Score.
Every morning a GitHub Actions job downloads the day's fixtures and two seasons of results, combines a
backtested team-form model with market-implied expected goals for every match, shortlists the strongest
candidates and commits a report to this repo.
No servers, no API keys — it runs even when your computer is off.

<!-- SCAN:START -->
### Latest scan — Saturday 26 September 2026 (13:51 SAST)

48 fixtures scanned · window Sat 13:46 → Sun 13:51 SAST · [open full report](reports/2026-09-26.md)

**Over 1.5 goals** — 7 pick(s)

| Kick-off | Match | Competition | Final prob. | Rating |
|---|---|---|---|---|
| Sun 27 Sep 01:30 | **Philadelphia Union v Orlando City** | USA · MLS | 88% | ⭐⭐ |
| Sat 26 Sep 16:00 | **Solihull v Boreham Wood** | England · National League | 87% | ⭐⭐ |
| Sat 26 Sep 16:00 | **Stockport v Peterboro** | England · League One | 86% | ⭐ |
| Sun 27 Sep 01:30 | **CF Montreal v FC Cincinnati** | USA · MLS | 85% | ⭐ |
| Sun 27 Sep 04:30 | **San Jose Earthquakes v Portland Timbers** | USA · MLS | 85% | ⭐ |
| Sun 27 Sep 01:30 | **Charlotte v Chicago Fire** | USA · MLS | 84% | ⭐ |
| Sun 27 Sep 02:30 | **Seattle Sounders v Minnesota United** | USA · MLS | 84% | ⭐ |

**Over 2.5 goals** — 14 pick(s)

| Kick-off | Match | Competition | Final prob. | Rating |
|---|---|---|---|---|
| Sun 27 Sep 01:30 | **Philadelphia Union v Orlando City** | USA · MLS | 70% | ⭐⭐⭐ |
| Sat 26 Sep 16:00 | **Solihull v Boreham Wood** | England · National League | 69% | ⭐⭐⭐ |
| Sat 26 Sep 16:00 | **Stockport v Peterboro** | England · League One | 67% | ⭐⭐ |
| Sun 27 Sep 01:30 | **CF Montreal v FC Cincinnati** | USA · MLS | 65% | ⭐⭐ |
| Sun 27 Sep 04:30 | **San Jose Earthquakes v Portland Timbers** | USA · MLS | 64% | ⭐⭐ |
| Sun 27 Sep 01:30 | **Charlotte v Chicago Fire** | USA · MLS | 64% | ⭐ |
| Sun 27 Sep 02:30 | **Seattle Sounders v Minnesota United** | USA · MLS | 63% | ⭐ |
| Sat 26 Sep 16:00 | **Boston Utd v Fylde** | England · National League | 62% | ⭐ |
| … | _6 more in the full report_ | | | |

**Both teams to score** — 14 pick(s)

| Kick-off | Match | Competition | Final prob. | Rating |
|---|---|---|---|---|
| Sun 27 Sep 01:30 | **Philadelphia Union v Orlando City** | USA · MLS | 68% | ⭐⭐⭐ |
| Sun 27 Sep 01:30 | **CF Montreal v FC Cincinnati** | USA · MLS | 66% | ⭐⭐⭐ |
| Sat 26 Sep 16:00 | **Solihull v Boreham Wood** | England · National League | 66% | ⭐⭐⭐ |
| Sun 27 Sep 04:30 | **San Jose Earthquakes v Portland Timbers** | USA · MLS | 65% | ⭐⭐ |
| Sun 27 Sep 02:30 | **Seattle Sounders v Minnesota United** | USA · MLS | 65% | ⭐⭐ |
| Sat 26 Sep 16:00 | **Boston Utd v Fylde** | England · National League | 64% | ⭐⭐ |
| Sun 27 Sep 01:30 | **Charlotte v Chicago Fire** | USA · MLS | 64% | ⭐⭐ |
| Sat 26 Sep 16:00 | **Aldershot v Tamworth** | England · National League | 64% | ⭐⭐ |
| … | _6 more in the full report_ | | | |

**Tracker**

| Market | Settled | Hits | Hit rate | Last 30 days | Pending | Avg odds | Flat-stake return |
|---|---|---|---|---|---|---|---|
| Over 1.5 goals | 0 | 0 | – | – | 10 | – | – |
| Over 2.5 goals | 0 | 0 | – | – | 16 | – | – |
| Both teams to score | 0 | 0 | – | – | 14 | – | – |

<!-- SCAN:END -->

---

## What you get every day

| File | Contents |
|---|---|
| `reports/YYYY-MM-DD.md` | Full report: shortlists per market, a ranked table of **every** fixture, and expandable per-match stats (model / market / final expected goals, goals for/against, home/away splits, O1.5/O2.5/O3.5 & BTTS rates, clean sheets, xG and shots on target where available, last 5 results, head-to-head, league context, bookmaker odds) |
| `reports/YYYY-MM-DD.csv` | Same data as a spreadsheet — every fixture, every number |
| `reports/latest.md` | Always the newest report |
| `data/tracker.csv` | Every shortlisted match, automatically settled once the result is in (hit / miss), so you can see the real hit-rate over time |
| `backtest/` | The backtest engine and its results (`RESULTS.md`) — the evidence behind every threshold |
| `README.md` | This page — the block at the top is refreshed with the latest shortlist |

## Coverage

38 competitions, all from the free [football-data.co.uk](https://www.football-data.co.uk) feeds:

* **England** Premier League, Championship, League One, League Two, National League
* **Scotland** Premiership, Championship, League One, League Two
* **Germany** Bundesliga, 2. Bundesliga · **Italy** Serie A, Serie B · **Spain** La Liga, Segunda
* **France** Ligue 1, Ligue 2 · **Netherlands** Eredivisie · **Belgium** Pro League · **Portugal** Primeira Liga
* **Turkey** Süper Lig · **Greece** Super League
* **Extra leagues** (no over/under odds in the feed, model only): Argentina, Austria, Brazil, China, Denmark,
  Finland, Ireland, Japan, Mexico, Norway, Poland, Romania, Russia, Sweden, Switzerland, USA (MLS)

## How it works (v2 — backtested)

1. **Team-form model.** Goals scored/conceded over the last two seasons, normalised by league average,
   time-weighted (a match 120 days ago counts half) and *strongly* shrunk towards league average
   (K = 40 matches). The backtest showed weak shrinkage made the old model over-confident by 5–10 points:
   recent goal form is mostly noise.
2. **Market-implied expected goals.** Where the feed publishes odds (the 22 main leagues), the Over/Under 2.5
   price fixes the expected total and the 1X2 prices fix the home/away split. Final expected goals are
   **90% market / 10% model** (📈 market+model). In the 16 leagues without odds the model is used alone
   (🧮 model only).
3. **Probabilities** for Over 1.5 / Over 2.5 / BTTS come from a Dixon-Coles-adjusted Poisson score matrix.
4. **Shortlist rule:** final probability ≥ threshold, ranked, max 15 per market. Team hit-rate floors and
   "model disagrees with market" filters were tested and added nothing, so they were removed.

| Market | Shortlist ≥ | ⭐⭐ ≥ | ⭐⭐⭐ ≥ | Backtest hit-rate 2025/26–26/27 (picks) |
|---|---|---|---|---|
| Over 1.5 | 84% | 87% | 90% | 87% · ⭐⭐ 88% · ⭐⭐⭐ 95% (903) |
| Over 2.5 | 60% | 64% | 68% | 67% · ⭐⭐ 71% · ⭐⭐⭐ 77% (1,675) |
| BTTS | 60% | 63% | 66% | 64% · ⭐⭐ 65% · ⭐⭐⭐ 71% (1,831) |

## What the backtest says (be honest with yourself)

52,000 matches, Aug 2023 – Sep 2026, replayed day by day with no look-ahead — `backtest/RESULTS.md` has every table.

* **The probabilities are calibrated.** When the scanner says 65%, about 65–68% of those matches go over.
  The old version said 68% and delivered 63%.
* **The market is the best predictor.** The team-form model alone beats league averages (especially in the
  odds-free leagues) but never beats bookmaker odds, at any blend weight. That is why the market dominates
  where odds exist.
* **Model optimism is not a value signal.** When the model was more bullish than the market, those matches
  under-delivered (ROI −7% to −20%). The "Model" column is context, not an edge.
* **Shortlisting by probability does not beat the bookmaker margin.** Backing every Over 2.5 pick at the
  published odds returned about −2% to −5% over the test period. Use this as a research and shortlisting
  tool, not a money machine.

Re-run it yourself: `python backtest/backtest.py` (≈1 minute after the first data download; `--grid` and
`--rho` re-tune the parameters).

## Setup (once, ~5 minutes)

1. Create a new GitHub repository (public or private) and upload these files, keeping the folder structure
   (`scanner.py`, `requirements.txt`, `README.md`, `.github/workflows/daily-scan.yml`).
2. Open the **Actions** tab. If GitHub asks, click **"I understand my workflows, go ahead and enable them"**.
3. Click **Daily goals scan → Run workflow** to run it immediately and check the output.
4. That's it — it now runs every day at 07:00 South African time (05:00 UTC).

If the commit step fails with a permissions error: **Settings → Actions → General → Workflow permissions →
"Read and write permissions"** → Save.

### Optional: Telegram alerts

1. In Telegram, message **@BotFather** → `/newbot` → copy the bot token.
2. Message your new bot once (any text), then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and copy the `"chat":{"id":…}` number.
3. In the repo: **Settings → Secrets and variables → Actions → New repository secret** — add
   `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.

The next run will send the shortlist to you automatically.

## Customising

Edit the `env:` block in `.github/workflows/daily-scan.yml` (no code changes needed):

| Variable | Default | Meaning |
|---|---|---|
| `TIMEZONE` / `TZ_LABEL` | `Africa/Johannesburg` / `SAST` | Timezone for all displayed times and the scan window (feed times are converted from UK time) |
| `WINDOW_HOURS` | `24` | Scan matches kicking off within this many hours of the run |
| `MIN_P_O15` / `MIN_P_O25` / `MIN_P_BTTS` | `0.84` / `0.60` / `0.60` | Shortlist probability thresholds |
| `MAX_PICKS` | `15` | Max picks per market |
| `LEAGUES` | _(all)_ | Restrict to some competitions, e.g. `E0,SP1,I1,D1,F1` (codes in `scanner.py`) |

To change the run time, edit the `cron:` line (GitHub cron is always UTC; SAST = UTC+2 all year).

Run it locally with `pip install -r requirements.txt && python scanner.py`.

## Notes & limits

* All kick-off times are shown in South African time (SAST). Fixtures appear in the feed a few days ahead of
  kick-off; the scanner only lists matches kicking off inside the scan window, so a 07:00 run covers that
  day's games plus overnight ones in the Americas.
* GitHub schedules can start up to ~30 minutes late at busy times. GitHub also pauses schedules in
  repositories with no activity for 60 days — the daily commits keep this one active; if it ever pauses
  you get an email with a one-click re-enable.
* Teams with too little history (usually newly promoted from a division outside the feed) are shown with
  ⚠️ and never shortlisted.
* This is statistical information, not advice. Past hit-rates do not guarantee future results.
