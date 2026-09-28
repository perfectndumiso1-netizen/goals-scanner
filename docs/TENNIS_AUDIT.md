# Tennis Scanner — repository audit, data-source verification and proposed architecture

Date: 2026-09-28 · Status: written **before** any Tennis model code (Steps 1–3 of the brief).

## 1. Current Football architecture (what exists, what it touches)

| Module | Role | Football-specific? |
| --- | --- | --- |
| `scanner.py` (2 448 lines) | Orchestrator: fixtures → history pool → Dixon-Coles model → markets → Sportybet prices → safest/bets of the day → app JSON → day history → reports → Telegram | Yes (model, CONFIG, MatchRow, publication). Contains the two generic Telegram helpers `send_telegram(text)` / `send_telegram_document(path, caption)` (35 lines) — usable only by importing the whole football scanner |
| `markets.py`, `safe.py`, `parlays.py`, `trends.py`, `teamstats.py`, `quality.py`, `verify.py`, `audit.py`, `appdata.py`, `history.py`, `worldfeed.py`, `squads.py`, `news.py` | Goals model markets, selection rules, team stats, football data-quality engine, football app JSON, football day archive, Livescore football archive | Yes — all of them hard-code goals/xG/O-U/BTTS/corners/cards or football file layouts |
| `livescore.py` | Livescore **football** day feed, live status, incidents | Yes (`/date/soccer/…`, `Tr1/Tr2` goals). The transport pattern (no `Origin` header, mobile UA) is reusable knowledge, not code |
| `sporty.py` | Sportybet ZA API: `_get()` (curl `--http2` transport that passes the WAF), `fetch_upcoming()` hard-wired to `sportId=sr:sport:1`, football market parser, team-name matcher | Transport `_get()`/`norm()`/`similarity()` are generic; everything else is football |
| `pdfgen.py` | Markdown → PDF (reportlab) | **Generic** (`markdown_to_pdf(md, path, title, subtitle)`) |
| `backtest/` | Football replay backtests + results | Yes |
| `data/` (git-ignored `state/` at runtime; published on branch **`data`**) | `data/app/latest.json`, `fx/`, `days/`, `teams/`, `reports/`, `ls/`, `safe_bets.csv`, tracker | Yes |
| `.github/workflows/scan.yml` | Every 30 min: clones branch `data`, runs `scanner.py`, `git add -A`, **amends and force-pushes a single commit to `data`** | Yes. Any second job pushing to `data` would race with this force-push |
| `.github/workflows/build-app.yml` | Android build on `android/**` changes | Shared build, sport-agnostic |
| `android/` | PlayReport WebView app (`core.js`, `views.js`, `pages.js`, `slip.js`, `export.js`); native shell (WebView, notifications, background checker for football alerts) | UI is football-specific; the shell (asset loader, `nfetch` proxy, notification channels, update flow) is generic |
| Tests | `android/ui_test.py` (Playwright UI smoke test), backtests | No pytest suite exists for football; nothing to break there, but the UI test must keep passing |
| `requirements.txt` | pandas, numpy, requests, reportlab | Tennis needs nothing new |

## 2. Infrastructure Tennis reuses (read-only, no changes)

* `pdfgen.markdown_to_pdf` — PDF report rendering.
* Sportybet transport pattern (curl over HTTP/2 first, requests as fallback — the WAF-safe approach found for football) — **re-implemented** in `tennis/data.py` (`_sporty_get`, ~25 lines) so the tennis job has no runtime dependency on `sporty.py`; `pdfgen.markdown_to_pdf` is the only football file imported.
* GitHub Actions pattern of `scan.yml` (wheels-only pip loop, state branch clone/commit) — copied, **not** shared: tennis publishes to its own branch `tennis-data`.
* Livescore transport conventions (learned): mobile UA, no `Origin` header. Tennis has its own client (`tennis/data.py`) for `/date/tennis/...`.
* Telegram: the two helpers are re-implemented in `tennis/notify.py` (30 lines) rather than importing `scanner.py`, so the tennis job never imports football code paths.
* Android shell: WebView, `nfetch` proxy, update flow, notification channel `reports_v2` for the "🎾 TENNIS SCANNER" report notice.

## 3. Football modules Tennis must not use (and does not)

`scanner.py` (model, CONFIG, MatchRow, publication), `markets.py`, `safe.py`, `parlays.py`, `teamstats.py`, `quality.py`, `verify.py`, `appdata.py`, `history.py`, `trends.py`, `worldfeed.py`, `livescore.py`, `squads.py`, `news.py`, `audit.py`, `backtest/*`, `data/tracker.csv`, `data/app/*` (football JSON), branch `data`. None of these files are modified by the tennis work.

## 4. Verified Tennis data sources (checked live on 2026-09-28)

| Source | Verified result | Fields | Update / depth | Limitations | Automation |
| --- | --- | --- | --- | --- | --- |
| **Jeff Sackmann ATP/WTA datasets** — upstream `github.com/JeffSackmann/tennis_atp`, `tennis_wta` | **Upstream repositories return 404** (removed, confirmed by third parties on 19–20 Sep 2026). Archival mirror `github.com/Aneeshers/tennis-sackmann-archive` (also on Hugging Face) is available: `atp/atp_matches_1968…2026.csv`, `atp_matches_qual_chall_*.csv` (Challengers/qualifying), `atp_rankings_*.csv`, `atp_players.csv`; `wta/` equivalents. Snapshot taken June 2026. Licence **CC BY-NC-SA 4.0** (non-commercial, attribution — PlayReport is a personal, non-commercial app; attribution added to reports/app) | tourney_id/name/level/date, surface, draw_size, round, best_of, minutes, score, winner/loser id, name, hand, height, ioc, age, rank, rank points; serve stats per player: aces, DFs, serve points, 1st in, 1st won, 2nd won, service games, BP saved/faced | Static snapshot: ATP main tour + Challengers and WTA through **June 2026**; serve stats from 1991 (ATP) / partial (WTA) | No updates after June 2026 → ratings continue from Livescore results; serve/return stats age from the snapshot date and are flagged stale; Challenger/ITF serve stats are largely missing | Yes (raw CSV over HTTPS; cached, processed once into `data/tennis/history/`) |
| **Livescore tennis API** `prod-public-api.livescore.com/v1/api/app/date/tennis/YYYYMMDD/2?MD=1` | Works (same transport as football). ~90–130 singles/doubles events per day across ATP 250/500/1000, Grand Slams, WTA, Challengers, ITF, team events | Tournament (`Snm`), category (`Cnm`: "ATP 250", "WTA 1000", "ATP Challenger", "WTA Challenger", "ITF Men/Women", team events), players with stable `ID`, name, country (`CoId`), start time `Esd`, status `Eps` (NS / set-by-set live / FT / Canc. / Ret.), set scores `Tr1S1…`, tiebreak points `Tr1S1T…` | Daily; any past date retrievable (used to backfill results from June 2026 to today) | **No surface, no round text, no statistics** (`statistics/tennis/{eid}` returns `{}` for every match tried, including ATP 250 main draw) → serve/return data going forward = **N/A** | Yes |
| **Sportybet ZA** `factsCenter/pcUpcomingEvents?sportId=sr:sport:5` | Works via the existing curl transport: 324 upcoming tennis events; per event full market list | Markets **186 Winner**, **189 Total Games** (several lines), **187 Game Handicap**, **190/191 Competitor total games**, plus set markets not used now; names "Surname, Firstname"; tournament e.g. "ATP Beijing, China Men Singles" | Live | Prices only — comparison layer, never a model input | Yes |
| tennis-data.co.uk (results + odds xlsx) | **HTTP 403 Cloudflare challenge** from the sandbox and (same WAF class) GitHub runners, also with `curl --http2` | — | — | Not automatable from our infrastructure | No — not used |
| ATP/WTA official sites, Sofascore, Flashscore | Bot-blocked / no public API / ToS | — | — | — | No — not used |

**Consequences for the model (honest limits)**

* Surface is not delivered by the fixture feed. It is resolved from a tournament→surface table derived from the Sackmann archive (tournament name + calendar month) and a small explicit override list; unresolved → `surface: N/A`, the surface component is switched off and the data-quality score drops.
* Serve/return statistics exist historically (through June 2026) but not for new matches. They are used only as slowly-varying player traits with an explicit staleness flag; the game markets carry `LOW DATA CONFIDENCE` when a player's serve sample is small or older than the freshness window.
* Rankings: Sackmann rankings through June 2026 only; Livescore fixtures carry no ranking → after the snapshot, "ranking" is shown as *as of <date>* and never treated as current. The model does not depend on rankings (Elo is computed from results), which is the main reason Elo was chosen.
* Player identity across sources is bridged by normalised names + country; unmatched players start with no history (shown as such, never given someone else's data).

## 5. Proposed Tennis architecture (isolated package)

```
tennis/
  __init__.py
  config.py     paths (data/tennis, data/app/tennis, reports/tennis), source URLs, thresholds, freshness windows
  data.py       Sackmann archive download/cache → base match table; Livescore tennis day feed (fixtures, results); Sportybet tennis odds;
                player-identity bridge; tournament→surface resolution
  stats.py      player observations: recent form (5/10/20), surface form, serve/return traits from raw match stats (N/A when missing),
                opponent-adjusted serve/return, match characteristics (games per match, straight sets, deciders, tiebreaks)
  model.py      Elo ability (overall + surface, K by experience) → set-win probability → best-of-3 / best-of-5 match probability and
                set-score distribution; Markov chain (serve-point → game → set → match) for total/player games and game handicap
  markets.py    Match winner, Total games, Player games, Game handicap: model probability, fair odds, bookmaker odds, implied %, edge
  quality.py    per-match data-quality checks (PASS/N/A per item) → score %; never a probability
  history.py    data/tennis/tracker.csv, per-day match files, settlement of tracked selections from results
  backtest.py   walk-forward replay of the Sackmann base (features strictly from earlier matches) → accuracy, Brier, log loss,
                calibration tables by bucket/surface/format/tour; parameter selection on early years, evaluation on later years
  scanner.py    daily orchestrator: fetch → validate → stats → model → markets → JSON → reports → history → Telegram
  notify.py     Telegram text/document helpers (tennis only, "🎾 TENNIS SCANNER" prefix)
  tests/        pytest: identity matching, duplicates, surface, bo3/bo5, missing stats, stale data, invalid fixtures/odds,
                probability bounds/sums, no look-ahead, insufficient history, name variations
```

Storage (never inside football paths): `data/tennis/{matches,players,tournaments,history}/`, `data/tennis/tracker.csv`, `data/tennis/latest.json`;
app-facing `data/app/tennis/{latest.json,matches/,players/,days/,tournaments/}`; reports `reports/tennis/YYYY-MM-DD.{md,csv,pdf}` + `latest.md`.
Published on git branch **`tennis-data`** by `.github/workflows/tennis-scan.yml` (independent schedule, independent state, commits only tennis files).

Methodology decisions to validate in the backtest before anything is published: Elo K-schedule and surface-blend weight (chosen on 2010–2018, evaluated on 2019–2026); set-level mapping so that best-of-5 is derived from set probability, not renamed best-of-3; serve-dominance baselines per tour/surface for the game markets; freshness windows for serve data. No bookmaker input anywhere in the model.

## 6. Implementation record (2026-09-28, first milestone)

Delivered exactly in the requested order: audit → source checks → architecture → skeleton → validation → historical data →
baseline model → backtest → calibration → markets → JSON → reports → workflow → minimal Android → tests.

**Model, as validated (`tennis/BACKTEST_RESULTS.md`)** — parameters chosen on 2012–2018 by log loss, evaluated on 2019–2026
(walk-forward, no look-ahead): Elo K schedule 150/(n+5)^0.3, surface blend 0.5, logistic scale 500 (400 was over-confident by
2–4 pp for favourites), best-of-5 through the set-probability mapping. Game model: Markov point/game chain pinned to the rating
probability with a *day-form spread* — the serve-point difference on the day is Normal(d0, σ), σ = 0.08 (ATP) / 0.10 (WTA)
fitted on the training period by matching the mean total games. Without it the independent-points chain over-predicted total
games by ~2 games and P(over 22.5) by ~12 pp; with it the out-of-sample bias is +0.3 games and the over/under calibration is
within 1–3 pp. These are the only fitted quantities; no other weights exist.

**Publication rules (conservative until the tennis tracker has evidence)** — a "Model above market" highlight needs: Sportybet
price ≥ 1.30, model ≥ 55 %, edge ≥ 5 pp (winner) or ≥ 10 pp (game markets; expected-total MAE ≈ 5 games), edge ≤ 20 pp
(bigger gaps are treated as information the model lacks and become warnings), data quality ≥ 60, both players ≥ 30 rated matches,
no low-confidence serve data; at most one highlight per match. The tracker records the rating favourite of every priced match
plus every highlight, and settles them from Livescore (retirements: winner settles, game markets void).

**Known limitations to keep in view** — the archive snapshot ends 2026-06-07 (serve/return statistics frozen there; results
continue from Livescore); players whose history is mostly ITF are under-rated (their matches show Medium/Low data quality and
large market gaps — that is the model's blind spot, not value); Sportybet identity matching is name-based (fuzzy matches are
flagged PARTIAL in the quality checks); no injury/withdrawal information; the mirror's provenance vs the removed upstream
repositories cannot be verified beyond internal consistency.
