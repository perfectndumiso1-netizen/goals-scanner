# Tennis engine — walk-forward backtest

Data: Jeff Sackmann's ATP (main tour + qualifying/Challengers) and WTA match files, archive snapshot June 2026 (239,324 matches 2009-01-04 → 2026-06-01). Replay in chronological order; every prediction uses only earlier matches. Training period 2012-01-01…2018-12-31 for parameter choice, evaluation 2019-01-01…2026-06-01. 'Rated' = both players had ≥ 10 earlier matches in the data.

## 1. Parameter selection (training period, rated matches, log loss — lower is better)

| K | shape | surface weight | log loss | accuracy | n |
| --- | --- | --- | --- | --- | --- |
| 250 | 0.4 | 0.5 | 0.6163 | 65.5% | 80,625 |
| 250 | 0.4 | 0.5 | 0.6163 | 65.5% | 80,625 |

Chosen: K = 250, shape = 0.4 (K schedule K/(matches+5)^shape), surface weight = 0.5.

Logistic scale of the rating difference (training period):

| scale | log loss | accuracy | n |
| --- | --- | --- | --- |
| 400.0 | 0.6163 | 65.5% | 80,625 |

Chosen scale: 400.

## 2. Evaluation period (out of sample)

| Subset | n | accuracy | Brier | log loss |
| --- | --- | --- | --- | --- |
| All matches (incl. players with little history) | 107,226 | 64.5% | 0.2191 | 0.6277 |
| Rated (both players ≥ 10 earlier matches) | 94,411 | 63.9% | 0.2216 | 0.6331 |
| Reference: better-ranked player wins (official ranking, rated subset with ranks) | 93,560 | 61.6% | — | — |
| Reference: coin flip |  | 50.0% | 0.2500 | 0.6931 |

## 3. Calibration (evaluation period, rated matches, favourite's probability)

| Probability bucket | Predictions | Mean predicted | Actual win rate | Gap (pp) |
| --- | --- | --- | --- | --- |
| 50-55% | 17,002 | 52.5% | 52.1% | -0.4 |
| 55-60% | 16,267 | 57.5% | 56.1% | -1.3 |
| 60-65% | 15,149 | 62.5% | 60.2% | -2.3 |
| 65-70% | 13,300 | 67.4% | 64.6% | -2.9 |
| 70-75% | 11,036 | 72.4% | 69.5% | -3.0 |
| 75-80% | 8,867 | 77.4% | 73.5% | -3.9 |
| 80-85% | 6,293 | 82.4% | 77.5% | -4.9 |
| 85-90% | 3,884 | 87.3% | 82.9% | -4.5 |
| 90-95% | 2,036 | 92.1% | 89.5% | -2.6 |
| 95-100% | 577 | 96.7% | 95.0% | -1.7 |

## 4. Breakdowns (evaluation period, rated matches)

### By surface

| surface | n | accuracy | Brier | log loss |
| --- | --- | --- | --- | --- |
| Hard | 50,809 | 64.3% | 0.2206 | 0.6310 |
| Clay | 37,942 | 63.4% | 0.2229 | 0.6363 |
| Grass | 5,492 | 64.0% | 0.2202 | 0.6303 |

### By tour

| tour | n | accuracy | Brier | log loss |
| --- | --- | --- | --- | --- |
| atp | 78,417 | 63.7% | 0.2221 | 0.6344 |
| wta | 15,994 | 64.9% | 0.2187 | 0.6270 |

### By format

| best_of | n | accuracy | Brier | log loss |
| --- | --- | --- | --- | --- |
| 3 | 90,658 | 63.6% | 0.2231 | 0.6370 |
| 5 | 3,753 | 71.6% | 0.1830 | 0.5407 |

### By level (G slam, M masters, A tour, PM/P/I WTA 1000/500/250, C challenger, D team)

| level | n | accuracy | Brier | log loss |
| --- | --- | --- | --- | --- |
| 50+H | 9 | 44.4% | 0.2505 | 0.6936 |
| A | 14,358 | 64.9% | 0.2173 | 0.6238 |
| C | 50,311 | 62.7% | 0.2266 | 0.6451 |
| D | 1,574 | 68.3% | 0.2013 | 0.5840 |
| F | 270 | 56.3% | 0.2344 | 0.6584 |
| G | 9,916 | 68.0% | 0.2018 | 0.5862 |
| I | 4,643 | 61.7% | 0.2312 | 0.6548 |
| M | 5,945 | 63.9% | 0.2217 | 0.6331 |
| O | 191 | 65.4% | 0.2027 | 0.5823 |
| P | 4,321 | 65.1% | 0.2219 | 0.6348 |
| PM | 2,626 | 65.0% | 0.2173 | 0.6240 |
| W | 247 | 68.8% | 0.2088 | 0.6055 |

### Best-of-5 format handling

| Variant | n | accuracy | Brier | log loss |
| --- | --- | --- | --- | --- |
| Set-level mapping: bo5 probability derived from the set probability (used) | 3,753 | 71.6% | 0.1830 | 0.5407 |
| No format adjustment (bo5 treated as bo3) | 3,753 | 71.5% | 0.1833 | 0.5423 |

## 5. Game markets (Markov chain pinned to the Elo probability; random sample of evaluation matches, rated players, no retirements)

An independent-points chain with fixed serve probabilities makes matches too long: real matches are more lopsided on the day than the players' average levels suggest. The game model therefore treats the serve-point difference on the day as Normal(d0, σ) (5-point Gauss-Hermite mixture, d0 solved so the mixture reproduces the rating probability). σ is the only fitted quantity: chosen per tour on the *training* period by matching the mean total games (bias closest to zero), then applied unchanged below.

| tour | bias σ=0.0 | bias σ=0.1 | chosen σ |
| --- | --- | --- | --- |
| atp | +2.07 (n=145) | -0.30 (n=145) | 0.1 |
| wta | N/A | N/A | 0.0 |

Sample: 184 matches; serve/return traits available for both players in 100% of them (tour/surface baseline used otherwise).

| Quantity | Value |
| --- | --- |
| Mean expected total games | 23.14 |
| Mean actual total games | 22.28 |
| Mean absolute error of expected total | 4.85 |
| Over model median line — accuracy / Brier / log loss | 56.5% / 0.2451 / 0.6834 |
| Over 22.5 (best-of-3) — accuracy / Brier / log loss | 69.5% / 0.2167 / 0.6245 |
| Favourite's games over the model median (ex ante) — accuracy / Brier / log loss | 64.1% / 0.2323 / 0.6572 |
| Favourite covers the model's median game handicap (ex ante) — accuracy / Brier / log loss | 62.0% / 0.2409 / 0.6748 |

By tour / format (expected vs actual mean total games):

| Group | n | expected | actual |
| --- | --- | --- | --- |
| tour atp | 156 | 23.05 | 22.29 |
| tour wta | 28 | 23.67 | 22.21 |
| best-of-3 | 177 | 22.73 | 21.70 |
| best-of-5 | 7 | 33.58 | 36.86 |

Calibration of P(over 22.5 games), best-of-3:

| Bucket | n | predicted | actual |
| --- | --- | --- | --- |
| 0-30% | 8 | 26.3% | 12.5% |
| 30-40% | 51 | 36.1% | 19.6% |
| 40-50% | 97 | 43.6% | 35.1% |
| 50-60% | 21 | 55.5% | 57.1% |
| 60-70% | 0 | N/A | N/A |
| 70-100% | 0 | N/A | N/A |

Calibration of P(favourite covers the median game handicap):

| Bucket | n | predicted | actual |
| --- | --- | --- | --- |
| 0-40% | 10 | 38.8% | 30.0% |
| 40-45% | 57 | 42.7% | 38.6% |
| 45-50% | 117 | 47.9% | 38.5% |
| 50-55% | 0 | N/A | N/A |
| 55-60% | 0 | N/A | N/A |
| 60-100% | 0 | N/A | N/A |

## 6. What this does and does not show

* Probabilities come from results only (Elo); bookmaker prices are not in the data set and were not used anywhere.
* Calibration is judged on the evaluation period, which the parameter choice never saw.
* Players with fewer than 10 earlier matches are predicted with provisional ratings; their matches are reported separately (line 'All matches').
* Game-market figures use a random sample and serve traits frozen at the archive snapshot when replayed live; treat them as a first validation, not proof of edge.
* No ROI is claimed: there are no historical Sportybet prices to compare against yet. The live tracker (data/tennis/tracker.csv) will accumulate that evidence.

Generated in 219 s by tennis/backtest.py.