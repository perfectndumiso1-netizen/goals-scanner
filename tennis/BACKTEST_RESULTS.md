# Tennis engine — walk-forward backtest

Data: Jeff Sackmann's ATP (main tour + qualifying/Challengers) and WTA match files, archive snapshot June 2026 (288,040 matches 2005-01-03 → 2026-06-01). Replay in chronological order; every prediction uses only earlier matches. Training period 2012-01-01…2018-12-31 for parameter choice, evaluation 2019-01-01…2026-06-01. 'Rated' = both players had ≥ 10 earlier matches in the data.

## 1. Parameter selection (training period, rated matches, log loss — lower is better)

| K | shape | surface weight | log loss | accuracy | n |
| --- | --- | --- | --- | --- | --- |
| 150 | 0.3 | 0.5 | 0.6141 | 65.8% | 81,108 |
| 100 | 0.3 | 0.5 | 0.6142 | 65.8% | 81,108 |
| 150 | 0.3 | 0.25 | 0.6145 | 65.7% | 81,108 |
| 250 | 0.4 | 0.5 | 0.6150 | 65.8% | 81,108 |
| 200 | 0.3 | 0.5 | 0.6170 | 65.6% | 81,108 |
| 150 | 0.3 | 0.75 | 0.6174 | 65.6% | 81,108 |
| 150 | 0.3 | 0.0 | 0.6185 | 65.4% | 81,108 |
| 150 | 0.2 | 0.5 | 0.6199 | 65.7% | 81,108 |
| 150 | 0.3 | 1.0 | 0.6244 | 64.9% | 81,108 |

Chosen: K = 150, shape = 0.3 (K schedule K/(matches+5)^shape), surface weight = 0.5.

Logistic scale of the rating difference (training period):

| scale | log loss | accuracy | n |
| --- | --- | --- | --- |
| 400.0 | 0.6141 | 65.8% | 81,108 |
| 450.0 | 0.6137 | 65.9% | 81,108 |
| 500.0 | 0.6136 | 65.8% | 81,108 |

Chosen scale: 500.

## 2. Evaluation period (out of sample)

| Subset | n | accuracy | Brier | log loss |
| --- | --- | --- | --- | --- |
| All matches (incl. players with little history) | 107,226 | 64.3% | 0.2194 | 0.6280 |
| Rated (both players ≥ 10 earlier matches) | 94,519 | 63.8% | 0.2214 | 0.6324 |
| Reference: better-ranked player wins (official ranking, rated subset with ranks) | 93,657 | 61.6% | — | — |
| Reference: coin flip |  | 50.0% | 0.2500 | 0.6931 |

## 3. Calibration (evaluation period, rated matches, favourite's probability)

| Probability bucket | Predictions | Mean predicted | Actual win rate | Gap (pp) |
| --- | --- | --- | --- | --- |
| 50-55% | 18,790 | 52.5% | 52.1% | -0.4 |
| 55-60% | 17,658 | 57.5% | 57.4% | -0.1 |
| 60-65% | 15,968 | 62.4% | 60.5% | -1.9 |
| 65-70% | 13,498 | 67.4% | 66.1% | -1.3 |
| 70-75% | 10,832 | 72.4% | 70.7% | -1.7 |
| 75-80% | 7,924 | 77.3% | 74.9% | -2.4 |
| 80-85% | 5,157 | 82.3% | 79.3% | -3.0 |
| 85-90% | 2,987 | 87.2% | 85.2% | -2.0 |
| 90-95% | 1,352 | 92.2% | 91.5% | -0.7 |
| 95-100% | 353 | 96.8% | 96.0% | -0.7 |

## 4. Breakdowns (evaluation period, rated matches)

### By surface

| surface | n | accuracy | Brier | log loss |
| --- | --- | --- | --- | --- |
| Hard | 50,872 | 64.2% | 0.2204 | 0.6301 |
| Clay | 37,984 | 63.3% | 0.2229 | 0.6359 |
| Grass | 5,495 | 64.2% | 0.2197 | 0.6285 |

### By tour

| tour | n | accuracy | Brier | log loss |
| --- | --- | --- | --- | --- |
| atp | 78,521 | 63.6% | 0.2220 | 0.6337 |
| wta | 15,998 | 64.7% | 0.2184 | 0.6258 |

### By format

| best_of | n | accuracy | Brier | log loss |
| --- | --- | --- | --- | --- |
| 3 | 90,765 | 63.5% | 0.2230 | 0.6362 |
| 5 | 3,754 | 71.4% | 0.1832 | 0.5411 |

### By level (G slam, M masters, A tour, PM/P/I WTA 1000/500/250, C challenger, D team)

| level | n | accuracy | Brier | log loss |
| --- | --- | --- | --- | --- |
| 50+H | 9 | 55.6% | 0.2517 | 0.6963 |
| A | 14,364 | 64.7% | 0.2175 | 0.6239 |
| C | 50,408 | 62.7% | 0.2263 | 0.6439 |
| D | 1,575 | 68.5% | 0.2014 | 0.5842 |
| F | 270 | 57.4% | 0.2338 | 0.6569 |
| G | 9,918 | 67.9% | 0.2020 | 0.5866 |
| I | 4,644 | 61.5% | 0.2305 | 0.6524 |
| M | 5,945 | 64.0% | 0.2216 | 0.6328 |
| O | 191 | 67.0% | 0.2014 | 0.5804 |
| P | 4,322 | 64.8% | 0.2219 | 0.6342 |
| PM | 2,626 | 65.1% | 0.2170 | 0.6229 |
| W | 247 | 68.4% | 0.2094 | 0.6077 |

### Best-of-5 format handling

| Variant | n | accuracy | Brier | log loss |
| --- | --- | --- | --- | --- |
| Set-level mapping: bo5 probability derived from the set probability (used) | 3,754 | 71.4% | 0.1832 | 0.5411 |
| No format adjustment (bo5 treated as bo3) | 3,754 | 71.4% | 0.1841 | 0.5444 |

## 5. Game markets (Markov chain pinned to the Elo probability; random sample of evaluation matches, rated players, no retirements)

An independent-points chain with fixed serve probabilities makes matches too long: real matches are more lopsided on the day than the players' average levels suggest. The game model therefore treats the serve-point difference on the day as Normal(d0, σ) (5-point Gauss-Hermite mixture, d0 solved so the mixture reproduces the rating probability). σ is the only fitted quantity: chosen per tour on the *training* period by matching the mean total games (bias closest to zero), then applied unchanged below.

| tour | bias σ=0.0 | bias σ=0.08 | bias σ=0.1 | bias σ=0.12 | chosen σ |
| --- | --- | --- | --- | --- | --- |
| atp | +2.01 (n=605) | +0.19 (n=605) | -0.46 (n=605) | -1.08 (n=605) | 0.08 |
| wta | +2.47 (n=164) | +0.72 (n=164) | +0.10 (n=164) | -0.48 (n=164) | 0.1 |

Sample: 2,205 matches; serve/return traits available for both players in 100% of them (tour/surface baseline used otherwise).

| Quantity | Value |
| --- | --- |
| Mean expected total games | 23.37 |
| Mean actual total games | 23.09 |
| Mean absolute error of expected total | 4.97 |
| Over model median line — accuracy / Brier / log loss | 54.7% / 0.2479 / 0.6888 |
| Over 22.5 (best-of-3) — accuracy / Brier / log loss | 58.6% / 0.2409 / 0.6746 |
| Favourite's games over the model median (ex ante) — accuracy / Brier / log loss | 59.3% / 0.2399 / 0.6726 |
| Favourite covers the model's median game handicap (ex ante) — accuracy / Brier / log loss | 55.9% / 0.2453 / 0.6837 |

By tour / format (expected vs actual mean total games):

| Group | n | expected | actual |
| --- | --- | --- | --- |
| tour atp | 1831 | 23.75 | 23.33 |
| tour wta | 374 | 21.54 | 21.90 |
| best-of-3 | 2127 | 22.89 | 22.62 |
| best-of-5 | 78 | 36.49 | 35.87 |

Calibration of P(over 22.5 games), best-of-3:

| Bucket | n | predicted | actual |
| --- | --- | --- | --- |
| 0-30% | 83 | 25.1% | 30.1% |
| 30-40% | 457 | 36.7% | 36.5% |
| 40-50% | 1366 | 45.2% | 42.4% |
| 50-60% | 215 | 52.2% | 51.2% |
| 60-70% | 5 | 61.7% | 40.0% |
| 70-100% | 1 | 70.5% | 0.0% |

Calibration of P(favourite covers the median game handicap):

| Bucket | n | predicted | actual |
| --- | --- | --- | --- |
| 0-40% | 159 | 38.5% | 38.4% |
| 40-45% | 588 | 42.8% | 38.9% |
| 45-50% | 1458 | 47.8% | 46.8% |
| 50-55% | 0 | N/A | N/A |
| 55-60% | 0 | N/A | N/A |
| 60-100% | 0 | N/A | N/A |

## 6. What this does and does not show

* Probabilities come from results only (Elo); bookmaker prices are not in the data set and were not used anywhere.
* Calibration is judged on the evaluation period, which the parameter choice never saw.
* Players with fewer than 10 earlier matches are predicted with provisional ratings; their matches are reported separately (line 'All matches').
* Game-market figures use a random sample and serve traits frozen at the archive snapshot when replayed live; treat them as a first validation, not proof of edge.
* No ROI is claimed: there are no historical Sportybet prices to compare against yet. The live tracker (data/tennis/tracker.csv) will accumulate that evidence.

Generated in 1863 s by tennis/backtest.py.