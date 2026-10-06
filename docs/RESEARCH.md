# Live research & context layer

*Phase A of the "Live Research & Context Intelligence" upgrade — collect, store, display; **the published
probability is still exactly the statistical model's**.*

The statistical engine stays the foundation. This layer adds structured, attributed, bounded *current football
information* about a fixture — availability, line-ups, team news, motivation/match context, fatigue/scheduling
and weather — and, only when a rule is explicitly enabled, translates a small number of those facts into a
capped adjustment of the goals expectation before the final probability is published.

Read `RESEARCH_AUDIT.md` (this folder) for the audit that preceded it: what the system was, which sources are
free and reliable, what the risks are, and the phase plan this implementation follows.

---

## 1. The contract

```
p_base   = probs_from_matrix(score_matrix(λh, λa))          ← the statistical model, unchanged, always stored
λh'      = λh × Π(context factors)   λa' = λa × Π(factors)   ← bounded, rule-based, explainable
p_final  = probs_from_matrix(score_matrix(λh', λa'))         ← what gets published (== p_base unless enabled)
```

* **The model is never modified.** `analyse()` produces `p_model` exactly as before; `MatchRow.mod_h/mod_a` and
  `p_model` keep their meaning. A context adjustment re-runs the *existing* `score_matrix()` /
  `probs_from_matrix()` on the adjusted rates (see `scanner.research_apply`), so 1X2, double chance, team goals,
  BTTS and the totals stay internally consistent (P(O1.5) ≥ P(O2.5), 1X2 summing to 1, …).
* **Odds are never an input.** There is no bookmaker/Sportybet field anywhere in `research/`; a test parses the
  package's AST and fails if one appears (`tests/test_research.py`).
* **Every fact carries provenance**: source, retrieval time (UTC), information time, confidence tier, and
  whether it is first-party (`verified`). Unavailable is written as `N/A`, never estimated.
* **Facts and interpretation are separate.** Facts live in `Fact` records; the interpretation lives in `Rule`
  records that name the facts they used, the weight, the reason and the resulting percentage points.
* **Weak, stale or contradictory evidence ⇒ adjustment 0**, by rule, and the record says so.

## 2. Where it runs

The layer is staged by cost, never applied to the whole sweep:

| Stage | Scope | What happens |
|:--|:--|:--|
| 1 — screening | all fixtures (~17k, 60 days) | unchanged statistical analysis only |
| 2 — research | fixtures within `RES_HORIZON_H` (default 30 h, i.e. the published window and the next few hours), capped by `RES_MAX_FIXTURES` (400) | facts collected: fatigue, motivation, line-ups (if published), team news, weather; quality graded; record stored |
| 3 — pre-match refresh | the same fixtures as the half-hourly runs approach kick-off | line-ups appear ~1 h before kick-off; the record and the probabilities are recomputed then |
| 4 — evaluation | published picks | `p_base` vs `p_final` vs outcome feed the context-failure categories in `backtest/error_analysis.py` |

## 3. Sources (all free, all already reachable)

| Category | Source | Notes |
|:--|:--|:--|
| Confirmed line-ups | Livescore public feed `/lineups/soccer/<eid>` | published close to kick-off; empty for many competitions ⇒ recorded as "not published", graded down, never guessed. **No predicted line-up exists in this system.** |
| Team news | the scanner's existing Google News cache (`news.py`) | shared cache + shared request budget ⇒ one lookup per team per run, no duplicate requests. Headlines are stored verbatim with outlet, link and publication time; an availability signal is tagged but never "verified". |
| Fatigue / scheduling | our own results archive | days since the last match, matches in the last 7/14 days — calendar days, deterministic, fully backtestable |
| Motivation / context | our own archive + the feed's competition format | **facts only in Phase A** (format, matches already archived). Stakes (title / relegation / qualification / rotation) are *not* asserted until the points model is backtested. |
| Weather | Open-Meteo (CC-BY 4.0) + cached OSM geocoding | forecasts only inside `RES_WEATHER_HORIZON_H`; severe conditions only (wind ≥ 45 km/h, rain ≥ 4 mm/h, ≥ 34 °C, ≤ 1 °C, storms/snow). **Normal weather is zero by rule.** |

Cost: **zero.** No subscription, no key, no paid tier. Request volume is bounded by TTL caches
(`data/research/lineups_cache.json`, `weather_cache.json`, `venues.json`) and per-run budgets — a geocode is
paid once per venue, a forecast once per venue-hour per TTL.

## 4. Configuration (env, all optional)

| Variable | Default | Meaning |
|:--|:--|:--|
| `RESEARCH` | `1` | collect, store and display researched facts |
| `RESEARCH_ADJUST` | `0` | master switch for adjusting λ at all |
| `RES_W_LINEUP`, `RES_W_FATIGUE`, `RES_W_MOTIVATION`, `RES_W_WEATHER` | `0.0` | per-category weights (the Phase-B gate) |
| `RES_MAX_ADJ_PP` | `2.0` | hard ceiling on any published market (percentage points) |
| `RES_MAX_LAMBDA_PCT` | `6.0` | hard ceiling on the combined λ move |
| `RES_HORIZON_H` | `30` | research window from now |
| `RES_MAX_FIXTURES` | `400` | hard cap per run |
| `RES_LINEUP_LEAD_MIN` | `120` | when the feed starts publishing XIs |
| `RES_WEATHER_HORIZON_H` | `48` | forecast horizon |
| `RES_TTL_H` | `6` | forecast/news cache TTL |
| `RES_KEEP_DAYS` | `7` | record retention |
| `RES_MAX_RECORDS` / `RES_STORE_MB` | `2000` / `8.0` | store limits (oldest first; the run log says when one bites) |
| `RES_NEWS_SHARE` | `0.4` | share of the news request budget research may spend (the app's News tab keeps the rest, both share one cache) |
| `RES_BUDGET_LINEUPS` / `RES_BUDGET_WEATHER` / `RES_BUDGET_GEOCODES` | `60` / `60` / `8` | per-run request budgets |

**Phase gate.** With the shipped defaults every rule proposes exactly `0.0` and the published probability is
identical to the statistical model — no matter what the facts say. Raising `RESEARCH_ADJUST=1` alone changes
nothing; a category weight has to be raised too, and only after the backtest supports it (§5).

## 5. Before any weight is enabled (Phase B)

1. `backtest/research_context.py` measures each category on the 52,331-match frame with the existing train/test
   gate (select on train ≤ Jun-2025, confirm on 25/26–26/27). Fatigue and motivation are reconstructible
   historically; weather is reconstructible where a venue map exists; line-ups/injuries are **not** — they cannot
   be backtested retrospectively and must earn their way in prospectively from published picks.
2. A category is enabled only if it does not degrade log-loss/Brier/calibration on the test split (the same bar
   as the boost studies, ≤ 0.0005 log-loss regression) and improves the subset it targets.
3. Results are published to `backtest/CONTEXT_RESULTS.md` **before** the weight is raised.

## 6. Quality grades (separate from data quality)

`HIGH · MEDIUM · LOW · INSUFFICIENT` per fixture, computed from what we hold (categories covered, first-party
source present, freshness, source agreement) and the competition's structural coverage — derived from how much
real match statistics the archive carries for those teams (`research_support()`). Competitions the feed does not
publish into can never grade HIGH: they are capped at LOW. Gap facts ("N/A — the feed has not published
line-ups") are shown but never count as evidence. **Research quality never feeds the probability.**

## 7. What is stored

`data/research/records.json` — one record per researched fixture: facts (with source, both timestamps,
confidence, staleness), conflicts (`source_a`, `source_b`, resolution, impact), per-category rule outcomes with
the percentage points each would contribute, base vs final probabilities, totals (λ %, worst pp, whether it was
capped) and the quality reasons.

The store is deliberately bounded — it is force-pushed with the state every 30 minutes, so it is pruned by age
(`RES_KEEP_DAYS`), by count (`RES_MAX_RECORDS`), and by size (`RES_STORE_MB`), oldest first, and a record that is
more than two days old has its bulky rule payloads (line-up name lists, structured values) dropped while its
evidence — fact text, source, both timestamps, confidence — is kept. The base-vs-final numbers for every
*published* pick live in `data/tracker.csv` and `data/safe_bets.csv`, which are small and permanent.

The app/detail payload gains one `context` block (base, final, quality, reasons, adjustments, conflicts, facts)
and the report prints a compact line per dossier:

```
BASE (statistical model) O2.5 67% · BTTS 63% · LIVE CONTEXT no adjustment — rest is adequate (9 day(s))
      · FINAL = BASE (O2.5 67%) · RESEARCH QUALITY MEDIUM
```

## 8. Publication gate

`verify.py` keeps blocking a silent blend: a published probability may differ from the statistical model **only**
through a context adjustment that the detail file *declares* (`context.totals.adjust_enabled`, `max_pp`,
`lam_pct_h/a`) and only within that declared size. An undeclared delta — the shape a bookmaker-odds leak would
take — is still a hard error that blocks the publication (`verify.context_budget`, covered by tests).

## 9. Tests

`tests/test_research.py` — 40 tests: missing data, stale data, conflicting sources, API failure, rate-limit and
budget exhaustion, no line-up published, predicted-vs-confirmed (structurally impossible), weather unavailable,
lower-league gaps, extreme adjustments (all three ceilings), odds-independence (AST guard), the publication
contract, naive/aware clock regressions, and "Phase A cannot move a probability".

## 10. Deliberately not done (yet)

* No numeric weight for injuries/suspensions: there is no free structured source and **no historical archive**,
  so it cannot be backtested retrospectively — it must be earned prospectively.
* No predicted line-ups: there is no source, and inventing one is forbidden by the accuracy rule.
* No travel/fatigue from travel: needs a full venue map (started, for weather) and travel modelling.
* No paid dependency: none is needed for the categories above.
