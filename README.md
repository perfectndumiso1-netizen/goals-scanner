# ⚽ PlayReport

Automatic football analysis that runs **every 30 minutes** on GitHub Actions and publishes to the PlayReport
Android app and Telegram — no servers, no API keys, and it runs while your phone is in your pocket.

* **Coverage** — every competition on the public live feed, worldwide (including women's and youth leagues),
  priced by Sportybet South Africa; the 22 main European leagues additionally get corners, cards and referee models.
* **Data-first model** — every probability comes from football data only (goals, form, venue, league baseline →
  Dixon-Coles score matrix); bookmaker prices are a *separate comparison layer* (implied %, difference, EV, market xG)
  and never feed the model. Every statistic carries its sample size (Very small 1–4 … Very strong 40+), every match
  has a transparent data-quality assessment, the raw matches used, extreme results flagged and the model's own
  numbers ("why 1.35 goals?") in the app's **Data** tab and in `python audit.py HOME AWAY`. Missing data is N/A, never 0.
* **Goals shortlists** — Over 1.5, Over 2.5, Both Teams To Score, from the backtested and calibrated model.
* **High-probability selections** — singles with model probability ≥ 70 % (**Over 2.5 and BTTS from 55 %**), priced by
  Sportybet, in the Over-goals / BTTS / corners / bookings markets — no team goals, no double chance, no unders
  (2026-10-17, see *Market policy* below). New ones are announced immediately (Telegram + app). Nothing is ever
  labelled "safe" or "guaranteed".
* **⭐ Bets of the day** — grouped card built on Over 1.5, Over 2.5, BTTS and bookings; 1X2 / BTTS / Over 2.5 only with strong supporting form; one market per match; graded separately.
* **Trends, head-to-head and home/away form** on every match page; live scores, line-ups and match statistics for
  every match in play; squad values (Transfermarkt) for the main leagues.
* **Live research & context** (Phase A: collected and shown, **not yet weighted**) — for the fixtures inside the
  published window the scanner also records attributed current information: confirmed line-ups from the live feed
  when they are published, reported team news (outlet, link and publication time, availability signals flagged but
  never "verified"), scheduling/fatigue from our own archive, the competition format, and Open-Meteo weather for
  genuinely severe conditions only. Each match shows **base probability → context → final probability** with a
  research-quality grade (HIGH/MEDIUM/LOW/INSUFFICIENT), the reasons, the sources and any unresolved conflict;
  missing information is N/A and normal weather is no adjustment by rule. With the shipped configuration the
  published probability is *identical* to the statistical model — see `docs/RESEARCH.md`.
* **Bet slip & tickets** in the app — build a multiple from priced selections, lock it, and PlayReport grades it from
  the scores and match statistics (private record on the phone).
* **Results archive** — every finished match on the live feed is kept with half-time score, corners, cards, shots and
  possession (`data/ls/` on the data branch), feeding the corners / cards models for every league over time.
* **Checked before publishing** — every run exports the app data to a staging directory and `verify.py` checks it
  (format, probabilities, prices, selection rules, day-card sections, detail files, evidence layer, no market
  contamination of model probabilities, ledger integrity) before it is
  promoted; a failed check keeps the previous publication and reports the problem on Telegram.
* **Season backfill** — up to two earlier seasons of every covered competition are archived from Livescore once,
  so head-to-head, form and league pages are complete outside football-data's leagues.
* **Delivery** — full report (Markdown + PDF) at 07:00 / 12:00 / 17:00 SAST on Telegram; a 9:16 shortlist reel
  (no background music; each slide holds until that pick's voice-over ends) once a day before 07:00 SAST, then
  deleted; app data on the `data` branch (`data/app/latest.json`, per-match files, 60-day history); a weekly
  performance digest on Mondays.

The code lives on `main`; all generated state (reports, ledgers, app data, the Livescore archive) lives on the
orphan `data` branch, which is force-pushed by every run so the history stays small.

Statistical information, not betting advice. 18+.

## 🎾 Tennis Scanner (separate module)

`tennis/` is an independent package built beside the football scanner — own data (`data/tennis/`, `data/app/tennis/`
on the orphan `tennis-data` branch), own model, tracker (`data/tennis/tracker.csv`), reports (`reports/tennis/`),
workflow (`.github/workflows/tennis-scan.yml`, four runs a day) and tests (`tennis/tests/`). It imports nothing from
the football model code; the only shared piece is the generic Markdown → PDF helper. See `docs/TENNIS_AUDIT.md`
(architecture, sources, limitations) and `tennis/BACKTEST_RESULTS.md` (walk-forward validation and calibration).

* **Coverage** — ATP / WTA main tours and ATP/WTA Challengers, singles only (no ITF, team events or doubles).
* **Data** — Jeff Sackmann's historical match files (tennisabstract.com, CC BY-NC-SA 4.0, June 2026 snapshot via the
  Aneeshers archive mirror; 288,040 matches 2005–2026) for ratings, form, serve/return statistics; Livescore for
  results after the snapshot (no statistics — serve/return traits from the archive are marked stale when old);
  Sportybet prices as a *comparison layer only*. Anything missing is N/A, never zero.
* **Model** — Elo (overall + surface blend, sample-size K schedule) → set probability → explicit best-of-3 / best-of-5
  match probability (2-0 / 2-1 / 3-0 / 3-1 / 3-2 each way) → Markov point/game chain for total games, player games
  and game handicap. Parameters chosen on 2012–2018, evaluated on 2019–2026 (walk-forward, no look-ahead).
* **Output** — per match: MODEL PROBABILITY, FAIR ODDS, BOOKMAKER ODDS, MARKET IMPLIED, EDGE and DATA QUALITY
  (a 14-check score of the evidence, not a win probability). Reports at 08:00 / 18:00 SAST on Telegram labelled
  "🎾 TENNIS SCANNER". No parlays, no tennis + football combinations.
* **Selections of the day** — one preferred market per match (`tennis/markets.py::select`): the highest model
  probability ≥ 60 % among Sportybet-priced markets (price ≥ 1.30) whose margin-free implied probability is ≥ 45 %
  (the market must not contradict the pick), data quality ≥ 60, both players ≥ 30 rated matches, no low-confidence
  game data, model − market ≤ 20 pp. **Strong** = model ≥ 70 % and market ≥ 50 %. Ranked by probability, never by
  edge. Grouped by market (Match winner / Total games / Player games / Game handicap) in `latest.json`
  (`selections`, `sections`, `strong`), the reports and Telegram.
* **Tracker** — `data/tennis/tracker.csv` grades four groups separately (`kind` = day / strong / highlight /
  favourite): hit rate vs average model probability and flat-stake units at the recorded price. Day files
  `data/app/tennis/days/<day>.json` keep every analysed match with its result and settlement; `days/index.json` lists them.
* **App** — sport switch (⚽ Football | 🎾 Tennis) at the top of every tab in `tennis.js`; the football views are
  wrapped, not modified. Tennis Home / Bets / Live / Matches / Days and a match page with Overview / Markets /
  Stats / Data (sample labels, last 10 matches with raw scores, H2H context only, quality checks, identity, inputs).
  Smoke test: `android/tennis_ui_test.py`.

### Model diet: every league the archive has enough data on (2026-10-11, widened 2026-10-17)
Fixture intake is filtered before analysis (`scanner.league_allowed` / `scanner.fixture_allowed`). A competition is in when it is on the **curated list** (big-5 + second tiers, the strong top flights, Brazil, Argentina, MLS, Liga MX, the big African leagues, UEFA Champions / Europa / Conference League), is one of the **22 football-data main divisions**, or passes the **archive rule** (`scanner.data_rich_from_facts`, computed once per run from `data/ls/stages` via `coverage.stage_facts`, ≈ 2 s): a league-shaped table (8–45 clubs), the registry's `eligible` flag, a median of at least 15 archived finished matches per club, a result inside the model's 400-day window, and match statistics on ≥ 50 % of the recent window — or, for a national league whose provider publishes no statistics (Ghana, Kenya, Tunisia, Algeria …), a table that is not a regional / amateur tier (`AMATEUR_TIER_RE`: Oberliga, Serie D, RFEF and "Group x" splits, Norwegian 3. divisjon …). On the 2026-10-17 archive that is **165 stages (was 36)**, including the **Chinese Super League and League One**, K League 1/2, the Saudi Pro League, the Indian Super League, UAE, Qatar, Thailand, Brazil Série B, USL, England League 1/2, the Scottish divisions, 3. Liga, Eerste Divisie, Liga Portugal 2 and Turkey's 1. Lig. As the stats collector fills more competitions they qualify automatically.
Hard blocks are unchanged and beat every rule: **Japan and Australia** (explicit user rule 2026-10-11), women, youth/reserve (incl. "Premier League 2"), friendlies, all domestic cups, internationals, qualifiers and play-offs. The 2026-10-17 pass also anchored the English patterns (`Northern Premier League`, step 4, used to slip through `premier league$`). Competitions that are in only through the archive rule are analysed `DIET_EXTRA_DAYS` (14) ahead — the app lists ten days of fixtures, so the far end of the 60-day window would only cost scan time (curated leagues and main divisions keep the full horizon). Depth gate: a fixture where either team has fewer than `MIN_TEAM_MATCHES` (8) recent matches with data is skipped entirely. Every app surface inherits the filter (shortlist, selections, bets of the day, accas, the Leagues browser, fixtures list and search); history collection stays wide so cup/international results still feed team form. Levers: `MODEL_DIET`, `MIN_TEAM_MATCHES`, `DIET_EXTRA_DAYS`, `DIET_MIN_PER_TEAM`, `DIET_STATS_PCT`, `SEED_STAGES`.

### Market policy (2026-10-17)
`policy.py` is the one place that decides which selections the model may recommend; `safe.selections()` asks it for every candidate, so the shortlist, high-probability selections, bets of the day, accas, the match pages and the app boards all inherit it (the app repeats the rule client-side so a payload published before a change cannot show a dropped market). **Dropped:** team goals (HO05 … AU15), double chance (1X/12/X2) and **every under** — total goals, no-BTTS, team unders, corner and card unders (the old pattern missed team-level corner/card unders, which is how `CAU55` / `KHU25` reached bets of the day). **Focus:** Over 1.5, Over 2.5, BTTS and bookings; 1X2 and corner overs stay on (not asked to go). **Over 2.5 and BTTS start from a 55 % model probability** (`policy.SEL_MIN_P`, in the shortlist bars, bets of the day, the high-probability list and the app boards); every other market keeps its bar (goals lines 70 %, corners & bookings 65 %, 1X2 60 %). Old codes still label and settle, so bets placed earlier keep grading. Levers: `MODEL_MARKETS=all` (or `unders,team,dc`) restores a dropped family, `MODEL_DROP=corners,result` switches those two off, `MIN_P_O25` / `MIN_P_BTTS` move the 55 %.

### Briefing videos go to Telegram, then the file is deleted (2026-10-13)
Shortlist briefing videos are sent with `send_telegram_video` (same `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` as the text picks). After a successful send the local file is unlinked. They are never committed, never published on the `data` branch, and never uploaded to Drive. Pass `PLAYREPORT_BRIEFING_VIDEO` on a report run to send one. Ultra-realistic voiceovers are cut in the agent session — Actions does not mint that voice.

### Sportybet names no longer mix matches + shortlist briefing (2026-10-13)
`attach_prices` looked up Sportybet events by `zip(todays.index, rows)`. The depth gate drops thin fixtures from `rows` but not from `todays`, so every later event slid onto the wrong match — `home_long` then painted the bookmaker name (Kaizer Chiefs on Bristol City) across the app. Lookup is now by fixture identity; `event_fits` refuses a name that is not the same club; matching is exclusive; carried cache events are dropped when they do not fit. The client ignores `home_long` / Sportybet deep-links that fail the same check, so an already-published file stops lying on update. Shortlist tab: **Tonight's briefing** — a video-style player with a male voiceover and a download (WebM when the WebView can record, otherwise a self-contained HTML briefing).

### Wrong-match fix, new sounds, corner & booking prices, focused trends (2026-10-13)
Four user-commissioned changes. **Wrong-match bug**: the client now verifies identity at every layer — a detail file must carry the tapped fixture's id AND its team names before it is rendered (`loadDetail`, `matchPage`), day-archive fallbacks are pinned by country (same-name pairs in two countries can never cross), and the on-phone cache moved to a fresh namespace (`pr_d:`) with a one-time sweep of the legacy `pr_c:*` entries, so data poisoned by pre-1.6.57 builds is gone on update. `tools/app_click_identity.mjs` boots the real app in jsdom against the live publication, taps every surface and asserts the right match opens — including poisoned-cache scenarios. **Notification sounds**: the whole `res/raw/pr_*.wav` family was re-synthesised (numpy additive synthesis, soft attack, exponential decay) to match each channel's meaning, and the channel ids were bumped to `_v4` (Android freezes a channel's sound at creation; old channels are deleted). **Corners & bookings prices**: `LIST_MARKETS` now includes Sportybet's total-corners (166) and bookings (139) markets — probed: the list endpoint carries both, so every priced fixture gets the ladders with no extra requests; `selections()` prices total corner/card lines from the list feed (per-event full list still wins) and adds team corner/card selections (`CH/CA/KH/KA` + O/U + line); `_sb_from_sels` rebuilds them across fetch outages; labels updated server- and client-side. **Trends**: non-Trends surfaces (match Overview) show only the 3 strongest trends by the strength score `s`; the Trends tabs keep everything.

### UEFA competitions + predicted line-ups (2026-10-12)
Two user-commissioned upgrades. **UEFA in**: `league_allowed` now admits the UEFA Champions League, Europa League and Conference League (allow entries: `^uefa$|^europe$` × `champions league|…`, plus the real Livescore shape `^champions league$|^europa league$|^conference league$` — the competition IS the country); the block regex keeps `qualif*|play-offs`, so UCL/UEL/UECL qualifiers and play-off rounds never enter. Intake seeds carry the probed-real stage keys `champions-league/league-stage,europa-league/league-stage,conference-league/league-stage` (all HTTP 200; the `uefa/*` slugs are 410); the Leagues tab derives from the index, so the app needs no client change. **Predicted line-ups**: all third-party prediction sources are bot-walled from server IPs, so the app grows its own — `research/lineups.XiArchive` harvests every confirmed XI the research layer already collects into `data/research/xi_archive.json` (eid-deduped, index capped 20k). A club with ≥3 archived XIs gets a projection (`XiArchive.projection`): formation by recency-weighted vote over the last 8 (0.75^i), starters ranked by weighted starts filled per position group (4-2-3-1 folds mid to n2+n3), bench from last-6 subs. `scanner.py` attaches projections to app rows before the shortlist pass; `appdata` publishes `lineup_proj`; `pages.js lineupsBlock` renders both XIs labelled **"Predicted by PlayReport … a projection, never official"** whenever the official XI is absent, and the official XI replaces it on publication. Projections never feed the model.

### Deep analysis + Telegram picks (2026-10-11)
### Calibration, safer doubles & the honest record (2026-10-11)
`calibration.py` learns a per-market-group isotonic map from the settled shortlist ledger and validates it OUT-OF-TIME (21-day holdout, Brier); it goes live per market group only where it beats the raw model. Live maps set `p_cal` on every pick and the honest composite on accas; the Performance page shows the curve, the per-market table and predicted-vs-actual bands. A second acca family — **safer doubles** (exactly 2 legs at ~2.00, same gates, never sharing a match with the 3.00 builds) — is tracked in its own ledger (`data/accas_doubles.csv`) with its own verification contract. `backtest/research_backtest.py` is the Phase-B evidence run: reconstructable research factors (rest, congestion, form gap) are tested against model residuals on the settled ledger; a factor earns a weight only on a monotone, well-sampled signal (2026-10-11 run: none — weights stay 0, see `backtest/RESEARCH_RESULTS.md`). The app notifies when the shortlist publishes (one push per run, `counts_shortlist` in the publication meta).

### Deep analysis + Telegram picks (2026-10-11) (`shortlist.match_article`) built only from its own MatchRow data — last-five form chips, a model-vs-bar-vs-market probability bar, goals per match, venue splits, head-to-head, and a verdict line; anything missing renders as N/A. The diet also filters the app-wide Leagues browser/fixtures index (`leagues.build(..., allow=league_allowed)`), so no off-diet competition appears anywhere. `scanner.telegram_shortlist()` pushes the day's primary picks (strongest market per match) to Telegram once per pick per day (`TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`, deduped via `data/app/telegram_state.json`).

### High-conviction shortlist (`shortlist.py`)
A strict filter over the day's board: hard gates (data checks, verified price, odds band 1.15–1.90, per-market probability bar, believable model/market gap) and soft gates (data quality, confidence, warnings, research conflicts, carried prices). EV and edge are displayed but never gate (user rule 2026-10-11) — value hunting lives on the Positive EV tab. At most 7 matches, one selection each; otherwise **NO QUALIFYING SELECTIONS**. Read-only: it never changes a probability. Every decision is logged to `data/shortlist.csv` before kick-off and settled for walk-forward evaluation. Levers: `SHORTLIST_MIN_ODDS`, `SHORTLIST_MAX`.

### Sequences tab & selection rules
User betting sequences (07–12, 12–16, 16–20, 20–00 SAST) get their own tab: the day's shortlist split into windows — the same gates, one strongest market per match across all markets, Sportybet price and model probability.
