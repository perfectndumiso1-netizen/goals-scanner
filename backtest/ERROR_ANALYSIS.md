# Model error analysis — where the predictions systematically fail

_Generated 2026-09-29 17:01. Read-only study: the model, its parameters and every published probability are **unchanged**. Predictions are a no-look-ahead replay of the **current production model** (two-strength log-space shrinkage — strength K=5, tempo K=40; validated 2026-09-28, see backtest/RESULTS.md; half-life 120 d, venue K=20, Dixon-Coles rho = -0.05). Only matches played strictly before each match date are used; league-tempo inputs are taken from the identical base single-K=40 replay (backtest/predictions.pkl)._

**Dataset:** 38,906 matches with a model prediction, Aug 2023 → 24 Sep 2026, 39 leagues in 27 countries (24,285 main-league matches with bookmaker odds; the rest without odds).

Matches by calendar year: 2023: 5,832 · 2024: 12,358 · 2025: 12,310 · 2026: 8,406 (2026 is partial, through 24 Sep).

**What 'gap' means below:** actual hit rate minus the model's average predicted probability. A positive gap = the model under-predicted that market in the group; negative = over-predicted. Groups with fewer than 120 matches are hidden (too noisy to be evidence).

## 1. Baseline accuracy (all evaluation matches)

| market   |     n | avg predicted   | actual   | gap   |   log-loss |   Brier |
|:---------|------:|:----------------|:---------|:------|-----------:|--------:|
| Over 1.5 | 38906 | 75.7%           | 75.5%    | -0.2% |     0.5478 |  0.1816 |
| Over 2.5 | 38906 | 51.1%           | 51.8%    | +0.7% |     0.6813 |  0.2442 |
| BTTS     | 38906 | 52.9%           | 54.0%    | +1.2% |     0.6859 |  0.2464 |
| Home win | 38906 | 43.9%           | 43.7%    | -0.1% |     0.651  |  0.2298 |
| Draw     | 38906 | 25.4%           | 26.3%    | +0.9% |     0.5733 |  0.1928 |
| Away win | 38906 | 30.7%           | 30.0%    | -0.8% |     0.5805 |  0.1974 |

## 2. Calibration by predicted probability (signed gap)

**Over 2.5**

| bucket    |    n | predicted   | actual   | gap    |
|:----------|-----:|:------------|:---------|:-------|
| 0.00–0.35 | 1095 | 31.5%       | 31.5%    | +0.0%  |
| 0.35–0.40 | 1495 | 37.9%       | 40.6%    | +2.7%  |
| 0.40–0.45 | 5056 | 42.9%       | 44.4%    | +1.4%  |
| 0.45–0.50 | 9360 | 47.6%       | 48.3%    | +0.7%  |
| 0.50–0.55 | 9930 | 52.5%       | 52.5%    | +0.0%  |
| 0.55–0.60 | 7241 | 57.2%       | 57.4%    | +0.2%  |
| 0.60–0.65 | 3591 | 62.0%       | 63.3%    | +1.3%  |
| 0.65–0.70 |  895 | 66.9%       | 68.9%    | +2.1%  |
| 0.70–0.75 |  196 | 71.9%       | 77.0%    | +5.1%  |
| 0.75–0.80 |   40 | 76.6%       | 82.5%    | +5.9%  |
| 0.80–1.00 |    7 | 80.8%       | 57.1%    | -23.6% |

**Over 1.5**

| bucket    |     n | predicted   | actual   | gap   |
|:----------|------:|:------------|:---------|:------|
| 0.00–0.75 | 16301 | 70.5%       | 70.3%    | -0.2% |
| 0.75–0.80 | 13691 | 77.4%       | 77.3%    | -0.2% |
| 0.80–0.85 |  7684 | 82.0%       | 81.8%    | -0.2% |
| 0.85–0.88 |   993 | 86.1%       | 85.5%    | -0.6% |
| 0.88–0.90 |   174 | 88.8%       | 92.0%    | +3.1% |
| 0.90–0.93 |    58 | 91.0%       | 91.4%    | +0.4% |
| 0.93–0.96 |     5 | 93.3%       | 100.0%   | +6.7% |

**BTTS**

| bucket    |     n | predicted   | actual   | gap    |
|:----------|------:|:------------|:---------|:-------|
| 0.00–0.35 |   184 | 33.3%       | 42.4%    | +9.1%  |
| 0.35–0.40 |   907 | 38.0%       | 43.6%    | +5.6%  |
| 0.40–0.45 |  2222 | 43.0%       | 43.6%    | +0.6%  |
| 0.45–0.50 |  7954 | 48.0%       | 50.8%    | +2.8%  |
| 0.50–0.55 | 13399 | 52.5%       | 53.8%    | +1.2%  |
| 0.55–0.60 | 10182 | 57.2%       | 56.8%    | -0.4%  |
| 0.60–0.65 |  3733 | 61.9%       | 62.3%    | +0.4%  |
| 0.65–0.70 |   322 | 66.1%       | 69.6%    | +3.4%  |
| 0.70–0.75 |     3 | 70.6%       | 100.0%   | +29.4% |

## 3. Systematic bias by league (|O2.5 gap| ranked)

| group                                   |    n | O1.5 gap   | O2.5 gap   | BTTS gap   |   O2.5 Brier | O2.5 actual   |
|:----------------------------------------|-----:|:-----------|:-----------|:-----------|-------------:|:--------------|
| Finland · Veikkausliiga                 |  554 | +0.4%      | +3.1%      | +1.2%      |        0.243 | 58.7%         |
| Russia · Premier League                 |  717 | -1.1%      | -3.1%      | +0.3%      |        0.246 | 48.0%         |
| England · League One                    | 1739 | -0.2%      | +2.5%      | +1.2%      |        0.249 | 50.5%         |
| USA · MLS                               | 1634 | -0.3%      | +2.5%      | +3.1%      |        0.237 | 60.1%         |
| Switzerland · Super League              |  724 | +0.9%      | +2.4%      | +4.1%      |        0.236 | 60.2%         |
| Norway · Eliteserien                    |  754 | +0.4%      | +1.9%      | -1.4%      |        0.237 | 59.8%         |
| Argentina · Copa De La Liga Profesional |  405 | -0.9%      | +1.9%      | +2.6%      |        0.234 | 37.8%         |
| England · Championship                  | 1751 | +0.6%      | +1.7%      | +3.1%      |        0.249 | 49.9%         |
| Italy · Serie B                         | 1175 | +1.0%      | +1.7%      | +5.3%      |        0.251 | 47.7%         |
| Romania · Superliga                     | 1001 | -2.1%      | -1.6%      | +1.4%      |        0.244 | 44.6%         |
| Germany · 2. Bundesliga                 |  956 | -0.2%      | +1.5%      | +0.8%      |        0.242 | 59.5%         |
| Denmark · Superliga                     |  613 | +1.5%      | +1.4%      | +2.1%      |        0.244 | 58.4%         |
| Brazil · Serie A                        | 1238 | +1.2%      | +1.4%      | +3.1%      |        0.249 | 47.5%         |
| Greece · Super League                   |  737 | +1.6%      | +1.3%      | -0.4%      |        0.246 | 51.6%         |
| Spain · Segunda División                | 1436 | -1.3%      | +1.3%      | +2.5%      |        0.245 | 45.5%         |
| Argentina · Liga Profesional            | 1288 | -0.4%      | -1.2%      | +2.1%      |        0.221 | 33.2%         |
| France · Ligue 2                        | 1044 | -3.1%      | +1.2%      | +0.2%      |        0.249 | 47.4%         |
| Scotland · Premiership                  |  726 | -0.4%      | +1.1%      | -1.5%      |        0.246 | 55.5%         |
| Germany · Bundesliga                    |  954 | +0.4%      | +1.1%      | -0.1%      |        0.231 | 62.6%         |
| Turkey · Süper Lig                      | 1071 | -1.1%      | -1.1%      | +0.5%      |        0.246 | 53.2%         |


_Shown: top 20 of 39 leagues by |O2.5 gap| (all leagues with ≥120 matches below)._

**Most over-predicted (model too bullish):** Finland · Veikkausliiga (+3.1%, n=554); England · League One (+2.5%, n=1739); USA · MLS (+2.5%, n=1634); Switzerland · Super League (+2.4%, n=724); Norway · Eliteserien (+1.9%, n=754).

**Most under-predicted (model too cautious):** Russia · Premier League (-3.1%, n=717); Romania · Superliga (-1.6%, n=1001); Argentina · Liga Profesional (-1.2%, n=1288); Turkey · Süper Lig (-1.1%, n=1071); Scotland · Championship (-0.7%, n=575).

## 4. Temporal pattern (drift, season start, calendar)

**By calendar year** (drift check: the model must stay calibrated as data ages)

|   group |     n | O1.5 gap   | O2.5 gap   | BTTS gap   |   O2.5 Brier | O2.5 actual   |
|--------:|------:|:-----------|:-----------|:-----------|-------------:|:--------------|
|    2024 | 12358 | -1.0%      | -0.1%      | +0.3%      |        0.244 | 51.2%         |
|    2025 | 12310 | -0.4%      | +0.4%      | +1.2%      |        0.245 | 51.1%         |
|    2026 |  8406 | +0.8%      | +1.9%      | +2.7%      |        0.244 | 53.6%         |
|    2023 |  5832 | +0.5%      | +1.2%      | +0.7%      |        0.244 | 52.2%         |

**By month of year** (European seasons dominate the data)

| group                            |    n | O1.5 gap   | O2.5 gap   | BTTS gap   |   O2.5 Brier | O2.5 actual   |
|:---------------------------------|-----:|:-----------|:-----------|:-----------|-------------:|:--------------|
| Aug–Sep (season start)           | 9579 | -0.3%      | +0.7%      | +1.0%      |        0.245 | 52.3%         |
| Apr–May (end of season)          | 8323 | +1.0%      | +2.3%      | +3.0%      |        0.244 | 53.6%         |
| Feb–Mar (spring)                 | 7350 | -1.1%      | -0.2%      | +0.9%      |        0.244 | 50.4%         |
| Oct–Nov                          | 6955 | -0.7%      | -0.0%      | -0.4%      |        0.242 | 50.9%         |
| Dec (midwinter)                  | 3015 | +0.2%      | +0.0%      | -0.2%      |        0.246 | 51.2%         |
| Jan (winter)                     | 2573 | -0.4%      | +0.4%      | +2.4%      |        0.247 | 51.3%         |
| July (summer-hemisphere seasons) | 1111 | -0.1%      | +1.3%      | +1.6%      |        0.241 | 53.4%         |

**By day of week**

| group    |     n | O1.5 gap   | O2.5 gap   | BTTS gap   |   O2.5 Brier | O2.5 actual   |
|:---------|------:|:-----------|:-----------|:-----------|-------------:|:--------------|
| Saturday | 16263 | -0.4%      | +0.7%      | +1.1%      |        0.245 | 52.1%         |
| Sunday   | 11431 | -0.2%      | +0.3%      | +0.6%      |        0.243 | 52.5%         |
| Mon–Fri  | 11212 | +0.1%      | +1.0%      | +1.8%      |        0.244 | 50.8%         |

## 5. Error by the model's own inputs

**By model total expected goals (λ = lh + la)**

| group          |     n | O1.5 gap   | O2.5 gap   | BTTS gap   |   O2.5 Brier | O2.5 actual   |
|:---------------|------:|:-----------|:-----------|:-----------|-------------:|:--------------|
| 2.6–2.9        | 14417 | -0.1%      | +0.2%      | +1.0%      |        0.249 | 51.9%         |
| λ > 2.9 (high) | 11234 | -0.3%      | +0.8%      | +0.4%      |        0.236 | 60.8%         |
| 2.3–2.6        | 10456 | -0.4%      | +1.1%      | +1.9%      |        0.248 | 46.1%         |
| 2.0–2.3        |  2193 | +0.1%      | +1.8%      | +1.6%      |        0.237 | 39.0%         |
| 1.7–2.0        |   594 | +0.6%      | +0.3%      | +3.6%      |        0.21  | 30.1%         |

**By league-average goals (the model's tempo input mu_h + mu_a)**

| group            |     n | O1.5 gap   | O2.5 gap   | BTTS gap   |   O2.5 Brier | O2.5 actual   |
|:-----------------|------:|:-----------|:-----------|:-----------|-------------:|:--------------|
| 2.4–2.7          | 17077 | -0.1%      | +1.3%      | +1.9%      |        0.248 | 48.9%         |
| 2.7–3.0          | 14554 | -0.5%      | +0.1%      | +0.5%      |        0.245 | 54.7%         |
| 3.0–3.3          |  4707 | -0.0%      | +0.3%      | -0.0%      |        0.234 | 61.3%         |
| league avg < 2.4 |  2506 | +0.8%      | +0.6%      | +2.7%      |        0.231 | 37.1%         |

**By the weaker team's effective sample size (recent weighted matches — the data the model has on the weaker side)**

| group                     |     n | O1.5 gap   | O2.5 gap   | BTTS gap   |   O2.5 Brier | O2.5 actual   |
|:--------------------------|------:|:-----------|:-----------|:-----------|-------------:|:--------------|
| 8–16                      | 22354 | -0.5%      | +0.5%      | +0.6%      |        0.244 | 52.3%         |
| > 16 (strong sample)      | 14407 | +0.3%      | +1.3%      | +2.2%      |        0.244 | 51.3%         |
| 4–8                       |  1261 | -2.1%      | -2.6%      | -1.6%      |        0.248 | 49.2%         |
| 2–4                       |   447 | -0.8%      | -1.2%      | +1.5%      |        0.247 | 50.6%         |
| 1–2                       |   219 | +3.3%      | +6.5%      | +3.6%      |        0.248 | 57.5%         |
| < 1 (≈ no recent matches) |   218 | -1.1%      | -4.4%      | +1.1%      |        0.25  | 46.8%         |

**By strength gap |lh − la|**

| group               |     n | O1.5 gap   | O2.5 gap   | BTTS gap   |   O2.5 Brier | O2.5 actual   |
|:--------------------|------:|:-----------|:-----------|:-----------|-------------:|:--------------|
| ≈ even (Δλ < 0.25)  | 11229 | -0.3%      | +1.0%      | +1.0%      |        0.245 | 49.6%         |
| 0.25–0.5            |  9953 | +0.1%      | +0.1%      | +0.6%      |        0.247 | 49.6%         |
| 0.5–0.8             |  8489 | -0.5%      | +0.5%      | +1.3%      |        0.246 | 51.4%         |
| 0.8–1.2             |  5928 | -1.1%      | +0.4%      | +1.2%      |        0.243 | 54.3%         |
| Δλ > 1.2 (mismatch) |  3307 | +1.5%      | +2.4%      | +2.8%      |        0.23  | 62.9%         |

**By which side the model favours** (venue check: home-favoured vs away-favoured games)

| group              |     n | O1.5 gap   | O2.5 gap   | BTTS gap   |   O2.5 Brier | O2.5 actual   |
|:-------------------|------:|:-----------|:-----------|:-----------|-------------:|:--------------|
| home side favoured | 27301 | -0.3%      | +0.6%      | +1.3%      |        0.243 | 51.9%         |
| away side favoured | 11605 | +0.0%      | +1.0%      | +0.8%      |        0.246 | 51.6%         |

**Team-goals asymmetry** — model P(team scores) vs actual (input: side of the pitch)

| market           |     n | avg predicted   | actual   | gap   |   Brier |
|:-----------------|------:|:----------------|:---------|:------|--------:|
| Home team scores | 38906 | 76.6%           | 77.4%    | +0.8% |  0.1693 |
| Away team scores | 38906 | 68.9%           | 69.5%    | +0.6% |  0.2064 |

## 6. Confident errors — where the model is wrong with conviction

The app publishes a selection when the model probability clears its production bar (O1.5 ≥ 84%, O2.5 ≥ 60%, BTTS ≥ 60%, result ≥ 70%). A **confident error** is a published call that went the other way — the mistake that actually costs money. Note the model's O2.5/BTTS probabilities naturally sit in the ~30–65% band (shrinkage keeps λ close to league averages), so these bars are the meaningful confidence levels for those markets.

**O1.5 (bar 84%)** — published on 5.3% of matches (2,072 calls); hit rate when published: 86.0% vs predicted 85.8%; confident-error rate 0.7% of all matches.

**O2.5 (bar 60%)** — published on 12.2% of matches (4,729 calls); hit rate when published: 65.1% vs predicted 63.5%; confident-error rate 4.2% of all matches.

**BTTS (bar 60%)** — published on 10.4% of matches (4,058 calls); hit rate when published: 62.9% vs predicted 62.2%; confident-error rate 3.9% of all matches.

**Result H/A (bar 70%)** — published on 4.1% of matches (1,612 calls); hit rate when published: 76.6% vs predicted 75.6%; confident-error rate 1.0% of all matches.

**Confident-error rate by league (O2.5, leagues with ≥ 40 published calls)**

| league                    |   published | hit rate   | conf-error rate   | avg predicted   |
|:--------------------------|------------:|:-----------|:------------------|:----------------|
| Norway · Eliteserien      |         223 | 71.3%      | 8.5%              | 63.6%           |
| Finland · Veikkausliiga   |         107 | 70.1%      | 5.8%              | 63.4%           |
| Sweden · Allsvenskan      |         103 | 63.1%      | 5.0%              | 62.7%           |
| Scotland · Premiership    |          92 | 65.2%      | 4.4%              | 64.6%           |
| Scotland · League One     |          77 | 67.5%      | 4.3%              | 63.3%           |
| England · National League |         217 | 65.4%      | 4.3%              | 62.7%           |
| France · Ligue 1          |          92 | 60.9%      | 3.7%              | 62.8%           |
| Turkey · Süper Lig        |         130 | 70.0%      | 3.6%              | 64.0%           |
| Mexico · Liga MX          |          88 | 62.5%      | 3.1%              | 62.3%           |
| Germany · Bundesliga      |         599 | 64.6%      | 22.2%             | 64.2%           |
| Portugal · Primeira Liga  |         100 | 72.0%      | 2.9%              | 64.5%           |
| Netherlands · Eredivisie  |         500 | 64.0%      | 18.6%             | 64.6%           |


**Confident-error rate by model input (O2.5)** — the table that answers *'which inputs are associated with the confident mistakes'*

| input              | group                     |     n | published share   | conf-error rate   |   mean |error| |
|:-------------------|:--------------------------|------:|:------------------|:------------------|---------------:|
| λ total            | 1.7–2.0                   |   594 | 0.0%              | 0.0%              |          0.419 |
| λ total            | 2.0–2.3                   |  2193 | 0.0%              | 0.0%              |          0.47  |
| λ total            | 2.3–2.6                   | 10456 | 0.0%              | 0.0%              |          0.496 |
| λ total            | 2.6–2.9                   | 14417 | 0.0%              | 0.0%              |          0.499 |
| λ total            | λ > 2.9 (high)            | 11234 | 42.1%             | 14.7%             |          0.475 |
| league tempo (mu)  | league avg < 2.4          |  2506 | 0.0%              | 0.0%              |          0.46  |
| league tempo (mu)  | 2.4–2.7                   | 17077 | 1.2%              | 0.4%              |          0.495 |
| league tempo (mu)  | 2.7–3.0                   | 14554 | 11.7%             | 3.9%              |          0.491 |
| league tempo (mu)  | 3.0–3.3                   |  4707 | 58.5%             | 21.0%             |          0.47  |
| weaker-team sample | < 1 (≈ no recent matches) |   218 | 9.6%              | 4.1%              |          0.495 |
| weaker-team sample | 1–2                       |   219 | 8.7%              | 2.3%              |          0.493 |
| weaker-team sample | 2–4                       |   447 | 12.1%             | 3.6%              |          0.491 |
| weaker-team sample | 4–8                       |  1261 | 11.9%             | 5.2%              |          0.492 |
| weaker-team sample | 8–16                      | 22354 | 14.1%             | 5.0%              |          0.488 |
| weaker-team sample | > 16 (strong sample)      | 14407 | 9.3%              | 3.0%              |          0.489 |
| strength gap       | ≈ even (Δλ < 0.25)        | 11229 | 5.4%              | 1.8%              |          0.489 |
| strength gap       | 0.25–0.5                  |  9953 | 6.2%              | 2.4%              |          0.492 |
| strength gap       | 0.5–0.8                   |  8489 | 8.7%              | 3.2%              |          0.492 |
| strength gap       | 0.8–1.2                   |  5928 | 17.2%             | 6.3%              |          0.488 |
| strength gap       | Δλ > 1.2 (mismatch)       |  3307 | 52.9%             | 17.1%             |          0.465 |
| calendar year      | 2023                      |  5832 | 11.0%             | 3.8%              |          0.488 |
| calendar year      | 2024                      | 12358 | 12.9%             | 4.7%              |          0.488 |
| calendar year      | 2025                      | 12310 | 10.9%             | 3.8%              |          0.489 |
| calendar year      | 2026                      |  8406 | 13.7%             | 4.6%              |          0.487 |
| day of week        | Mon–Fri                   | 11212 | 10.0%             | 3.4%              |          0.488 |
| day of week        | Saturday                  | 16263 | 11.4%             | 4.1%              |          0.489 |
| day of week        | Sunday                    | 11431 | 15.3%             | 5.3%              |          0.487 |


**Where the confident O2.5 errors live** — share of ALL confident errors (1,651 over the period) falling in each input bucket, with *lift* = share ÷ the bucket's share of all matches (lift > 1 = errors are over-concentrated there; lift < 1 = under-concentrated):

| input              | group                     |     n |   confident errors | share of all errors   |   lift |
|:-------------------|:--------------------------|------:|-------------------:|:----------------------|-------:|
| λ total            | 1.7–2.0                   |   594 |                  0 | 0.0%                  |   0    |
| λ total            | 2.0–2.3                   |  2193 |                  0 | 0.0%                  |   0    |
| λ total            | 2.3–2.6                   | 10456 |                  0 | 0.0%                  |   0    |
| λ total            | 2.6–2.9                   | 14417 |                  0 | 0.0%                  |   0    |
| λ total            | λ > 2.9 (high)            | 11234 |               1651 | 100.0%                |   3.46 |
| league tempo (mu)  | league avg < 2.4          |  2506 |                  0 | 0.0%                  |   0    |
| league tempo (mu)  | 2.4–2.7                   | 17077 |                 70 | 4.2%                  |   0.1  |
| league tempo (mu)  | 2.7–3.0                   | 14554 |                569 | 34.5%                 |   0.92 |
| league tempo (mu)  | 3.0–3.3                   |  4707 |                989 | 59.9%                 |   4.95 |
| weaker-team sample | < 1 (≈ no recent matches) |   218 |                  9 | 0.5%                  |   0.97 |
| weaker-team sample | 1–2                       |   219 |                  5 | 0.3%                  |   0.54 |
| weaker-team sample | 2–4                       |   447 |                 16 | 1.0%                  |   0.84 |
| weaker-team sample | 4–8                       |  1261 |                 66 | 4.0%                  |   1.23 |
| weaker-team sample | 8–16                      | 22354 |               1122 | 68.0%                 |   1.18 |
| weaker-team sample | > 16 (strong sample)      | 14407 |                433 | 26.2%                 |   0.71 |
| strength gap       | ≈ even (Δλ < 0.25)        | 11229 |                201 | 12.2%                 |   0.42 |
| strength gap       | 0.25–0.5                  |  9953 |                239 | 14.5%                 |   0.57 |
| strength gap       | 0.5–0.8                   |  8489 |                271 | 16.4%                 |   0.75 |
| strength gap       | 0.8–1.2                   |  5928 |                375 | 22.7%                 |   1.49 |
| strength gap       | Δλ > 1.2 (mismatch)       |  3307 |                565 | 34.2%                 |   4.03 |
| calendar year      | 2023                      |  5832 |                223 | 13.5%                 |   0.9  |
| calendar year      | 2024                      | 12358 |                575 | 34.8%                 |   1.1  |
| calendar year      | 2025                      | 12310 |                467 | 28.3%                 |   0.89 |
| calendar year      | 2026                      |  8406 |                386 | 23.4%                 |   1.08 |
| day of week        | Mon–Fri                   | 11212 |                381 | 23.1%                 |   0.8  |
| day of week        | Saturday                  | 16263 |                661 | 40.0%                 |   0.96 |
| day of week        | Sunday                    | 11431 |                609 | 36.9%                 |   1.26 |

## 7. 1X2 (result market)

Calibration of the model's win/draw/loss probabilities (re-derived from the same score matrix):

| outcome   | avg predicted   | actual   | gap   |   log-loss |
|:----------|:----------------|:---------|:------|-----------:|
| Home win  | 43.9%           | 43.7%    | -0.1% |     0.651  |
| Draw      | 25.4%           | 26.3%    | +0.9% |     0.5733 |
| Away win  | 30.7%           | 30.0%    | -0.8% |     0.5805 |

**Home-win probability calibration**

| bucket    |     n | predicted   | actual   | gap   |
|:----------|------:|:------------|:---------|:------|
| 0.00–0.30 |  6373 | 23.4%       | 25.2%    | +1.8% |
| 0.30–0.40 |  9221 | 35.4%       | 36.0%    | +0.6% |
| 0.40–0.50 | 10851 | 44.9%       | 45.2%    | +0.3% |
| 0.50–0.60 |  7520 | 54.5%       | 51.7%    | -2.9% |
| 0.60–0.70 |  3515 | 64.2%       | 62.3%    | -1.9% |
| 0.70–0.80 |  1162 | 74.0%       | 75.8%    | +1.8% |
| 0.80–1.00 |   264 | 83.6%       | 84.1%    | +0.5% |

**1X2 gap by league (top 12 by |home-win gap|)**

| league                                  |    n | H gap   | D gap   | A gap   |
|:----------------------------------------|-----:|:--------|:--------|:--------|
| Germany · Bundesliga                    |  954 | -2.6%   | +2.5%   | +0.1%   |
| Netherlands · Eredivisie                |  970 | -2.5%   | +3.3%   | -0.7%   |
| Argentina · Copa De La Liga Profesional |  405 | -2.1%   | +3.0%   | -0.9%   |
| Brazil · Serie A                        | 1238 | +2.0%   | -0.1%   | -2.0%   |
| USA · MLS                               | 1634 | -2.0%   | +1.8%   | +0.2%   |
| Scotland · League Two                   |  578 | +1.9%   | +0.7%   | -2.6%   |
| Norway · Eliteserien                    |  754 | +1.8%   | -2.5%   | +0.6%   |
| Ireland · Premier Division              |  571 | -1.6%   | +2.9%   | -1.3%   |
| Italy · Serie B                         | 1175 | -1.6%   | +5.2%   | -3.7%   |
| Spain · Segunda División                | 1436 | +1.6%   | -0.1%   | -1.5%   |
| Finland · Veikkausliiga                 |  554 | +1.4%   | -0.4%   | -1.0%   |
| Portugal · Primeira Liga                |  971 | -1.3%   | +2.0%   | -0.7%   |

## 8. Low scores and extreme totals (Dixon-Coles territory)

| cell      | actual   | model   | gap (actual−model)   |   Brier |
|:----------|:---------|:--------|:---------------------|--------:|
| 0-0 score | 7.2%     | 7.4%    | -0.2%                |  0.0661 |
| 1-1 score | 12.2%    | 11.9%   | +0.3%                |  0.107  |
| 4+ goals  | 29.5%    | 29.5%   | +0.0%                |  0.2027 |
| 5+ goals  | 14.4%    | 14.6%   | -0.2%                |  0.1209 |

**0-0 by λ total** (where does the model misprice the low end most?)

| λ total        |     n | actual 0-0   | model 0-0   | gap   |
|:---------------|------:|:-------------|:------------|:------|
| 1.7–2.0        |   594 | 17.8%        | 15.5%       | +2.3% |
| 2.0–2.3        |  2193 | 12.2%        | 12.0%       | +0.2% |
| 2.3–2.6        | 10456 | 8.6%         | 9.1%        | -0.4% |
| 2.6–2.9        | 14417 | 6.9%         | 7.0%        | -0.1% |
| λ > 2.9 (high) | 11234 | 4.7%         | 5.0%        | -0.3% |

## 9. Where the bookmaker disagrees (reference only — never a model input)

On the main leagues (odds available) the opening O/U 2.5 price is shown **for comparison only**, in line with the data-first rule. This table says where the market and the model split — and who the subsequent result agreed with. It is context for any future decision, not a change.

| league                    |    n | disagree on side of 50%   | market right where they split   | model right where they split   | model O2.5 gap   | market O2.5 gap   |
|:--------------------------|-----:|:--------------------------|:--------------------------------|:-------------------------------|:-----------------|:------------------|
| England · Championship    | 1751 | 25.0%                     | 13.8%                           | 11.2%                          | +1.7%            | +0.8%             |
| England · League Two      | 1740 | 23.7%                     | 13.1%                           | 10.6%                          | -0.4%            | -0.2%             |
| England · League One      | 1739 | 25.5%                     | 14.3%                           | 11.3%                          | +2.5%            | +1.2%             |
| England · National League | 1736 | 17.5%                     | 9.5%                            | 8.0%                           | +0.7%            | +0.9%             |
| Spain · Segunda División  | 1436 | 13.8%                     | 8.6%                            | 5.2%                           | +1.3%            | +1.9%             |
| Spain · La Liga           | 1209 | 19.1%                     | 10.2%                           | 8.9%                           | -0.6%            | +0.2%             |
| Italy · Serie A           | 1190 | 22.9%                     | 13.4%                           | 9.6%                           | +0.0%            | +0.1%             |
| England · Premier League  | 1190 | 14.4%                     | 7.4%                            | 7.0%                           | +1.0%            | +1.0%             |
| Italy · Serie B           | 1175 | 14.8%                     | 7.6%                            | 7.2%                           | +1.7%            | +3.0%             |
| Turkey · Süper Lig        | 1071 | 22.5%                     | 12.0%                           | 10.5%                          | -1.1%            | -1.1%             |
| France · Ligue 2          | 1044 | 20.7%                     | 11.7%                           | 9.0%                           | +1.2%            | +1.2%             |
| Belgium · Pro League      |  983 | 21.0%                     | 10.8%                           | 10.2%                          | +0.2%            | -2.3%             |

## 10. Input–error associations (Spearman rank correlation)

Association, not causation. Two columns: **signed error** (actual − predicted) and **|error|** (magnitude of the mistake). The signed column is partly structural — higher λ raises the prediction, which mechanically lowers the signed error — so the honest signal is the |error| column: on 40k+ matches |ρ| ≥ 0.03 is a real association.

| input                     |   ρ vs signed O2.5 error |   ρ vs |O2.5 error| |
|:--------------------------|-------------------------:|--------------------:|
| model λ home (lh)         |                  -0.2    |             -0.0404 |
| model λ away (la)         |                  -0.0949 |              0.0359 |
| strength gap |lh−la|      |                  -0.1299 |             -0.0494 |
| league avg goals (mu)     |                  -0.3123 |             -0.0407 |
| weaker-team sample (neff) |                   0.0676 |              0.0029 |
| home O2.5 hit-rate        |                  -0.2267 |             -0.042  |
| away O2.5 hit-rate        |                  -0.2258 |             -0.019  |
| home BTTS hit-rate        |                  -0.1693 |             -0.0137 |
| away BTTS hit-rate        |                  -0.1586 |             -0.0134 |
| home sample (h_n)         |                   0.1039 |              0.014  |
| away sample (a_n)         |                   0.1022 |              0.0217 |

## 11. What the evidence says — inputs associated with systematic error, ranked

1. **Clear mismatches (strength gap Δλ > 1.2) are the largest pure calibration bias and the main
   reservoir of confident O2.5 errors.** In the 3,307 matches where the model sees a big strength gap, goals
   are under-priced: O2.5 +2.4 %, O1.5 +1.5 %. They also hold 34.2 % of all confident O2.5 errors from 8.5 %
   of matches (lift 4.0; confident-error rate 17.1 % vs 1.8 % in even games), and the model's O2.5 calls
   concentrate there (52.9 % of all published O2.5). The 2026-09-28 two-K shrinkage already cut this bias
   sharply (the old single-K variant under-priced Δλ 0.8–1.2 by +10.7 %); a +2.4 % residual remains where the
   gap is largest. The high-λ bucket (λ > 2.9) is similar: 100 % of confident errors live there (lift 3.5),
   mostly structural — the 60 % bar is only cleared in high-λ matches — with a +0.8 % residual under-price.
2. **League identity — both goals and result.** On goals the model under-prices in Finland (+3.1 %),
   England League One (+2.5 %), MLS (+2.5 %), Switzerland (+2.4 %) and Norway (+1.9 %), and over-prices in
   Russia (−3.1 %). The Scandinavian leagues also carry the highest confident-O2.5 error rates per match
   (Norway 8.5 %, Finland 5.8 %, Sweden 5.0 %). On results, home wins are over-priced in the Bundesliga
   (−2.6 %), Eredivisie (−2.5 %) and MLS (−2.0 %) while draws are under-priced in Italy Serie B (+5.2 %),
   Eredivisie (+3.3 %), Argentina Copa (+3.0 %) and Ireland (+2.9 %); home wins are under-priced in Brazil
   (+2.0 %), Scotland League Two (+1.9 %) and Norway (+1.8 %). League-average tempo (mu) alone is a weaker
   signal than league identity in the production model (mu ≥ 3.0 bucket: O2.5 gap only +0.3 %) — but
   confident O2.5 errors still cluster there (59.9 % of all, lift 4.95) because the 60 % bar is only cleared
   in high-tempo matches.
3. **1X2 is well calibrated in the production model — the old favourite–longshot pathology is gone.** The
   0.60–0.70 home-win bucket now runs −1.9 % (predicted 64.2 % vs actual 62.3 %, n=3,515) and 0.80+ runs
   +0.5 % — versus +21.5 % in the old single-K variant. The remaining result-market issues are league-level
   home/draw tilts (point 2), plus draws under-priced overall by +0.9 %. The 70 % result bar is reachable
   (4.1 % of matches, 1,612 calls) and its hit rate (76.6 %) beats the predicted rate (75.6 %).
4. **All four production publish bars are honest-to-slightly-conservative** — no published market is
   over-confident: O1.5 ≥ 84 % → 86.0 % actual vs 85.8 % predicted (2,072 calls); O2.5 ≥ 60 % → 65.1 % vs
   63.5 % (4,729 calls); BTTS ≥ 60 % → 62.9 % vs 62.2 % (4,058 calls); result ≥ 70 % → 76.6 % vs 75.6 %
   (1,612 calls). The app's ⭐ tier is publishing calls it slightly over-hedges, not calls it over-sells.
5. **Small but real effects:** 0-0 is under-priced by 2.3 pp when the model expects a very low-scoring match
   (λ 1.7–2.0: actual 17.8 % vs model 15.5 %); the weaker team's sample size is bimodal (1–2 recent matches:
   O2.5 under-priced +6.5 %, n=219; 4–8: over-priced −2.6 %, n=1,261); season end (Apr–May, +2.3 %) is
   under-priced more than the middle of the season; 2026 so far runs +1.9 % under-priced — the largest yearly
   gap of the four evaluation years (2024: −0.1 %, 2025: +0.4 %) and worth monitoring rather than acting on.
6. **What is NOT associated with errors:** day of week (goals gaps all within ±1 %; Sunday confident-error
   lift 1.26 — weak), which side the model favours (O2.5 +0.6 % home-favoured vs +1.0 % away-favoured), the
   middle months, and team sample size away from the extremes. No Monday/Sunday or home/away structural flaw.

**Bottom line:** the production model's systematic failures are one-directional and modest in size — it
under-prices goals in clear mismatches and in specific high-scoring leagues (Finland, England L1, MLS,
Switzerland, Norway), over-prices home wins in the Bundesliga/Eredivisie/MLS and under-prices draws in Serie
B/Eredivisie/Copa/Ireland, and shows a mild 2026 under-pricing drift that is still within the range of the
other years. Everything it publishes at its production bars is honest to conservative. Per the agreement,
nothing has been changed; this report is the evidence base for any future adjustment.