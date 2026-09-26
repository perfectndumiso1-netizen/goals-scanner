# Markets backtest (v3)

_Generated 2026-09-26 12:21. Main leagues, 32,242 matches 2022-26; evaluation from Aug 2023; train = to Jun 2025, test = after._

## Corners

Model: team corner rates for/against (league-normalised, decayed, shrinkage K=40), negative binomial size r=80. Test log-loss for 'Over 9.5 corners': **0.6867** vs league-average baseline 0.6932; mean absolute error on total corners 2.68 vs 2.71 baseline.

**Over 8.5 total corners** — test seasons

| bucket    |    n | predicted   | actual   | gap    |
|:----------|-----:|:------------|:---------|:-------|
| 0.40–0.50 |  158 | 48.3%       | 58.2%    | +10.0% |
| 0.50–0.60 | 2903 | 56.3%       | 55.3%    | -1.0%  |
| 0.60–0.70 | 4761 | 64.4%       | 65.1%    | +0.7%  |
| 0.70–0.80 |  492 | 71.9%       | 71.7%    | -0.2%  |

**Over 9.5 total corners** — test seasons

| bucket    |    n | predicted   | actual   | gap    |
|:----------|-----:|:------------|:---------|:-------|
| 0.00–0.30 |    2 | 29.5%       | 0.0%     | -29.5% |
| 0.30–0.40 |  466 | 37.9%       | 42.9%    | +5.0%  |
| 0.40–0.50 | 3818 | 45.9%       | 45.6%    | -0.3%  |
| 0.50–0.60 | 3745 | 54.0%       | 56.2%    | +2.2%  |
| 0.60–0.70 |  283 | 62.0%       | 56.5%    | -5.5%  |

**Over 10.5 total corners** — test seasons

| bucket    |    n | predicted   | actual   | gap   |
|:----------|-----:|:------------|:---------|:------|
| 0.00–0.30 |  712 | 27.9%       | 31.2%    | +3.3% |
| 0.30–0.40 | 4572 | 35.6%       | 35.6%    | -0.1% |
| 0.40–0.50 | 2889 | 43.6%       | 46.1%    | +2.5% |
| 0.50–0.60 |  141 | 51.8%       | 51.8%    | -0.0% |

**Over 11.5 total corners** — test seasons

| bucket    |    n | predicted   | actual   | gap   |
|:----------|-----:|:------------|:---------|:------|
| 0.00–0.30 | 5581 | 24.9%       | 25.8%    | +0.9% |
| 0.30–0.40 | 2653 | 33.3%       | 34.8%    | +1.5% |
| 0.40–0.50 |   80 | 41.5%       | 45.0%    | +3.5% |

**Home team over 3.5 corners** — test seasons (NB size 10)

| bucket    |    n | predicted   | actual   | gap    |
|:----------|-----:|:------------|:---------|:-------|
| 0.40–0.50 |    2 | 49.1%       | 0.0%     | -49.1% |
| 0.50–0.60 |  135 | 57.7%       | 41.5%    | -16.2% |
| 0.60–0.70 | 3175 | 66.9%       | 64.4%    | -2.5%  |
| 0.70–0.80 | 4842 | 73.6%       | 75.7%    | +2.1%  |
| 0.80–1.00 |  160 | 81.4%       | 87.5%    | +6.1%  |

**Home team over 4.5 corners** — test seasons (NB size 10)

| bucket    |    n | predicted   | actual   | gap    |
|:----------|-----:|:------------|:---------|:-------|
| 0.30–0.40 |   36 | 38.1%       | 19.4%    | -18.7% |
| 0.40–0.50 |  916 | 47.1%       | 43.2%    | -3.9%  |
| 0.50–0.60 | 5323 | 55.4%       | 55.5%    | +0.0%  |
| 0.60–0.70 | 1990 | 63.0%       | 68.0%    | +5.0%  |
| 0.70–0.80 |   49 | 72.2%       | 79.6%    | +7.3%  |

**Home team over 5.5 corners** — test seasons (NB size 10)

| bucket    |    n | predicted   | actual   | gap    |
|:----------|-----:|:------------|:---------|:-------|
| 0.00–0.30 |  146 | 27.7%       | 11.0%    | -16.7% |
| 0.30–0.40 | 2700 | 36.8%       | 34.9%    | -1.9%  |
| 0.40–0.50 | 4733 | 44.2%       | 46.4%    | +2.1%  |
| 0.50–0.60 |  717 | 52.7%       | 58.9%    | +6.2%  |
| 0.60–0.70 |   18 | 62.4%       | 77.8%    | +15.4% |

## Cards (bookings)

Model: team card rates (received / provoked, league-normalised, decayed, shrinkage K=20), with a referee factor, negative binomial size r=30. Test log-loss for 'Over 4.5 cards': **0.6569** vs baseline 0.6797. In the UK leagues (where referees are known): with referee 0.6517 vs without 0.6554 vs baseline 0.6674.

**Over 3.5 total cards** — test seasons

| bucket    |    n | predicted   | actual   | gap   |
|:----------|-----:|:------------|:---------|:------|
| 0.00–0.30 |    8 | 28.0%       | 37.5%    | +9.5% |
| 0.30–0.40 |  344 | 36.9%       | 39.2%    | +2.3% |
| 0.40–0.50 | 1755 | 45.9%       | 48.0%    | +2.0% |
| 0.50–0.60 | 2838 | 55.0%       | 56.7%    | +1.7% |
| 0.60–0.70 | 2334 | 64.8%       | 65.3%    | +0.4% |
| 0.70–0.80 | 1441 | 74.2%       | 76.0%    | +1.8% |
| 0.80–1.00 |  155 | 82.0%       | 81.3%    | -0.7% |

**Over 4.5 total cards** — test seasons

| bucket    |    n | predicted   | actual   | gap   |
|:----------|-----:|:------------|:---------|:------|
| 0.00–0.30 | 1603 | 25.6%       | 27.2%    | +1.6% |
| 0.30–0.40 | 2862 | 35.0%       | 36.7%    | +1.6% |
| 0.40–0.50 | 2275 | 44.7%       | 45.3%    | +0.6% |
| 0.50–0.60 | 1508 | 54.6%       | 53.2%    | -1.3% |
| 0.60–0.70 |  588 | 63.4%       | 60.9%    | -2.5% |
| 0.70–0.80 |   39 | 72.2%       | 74.4%    | +2.1% |

**Over 5.5 total cards** — test seasons

| bucket    |    n | predicted   | actual   | gap   |
|:----------|-----:|:------------|:---------|:------|
| 0.00–0.30 | 5884 | 20.4%       | 20.1%    | -0.3% |
| 0.30–0.40 | 1891 | 34.5%       | 32.7%    | -1.8% |
| 0.40–0.50 |  940 | 44.2%       | 44.6%    | +0.4% |
| 0.50–0.60 |  154 | 53.1%       | 50.0%    | -3.1% |
| 0.60–0.70 |    6 | 62.1%       | 66.7%    | +4.6% |

## 1X2, double chance and team goals

Multi-class log-loss of the 1X2 probabilities (score matrix vs bookmaker-implied, blended):

|   market weight |   train 1X2 log-loss |   test 1X2 log-loss |
|----------------:|---------------------:|--------------------:|
|             0   |               0.9998 |              1.0065 |
|             0.5 |               0.9987 |              1.0053 |
|             0.8 |               0.9982 |              1.0048 |
|             0.9 |               0.998  |              1.0046 |
|             1   |               0.9978 |              1.0044 |

**Calibration (test seasons, 90% market):** home win / draw / away win / double chance 1X

| market   | bucket    |    n | predicted   | actual   | gap   |
|:---------|:----------|-----:|:------------|:---------|:------|
| Home win | 0.00–0.20 |  491 | 15.0%       | 11.4%    | -3.6% |
| Home win | 0.20–0.30 | 1097 | 25.8%       | 22.8%    | -3.0% |
| Home win | 0.30–0.40 | 2230 | 35.3%       | 33.9%    | -1.4% |
| Home win | 0.40–0.50 | 2442 | 44.7%       | 45.5%    | +0.8% |
| Home win | 0.50–0.60 | 1519 | 54.3%       | 55.6%    | +1.2% |
| Home win | 0.60–0.70 |  678 | 64.4%       | 67.6%    | +3.1% |
| Home win | 0.70–0.80 |  319 | 74.4%       | 78.7%    | +4.2% |
| Home win | 0.80–0.90 |   86 | 82.8%       | 88.4%    | +5.6% |
| Home win | 0.90–1.00 |    1 | 91.2%       | 100.0%   | +8.8% |

| market   | bucket    |    n | predicted   | actual   | gap   |
|:---------|:----------|-----:|:------------|:---------|:------|
| Draw     | 0.00–0.20 |  743 | 16.6%       | 15.3%    | -1.2% |
| Draw     | 0.20–0.30 | 7578 | 26.3%       | 27.0%    | +0.7% |
| Draw     | 0.30–0.40 |  542 | 30.9%       | 32.5%    | +1.6% |

| market   | bucket    |    n | predicted   | actual   | gap    |
|:---------|:----------|-----:|:------------|:---------|:-------|
| Away win | 0.00–0.20 | 1662 | 14.5%       | 11.9%    | -2.6%  |
| Away win | 0.20–0.30 | 2831 | 25.2%       | 24.2%    | -0.9%  |
| Away win | 0.30–0.40 | 2414 | 34.5%       | 34.3%    | -0.2%  |
| Away win | 0.40–0.50 | 1135 | 44.2%       | 44.5%    | +0.3%  |
| Away win | 0.50–0.60 |  500 | 54.4%       | 56.2%    | +1.8%  |
| Away win | 0.60–0.70 |  227 | 64.4%       | 66.1%    | +1.7%  |
| Away win | 0.70–0.80 |   87 | 73.7%       | 81.6%    | +7.9%  |
| Away win | 0.80–0.90 |    7 | 82.3%       | 71.4%    | -10.9% |

| market           | bucket    |    n | predicted   | actual   | gap    |
|:-----------------|:----------|-----:|:------------|:---------|:-------|
| Double chance 1X | 0.00–0.20 |    7 | 17.7%       | 28.6%    | +10.9% |
| Double chance 1X | 0.20–0.30 |   87 | 26.3%       | 18.4%    | -7.9%  |
| Double chance 1X | 0.30–0.40 |  227 | 35.6%       | 33.9%    | -1.7%  |
| Double chance 1X | 0.40–0.50 |  500 | 45.6%       | 43.8%    | -1.8%  |
| Double chance 1X | 0.50–0.60 | 1135 | 55.8%       | 55.5%    | -0.3%  |
| Double chance 1X | 0.60–0.70 | 2414 | 65.5%       | 65.7%    | +0.2%  |
| Double chance 1X | 0.70–0.80 | 2831 | 74.8%       | 75.8%    | +0.9%  |
| Double chance 1X | 0.80–0.90 | 1369 | 84.1%       | 86.0%    | +2.0%  |
| Double chance 1X | 0.90–1.00 |  293 | 92.4%       | 97.6%    | +5.2%  |

**Team goals (test seasons):**

| market        | bucket    |    n | predicted   | actual   | gap    |
|:--------------|:----------|-----:|:------------|:---------|:-------|
| Home over 0.5 | 0.40–0.50 |   24 | 48.5%       | 33.3%    | -15.1% |
| Home over 0.5 | 0.50–0.60 |  210 | 56.0%       | 50.0%    | -6.0%  |
| Home over 0.5 | 0.60–0.70 | 1464 | 66.4%       | 65.8%    | -0.6%  |
| Home over 0.5 | 0.70–0.80 | 4279 | 75.3%       | 75.8%    | +0.6%  |
| Home over 0.5 | 0.80–0.90 | 2533 | 83.8%       | 86.5%    | +2.6%  |
| Home over 0.5 | 0.90–1.00 |  353 | 92.4%       | 97.7%    | +5.4%  |

| market        | bucket    |    n | predicted   | actual   | gap   |
|:--------------|:----------|-----:|:------------|:---------|:------|
| Home over 1.5 | 0.00–0.30 |  903 | 25.3%       | 23.3%    | -2.0% |
| Home over 1.5 | 0.30–0.40 | 2631 | 35.5%       | 33.8%    | -1.8% |
| Home over 1.5 | 0.40–0.50 | 3011 | 44.8%       | 44.2%    | -0.5% |
| Home over 1.5 | 0.50–0.60 | 1507 | 54.2%       | 56.2%    | +2.0% |
| Home over 1.5 | 0.60–0.70 |  576 | 64.2%       | 68.2%    | +4.0% |
| Home over 1.5 | 0.70–0.80 |  209 | 74.1%       | 80.9%    | +6.7% |
| Home over 1.5 | 0.80–0.90 |   25 | 82.9%       | 84.0%    | +1.1% |
| Home over 1.5 | 0.90–1.00 |    1 | 90.6%       | 100.0%   | +9.4% |

| market        | bucket    |    n | predicted   | actual   | gap   |
|:--------------|:----------|-----:|:------------|:---------|:------|
| Away over 0.5 | 0.40–0.50 |  114 | 47.2%       | 39.5%    | -7.7% |
| Away over 0.5 | 0.50–0.60 | 1007 | 56.6%       | 56.7%    | +0.1% |
| Away over 0.5 | 0.60–0.70 | 3560 | 65.5%       | 65.3%    | -0.1% |
| Away over 0.5 | 0.70–0.80 | 3145 | 74.3%       | 75.6%    | +1.3% |
| Away over 0.5 | 0.80–0.90 |  953 | 83.7%       | 87.8%    | +4.1% |
| Away over 0.5 | 0.90–1.00 |   84 | 91.6%       | 95.2%    | +3.6% |

| market        | bucket    |    n | predicted   | actual   | gap    |
|:--------------|:----------|-----:|:------------|:---------|:-------|
| Away over 1.5 | 0.00–0.30 | 3284 | 24.5%       | 25.2%    | +0.7%  |
| Away over 1.5 | 0.30–0.40 | 3228 | 34.7%       | 34.1%    | -0.6%  |
| Away over 1.5 | 0.40–0.50 | 1536 | 44.2%       | 45.5%    | +1.4%  |
| Away over 1.5 | 0.50–0.60 |  575 | 54.1%       | 55.8%    | +1.7%  |
| Away over 1.5 | 0.60–0.70 |  203 | 64.3%       | 70.4%    | +6.2%  |
| Away over 1.5 | 0.70–0.80 |   34 | 73.6%       | 64.7%    | -8.9%  |
| Away over 1.5 | 0.80–0.90 |    3 | 81.4%       | 66.7%    | -14.7% |

## Parlay strategy (3 per run, 2.70–3.50 combined odds, legs = 1X2 / double chance / O-U 2.5)

Simulated on the test seasons (2025/26–26/27) with **real opening odds**: {'parlays': 734, 'days': 252, 'avg legs': np.float64(2.97), 'avg odds': np.float64(2.72), 'avg model probability': '29.9%', 'actual hit rate': '30.5%', 'ROI (1 unit per parlay)': '-16.9%'}

| window    |   parlays | hit_rate   |   avg_odds | avg_p   | roi     |
|:----------|----------:|:-----------|-----------:|:--------|:--------|
| afternoon |       135 | 25.2%      |       2.72 | 29.2%   | -31.6%  |
| evening   |       598 | 31.8%      |       2.72 | 30.1%   | -13.4%  |
| morning   |         1 | 0.0%       |       2.74 | 30.7%   | -100.0% |

By month:

| month   |   parlays |   hits | roi     |
|:--------|----------:|-------:|:--------|
| 2025-07 |         2 |      0 | -100.0% |
| 2025-08 |        58 |     23 | +8.0%   |
| 2025-09 |        59 |     15 | -31.0%  |
| 2025-10 |        52 |     14 | -27.0%  |
| 2025-11 |        52 |     14 | -26.9%  |
| 2025-12 |        67 |     20 | -19.0%  |
| 2026-01 |        77 |     25 | -11.5%  |
| 2026-02 |        65 |     15 | -37.4%  |
| 2026-03 |        68 |     24 | -3.9%   |
| 2026-04 |        83 |     29 | -5.2%   |
| 2026-05 |        55 |     19 | -4.9%   |
| 2026-08 |        49 |     15 | -16.2%  |
| 2026-09 |        47 |     11 | -36.0%  |

_Interpretation: a parlay at ~3.0 needs to win 1 in 3 to break even. The model probability tells you what to expect; the ROI shows what the bookmaker margin does to it._

## Value finder check (best available price vs sharp reference)

Reference = Pinnacle (to 2024/25) or Betfair Exchange (after), margin removed. 'Edge' = fair probability × price − 1. Main leagues, Aug 2023 – Sep 2026, opening prices.

| selection   | edge >   | price               |   bets | hit rate   |   avg odds | ROI   |
|:------------|:---------|:--------------------|-------:|:-----------|-----------:|:------|
| Over 2.5    | 0%       | best price (Max)    |   1455 | 51.3%      |       2.05 | +3.2% |
| Over 2.5    | 0%       | average price (Avg) |    140 | 47.9%      |       1.95 | -9.6% |
| Over 2.5    | 2%       | best price (Max)    |    382 | 51.0%      |       2.07 | +3.6% |
| Over 2.5    | 2%       | average price (Avg) |    126 | 48.4%      |       1.96 | -7.1% |
| Over 2.5    | 4%       | best price (Max)    |    216 | 51.4%      |       2.07 | +4.4% |
| Over 2.5    | 4%       | average price (Avg) |    115 | 47.0%      |       1.98 | -9.6% |
| Over 2.5    | 6%       | best price (Max)    |    170 | 51.2%      |       2.08 | +2.9% |
| Over 2.5    | 6%       | average price (Avg) |    101 | 46.5%      |       1.98 | -9.6% |
| Under 2.5   | 0%       | best price (Max)    |   2306 | 44.6%      |       2.3  | -3.0% |
| Under 2.5   | 0%       | average price (Avg) |    189 | 42.9%      |       2.35 | -5.1% |
| Under 2.5   | 2%       | best price (Max)    |    670 | 40.0%      |       2.53 | -5.5% |
| Under 2.5   | 2%       | average price (Avg) |    161 | 44.7%      |       2.35 | -0.7% |
| Under 2.5   | 4%       | best price (Max)    |    311 | 39.5%      |       2.63 | -5.5% |
| Under 2.5   | 4%       | average price (Avg) |    137 | 43.8%      |       2.36 | -4.0% |
| Under 2.5   | 6%       | best price (Max)    |    198 | 42.9%      |       2.59 | +3.0% |
| Under 2.5   | 6%       | average price (Avg) |    118 | 44.9%      |       2.38 | +0.4% |

_The 'best price' rows need accounts at whichever bookmaker is top that day; the 'average price' rows are what a typical single bookmaker offers._
