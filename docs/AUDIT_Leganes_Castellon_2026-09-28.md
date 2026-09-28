# Data audit — Leganes v Castellon

Spain · Segunda División (Spain) · kick-off 2026-09-28 20:30 · generated 2026-09-28 13:03

Vocabulary: **historical frequency** = what happened in the sample; **model probability** = football-data model (Dixon-Coles); **market implied** = bookmaker price with the margin removed (comparison only, never a model input).

## 1. Data quality

**Overall: High** (score 0.98 / 1.00) — Data quality describes the evidence behind the numbers. It changes the confidence wording, never the probability.

| Component | Score | Reason |
|---|---|---|
| completeness | 1.00 | 100% of tracked fields present |
| sample | 1.00 | Leganes: 40 matches (Very strong), Castellon: 40 matches (Very strong); weighted 14.7 / 14.7 |
| recency | 1.00 | last match 9 days ago (older of the two teams) |
| consistency | 0.80 | Castellon: 1 extreme result in the last 10 |
| competition | 1.00 | 100% of the smaller sample is from this competition |
| venue | 1.00 | Leganes home matches: 19, Castellon away matches: 20 in sample |
| verification | 1.00 | football-data.co.uk results (verified feed) + Livescore |

Missing fields: none. Sources: football-data.co.uk results (verified feed) + Livescore. Data collected: 2026-09-28 13:03.

## 2a. Team profile — Leganes (home)

* Sample: **40 matches** (Very strong evidence), 2025-10-11 → 2026-09-20, last match 8 days ago
* Composition: current season 6, previous 34; home 19, away 21; competitions: Segunda División (40); friendlies included 0, excluded 0
* Fields present: xG in 6, shots on target in 40, corners in 40, cards in 40 of 40 matches
* Ratings (1.00 = competition average): raw attack 0.735 / defence 0.895; venue raw 0.948 / 0.914 (venue weight 0.254); after venue blend 0.789 / 0.9; **after shrinkage 0.909 / 1.003** (weighted matches 14.7)
* Opponent context (information only, not a model input): average opponent attack faced 0.99 / defence faced 1.006; opponent-adjusted raw attack 0.731 / defence 0.904

**Recent form v baseline** (historical frequencies; the model's time-weighting already includes them)

* Last 5: 1.0 scored / 0.8 conceded per game (n=5); last 10: 0.8 / 1.0 (n=10); weighted baseline 1.0 / 1.2
* Recent attack: in line with baseline · recent defence: in line with baseline

**Home / away splits** (plain historical frequencies)

| Split | n | Evidence | GF | GA | O1.5 | O2.5 | BTTS | Clean sheets | Scored | SOT for/ag | Corners for/ag |
|---|---|---|---|---|---|---|---|---|---|---|---|
| All | 40 | Very strong | 1.02 | 1.23 | 27/40 (68%) | 18/40 (45%) | 18/40 (45%) | 14/40 | 25/40 | 4.1 / 4.6 (n=40) | 4.7 / 5.0 (n=40) |
| Home | 19 | Moderate | 1.26 | 1.05 | 12/19 (63%) | 8/19 (42%) | 7/19 (37%) | 8/19 | 13/19 | 5.0 / 4.4 (n=19) | 5.6 / 4.7 (n=19) |
| Away | 21 | Strong | 0.81 | 1.38 | 15/21 (71%) | 10/21 (48%) | 11/21 (52%) | 6/21 | 12/21 | 3.3 / 4.9 (n=21) | 3.8 / 5.2 (n=21) |
| Current season | 6 | Small | 1.00 | 0.83 | 3/6 (50%) | 1/6 (17%) | 2/6 (33%) | 3/6 | 4/6 | 4.5 / 4.7 (n=6) | 2.7 / 6.0 (n=6) |
| Previous season | 34 | Strong | 1.03 | 1.29 | 24/34 (71%) | 17/34 (50%) | 16/34 (47%) | 11/34 | 21/34 | 4.1 / 4.6 (n=34) | 5.0 / 4.8 (n=34) |

**Extreme results in the sample** (kept, flagged):
* 2026-04-26: 0-4 v Andorra (margin)
* 2026-03-21: 5-2 v Ceuta (total)

<details><summary>Matches used (raw observations)</summary>

| Date | Venue | Opponent | Score | Competition | Season | xG f/a | SOT f/a | Corners f/a | Cards f/a | Flag |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-09-20 | H | Granada | 3-2 | Segunda División | current | 2.16 / 2.4 | 12 / 7 | 6 / 4 | 2 / 4 |  |
| 2026-09-13 | A | Tenerife | 0-2 | Segunda División | current | 0.59 / 1.52 | 2 / 4 | 4 / 3 | 2 / 2 |  |
| 2026-09-04 | A | Las Palmas | 0-0 | Segunda División | current | 1.56 / 0.16 | 2 / 1 | 4 / 3 | 2 / 3 |  |
| 2026-08-29 | H | Eldense | 1-0 | Segunda División | current | 1.58 / 0.64 | 6 / 4 | 0 / 8 | 1 / 0 |  |
| 2026-08-22 | A | Oviedo | 1-0 | Segunda División | current | 0.21 / 1.65 | 2 / 5 | 2 / 9 | 1 / 3 |  |
| 2026-08-16 | A | Girona | 1-1 | Segunda División | current | 0.58 / 2.09 | 3 / 7 | 0 / 9 | 3 / 2 |  |
| 2026-05-31 | H | Mirandes | 1-0 | Segunda División | previous | N/A | 2 / 5 | 5 / 3 | 3 / 5 |  |
| 2026-05-24 | A | Cadiz | 0-3 | Segunda División | previous | N/A | 5 / 3 | 6 / 4 | 4 / 5 |  |
| 2026-05-18 | H | Huesca | 0-0 | Segunda División | previous | N/A | 2 / 2 | 3 / 7 | 2 / 2 |  |
| 2026-05-10 | H | Santander | 1-2 | Segunda División | previous | N/A | 4 / 5 | 5 / 3 | 6 / 2 |  |
| 2026-05-01 | A | La Coruna | 1-2 | Segunda División | previous | N/A | 6 / 6 | 2 / 9 | 2 / 4 |  |
| 2026-04-26 | H | Andorra | 0-4 | Segunda División | previous | N/A | 8 / 10 | 9 / 5 | 5 / 1 | margin |
| 2026-04-17 | A | Las Palmas | 0-2 | Segunda División | previous | N/A | 1 / 5 | 5 / 5 | 0 / 3 |  |
| 2026-04-11 | H | Albacete | 2-1 | Segunda División | previous | N/A | 5 / 3 | 10 / 4 | 1 / 3 |  |
| 2026-04-05 | A | Almeria | 1-2 | Segunda División | previous | N/A | 3 / 7 | 1 / 5 | 2 / 3 |  |
| 2026-04-02 | H | Zaragoza | 1-1 | Segunda División | previous | N/A | 5 / 8 | 3 / 10 | 2 / 0 |  |
| 2026-03-28 | A | Malaga | 0-0 | Segunda División | previous | N/A | 3 / 6 | 5 / 9 | 3 / 0 |  |
| 2026-03-21 | H | Ceuta | 5-2 | Segunda División | previous | N/A | 8 / 5 | 4 / 7 | 5 / 2 | total |
| 2026-03-14 | A | Valladolid | 2-3 | Segunda División | previous | N/A | 4 / 8 | 4 / 3 | 2 / 2 |  |
| 2026-03-08 | H | Eibar | 0-1 | Segunda División | previous | N/A | 3 / 6 | 10 / 2 | 4 / 0 |  |
| 2026-03-02 | A | Sp Gijon | 0-0 | Segunda División | previous | N/A | 0 / 4 | 0 / 5 | 3 / 2 |  |
| 2026-02-21 | H | Cultural Leonesa | 1-1 | Segunda División | previous | N/A | 1 / 2 | 7 / 0 | 3 / 3 |  |
| 2026-02-14 | A | Cordoba | 1-2 | Segunda División | previous | N/A | 4 / 6 | 4 / 7 | 1 / 1 |  |
| 2026-02-06 | H | Granada | 1-0 | Segunda División | previous | N/A | 2 / 1 | 3 / 5 | 1 / 3 |  |
| 2026-01-31 | A | Burgos | 1-2 | Segunda División | previous | N/A | 4 / 4 | 5 / 1 | 2 / 4 |  |
| 2026-01-24 | H | Sociedad B | 2-0 | Segunda División | previous | N/A | 7 / 4 | 6 / 3 | 2 / 1 |  |
| 2026-01-16 | A | Castellon | 0-2 | Segunda División | previous | N/A | 1 / 4 | 2 / 2 | 1 / 3 |  |
| 2026-01-11 | H | Valladolid | 3-0 | Segunda División | previous | N/A | 4 / 2 | 4 / 8 | 4 / 2 |  |
| 2026-01-04 | A | Albacete | 3-1 | Segunda División | previous | N/A | 5 / 4 | 5 / 5 | 3 / 1 |  |
| 2025-12-20 | H | Sp Gijon | 0-1 | Segunda División | previous | N/A | 4 / 5 | 6 / 7 | 2 / 3 |  |
| 2025-12-13 | A | Santander | 1-1 | Segunda División | previous | N/A | 4 / 7 | 7 / 7 | 3 / 4 |  |
| 2025-12-07 | H | Cordoba | 0-0 | Segunda División | previous | N/A | 2 / 3 | 4 / 5 | 3 / 1 |  |
| 2025-11-30 | A | Zaragoza | 2-3 | Segunda División | previous | N/A | 2 / 11 | 3 / 5 | 6 / 2 |  |
| 2025-11-22 | H | Almeria | 0-3 | Segunda División | previous | N/A | 10 / 4 | 5 / 0 | 1 / 4 |  |
| 2025-11-16 | A | Ceuta | 2-1 | Segunda División | previous | N/A | 5 / 1 | 3 / 6 | 2 / 2 |  |
| 2025-11-08 | A | Sociedad B | 1-2 | Segunda División | previous | N/A | 3 / 2 | 6 / 2 | 7 / 4 |  |
| 2025-11-01 | H | Burgos | 1-2 | Segunda División | previous | N/A | 3 / 2 | 9 / 4 | 3 / 3 |  |
| 2025-10-25 | A | Eibar | 0-0 | Segunda División | previous | N/A | 3 / 3 | 2 / 7 | 5 / 2 |  |
| 2025-10-19 | H | Malaga | 2-0 | Segunda División | previous | N/A | 8 / 5 | 7 / 5 | 1 / 0 |  |
| 2025-10-11 | A | Mirandes | 0-0 | Segunda División | previous | N/A | 7 / 4 | 10 / 3 | 1 / 6 |  |

</details>

## 2b. Team profile — Castellon (away)

* Sample: **40 matches** (Very strong evidence), 2025-10-12 → 2026-09-19, last match 9 days ago
* Composition: current season 6, previous 34; home 20, away 20; competitions: Segunda División (40); friendlies included 0, excluded 0
* Fields present: xG in 6, shots on target in 40, corners in 40, cards in 40 of 40 matches
* Ratings (1.00 = competition average): raw attack 1.364 / defence 0.671; venue raw 1.267 / 0.734 (venue weight 0.265); after venue blend 1.339 / 0.688; **after shrinkage 1.268 / 0.771** (weighted matches 14.7)
* Opponent context (information only, not a model input): average opponent attack faced 0.988 / defence faced 1.007; opponent-adjusted raw attack 1.355 / defence 0.679

**Recent form v baseline** (historical frequencies; the model's time-weighting already includes them)

* Last 5: 2.2 scored / 0.4 conceded per game (n=5); last 10: 1.7 / 0.5 (n=10); weighted baseline 1.84 / 0.9
* Recent attack: in line with baseline · recent defence: in line with baseline

**Home / away splits** (plain historical frequencies)

| Split | n | Evidence | GF | GA | O1.5 | O2.5 | BTTS | Clean sheets | Scored | SOT for/ag | Corners for/ag |
|---|---|---|---|---|---|---|---|---|---|---|---|
| All | 40 | Very strong | 1.73 | 1.02 | 30/40 (75%) | 19/40 (48%) | 22/40 (55%) | 15/40 | 32/40 | 5.3 / 3.8 (n=40) | 6.2 / 3.6 (n=40) |
| Home | 20 | Strong | 2.10 | 0.95 | 17/20 (85%) | 10/20 (50%) | 11/20 (55%) | 8/20 | 18/20 | 5.3 / 3.9 (n=20) | 5.7 / 3.4 (n=20) |
| Away | 20 | Strong | 1.35 | 1.10 | 13/20 (65%) | 9/20 (45%) | 11/20 (55%) | 7/20 | 14/20 | 5.3 / 3.8 (n=20) | 6.7 / 3.9 (n=20) |
| Current season | 6 | Small | 2.00 | 0.33 | 4/6 (67%) | 3/6 (50%) | 2/6 (33%) | 4/6 | 5/6 | 5.3 / 2.8 (n=6) | 5.7 / 3.8 (n=6) |
| Previous season | 34 | Strong | 1.68 | 1.15 | 26/34 (76%) | 16/34 (47%) | 20/34 (59%) | 11/34 | 27/34 | 5.3 / 4.0 (n=34) | 6.3 / 3.6 (n=34) |

**Extreme results in the sample** (kept, flagged):
* 2026-09-19: 5-0 v Tenerife (margin) — last-10 goals for 1.7 with / 1.33 without; against 0.5 / 0.56
* 2026-02-08: 4-0 @ Valladolid (margin)
* 2025-11-15: 5-4 v Sociedad B (total)

<details><summary>Matches used (raw observations)</summary>

| Date | Venue | Opponent | Score | Competition | Season | xG f/a | SOT f/a | Corners f/a | Cards f/a | Flag |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-09-19 | H | Tenerife | 5-0 | Segunda División | current | 2.64 / 0.69 | 5 / 4 | 0 / 5 | 0 / 2 | margin |
| 2026-09-12 | A | Girona | 2-1 | Segunda División | current | 2.72 / 0.94 | 9 / 5 | 11 / 4 | 2 / 6 |  |
| 2026-09-06 | H | Albacete | 2-0 | Segunda División | current | 3.55 / 0.39 | 7 / 3 | 7 / 3 | 1 / 1 |  |
| 2026-08-31 | A | Celta B | 2-1 | Segunda División | current | 1.52 / 0.88 | 5 / 4 | 3 / 3 | 3 / 1 |  |
| 2026-08-23 | H | Sabadell | 0-0 | Segunda División | current | 0.47 / 1.15 | 1 / 0 | 5 / 3 | 2 / 5 |  |
| 2026-08-14 | A | Sociedad B | 1-0 | Segunda División | current | 1.45 / 0.22 | 5 / 1 | 8 / 5 | 4 / 2 |  |
| 2026-05-31 | H | Eibar | 2-1 | Segunda División | previous | N/A | 9 / 2 | 8 / 6 | 0 / 1 |  |
| 2026-05-24 | A | Huesca | 1-0 | Segunda División | previous | N/A | 9 / 2 | 9 / 2 | 0 / 4 |  |
| 2026-05-15 | H | Cadiz | 1-1 | Segunda División | previous | N/A | 2 / 4 | 6 / 1 | 3 / 6 |  |
| 2026-05-09 | A | Ceuta | 1-1 | Segunda División | previous | N/A | 5 / 4 | 6 / 6 | 2 / 4 |  |
| 2026-05-02 | H | Cordoba | 1-2 | Segunda División | previous | N/A | 10 / 7 | 12 / 3 | 1 / 6 |  |
| 2026-04-25 | A | Malaga | 3-2 | Segunda División | previous | N/A | 8 / 7 | 3 / 1 | 4 / 2 |  |
| 2026-04-18 | H | Burgos | 3-1 | Segunda División | previous | N/A | 6 / 2 | 7 / 1 | 5 / 2 |  |
| 2026-04-12 | A | Mirandes | 2-2 | Segunda División | previous | N/A | 6 / 7 | 7 / 8 | 2 / 0 |  |
| 2026-04-06 | H | Granada | 3-2 | Segunda División | previous | N/A | 3 / 6 | 6 / 4 | 2 / 3 |  |
| 2026-04-02 | H | Almeria | 2-0 | Segunda División | previous | N/A | 6 / 3 | 8 / 5 | 4 / 4 |  |
| 2026-03-28 | A | Albacete | 1-1 | Segunda División | previous | N/A | 6 / 4 | 8 / 6 | 7 / 4 |  |
| 2026-03-23 | H | Cultural Leonesa | 1-1 | Segunda División | previous | N/A | 4 / 5 | 1 / 4 | 3 / 5 |  |
| 2026-03-15 | A | Sp Gijon | 1-4 | Segunda División | previous | N/A | 5 / 6 | 5 / 1 | 4 / 2 |  |
| 2026-03-07 | A | Sociedad B | 2-4 | Segunda División | previous | N/A | 8 / 8 | 6 / 2 | 3 / 6 |  |
| 2026-02-28 | H | Santander | 1-3 | Segunda División | previous | N/A | 3 / 7 | 3 / 3 | 3 / 2 |  |
| 2026-02-21 | A | Las Palmas | 1-1 | Segunda División | previous | N/A | 6 / 3 | 4 / 4 | 4 / 2 |  |
| 2026-02-15 | H | La Coruna | 2-0 | Segunda División | previous | N/A | 3 / 1 | 4 / 3 | 3 / 3 |  |
| 2026-02-08 | A | Valladolid | 4-0 | Segunda División | previous | N/A | 4 / 3 | 3 / 3 | 2 / 1 | margin |
| 2026-02-01 | H | Andorra | 2-0 | Segunda División | previous | N/A | 6 / 5 | 6 / 6 | 3 / 4 |  |
| 2026-01-25 | A | Zaragoza | 0-0 | Segunda División | previous | N/A | 3 / 0 | 13 / 3 | 4 / 4 |  |
| 2026-01-16 | H | Leganes | 2-0 | Segunda División | previous | N/A | 4 / 1 | 2 / 2 | 3 / 1 |  |
| 2026-01-11 | A | Granada | 0-0 | Segunda División | previous | N/A | 3 / 4 | 6 / 6 | 0 / 0 |  |
| 2026-01-03 | H | Huesca | 4-1 | Segunda División | previous | N/A | 8 / 6 | 1 / 3 | 3 / 2 |  |
| 2025-12-21 | A | Cadiz | 0-2 | Segunda División | previous | N/A | 2 / 4 | 12 / 6 | 2 / 4 |  |
| 2025-12-15 | H | Mirandes | 3-1 | Segunda División | previous | N/A | 6 / 2 | 5 / 4 | 4 / 2 |  |
| 2025-12-07 | A | La Coruna | 3-1 | Segunda División | previous | N/A | 5 / 3 | 9 / 3 | 6 / 4 |  |
| 2025-11-30 | H | Las Palmas | 1-0 | Segunda División | previous | N/A | 5 / 1 | 3 / 3 | 3 / 2 |  |
| 2025-11-22 | A | Andorra | 3-1 | Segunda División | previous | N/A | 6 / 4 | 4 / 2 | 2 / 2 |  |
| 2025-11-15 | H | Sociedad B | 5-4 | Segunda División | previous | N/A | 8 / 9 | 14 / 1 | 3 / 1 | total |
| 2025-11-10 | A | Burgos | 0-0 | Segunda División | previous | N/A | 2 / 3 | 6 / 5 | 2 / 2 |  |
| 2025-11-02 | H | Malaga | 2-1 | Segunda División | previous | N/A | 6 / 1 | 7 / 4 | 7 / 3 |  |
| 2025-10-26 | A | Almeria | 0-1 | Segunda División | previous | N/A | 4 / 4 | 3 / 6 | 2 / 1 |  |
| 2025-10-19 | H | Albacete | 0-1 | Segunda División | previous | N/A | 5 / 8 | 9 / 3 | 7 / 4 |  |
| 2025-10-12 | A | Eibar | 0-0 | Segunda División | previous | N/A | 5 / 0 | 7 / 1 | 4 / 1 |  |

</details>

## 3. Head-to-head

* Sample: **2 matches** — evidence strength **Very small**; used by the model: **no** (context only)
* 2025-09-29 → 2026-01-16 · avg 1.5 goals · O2.5 in 0/2 · BTTS in 0/2 · Segunda División
  * 2026-01-16: Castellon 2-0 Leganes (Segunda División)
  * 2025-09-29: Leganes 0-1 Castellon (Segunda División)
* Head-to-head is shown for context only; it is not a model input. Sample of this size cannot support conclusions on its own.

## 4. Model (football data only)

* League baseline (SP2): 1.474 home + 1.189 away goals per match (weighted n 180.0); O2.5 in 49%, BTTS in 53% of league matches
* **Model xG home 1.03** = league home average x home attack x away defence = 1.474 × 0.909 × 0.771
* **Model xG away 1.51** = league away average x away attack x home defence = 1.189 × 1.268 × 1.003
* Model total 2.55

| Market | Model probability | Confidence |
|---|---|---|
| Over 1.5 | 73% | High |
| Over 2.5 | 47% | High |
| Over 3.5 | 25% | High |
| Both teams to score | 51% | High |
| Home / draw / away | 25% / 27% / 48% | High |

Steps:
* 1. Every past match of the team (last 40, max 400 days, friendlies excluded when enough competitive matches exist) is expressed as goals scored / conceded relative to the average of that competition (league-normalised).
* 2. Matches are time-weighted (half-life 120 days) and averaged: raw attack and defence ratings.
* 3. Venue-specific rates are blended in with weight n_venue / (n_venue + 20.0).
* 4. Ratings are shrunk towards the league average (1.00): the attack/defence ratio (strength) with K = 5.0 and the overall tempo with K = 40.0 weighted matches — small samples stay close to the average.
* 5. Expected goals (lambda) = league venue average x attack x opponent's defence; score matrix = Dixon-Coles bivariate Poisson (rho -0.05), 0-10 goals per team; every market probability is read off that matrix.
* Bookmaker prices are not used anywhere in steps 1-5.

**Independent recomputation** — Dixon-Coles matrix rebuilt here from λ home / λ away and rho as published above; a mismatch would mean the file and the model disagree:

| Market | Published | Recomputed | Match |
|---|---|---|---|
| Over 1.5 | 73% | 73% | ✅ |
| Over 2.5 | 47% | 47% | ✅ |
| Over 3.5 | 25% | 25% | ✅ |
| Both teams to score | 51% | 51% | ✅ |
| Home win | 25% | 25% | ✅ |
| Draw | 27% | 27% | ✅ |
| Away win | 48% | 48% | ✅ |

## 5. Market comparison (separate layer)

* Market xG: home 1.25 / away 1.44 / total 2.7 (source: reference odds (football-data.co.uk)) — v model total 2.55 → gap -0.15

| Selection | Model % | Sportybet price | Implied % | Difference (pp) | EV |
|---|---|---|---|---|---|
| Leganes to win | 25% | 3.1 | 30% | -5.1 | -21.7% |
| Draw | 27% | 3.33 | 28% | -1.1 | -10.0% |
| Castellon to win | 48% | 2.3 | 42% | 6.2 | +9.7% |
| Leganes or draw | 52% | 1.56 | 58% | -6.2 | -18.4% |
| Leganes or Castellon | 73% | 1.32 | 72% | 1.1 | -3.7% |
| Draw or Castellon | 75% | 1.35 | 70% | 5.1 | +0.9% |
| Over 0.5 goals | 92% | 1.05 | 90% | 1.9 | -3.9% |
| Over 1.5 goals | 73% | 1.28 | 74% | -0.9 | -6.8% |
| Under 1.5 goals | 27% | 3.6 | 26% | 0.9 | -2.2% |
| Over 2.5 goals | 47% | 1.88 | 50% | -3.3 | -12.0% |
| Under 2.5 goals | 53% | 1.89 | 50% | 3.3 | +0.5% |
| Over 3.5 goals | 25% | 3.1 | 30% | -5.1 | -21.7% |
| Under 3.5 goals | 75% | 1.35 | 70% | 5.1 | +0.9% |
| Over 4.5 goals | 12% | 5.9 | 16% | -4.4 | -32.1% |
| Under 4.5 goals | 88% | 1.12 | 84% | 4.4 | -0.9% |
| Over 5.5 goals | 4% | 10.5 | 9% | -4.5 | -52.5% |
| Under 5.5 goals | 96% | 1.04 | 91% | 4.5 | -0.7% |
| Both teams to score | 51% | 1.69 | 55% | -4.0 | -14.1% |
| Not both teams to score | 49% | 2.05 | 45% | 4.0 | +0.8% |
| Leganes over 0.5 goals | 64% | 1.35 | 70% | -5.2 | -13.0% |
| Leganes over 1.5 goals | 28% | 2.6 | 36% | -8.3 | -28.1% |
| Leganes under 1.5 goals | 72% | 1.46 | 64% | 8.3 | +5.6% |
| Castellon over 0.5 goals | 78% | 1.25 | 75% | 3.0 | -2.5% |
| Castellon over 1.5 goals | 45% | 2.15 | 43% | 1.2 | -4.0% |
| Castellon under 1.5 goals | 55% | 1.65 | 57% | -1.2 | -8.7% |
| Over 8.5 corners | 60% | 1.67 | 55% | 4.8 | +0.0% |
| Under 8.5 corners | 40% | 2.05 | 45% | -4.8 | -17.8% |
| Over 9.5 corners | 48% | 2.1 | 44% | 3.4 | -0.1% |
| Under 9.5 corners | 52% | 1.66 | 56% | -3.4 | -12.9% |

Difference = model − market implied; EV = model probability × price − 1. The market never feeds back into the model.

## 6. Warnings and checks

* ℹ️ Castellon: recent scoring average affected by extreme result 5-0 v Tenerife (2026-09-19): last-10 goals for 1.70 with / 1.33 without, against 0.50 / 0.56
* ℹ️ Head-to-head sample: 2 matches — evidence strength Very small; context only

## 7. Traceability

final probability ← Dixon-Coles score matrix ← λ home / λ away ← league baseline × shrunk ratings ← time-weighted, league-normalised goals of the matches listed above ← results feeds (football-data.co.uk / Livescore).
