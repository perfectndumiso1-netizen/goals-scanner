# Audit — adding a live research / context layer to the PlayReport scanner

**Date:** 2026-10-06 · **Repo:** `perfectndumiso1-netizen/goals-scanner` @ `dec8f04` · **Status:** audit only — **no file in the repository was changed by this audit.**

Everything below is either read from the code/state, measured from the live feeds, or quoted from a published
run. Where I measured something myself, the method is stated so you can reproduce it.

---

## 1. CURRENT SYSTEM — what the scanner actually does

### 1.1 Pipeline, in order

| Stage | Module | What happens | Scale (per run) |
|:--|:--|:--|:--|
| Fixtures | `scanner.py::load_fixtures` + `worldfeed.py` | football-data.co.uk CSVs (league fixtures + reference odds) **plus** the Livescore public app feed: day feeds + one season feed per competition stage | ~17k fixtures discovered across the 60-day coverage window (`COVER_DAYS=60`) |
| Results archive | `worldfeed.py::Archive`, `history.py` | Finished matches stored per stage in `data/ls/stages/*.json` (**560 archived stages**), topped up from day feeds; football-data results for the main leagues | the model looks back **400 days** (`MAX_HISTORY_DAYS`) and **max 60 matches per team**; **2 earlier seasons** backfilled per competition, **5 seasons** for H2H; the backtest frame over the same engine is **52,331 matches** |
| Team profiles | `scanner.py::build_profile` → `teamstats.py` | Time-weighted, league-normalised goals for/against; venue splits; 60 matches per team; shrinkage of tempo (K=40) and of the attack/defence *ratio* (K_s=5, validated 2026-09-28) | per team |
| **Probability** | `scanner.py::analyse` (line 935) | `mod_h = league tempo × attack × opponent defence` → **Dixon-Coles score matrix** `M = score_matrix(mod_h, mod_a, ρ=−0.05)` → `p_model = probs_from_matrix(M)` → **`p_final = dict(p_model)`** (line 951) | all data_ok fixtures |
| Extra markets | `markets.py` | 1X2 / double chance / team goals from the same matrix; corners and cards from their own models (negative binomial, league-normalised, backtested) | same fixtures |
| Market layer | `scanner.py`, `sporty.py` | Reference odds → implied O2.5 + market-implied xG; Sportybet prices fetched and de-margined (power method) for the "implied %" / edge display — fetched only where Sportybet returns a market | priced where available, every market list requested once per run |
| Selections & boards | `safe.py` | Every market as a `Sel` with `p_model` (ranking) and `p_sb` (market, comparison only); thresholds on the final probability; OVERS_ONLY; one market per match on the card | shortlists top-15 per market (`MAX_PICKS=15`) |
| Accas | `accas.py` | 3 daily builds to ~3.00 from gated legs, tracked and settled | 3/day |
| Quality / evidence | `quality.py` | Sample composition, per-fixture data quality score (High/Medium/Low), warnings, confidence labels, explanation of the λ decomposition — **descriptive only, never changes a probability** | all data_ok |
| Context (display only) | `news.py`, `squads.py`, `trends.py`, `livescore.py` | Google News RSS headlines per team/fixture (reputable-source filter, TTL 6 h, 90/run budget, 72 h horizon, source + UTC timestamp + 24h/3d/7d freshness stored); Transfermarkt squad values for 8 competitions; plain-language trends; live scores/incidents | ≤90 news queries/run |
| Publication | `appdata.py`, `pdfgen.py`, `history.py`, Telegram | `reports/YYYY-MM-DD.md|.pdf|.csv`, `data/app/latest.json` (181 fixtures) + per-fixture detail files, day files, ledgers | 181 published fixtures |
| Gate | `verify.py` | Publication is blocked on any error (unknown fixtures, min-p rule, one market per match, acca contract, market contamination, JSON validity) | every run |

### 1.2 Where the final probability is generated (the exact insertion point)

```
scanner.py:935   def analyse(...)
scanner.py:945   mod_h, mod_a          # league tempo × team attack × opponent defence   ← statistical only
scanner.py:948   M = score_matrix(...) # Dixon-Coles
scanner.py:949   p_model = probs_from_matrix(M)
scanner.py:951   p_final = dict(p_model)   ← THE final published probability
```

`MatchRow.p_final` (documented in code as *"== p_model — the name is kept for the many callers; nothing else is
ever blended in"*) is what every consumer uses: shortlists, safest bets, the acca gate, the app, the report,
`tracker.csv`. **This single line is where a context layer connects.**

**Bookmaker odds are not an input.** Verified in code: the model path reads no odds; the market layer
(`mkt_h/mkt_a`, `p_market_o25`, `p_sb`) is attached after and only used for comparison/display. One legacy
exception: `parlays.py` blends 90% de-margined market probability into parlay legs — but parlays are **dormant**
(`scanner.py:2490` publishes an empty parlay set) and the daily accas replaced them using model probability
only. Any new research layer must inherit the rule as-is.

### 1.3 Data sources already in use

| Source | Used for | Notes |
|:--|:--|:--|
| football-data.co.uk | league fixtures, results, reference odds, referees | free CSVs, no key; cached in `data/cache` (84 files, 13.6 MB) |
| Livescore public app feed (`prod-public-api`) | world fixture spine, results archive, match statistics, incidents | unofficial, no key; **the app already calls `/lineups/soccer/<eid>` client-side** (Match Center → Line-ups) |
| Sportybet public JSON | prices, de-margined implied probabilities | unofficial; the app uses it for pricing/payout only |
| Google News RSS | per-team / per-fixture headlines | free; already budgeted + cached + source-attributed |
| Transfermarkt public alpha API | squad market values | free; only 8 competitions matched so far |
| Sackmann (tennis) | tennis scanner | separate pipeline |

### 1.4 Existing safety rails (worth reusing, not rebuilding)

- **Budgets are house style:** worldfeed stage refresh = 6 h TTL, 150 s budget, 60-request backfill cap; stats refresh = 60 s / 400 requests; news = 90 queries/run with a 6 h TTL cache and stale-fallback.
- **Fail soft everywhere:** news, squads, Sportybet, Livescore all return empty on error and log a warning; nothing takes the run down.
- **Feature flags:** `WORLD`, `NEWS`, `SPORTYBET`, `PDF`, `LIVESCORE`, `ACCA_*` — everything optional is env-gated.
- **`verify.py` blocks bad publications**, and `quality.py` already models "quality of the evidence" (High/Medium/Low) — a different question from research quality, and the two must stay separate.

### 1.5 Runtime, storage and workflow constraints (measured)

| Measure | Value | Implication |
|:--|:--|:--|
| Scan job timeout | **45 min** (`scan.yml`) | hard ceiling |
| Actual run duration | median **24.8 min**, max 27.8 (20 successful runs sampled via the Actions API) | ~**20 min headroom** |
| Cron | every 30 min; full-report runs 07:00/12:00/17:00 SAST | a natural pre-match refresh cadence already exists |
| Published window | 181 fixtures, **100% carry a `livescore_id`** | every published match is addressable on the live feed |
| Analysed sweep | ~17k fixtures (60-day window) | any per-fixture research must be **fenced off** from this |
| State branch | 176 MB / 4,338 files (reports CSVs ~6 MB/day, `data/app` 104 MB, `data/ls` 13 MB) | room for a research store, but records must be window-scoped and pruned |
| State history | single amended commit, force-push | repo stays small; no history growth from records |
| Coverage registry | **598 competitions** (566 active, 397 eligible) — and **214 of them publish no match statistics at all** | the single most important constraint on research quality |

### 1.6 Backtesting / error analysis already available

- `backtest/backtest.py` replays the production model over **52,331 matches** with a no-look-ahead engine; produces per-match model probabilities and columns (`lh`, `la`, `mu`, `gap`, DC probabilities).
- Metrics already implemented: **log-loss, Brier, calibration tables**, per-league and per-market breakdowns, threshold curves; strict gate **select on train ≤ Jun-2025 → confirm on test (25/26–26/27)**.
- `backtest/error_analysis.py` already produces 11 sections (calibration gaps, bias by league, temporal drift, error by model input, confident errors, 1X2, low/high totals, market-disagreement, input–error correlations).
- Settlement machinery exists and is battle-tested: `tracker.csv` already stores `p_model`, `p_market`, **`p_final`**, odds and outcome per published market — the perfect place to add a `p_base` column and evaluate base vs final prospectively.
- Nothing in the last 15 commits touched the probability maths; the last model change was the 2026-10-01 boost study (form half-life, venue K, 60 matches/team) documented in `backtest/RESULTS.md`.

---

## 2. RESEARCH CAPABILITY — what live information can realistically be added

I probed the live feed myself rather than assuming. Method: today's Livescore day feed, then `/lineups/soccer/<eid>`
for a spread of matches that had **already kicked off** (so a line-up must exist if the competition is covered).

| Category | Available free? | Evidence | Coverage / freshness |
|:--|:--|:--|:--|
| **Confirmed lineups** | **Yes, server-side** — `/lineups/soccer/<eid>` on the feed already in use; the app already renders it (Match Center → Line-ups, shown only near kick-off) | **6 of 10** sampled fixtures returned both XIs (22 players); the 4 misses were club friendlies, Uruguay Primera, Colombia Primera B and a U21 qualifier 12 min before kick-off | competition-dependent; published shortly before kick-off |
| **Predicted lineups** | **No source** | the endpoint publishes only actual XIs; no predicted-lineup field anywhere in the payload | n/a — never pretend |
| **Injuries / suspensions / doubtful** | **Not in any feed in use** | lineup player objects carry only name/number/position; `/incidents` and `/statistics` carry no availability data | only free signal is news text (below) |
| **Team news / official announcements / manager comments** | **Already collected** | `news.py`: Google News RSS per team + per fixture, reputable-source filter, keyword scoring, 4 items/team, **source + UTC timestamp + 24h/3d/7d freshness stored**, 6 h TTL cache (1,290 cached queries) | patchy for lower leagues; text-only, not structured |
| **Motivation / match context** | **Yes — computed from data we already hold** | league tables (`leagues.py`, `teamstats.py`), stage results archive (560 competitions), remaining fixtures, competition format detection (`league_like`) | needs zero external calls; fully backtestable |
| **Fatigue / congestion** | **Yes — computed from data we already hold** | match dates per team in the results pool + stage archive; extra time visible from feed status (AET) | zero external calls; fully backtestable |
| **Travel** | No | no venue/coordinates in the feeds in use | would need a coordinate map (see cost) |
| **Weather** | **Yes — free** | Open-Meteo (forecast + historical archive + previous-runs), no key | **needs coordinates**; only meaningful for severe conditions by our own rule |

**Two structural findings that shape the design:**

1. **Lineups are real but arrive late and only for covered competitions.** They are useless at 07:00 and useful
   in the last hour before kick-off — i.e. they belong to a *pre-match refresh* stage, not the morning board.
2. **Availability data (injuries/suspensions) has no free structured source in the feeds we already use**, and —
   critically — **there is no historical archive of it**, so any weight given to it cannot be backtested
   retrospectively. Per your own rule (accuracy over completeness, never invent), this category must start at
   **zero numeric weight** and earn its way in by forward monitoring of published picks.

---

## 3. DATA SOURCES — by category

| Category | Source | Access | Free? | Freshness | Reliability / caution |
|:--|:--|:--|:--|:--|:--|
| Confirmed lineups | Livescore app feed `/lineups/soccer/<eid>` | HTTP, already in use | Free, unofficial, no published quota | ~1 h pre-KO | Official-ish, broadcast-derived; **absent for many competitions** — detect and record "not published", never infer |
| Team news, injuries as *text* | Google News RSS (via `news.py`) | already integrated | Free | minutes–hours | Only explicit claims from reputable sources; each fact keeps source + timestamp; conflicting claims → no adjustment |
| Motivation / context | own archives (tables, results, remaining fixtures, competition format) | local | Free | per run | Deterministic and auditable; reconstruct standings *as of* each historical date for backtests (no look-ahead) |
| Fatigue / congestion | own archives (match dates, AET) | local | Free | per run | Deterministic; travel excluded (no coordinates) |
| Weather | **Open-Meteo** forecast + historical archive | HTTP, no key | Free (fair-use; attribution) | hourly, updates every 15 min | Genuinely reliable; **requires venue coordinates** |
| Venue coordinates | OSM Nominatim geocoding, cached in-repo | HTTP | Free (1 req/s, attribution) | one-time + refresh | Needed for weather (and later travel); only worthwhile for competitions we actually publish |
| Referees | football-data.co.uk CSVs | already in use | Free | per match | Already used for the cards model (UK leagues) |
| Squad values | Transfermarkt public alpha API (`squads.py`) | already in use | Free | weekly | 8 competitions only; context/display |

**Not used, and I recommend keeping it that way:** any site that publishes *predictions* (tipster sites,
"predicted XI" aggregators) — your rule against treating someone else's prediction as ours, and the accuracy rule,
both point the same way.

---

## 4. COST

**Everything in the recommended plan is free.** Concretely:

- Open-Meteo (weather): free, no key, no card, ~10k calls/day fair use — we would use **tens per run**, with cache.
- OSM Nominatim (coordinates): free, 1 req/s, attribution — a **one-time** build, cached in the repo.
- Lineups / news / motivation / fatigue: no new cost at all.
- No subscription, no trial, no paid tier is required for the recommended scope. **Nothing has been subscribed and nothing will be without asking you first.**

If you later want structured **injuries/suspensions or predicted lineups at scale**, that is the one category that
needs money. In the format you asked for (prices to be confirmed before any decision — I have not signed up for
anything):

| | Candidate |
|:--|:--|
| **Service** | A football data API with an injuries/suspensions endpoint (API-Football, Sportmonks and similar) |
| **Why needed** | Free feeds carry no availability data, and there is no historical archive to backtest against |
| **Free alternative** | News-RSS facts with source attribution and **zero numeric weight** until forward evidence exists |
| **Free-tier limitation** | Typical free tiers are ~100 requests/day — enough for a handful of near-kick-off matches, not for a daily shortlist of 40+ |
| **Estimated cost** | Paid tiers start around a few tens of USD/month; needs verification before any commitment |
| **Expected benefit** | Unproven. It is the one category with a plausible real edge (a missing first-choice XI is information the market may price slowly), but it cannot be validated retroactively and would still be forward-tested |

---

## 5. ARCHITECTURE — exactly where the layer connects

### 5.1 The one-line insertion point, done the safe way

Keep the statistical model untouched and **adjust the goal rates, not the probabilities**:

```
p_base   = probs_from_matrix(score_matrix(λh, λa))                 # today's model, unchanged, always stored
λh' = λh × Π(context factors)   λa' = λa × Π(context factors)       # bounded, per-factor, explainable
p_final  = probs_from_matrix(score_matrix(λh', λa'))               # every market stays internally consistent
```

Why rates and not probabilities: adjusting each market's probability independently breaks internal coherence
(P(Over 2.5) could exceed P(Over 1.5); 1X2 could stop summing to 1; BTTS could contradict the goal markets). A λ
multiplier flows through the existing matrix, so **every market moves together and the existing maths is reused
verbatim**. The per-factor effects are still reportable in percentage points: apply factors one at a time and
record the resulting Δp per market.

### 5.2 Where each stage runs (the cost control that matters)

**Research never touches the 17k sweep.** Stages are fenced by the existing gates:

| Stage | Scope | Volume | What happens |
|:--|:--|:--|:--|
| 0 | all analysed fixtures | ~17k | statistics only — unchanged. `p_base` recorded |
| 1 | app window (published) | ~180 | cheap facts: fatigue, motivation, weather (TTL-cached) |
| 2 | shortlist + dossiers + acca legs | ~20–60 | lineups, news facts (budgeted like `news.py`) |
| 3 | pre-match refresh (within ~2 h of KO, using the existing 30-min runs) | ~tens | re-check lineups/news/weather → recompute → **final** probability that gets published/settled |
| 4 | post-match | same rows | attribute the outcome against the recorded facts → error-analysis category |

### 5.3 New code (small, isolated, reversible)

```
research/
  __init__.py      # one entry point: research.apply(rows, now, ctx) -> None  (mutates only what it owns)
  facts.py         # the fact record: id, category, text, subject, source, url, retrieved_at, effective_at,
                   # confidence, status (current/stale/conflict), evidence-strength
  sources.py       # source registry + attribution + reputation rules (official > reputable provider > press)
  lineups.py       # confirmed XI only (feed `/lineups/<eid>`), extracted to strength deltas
  news_facts.py    # pulls from the EXISTING news.py cache; categorises explicit claims; never guesses
  motivation.py    # table position, gap to objectives, games left, competition priority — from own archives
  fatigue.py       # days since last match, matches in 7/14 days, extra time — from own archives
  weather.py       # Open-Meteo, only for fixtures with cached coordinates
  context.py       # the scoring rules, caps, conflict handling, research-quality score
  store.py         # per-fixture research records + TTL cache + pruning
```

- **Config flags, default off** (house pattern): `RESEARCH=0|1`, `RES_CONTEXT_WEIGHT=0.0` (0 = collect & display
  but **no** probability change), `RES_MAX_ADJ_PP=2.0`, `RES_MAX_LAMBDA_PCT=6.0`, `RES_LINEUP_LEAD_MIN=120`,
  `RES_WEATHER=1`, `RES_BUDGET=60`, `RES_TTL_H=3`.
- **Storage:** `data/research/<fixture-key>.json` (facts, sources, timestamps, per-factor Δp, quality, base/final),
  pruned to the window + 21 days. A compact `context` block added to the existing per-fixture detail file and the
  report card. New ledger columns on publication: `p_base`, `p_final`, `ctx_adj_pp`, `res_quality`, `res_top`.
- **Lifecycle:** identical to your §11 — earlier scan → pre-match refresh → confirmed lineup recalculates context →
  final probability published; the existing half-hourly runs supply the cadence, with `last_context_at` +
  kickoff-proximity gates so nothing is fetched twice.

### 5.4 The scoring rules (bounded, explainable, never random)

| Factor (example) | Direction | Default weight | Cap |
|:--|:--|:--|:--|
| First-choice GK / CB missing (confirmed XI) | λ against ↑ | small | per-player, capped |
| First-choice striker missing | λ for ↓ | small | per-player, capped |
| Opponent key absence | opposite | small | per-player, capped |
| Congestion: ≤3 days since last match, or ET in last match | both λ ↓ | small | −3% λ |
| Motivation: must-win vs dead rubber (evidence: points/games left + competition format) | λ for ↑/↓ | small | ±2% λ |
| Weather: only severe (e.g. high wind, heavy rain, extreme heat) | total goals ↓ | 0 unless severe | ±2% λ |
| **Normal weather** | — | **0 by rule** | — |
| Conflicts / weak evidence / stale (beyond TTL) | — | **0 by rule** | — |

Hard ceilings: **per-factor ≤ 2 pp**, **total context adjustment ≤ `RES_MAX_ADJ_PP` (default 2 pp) on any published
market**, **λ multiplier product within ±6%**. The statistical model therefore remains dominant by construction, and
`p_final` can never drift far from `p_base`.

### 5.5 Research quality (separate from data quality)

`Research quality: HIGH | MEDIUM | LOW | INSUFFICIENT`, computed from: confirmed lineup present?, news facts with
fresh timestamps?, official source present?, weather available?, source agreement?, and **competition coverage**
(using the registry's 214 no-stats competitions as a prior). It is stored and displayed — **it never multiplies into
the probability**. It also drives the display: LOW/INSUFFICIENT → the card says so and the adjustment is 0.

### 5.6 Explainability output (your §14, adapted to the existing format)

Stored per fixture and rendered compactly (app Match Center + report card + ledger columns):

```
BASE 67%  ·  CONTEXT +2%  ·  FINAL 69%  ·  RESEARCH QUALITY: HIGH
  +1 pp  Opponent GK absent            (Official club, confirmed XI, 16:10 SAST)
  +1 pp  Home striker confirmed        (Feed lineup, 16:10 SAST)
   0 pp  Normal weather                (Open-Meteo, 15:40 SAST)
   0 pp  Congestion 3 days             (own archive — below threshold)
Conflicts: none
```

---

## 6. RISK — what could break, and how it is prevented

| Risk | Prevention |
|:--|:--|
| **Odds leaking into the probability** (your most important rule) | The research package has no odds input; `verify.py` gains a check that `p_final` never moves more than the cap from `p_base` and that no price field is read in the research path; a test asserts `p_final == p_base` when `RES_CONTEXT_WEIGHT=0` |
| **Invented / substituted information** (wrong team, wrong player, stale news) | Every fact requires source + retrieval timestamp + confidence; unmatched or unverifiable → `N/A` with zero weight; a fact whose team/player cannot be resolved is dropped and logged, never guessed |
| **Conflicting sources** | Recorded as a conflict with **no adjustment** until a higher-quality/current source resolves it (explicit rule, tested) |
| **Silent calibration damage** | Two caps (λ % and pp) + **mandatory backtest gate** before any category gets weight; categories that fail stay display-only |
| **Over-fitting the new layer** | Reuse the existing train ≤ Jun-2025 / test gate; no parameter tuning on the test split; report both sides |
| **Rate limits / runtime** | Staged scope (never the 17k sweep), TTL caches, per-run request budget, fail-soft; measured headroom is ~20 min and expected cost is well under 1 min |
| **Storage growth** | Records window-scoped and pruned by age, count *and* size (oldest first), bulky payloads dropped once a fixture is settled, size logged each run; published base-vs-final numbers live in the small, permanent ledgers |
| **Breaking the working PlayReport** | Everything behind `RESEARCH=0` by default; publication still gated by `verify.py`; app payload additions are additive (older app ignores unknown keys); one revert commit returns to today's behaviour |
| **Confusing research quality with data quality** | Separate fields, separate vocabulary, documented; neither feeds the probability |
| **UI over-trust** ("+2%" read as certainty) | Every surface shows **base vs final** together, plus the quality label; LOW/INSUFFICIENT says "no reliable live information" |
| **Wasted effort on uncovered competitions** | Research quality is computed per competition from measured availability (the 6/10 probe becomes a tracked metric, not a guess) |

---

## 7. EXPECTED BENEFIT — honest

**Certain benefits (no probability change needed):**
- Every published pick carries base vs final, the evidence, sources, timestamps and a research-quality label — auditable, and impossible to confuse with a guess.
- A pre-match refresh stage that finally uses confirmed line-ups in the hour before kick-off (today the app *shows* lineups but the model never sees them).
- A new error-analysis axis: whether failures tracked to context (stale info, missing info, conflict, over/under-adjustment).
- A documented, tested pipeline for adding sources later without touching the model.

**Probable but unproven benefits (must pass the backtest gate):**
- Fatigue/congestion and motivation are cheap, deterministic and fully backtestable on 52k matches.
- Weather is free and backtestable *if* coordinates exist; expected effect ≈ 0 except in severe conditions by design.

**Benefits that cannot be measured retroactively** (lineups, injuries, news): they get **zero or minimal weight**
until forward evidence accumulates from the published picks themselves (`p_base` vs `p_final` vs outcome).

**What I would not claim:** that this materially improves accuracy. The model is already calibrated to ±2 points,
and the literature on context adjustments is mixed. The realistic outcome is "same calibration, better explained,
with a small chance of a real edge in specific conditions" — which is exactly why the plan is phased and gated.

---

## 8. RECOMMENDATION

**Add the research layer, but only as a selected, phased, default-off capability.** Not a rewrite, not a
replacement, and not with numeric weight until evidence exists.

1. **Phase A — collect, store, display (no probability change).** Build `research/` with facts, sources,
   timestamps, quality, and the **base-vs-final** presentation; `RES_CONTEXT_WEIGHT=0` so `p_final == p_base` by
   construction. Ship the ledger columns and the evaluation plumbing. Risk: near zero; benefit: full information
   layer + everything needed to evaluate later.
2. **Phase B — backtest, then enable the provable categories.** Fatigue, motivation, weather through the existing
   harness; enable only what passes (no log-loss/Brier/calibration regression on the test split, and a stated
   improvement on the subset it targets). Caps: 2 pp per factor, 2–4 pp total.
3. **Phase C — forward-test lineups.** Use the pre-match refresh, record `p_base` vs `p_final` on published picks,
   and revisit after a meaningful sample (200+ settled picks) with the settlement machinery already in place.
4. **Do not (yet):** give injuries/suspensions numeric weight (no free structured source, no history), use predicted
   lineups (no source), model travel (no coordinates), or subscribe to anything.

**Verdict on your four options:** *keep unchanged* — no; *add only selected categories* — yes, that is exactly
this plan; *add the full layer with adjustments* — not before the backtests; *wait* — not necessary, because
Phase A carries no model risk and produces the evidence the later phases need.

---

## 9. PHASE-2 DESIGN SKETCH (what implementation would look like)

- **Files:** the `research/` package above (~8 modules, each small and independently testable); edits confined to
  `scanner.py` (one call in `analyse`/`main`), `appdata.py` (payload block), `safe.py`/`accas.py` (ledger columns),
  `verify.py` (context contract), `scanner.py` report section.
- **Data shapes:** fact record, research record, context block (all JSON, all with source + retrieved_at).
- **Rules:** the scoring table in §5.4, conflicts → 0, stale → 0, caps enforced in `context.py` and re-checked in
  `verify.py`.
- **Tests (your §18 list, plus the existing suite):** missing data, stale data, conflicting sources, API failure,
  rate-limit exhaustion, no lineup, predicted-vs-confirmed (structurally impossible — asserted), weather
  unavailable, lower-league gaps, extreme adjustments (clamped), odds-independence, `RESEARCH=0` byte-identical
  output.
- **Backtest:** `research/backtest_context.py` reusing `backtest.py`'s replay + metrics, joining fatigue/motivation
  (and weather where coordinates exist) to the 52k-match frame; train/test gate; per-league and per-market tables;
  published to `backtest/CONTEXT_RESULTS.md` before any weight is enabled.
- **Acceptance criteria before Phase B is switched on:** no market regresses by more than 0.0005 log-loss on the
  test split (the same bar the boost studies used), calibration within ±2 points holds, and the adjustment is
  explainable on every published pick.

---

## 10. DECISIONS I NEED FROM YOU

1. **Phase A now, or review the design first?** (Phase A changes no probability — it only collects, stores and displays.)
2. **Coordinates:** may I build a one-time cached stadium-coordinate map (free geocoding) for the competitions we
   actually publish? Without it there is no weather, and later no travel.
3. **If a Phase-B category passes the backtest, do I enable it, or come back to you with the numbers first?**
4. **Confirm: no paid service** — the free path is the plan, and I will not sign up for anything.

*No code was modified during this audit. The live-feed probes used 15 requests in total to the public endpoints
already in daily use; the state branch was fetched read-only for measurement.*
