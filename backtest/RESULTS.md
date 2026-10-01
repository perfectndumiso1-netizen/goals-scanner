# Backtest results

## 2026-10-01 — boost studies: form 150 d, venue K 40, 60 matches adopted; market-bias evidence; xG pending

Review of Liam Hartley's football-betting-algorithm video surfaced three testable ideas; all were run through
`backtest/boost_studies.py` (52,331 matches; strict gate: select on train ≤ Jun 2025 → confirm on test 25/26–26/27 →
no market may regress by > 0.0005 log-loss). Full tables: [BOOST_RESULTS.md](BOOST_RESULTS.md).

| variant | train mean LL | test mean LL | test O15 | test O25 | test BTTS | test HW | test AW |
|:--|--:|--:|--:|--:|--:|--:|--:|
| base (production until today) | 0.6299 | 0.6276 | 0.5392 | 0.6808 | 0.6841 | 0.6510 | 0.5829 |
| **adopted: HL 150, venue K 40, 60 matches** | **0.6296** | **0.6272** | **0.5389** | **0.6806** | 0.6841 | **0.6503** | **0.5822** |

Decisions:

* **Adopted: form half-life 150 days (was 120), venue blend K 40 (was 20), 60 matches per team (was 40).** Selected on
  train, confirmed on test: every market equal or better, four of five strictly better. Calibration holds — home win
  ≥ 0.60: predicted 0.671 → actual 0.670; Over 1.5 ≥ 0.84: 0.853 → 0.856. Dixon-Coles ρ = −0.05 re-confirmed as the
  train optimum. Evidence-first process: the video's "ML parameter optimization" future plan, executed properly.
* **Market-bias study (display layer only):** on 24,393 priced matches (2023–26), 1X2 outcomes priced 5–20% win less
  than implied (−3.8 / −2.1 / −1.2 pp, same sign in ≥3 seasons) — the classic favorite-longshot / public-money bias;
  Over-2.5 bands 35–40% and 60–65% land more than implied (+2.3 / +2.4 pp). Published on the app's Performance page
  as context; odds still never filter any selection.
* **Model-vs-market snapshot** added to the Performance page (held-out seasons; market leads on 1X2, the model is
  within 0.007 on O2.5 without ever seeing a price).
* **xG ratings — not adopted (yet).** football-data.co.uk publishes HxG/AxG only from season 26/27 (Understat blocks
  scraping), so the honest window is n = 2,408: blend weights 0.3/0.5/0.7/1.0 all land within noise of goals-only
  (mean Δ −0.0002…−0.0003). Re-run `python3 backtest/boost_studies.py --skip-sweep --skip-bias` once 26/27 reaches
  ≥ 3,000 evaluated matches.

## 2026-09-28 — data-first engine: model-only probabilities and two-strength shrinkage

The production model no longer blends market-implied expected goals into its probabilities (data-first engine:
football data → model; bookmaker prices → separate comparison layer). To make the model-only probabilities as good
as possible on their own, `backtest/model_variants.py` replayed 52,253 matches (2022-27, no look-ahead, same data as
below; evaluation from Aug 2023, train ≤ Jun 2025, test = 25/26–26/27) with these football-data-only variants:

| variant (test seasons, n = 14,135)       | O1.5   | O2.5   | BTTS   | Home win | Away win | HW calibration 0.60+ bucket |
|:------------------------------------------|:-------|:-------|:-------|:---------|:---------|:----------------------------|
| base — K=40 shrinkage (old production)    | 0.5399 | 0.6818 | 0.6836 | 0.6640   | 0.5928   | n=56, pred 0.62 → actual 0.86 (badly under-confident) |
| goals capped at 5 per team                | 0.5399 | 0.6820 | 0.6836 | 0.6642   | 0.5929   | same |
| opponent-adjusted ratings (two-pass)      | 0.5400 | 0.6822 | 0.6836 | 0.6641   | 0.5929   | same |
| single K=10                               | 0.5412 | 0.6837 | 0.6861 | 0.6514   | 0.5822   | 0.66 → 0.72 |
| **two-K: strength K=5, tempo K=40**       | **0.5395** | **0.6808** | 0.6842 | **0.6507** | **0.5825** | n=1,762, pred 0.67 → actual 0.67 |
| two-K: strength K=10, tempo K=40          | 0.5398 | 0.6813 | 0.6839 | 0.6515   | 0.5826   | 0.65 → 0.72 |
| two-K K=5/40 + opponent adjustment        | 0.5396 | 0.6810 | 0.6844 | 0.6501   | 0.5821   | 0.67 → 0.67 |
| market (average bookmaker odds), reference | –     | 0.6784 | –      | 0.6231   | 0.5638   | – |

Findings and decisions:

* **Adopted: two-strength shrinkage** (`SHRINK_K_STRENGTH` = 5 for the attack/defence *ratio*, `SHRINK_K` = 40 for the
  goal *tempo*, in log space). A team's strength relative to its opponents is more persistent than its goal tempo, so
  it needs less shrinkage. It improves every market at once — Over 1.5, Over 2.5, home win (0.664 → 0.651) and away
  win (0.593 → 0.583) — and fixes the 1X2 calibration, which matters now that 1X2 is model-only (previously 90 %
  market). BTTS is unchanged within noise.
* **Not adopted: opponent-adjusted ratings.** No measurable gain on any goals market (league normalisation already
  captures most of it) and a 2.5× slower run. Opponent strength is instead *reported* per team (average rating of the
  opponents faced, raw v opponent-adjusted attack/defence) as information in the audit, never as a model input.
* **Not adopted: capping extreme scores.** No effect on accuracy; extreme results stay in the sample and are flagged
  with their effect on the recent averages (audit / Data tab).
* **Honest trade-off:** the pure football-data model remains slightly behind the market on Over 2.5 (0.6808 v 0.6784)
  and clearly behind on the match result (0.651 v 0.623) — the market knows line-ups, injuries and motivation. The
  old market-blended headline probability (0.6788 on O2.5) was marginally more accurate than the model-only one, and
  it was given up on purpose: the probability must be traceable to football data. Market disagreement is shown, not
  used, and (as found in 2026-09-26) it is not a reliable value signal.

Calibration of the adopted model on the test seasons — Over 1.5 ≥ 0.84 bucket: predicted 0.853, actual 0.860
(n = 728); home win 0.50–0.60: 0.545 → 0.524 (n = 2,641); home win ≥ 0.60: 0.671 → 0.670 (n = 1,762).

---

_Generated 2026-09-26 11:50 (the sections below pre-date the data-first engine; 'final probability' there means the old market blend). Parameters: half-life 120 days, shrinkage K=40, venue K=20, Dixon-Coles rho=-0.05, market-xG weight=0.9._

_Generated 2026-09-29 16:38. Parameters: half-life 120 days, shrinkage K=40, venue K=20, Dixon-Coles rho=-0.05, market-xG weight=0.9._

## Model accuracy

Matches with a prediction from Aug 2023: **38,906** (main leagues with odds: 24,285; extra leagues: 14,621)

### Accuracy by model (log-loss, lower = better; Brier in brackets)

| split               | model                      | O15             | O25             | BTTS            |
|:--------------------|:---------------------------|:----------------|:----------------|:----------------|
| test (25/26–26/27)  | League average (no model)  | 0.5473 (0.1807) | 0.6916 (0.2492) | 0.6878 (0.2473) |
| test (25/26–26/27)  | Team hit-rates only        | 0.5462 (0.1800) | 0.6903 (0.2476) | 0.6935 (0.2487) |
| test (25/26–26/27)  | Poisson (current)          | 0.5396 (0.1779) | 0.6819 (0.2444) | 0.6836 (0.2453) |
| test (25/26–26/27)  | Dixon-Coles                | 0.5393 (0.1778) | 0.6819 (0.2444) | 0.6834 (0.2452) |
| test (25/26–26/27)  | Market odds only (O2.5)    | –               | 0.6784 (0.2428) | –               |
| test (25/26–26/27)  | Current blend 60/40 (O2.5) | –               | 0.6821 (0.2446) | –               |
| test (25/26–26/27)  | Market-xG blend            | 0.5393 (0.1781) | 0.6788 (0.2429) | 0.6844 (0.2456) |
| train (23/24–24/25) | League average (no model)  | 0.5616 (0.1872) | 0.6928 (0.2498) | 0.6909 (0.2489) |
| train (23/24–24/25) | Team hit-rates only        | 0.5625 (0.1870) | 0.6893 (0.2476) | 0.6949 (0.2506) |
| train (23/24–24/25) | Poisson (current)          | 0.5540 (0.1843) | 0.6829 (0.2449) | 0.6873 (0.2471) |
| train (23/24–24/25) | Dixon-Coles                | 0.5539 (0.1843) | 0.6829 (0.2449) | 0.6875 (0.2472) |
| train (23/24–24/25) | Market odds only (O2.5)    | –               | 0.6757 (0.2414) | –               |
| train (23/24–24/25) | Current blend 60/40 (O2.5) | –               | 0.6800 (0.2435) | –               |
| train (23/24–24/25) | Market-xG blend            | 0.5412 (0.1791) | 0.6761 (0.2416) | 0.6844 (0.2457) |

### Calibration — Over 2.5, test seasons

**Poisson model alone**

| bucket    |    n | predicted   | actual   | gap    |
|:----------|-----:|:------------|:---------|:-------|
| 0.00–0.40 |  797 | 34.0%       | 37.1%    | +3.2%  |
| 0.40–0.45 | 1807 | 43.1%       | 45.5%    | +2.4%  |
| 0.45–0.50 | 4001 | 47.6%       | 49.2%    | +1.6%  |
| 0.50–0.55 | 3808 | 52.4%       | 54.3%    | +1.9%  |
| 0.55–0.60 | 2652 | 57.2%       | 57.9%    | +0.7%  |
| 0.60–0.65 | 1226 | 62.0%       | 63.9%    | +2.0%  |
| 0.65–0.70 |  235 | 66.7%       | 77.4%    | +10.7% |
| 0.70–0.75 |   19 | 71.3%       | 89.5%    | +18.1% |

**Current final (60% model / 40% market where odds exist)**

| bucket    |    n | predicted   | actual   | gap    |
|:----------|-----:|:------------|:---------|:-------|
| 0.00–0.40 |  831 | 34.2%       | 36.7%    | +2.5%  |
| 0.40–0.45 | 1793 | 43.1%       | 44.2%    | +1.1%  |
| 0.45–0.50 | 3829 | 47.6%       | 48.2%    | +0.5%  |
| 0.50–0.55 | 3718 | 52.4%       | 54.2%    | +1.8%  |
| 0.55–0.60 | 2738 | 57.3%       | 59.5%    | +2.2%  |
| 0.60–0.65 | 1333 | 62.0%       | 64.2%    | +2.2%  |
| 0.65–0.70 |  265 | 66.9%       | 75.1%    | +8.2%  |
| 0.70–0.75 |   35 | 71.8%       | 88.6%    | +16.7% |
| 0.75–0.80 |    3 | 76.8%       | 100.0%   | +23.2% |

**BTTS (Poisson)**

| bucket    |    n | predicted   | actual   | gap    |
|:----------|-----:|:------------|:---------|:-------|
| 0.00–0.45 |  728 | 40.1%       | 44.1%    | +4.0%  |
| 0.45–0.50 | 2226 | 48.3%       | 50.6%    | +2.3%  |
| 0.50–0.55 | 5281 | 52.6%       | 53.6%    | +1.0%  |
| 0.55–0.60 | 4161 | 57.3%       | 57.4%    | +0.1%  |
| 0.60–0.65 | 1893 | 62.0%       | 62.5%    | +0.5%  |
| 0.65–0.70 |  252 | 66.5%       | 68.3%    | +1.8%  |
| 0.70–1.00 |    4 | 70.7%       | 100.0%   | +29.3% |

**Over 1.5 (Poisson)**

| bucket    |    n | predicted   | actual   | gap   |
|:----------|-----:|:------------|:---------|:------|
| 0.00–0.70 | 2055 | 65.7%       | 67.1%    | +1.5% |
| 0.70–0.75 | 4918 | 72.7%       | 73.6%    | +0.9% |
| 0.75–0.80 | 5009 | 77.4%       | 78.9%    | +1.6% |
| 0.80–0.84 | 2157 | 81.7%       | 82.8%    | +1.1% |
| 0.84–0.88 |  392 | 85.2%       | 89.5%    | +4.3% |
| 0.88–0.92 |   14 | 88.5%       | 92.9%    | +4.4% |

## Shortlist simulation (current rules, top-15 per day)

### Poisson only

| market   | split   |   picks |   per_day | hit_rate   | avg_pred   | avg_odds   | roi_open   | roi_close   |
|:---------|:--------|--------:|----------:|:-----------|:-----------|:-----------|:-----------|:------------|
| O15      | test    |     390 |      2.55 | 89.2%      | 85.3%      | –          | –          | –           |
| O15      | train   |     458 |      2.11 | 88.9%      | 85.1%      | –          | –          | –           |
| O25      | test    |    1350 |      5.27 | 65.9%      | 63.0%      | 1.46       | -7.4%      | -8.2%       |
| O25      | train   |    1965 |      4.91 | 64.3%      | 62.6%      | 1.51       | -4.3%      | -4.2%       |
| BTTS     | test    |    1036 |      4.65 | 63.0%      | 64.1%      | –          | –          | –           |
| BTTS     | train   |    1377 |      3.91 | 63.3%      | 63.7%      | –          | –          | –           |

### Current production (60/40 market blend for O2.5)

| market   | split   |   picks |   per_day | hit_rate   | avg_pred   | avg_odds   | roi_open   | roi_close   |
|:---------|:--------|--------:|----------:|:-----------|:-----------|:-----------|:-----------|:------------|
| O15      | test    |     390 |      2.55 | 89.2%      | 85.3%      | –          | –          | –           |
| O15      | train   |     458 |      2.11 | 88.9%      | 85.1%      | –          | –          | –           |
| O25      | test    |    1444 |      5.45 | 66.6%      | 63.3%      | 1.41       | -8.1%      | -8.7%       |
| O25      | train   |    2064 |      5.07 | 67.0%      | 63.1%      | 1.45       | -2.4%      | -2.5%       |
| BTTS     | test    |    1036 |      4.65 | 63.0%      | 64.1%      | –          | –          | –           |
| BTTS     | train   |    1377 |      3.91 | 63.3%      | 63.7%      | –          | –          | –           |

### Candidate: Dixon-Coles + market-xG blend

| market   | split   |   picks |   per_day | hit_rate   | avg_pred   | avg_odds   | roi_open   | roi_close   |
|:---------|:--------|--------:|----------:|:-----------|:-----------|:-----------|:-----------|:------------|
| O15      | test    |     860 |      3.98 | 87.4%      | 86.1%      | –          | –          | –           |
| O15      | train   |    1203 |      3.68 | 87.9%      | 86.3%      | –          | –          | –           |
| O25      | test    |    1622 |      5.86 | 67.3%      | 64.3%      | 1.42       | -5.2%      | -5.6%       |
| O25      | train   |    2346 |      5.51 | 67.3%      | 64.4%      | 1.45       | -1.7%      | -1.9%       |
| BTTS     | test    |    1135 |      4.77 | 63.5%      | 64.3%      | –          | –          | –           |
| BTTS     | train   |    1197 |      3.55 | 65.4%      | 64.0%      | –          | –          | –           |

## Shortlist simulation — production v2 rules (final probability, no team-form floors)

| market   | split               |   picks |   per day | hit rate   | predicted   | ⭐⭐ hit rate   | ⭐⭐⭐ hit rate   | ROI @ open odds   |
|:---------|:--------------------|--------:|----------:|:-----------|:------------|:----------------|:------------------|:------------------|
| O15      | test (25/26–26/27)  |     903 |       4.1 | 87.4%      | 86.0%       | 88.3% (n=223)   | 94.7% (n=38)      | –                 |
| O15      | train (23/24–24/25) |    1285 |       3.8 | 88.1%      | 86.3%       | 90.8% (n=382)   | 93.8% (n=81)      | –                 |
| O25      | test (25/26–26/27)  |    1675 |       6   | 67.3%      | 64.3%       | 70.9% (n=704)   | 77.0% (n=239)     | -5.4%             |
| O25      | train (23/24–24/25) |    2454 |       5.7 | 67.2%      | 64.4%       | 70.8% (n=1046)  | 73.8% (n=400)     | -2.1%             |
| BTTS     | test (25/26–26/27)  |    1831 |       6.3 | 63.5%      | 63.1%       | 64.5% (n=816)   | 71.4% (n=192)     | –                 |
| BTTS     | train (23/24–24/25) |    2379 |       5.4 | 63.5%      | 62.5%       | 67.2% (n=787)   | 69.1% (n=136)     | –                 |

_The ROI line is a reality check, not a promise: shortlisting by probability means backing short-priced favourites, and the bookmaker margin (~5%) is not overcome on average._

## Threshold curves (production v2 final probability)

**Over 2.5**

| threshold   | split   |   picks |   per day | hit rate   | predicted   |   avg odds | ROI open   | ROI close   |
|:------------|:--------|--------:|----------:|:-----------|:------------|-----------:|:-----------|:------------|
| ≥55%        | train   |    4185 |       7.7 | 64.1%      | 61.6%       |       1.51 | -3.3%      | -3.6%       |
| ≥55%        | test    |    2669 |       7.9 | 64.1%      | 61.8%       |       1.49 | -5.2%      | -5.5%       |
| ≥58%        | train   |    3429 |       7   | 65.5%      | 62.8%       |       1.48 | -2.9%      | -3.2%       |
| ≥58%        | test    |    2163 |       6.8 | 66.0%      | 63.1%       |       1.45 | -5.3%      | -5.6%       |
| ≥60%        | train   |    2454 |       5.7 | 67.2%      | 64.4%       |       1.45 | -2.1%      | -2.4%       |
| ≥60%        | test    |    1675 |       6   | 67.3%      | 64.3%       |       1.42 | -5.4%      | -5.8%       |
| ≥63%        | train   |    1476 |       4.2 | 69.9%      | 66.6%       |       1.4  | -1.9%      | -2.2%       |
| ≥63%        | test    |    1032 |       4.4 | 68.3%      | 66.1%       |       1.38 | -6.4%      | -6.8%       |
| ≥65%        | train   |     829 |       2.9 | 71.9%      | 68.9%       |       1.35 | -2.6%      | -2.9%       |
| ≥65%        | test    |     537 |       3.2 | 72.4%      | 68.4%       |       1.34 | -4.5%      | -4.8%       |
| ≥68%        | train   |     437 |       2.2 | 74.1%      | 71.3%       |       1.31 | -2.7%      | -3.2%       |
| ≥68%        | test    |     279 |       2.2 | 76.3%      | 70.6%       |       1.3  | -3.8%      | -3.5%       |
| ≥70%        | train   |     246 |       1.6 | 76.0%      | 73.2%       |       1.27 | -3.4%      | -3.6%       |
| ≥70%        | test    |     126 |       1.6 | 83.3%      | 73.0%       |       1.26 | +4.3%      | +4.2%       |
| ≥73%        | train   |     118 |       1.4 | 79.7%      | 75.6%       |       1.23 | -2.4%      | -2.8%       |
| ≥73%        | test    |      54 |       1.2 | 88.9%      | 75.7%       |       1.22 | +8.3%      | +8.0%       |
| ≥75%        | train   |      65 |       1.3 | 84.6%      | 77.2%       |       1.2  | +1.5%      | +1.2%       |
| ≥75%        | test    |      26 |       1   | 96.2%      | 77.8%       |       1.19 | +14.3%     | +13.3%      |

**BTTS**

| threshold   | split   |   picks |   per day | hit rate   | predicted   |
|:------------|:--------|--------:|----------:|:-----------|:------------|
| ≥55%        | train   |    4838 |       8.5 | 60.8%      | 60.1%       |
| ≥55%        | test    |    3030 |       8.6 | 62.0%      | 60.9%       |
| ≥58%        | train   |    3758 |       7.2 | 62.1%      | 61.1%       |
| ≥58%        | test    |    2486 |       7.6 | 62.6%      | 62.0%       |
| ≥60%        | train   |    2379 |       5.4 | 63.5%      | 62.5%       |
| ≥60%        | test    |    1831 |       6.3 | 63.5%      | 63.1%       |
| ≥63%        | train   |     997 |       3.2 | 66.7%      | 64.4%       |
| ≥63%        | test    |     993 |       4.4 | 63.6%      | 64.6%       |
| ≥65%        | train   |     273 |       1.8 | 68.9%      | 66.6%       |
| ≥65%        | test    |     339 |       2.4 | 66.7%      | 66.7%       |
| ≥68%        | train   |      61 |       1.4 | 63.9%      | 69.0%       |
| ≥68%        | test    |      76 |       1.6 | 69.7%      | 69.1%       |
| ≥70%        | train   |      13 |       1.2 | 23.1%      | 71.3%       |
| ≥70%        | test    |      19 |       1.4 | 78.9%      | 70.8%       |
| ≥73%        | train   |       2 |       1   | 50.0%      | 74.1%       |
| ≥73%        | test    |       1 |       1   | 100.0%     | 72.8%       |
| ≥75%        | train   |       0 |       0   | nan%       | nan%        |
| ≥75%        | test    |       0 |       0   | nan%       | nan%        |

**Over 1.5**

| threshold   | split   |   picks |   per day | hit rate   | predicted   |
|:------------|:--------|--------:|----------:|:-----------|:------------|
| ≥78%        | train   |    4555 |       8.1 | 83.5%      | 82.7%       |
| ≥78%        | test    |    2869 |       8.2 | 84.1%      | 82.8%       |
| ≥80%        | train   |    3662 |       7.3 | 84.5%      | 83.5%       |
| ≥80%        | test    |    2315 |       7.1 | 85.1%      | 83.7%       |
| ≥82%        | train   |    2531 |       5.8 | 85.4%      | 84.6%       |
| ≥82%        | test    |    1726 |       6.1 | 86.0%      | 84.6%       |
| ≥84%        | train   |    1285 |       3.8 | 88.1%      | 86.3%       |
| ≥84%        | test    |     903 |       4.1 | 87.4%      | 86.0%       |
| ≥86%        | train   |     567 |       2.4 | 88.7%      | 88.0%       |
| ≥86%        | test    |     363 |       2.6 | 90.6%      | 87.8%       |
| ≥88%        | train   |     238 |       1.6 | 91.2%      | 89.6%       |
| ≥88%        | test    |     122 |       1.6 | 91.8%      | 89.6%       |
| ≥90%        | train   |      81 |       1.3 | 93.8%      | 91.3%       |
| ≥90%        | test    |      38 |       1.2 | 94.7%      | 91.4%       |
| ≥92%        | train   |      15 |       1.1 | 100.0%     | 92.9%       |
| ≥92%        | test    |      10 |       1.1 | 100.0%     | 93.2%       |
| ≥94%        | train   |       0 |       0   | nan%       | nan%        |
| ≥94%        | test    |       3 |       1   | 100.0%     | 94.7%       |

## By league — Over 2.5 (production v2 final probability, all evaluation seasons)

| league                                  |   matches | O2.5 rate   |   log-loss |   picks | pick hit rate   | pick predicted   | gap   |
|:----------------------------------------|----------:|:------------|-----------:|--------:|:----------------|:-----------------|:------|
| Argentina · Liga Profesional            |      1288 | 33%         |     0.6344 |       0 | –               | –                | –     |
| Germany · Bundesliga                    |       954 | 63%         |     0.641  |     476 | 72%             | 66%              | +6%   |
| Netherlands · Eredivisie                |       970 | 61%         |     0.6525 |     425 | 69%             | 66%              | +3%   |
| Argentina · Copa De La Liga Profesional |       405 | 38%         |     0.6602 |       0 | –               | –                | –     |
| Spain · La Liga                         |      1209 | 49%         |     0.6625 |     157 | 71%             | 66%              | +5%   |
| Switzerland · Super League              |       724 | 60%         |     0.6651 |     227 | 68%             | 63%              | +5%   |
| USA · MLS                               |      1634 | 60%         |     0.6681 |     474 | 68%             | 63%              | +5%   |
| Portugal · Primeira Liga                |       971 | 53%         |     0.6686 |     127 | 72%             | 64%              | +7%   |
| Norway · Eliteserien                    |       754 | 60%         |     0.6696 |     177 | 71%             | 62%              | +9%   |
| England · Premier League                |      1190 | 58%         |     0.6712 |     425 | 63%             | 65%              | -2%   |
| Turkey · Süper Lig                      |      1071 | 53%         |     0.6719 |     203 | 72%             | 65%              | +8%   |
| China · Super League                    |       770 | 59%         |     0.672  |     262 | 64%             | 63%              | +1%   |
| Germany · 2. Bundesliga                 |       956 | 60%         |     0.6721 |     332 | 64%             | 63%              | +1%   |
| Spain · Segunda División                |      1436 | 45%         |     0.6749 |      20 | 55%             | 62%              | -7%   |
| Scotland · Premiership                  |       726 | 56%         |     0.6766 |     148 | 65%             | 65%              | +0%   |
| France · Ligue 1                        |       963 | 54%         |     0.6769 |     177 | 67%             | 64%              | +2%   |
| Scotland · League One                   |       578 | 55%         |     0.6785 |      62 | 71%             | 65%              | +6%   |
| England · National League               |      1749 | 55%         |     0.6798 |     219 | 63%             | 63%              | -0%   |
| Finland · Veikkausliiga                 |       554 | 59%         |     0.6811 |      86 | 65%             | 63%              | +2%   |
| Denmark · Superliga                     |       613 | 58%         |     0.6814 |     134 | 60%             | 62%              | -2%   |
| England · League One                    |      1739 | 51%         |     0.6829 |      35 | 66%             | 62%              | +4%   |
| Belgium · Pro League                    |       983 | 53%         |     0.6833 |     137 | 69%             | 63%              | +6%   |
| France · Ligue 2                        |      1044 | 47%         |     0.6839 |       9 | 100%            | 63%              | +37%  |
| England · Championship                  |      1751 | 50%         |     0.6845 |      48 | 65%             | 63%              | +2%   |
| Romania · Superliga                     |      1001 | 45%         |     0.6848 |       0 | –               | –                | –     |
| Scotland · Championship                 |       575 | 48%         |     0.6853 |      11 | 64%             | 63%              | +1%   |
| England · League Two                    |      1740 | 50%         |     0.6858 |      50 | 66%             | 62%              | +4%   |
| Italy · Serie A                         |      1190 | 48%         |     0.6862 |      41 | 54%             | 63%              | -9%   |
| Sweden · Allsvenskan                    |       753 | 54%         |     0.6863 |      62 | 63%             | 62%              | +1%   |
| Ireland · Premier Division              |       571 | 46%         |     0.687  |       1 | 0%              | 60%              | -60%  |
| Mexico · Liga MX                        |      1068 | 55%         |     0.6874 |      37 | 57%             | 62%              | -5%   |
| Greece · Super League                   |       737 | 52%         |     0.6874 |      45 | 71%             | 63%              | +8%   |
| Poland · Ekstraklasa                    |       971 | 51%         |     0.6892 |      10 | 80%             | 61%              | +19%  |
| Russia · Premier League                 |       717 | 48%         |     0.6893 |       8 | 38%             | 61%              | -23%  |
| Scotland · League Two                   |       578 | 51%         |     0.6902 |      26 | 65%             | 62%              | +3%   |
| Japan · J1 League                       |       948 | 47%         |     0.691  |       1 | 0%              | 62%              | -62%  |
| Brazil · Serie A                        |      1238 | 47%         |     0.6911 |       0 | –               | –                | –     |
| Italy · Serie B                         |      1175 | 48%         |     0.6913 |       6 | 67%             | 62%              | +4%   |
| Austria · Bundesliga                    |       612 | 51%         |     0.6977 |       2 | 0%              | 61%              | -61%  |
