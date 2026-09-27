# ⚽ Goals Scanner — Sunday 27 September 2026

**Manual run 09:15 sast** · scan window Sun 27 Sep 09:10 → Mon 28 Sep 09:15 · **9 fixtures** across **3 competitions** · generated 09:15 SAST · next run Sun 12:00

> Sportybet (ZA): 9 of 9 fixtures priced.

## 🎟️ Parlays — manual run 09:15 · combined odds 2.70–3.50

_Prices: **Sportybet**. Window: whole 24 h window (fewer than 4 priced matches before the next run). 9 priced matches, 72 candidate legs. Legs are limited to 1X2, double chance and Over/Under 2.5 — markets with real prices. Each parlay maximises expected return (calibrated probability × price) inside the odds band._

### Parlay 1 — 2 legs @ **2.79** · win probability **34%** · expected return -4.1% · id `20260927-01`

| Kick-off | Match | Competition | Selection | Price | Fair odds | Probability | Leg edge |
|---|---|---|---|---|---|---|---|
| 09-27 20:00 | **UNAM Pumas v Atl. San Luis** | Liga MX | **Home win** | **2.05** | 2.08 | 48% | -1.2% |
| 09-28 01:00 | **Columbus Crew v Inter Miami** | MLS | **Over 2.5 goals** | **1.36** | 1.40 | 71% | -2.9% |

### Parlay 2 — 2 legs @ **2.94** · win probability **32%** · expected return -5.9% · id `20260927-02`

| Kick-off | Match | Competition | Selection | Price | Fair odds | Probability | Leg edge |
|---|---|---|---|---|---|---|---|
| 09-27 14:00 | **Valladolid v Cordoba** | Segunda División | **Home win** | **2.35** | 2.40 | 42% | -2.1% |
| 09-27 18:30 | **Burgos v Eldense** | Segunda División | **Home or draw (1X)** | **1.25** | 1.30 | 77% | -3.9% |

### Parlay 3 — 2 legs @ **3.34** · win probability **28%** · expected return -7.0% · id `20260927-03`

| Kick-off | Match | Competition | Selection | Price | Fair odds | Probability | Leg edge |
|---|---|---|---|---|---|---|---|
| 09-27 21:00 | **Oviedo v Sp Gijon** | Segunda División | **Home win** | **2.10** | 2.16 | 46% | -2.7% |
| 09-28 03:00 | **Club Leon v Juarez** | Liga MX | **Over 2.5 goals** | **1.59** | 1.66 | 60% | -4.4% |

**Parlay record:** 0/7 won (0%, expected 31%) · flat-stake return -100.0% · last 30 days 0/7 (0%, -100.0%)

> ⚠️ Honest expectation: a parlay at ~3.1 needs to win about 1 in 3 to break even. In the 2023-26 backtest this exact construction won 30-33% of the time and returned −4% to −13% per unit at average prices — the bookmaker margin compounds across legs. Treat parlays as entertainment with a known cost, not as income. Full test: `backtest/PARLAY_EXPERIMENT.md`.

## 🔒 Safest bets — manual run 09:15

_Selections across every modelled market whose probability is at least 70% on **both** views (calibrated model and the de-margined Sportybet price) at a Sportybet price of 1.30 or more. Three trebles are built from that pool — one leg per match, no match repeated — ranked by probability. Legs from the whole 24 h window (too few before the next run). Both lists are graded automatically (`data/safe_bets.csv`, `data/safe_accas.csv`)._

### Safest treble 1 — odds **2.21** · win probability **39%** · id `S20260927-03`

| Kick-off | Match | Competition | Selection | Price | Probability |
|---|---|---|---|---|---|
| 09-27 16:15 | **Mallorca v Almeria** | Segunda División | **Over 1.5 goals** | **1.31** | 74% |
| 09-27 20:00 | **UNAM Pumas v Atl. San Luis** | Liga MX | **UNAM Pumas or draw** | **1.30** | 73% |
| 09-27 21:00 | **Oviedo v Sp Gijon** | Segunda División | **Oviedo over 0.5 goals** | **1.30** | 73% |

### Safest treble 2 — odds **2.32** · win probability **38%** · id `S20260927-04`

| Kick-off | Match | Competition | Selection | Price | Probability |
|---|---|---|---|---|---|
| 09-27 14:00 | **Valladolid v Cordoba** | Segunda División | **Valladolid or Cordoba** | **1.31** | 73% |
| 09-27 18:30 | **Eibar v Las Palmas** | Segunda División | **Eibar or Las Palmas** | **1.30** | 73% |
| 09-28 05:10 | **Necaxa v Club America** | Liga MX | **Necaxa over 0.5 goals** | **1.36** | 73% |

### Safest single bets — top 13 of 13

| Kick-off | Match | Competition | Selection | Price | Probability | Model | Sportybet |
|---|---|---|---|---|---|---|---|
| 09-27 16:15 | Mallorca v Almeria | Segunda División | **Over 1.5 goals** | **1.31** | **74%** | 75% | 72% |
| 09-27 20:00 | UNAM Pumas v Atl. San Luis | Liga MX | **UNAM Pumas or draw** | **1.30** | **73%** | 74% | 73% |
| 09-27 21:00 | Oviedo v Sp Gijon | Segunda División | **Oviedo over 0.5 goals** | **1.30** | **73%** | 74% | 72% |
| 09-28 05:10 | Necaxa v Club America | Liga MX | **Necaxa over 0.5 goals** | **1.36** | **73%** | 77% | 69% |
| 09-27 18:30 | Eibar v Las Palmas | Segunda División | **Eibar or Las Palmas** | **1.30** | **73%** | 73% | 73% |
| 09-27 14:00 | Valladolid v Cordoba | Segunda División | **Valladolid or Cordoba** | **1.31** | **73%** | 73% | 73% |
| 09-27 16:15 | Mallorca v Almeria | Segunda División | **Mallorca or Almeria** | **1.31** | **72%** | 72% | 72% |
| 09-27 16:15 | Mallorca v Almeria | Segunda División | **Under 3.5 goals** | **1.31** | **72%** | 72% | 72% |
| 09-27 18:30 | Eibar v Las Palmas | Segunda División | **Under 3.5 goals** | **1.35** | **72%** | 73% | 70% |
| 09-27 18:30 | Burgos v Eldense | Segunda División | **Burgos or Eldense** | **1.32** | **72%** | 72% | 72% |
| 09-28 01:00 | Columbus Crew v Inter Miami | MLS | **Under 4.5 goals** | **1.43** | **71%** | 75% | 67% |
| 09-27 14:00 | Valladolid v Cordoba | Segunda División | **Cordoba over 0.5 goals** | **1.32** | **71%** | 71% | 71% |
| 09-27 18:30 | Eibar v Las Palmas | Segunda División | **Las Palmas under 1.5 goals** | **1.34** | **71%** | 71% | 70% |

_Track record — safest bets: 4/8 hit (50%, expected 74%); trebles: 0/3 won (0%, expected 40%)._

## 🎯 Shortlist

### Over 1.5 goals — 1 pick(s)
_Rule: final probability ≥ 84% (⭐⭐ ≥ 87%, ⭐⭐⭐ ≥ 90%). Backtest 2025/26–26/27: 87% of shortlisted matches (⭐⭐ 88%, ⭐⭐⭐ 95%) over 900 picks._

| # | Kick-off (SAST) | Competition | Match | Final | Rating | Model | Basis | Last-10 form | Exp. goals |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Mon 28 Sep 01:00 | USA · MLS | **Columbus Crew v Inter Miami** | **86%** | ⭐ | 86% | 🧮 model only | H 9/10 · A 9/10 | 1.8 – 1.6 |

### Over 2.5 goals — 1 pick(s)
_Rule: final probability ≥ 60% (⭐⭐ ≥ 64%, ⭐⭐⭐ ≥ 68%). Backtest 2025/26–26/27: 67% of shortlisted matches (⭐⭐ 71%, ⭐⭐⭐ 77%) over 1,675 picks._

| # | Kick-off (SAST) | Competition | Match | Final | Rating | Market (odds) | Model | Basis | Last-10 form | Exp. goals |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Mon 28 Sep 01:00 | USA · MLS | **Columbus Crew v Inter Miami** | **66%** | ⭐⭐ | – | 66% | 🧮 model only | H 8/10 · A 8/10 | 1.8 – 1.6 |

### Both teams to score — 1 pick(s)
_Rule: final probability ≥ 60% (⭐⭐ ≥ 63%, ⭐⭐⭐ ≥ 66%). Backtest 2025/26–26/27: 64% of shortlisted matches (⭐⭐ 65%, ⭐⭐⭐ 71%) over 1,800 picks._

| # | Kick-off (SAST) | Competition | Match | Final | Rating | Model | Basis | Last-10 form | Exp. goals |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Mon 28 Sep 01:00 | USA · MLS | **Columbus Crew v Inter Miami** | **67%** | ⭐⭐⭐ | 67% | 🧮 model only | H 7/10 · A 9/10 | 1.8 – 1.6 |

## 📊 Full scan — every fixture, ranked by Over 2.5 probability

| Kick-off (SAST) | Competition | Match | Exp. goals | O1.5 | O2.5 | BTTS | Market O2.5 (odds) | Model O2.5 | Basis | O2.5 last-10 form | Data |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Mon 28 Sep 01:00 | USA · MLS | Columbus Crew v Inter Miami | 1.8 – 1.6 | 86% | **66%** | 67% | – | 66% | 🧮 model only | H 8/10 · A 8/10 | ✅ |
| Mon 28 Sep 03:00 | Mexico · Liga MX | Club Leon v Juarez | 1.8 – 1.2 | 80% | **57%** | 58% | – | 57% | 🧮 model only | H 4/10 · A 6/10 | ✅ |
| Sun 27 Sep 20:00 | Mexico · Liga MX | UNAM Pumas v Atl. San Luis | 1.7 – 1.2 | 80% | **56%** | 58% | – | 56% | 🧮 model only | H 6/10 · A 7/10 | ✅ |
| Mon 28 Sep 05:10 | Mexico · Liga MX | Necaxa v Club America | 1.5 – 1.4 | 78% | **54%** | 58% | – | 54% | 🧮 model only | H 7/10 · A 7/10 | ✅ |
| Sun 27 Sep 14:00 | Spain · Segunda División | Valladolid v Cordoba | 1.5 – 1.2 | 76% | **51%** | 56% | 1.81 (51%) | 50% | 📈 market+model | H 2/10 · A 6/10 | ✅ |
| Sun 27 Sep 16:15 | Spain · Segunda División | Mallorca v Almeria | 1.5 – 1.2 | 75% | **50%** | 54% | 1.85 (50%) | 48% | 📈 market+model | H 3/10 · A 4/10 | ✅ |
| Sun 27 Sep 18:30 | Spain · Segunda División | Eibar v Las Palmas | 1.6 – 1.1 | 74% | **49%** | 52% | 1.91 (49%) | 49% | 📈 market+model | H 6/10 · A 6/10 | ✅ |
| Sun 27 Sep 18:30 | Spain · Segunda División | Burgos v Eldense | 1.5 – 1.0 | 71% | **44%** | 49% | 2.10 (44%) | 45% | 📈 market+model | H 4/10 · A 3/6 | ✅ |
| Sun 27 Sep 21:00 | Spain · Segunda División | Oviedo v Sp Gijon | 1.4 – 1.0 | 68% | **41%** | 46% | 2.29 (41%) | 41% | 📈 market+model | H 3/10 · A 5/10 | ✅ |

## 💰 Sportybet price check — shortlisted picks

_Fair odds = 1 / calibrated probability (90% sharp market, 10% model where prices exist). A positive edge means Sportybet pays more than the fair price; the backtest found positive edges of this kind on Over 2.5 returned about +3% at the best available price — small, but real. Negative edges mean the price is below fair value._

| Market | Match | Kick-off | Probability | Fair odds | Sportybet | Edge |
|---|---|---|---|---|---|---|
| Over 1.5 goals | **Columbus Crew v Inter Miami** | Mon 01:00 | 87% | 1.15 | **1.11** | -3.1% ❌ short |
| Over 2.5 goals | **Columbus Crew v Inter Miami** | Mon 01:00 | 71% | 1.40 | **1.36** | -2.9% ≈ fair |
| Both teams to score | **Columbus Crew v Inter Miami** | Mon 01:00 | 70% | 1.44 | **1.35** | -6.2% ❌ short |

## 🧾 Other markets — 1X2, double chance, team goals, corners, cards

_Probabilities are model + sharp-market blends (1X2, team goals) or the backtested count models (corners / cards, main leagues only). Sportybet column = 1X2 prices where the match was found._

| Kick-off (SAST) | Match | Competition | Home / Draw / Away | 1X / X2 | Home to score / 2+ | Away to score / 2+ | Corners exp. (O9.5 · O10.5) | Cards exp. (O3.5 · O4.5) | Sportybet 1X2 |
|---|---|---|---|---|---|---|---|---|---|
| Sun 27 Sep 14:00 | **Valladolid v Cordoba** | Spain · Segunda División | 42% / 27% / 31% | 69% / 58% | 77% / 44% | 71% / 35% | 9.1 (42% · 31%) | 5.6 (79% · 64%) | 2.35 / 3.40 / 2.95 |
| Sun 27 Sep 16:15 | **Mallorca v Almeria** | Spain · Segunda División | 46% / 28% / 27% | 73% / 54% | 78% / 45% | 68% / 32% | 9.2 (44% · 33%) | 5.1 (73% · 56%) | 2.10 / 3.33 / 3.50 |
| Sun 27 Sep 18:30 | **Burgos v Eldense** | Spain · Segunda División | 49% / 28% / 23% | 77% / 51% | 77% / 43% | 62% / 25% | 9.4 (46% · 35%) | 5.0 (71% · 54%) | 2.00 / 3.30 / 3.90 |
| Sun 27 Sep 18:30 | **Eibar v Las Palmas** | Spain · Segunda División | 49% / 27% / 23% | 77% / 51% | 79% / 46% | 65% / 29% | 9.2 (43% · 32%) | 4.6 (66% · 48%) | 1.94 / 3.40 / 3.90 |
| Sun 27 Sep 20:00 | **UNAM Pumas v Atl. San Luis** | Mexico · Liga MX | 48% / 26% / 26% | 74% / 52% | 82% / 52% | 70% / 34% | – | – | 2.05 / 3.60 / 3.50 |
| Sun 27 Sep 21:00 | **Oviedo v Sp Gijon** | Spain · Segunda División | 46% / 30% / 24% | 76% / 54% | 74% / 39% | 61% / 25% | 9.3 (45% · 33%) | 4.8 (69% · 52%) | 2.10 / 3.10 / 3.80 |
| Mon 28 Sep 01:00 | **Columbus Crew v Inter Miami** | USA · MLS | 35% / 23% / 42% | 58% / 65% | 83% / 52% | 80% / 48% | – | – | 2.85 / 4.10 / 2.30 |
| Mon 28 Sep 03:00 | **Club Leon v Juarez** | Mexico · Liga MX | 61% / 22% / 18% | 82% / 39% | 84% / 54% | 69% / 32% | – | – | 1.56 / 4.40 / 5.50 |
| Mon 28 Sep 05:10 | **Necaxa v Club America** | Mexico · Liga MX | 26% / 25% / 49% | 51% / 74% | 77% / 43% | 75% / 40% | – | – | 3.80 / 3.70 / 1.95 |

## 🔍 Match details (click to expand)

<details><summary><b>Valladolid v Cordoba</b> — Spain · Segunda División, Sun 27 Sep 14:00 · O2.5 51% · BTTS 56%</summary>

* Final expected goals: **1.48 – 1.24** (total 2.72, market+model) · P(O1.5) **76%** · P(O2.5) **51%** · P(O3.5) 29% · P(BTTS) **56%**
* Team-form model alone: 1.42 – 1.27 · P(O2.5) 50% · P(BTTS) 55% · Market-implied: 1.49 – 1.24
* Market: Over 2.5 @ 1.81 / Under 2.5 @ 1.91 (implied O2.5 51%) · 1X2 2.18 / 3.35 / 2.99
* League context: avg 1.45 home + 1.19 away goals · O2.5 in 50% · BTTS in 53% of matches
* **1X2** (fair, market+Sportybet+model): home 42% · draw 27% · away 31% → fair odds 2.40 / 3.68 / 3.21 · **Double chance** 1X 69% · 12 73% · X2 58%
* **Team goals:** Valladolid to score 77% (2+ 44%) · Cordoba to score 71% (2+ 35%)
* **Corners:** expected 4.7 (home) + 4.4 (away) = **9.1** · total O8.5 **55%** · O9.5 **42%** · O10.5 **31%** · O11.5 **22%** · home O3.5 64% · O4.5 48% · O5.5 34% · away O3.5 60% · O4.5 44% · O5.5 30% _(team averages: Valladolid 4.3 for / 3.7 against over 40 games, Cordoba 6.5 / 3.6 over 40)_
* **Cards** (yellow + red): expected 2.7 + 3.0 = **5.6** · total O3.5 **79%** · O4.5 **64%** · O5.5 **48%** _(team averages: Valladolid 3.1 received / 2.7 opponents booked, Cordoba 2.9 / 2.8)_
* **Sportybet:** 1X2 2.35 / 3.40 / 2.95 · DC 1X/12/X2 1.38 / 1.31 / 1.54 · goals O1.5 1.26 / U 3.75 · O2.5 1.82 / U 1.95 · O3.5 3.00 / U 1.38 · BTTS 1.65 / 2.10 · Valladolid goals O0.5 1.24 / U 3.75 · O1.5 2.15 / U 1.66 · Cordoba goals O0.5 1.32 / U 3.20 · O1.5 2.45 / U 1.50
* **Sportybet corners / cards:** total corners O8.5 1.73 / U 2.00 · O9.5 2.15 / U 1.61 · 1st-half corners O3.5 1.56 / U 2.30 · O4.5 2.15 / U 1.63 · O5.5 3.20 / U 1.31 _(no model — market only)_

**Valladolid** (Home) — 40 matches used (weighted 14.8), 18 home

| Stat | Value |
|---|---|
| Goals for / against per game | 0.82 / 1.45 |
| Home goals for / against | 0.86 / 1.15 |
| Attack / defence strength (1.00 = league avg) | 0.90 / 1.01 |
| Over 1.5 / 2.5 / 3.5 rate | 63% / 36% / 17% |
| BTTS rate | 37% |
| Clean sheets / failed to score | 22% / 44% |
| Avg total goals, last 5 | 1.80 |
| xG for / against (last 10) | 0.95 / 0.99 |
| Shots on target for / against (last 10) | 3.2 / 4.6 |
| Last 5 | D 1-1 @ Ceuta · L 0-3 v Oviedo · W 1-0 v Andorra · D 1-1 @ Cadiz · L 0-1 @ Eibar |

**Cordoba** (Away) — 40 matches used (weighted 14.8), 19 away

| Stat | Value |
|---|---|
| Goals for / against per game | 1.42 / 1.74 |
| Away goals for / against | 1.67 / 1.97 |
| Attack / defence strength (1.00 = league avg) | 1.05 / 1.09 |
| Over 1.5 / 2.5 / 3.5 rate | 89% / 68% / 38% |
| BTTS rate | 71% |
| Clean sheets / failed to score | 11% / 20% |
| Avg total goals, last 5 | 3.40 |
| xG for / against (last 10) | 1.60 / 1.68 |
| Shots on target for / against (last 10) | 5.0 / 4.1 |
| Last 5 | W 2-1 @ Albacete · L 0-2 v Almeria · L 2-3 @ Sabadell · L 1-3 v Granada · W 2-1 v Girona |

**Head-to-head** (last 2): avg 2.0 goals, O2.5 in 1/2, BTTS in 1/2  
31 Jan 26: Cordoba 3-1 Valladolid; 30 Aug 25: Valladolid 0-0 Cordoba

</details>

<details><summary><b>Mallorca v Almeria</b> — Spain · Segunda División, Sun 27 Sep 16:15 · O2.5 50% · BTTS 54%</summary>

* Final expected goals: **1.51 – 1.15** (total 2.66, market+model) · P(O1.5) **75%** · P(O2.5) **50%** · P(O3.5) 28% · P(BTTS) **54%**
* Team-form model alone: 1.43 – 1.15 · P(O2.5) 48% · P(BTTS) 53% · Market-implied: 1.52 – 1.15
* Market: Over 2.5 @ 1.85 / Under 2.5 @ 1.85 (implied O2.5 50%) · 1X2 2.06 / 3.26 / 3.33
* League context: avg 1.45 home + 1.19 away goals · O2.5 in 50% · BTTS in 53% of matches
* **1X2** (fair, market+Sportybet+model): home 46% · draw 28% · away 27% → fair odds 2.19 / 3.59 / 3.77 · **Double chance** 1X 73% · 12 72% · X2 54%
* **Team goals:** Mallorca to score 78% (2+ 45%) · Almeria to score 68% (2+ 32%)
* **Corners:** expected 4.9 (home) + 4.3 (away) = **9.2** · total O8.5 **57%** · O9.5 **44%** · O10.5 **33%** · O11.5 **23%** · home O3.5 67% · O4.5 51% · O5.5 37% · away O3.5 58% · O4.5 42% · O5.5 28% _(team averages: Mallorca 3.7 for / 5.7 against over 40 games, Almeria 4.1 / 5.1 over 40)_
* **Cards** (yellow + red): expected 2.5 + 2.6 = **5.1** · total O3.5 **73%** · O4.5 **56%** · O5.5 **40%** _(team averages: Mallorca 2.3 received / 2.1 opponents booked, Almeria 2.5 / 2.9)_
* **Sportybet:** 1X2 2.10 / 3.33 / 3.50 · DC 1X/12/X2 1.29 / 1.31 / 1.65 · goals O1.5 1.31 / U 3.40 · O2.5 1.96 / U 1.82 · O3.5 3.33 / U 1.31 · BTTS 1.76 / 1.95 · Mallorca goals O0.5 1.24 / U 3.80 · O1.5 2.10 / U 1.68 · Almeria goals O0.5 1.42 / U 2.75 · O1.5 2.95 / U 1.37

**Mallorca** (Home) — 40 matches used (weighted 14.3), 20 home

| Stat | Value |
|---|---|
| Goals for / against per game | 1.31 / 1.01 |
| Home goals for / against | 2.02 / 0.61 |
| Attack / defence strength (1.00 = league avg) | 1.00 / 0.91 |
| Over 1.5 / 2.5 / 3.5 rate | 78% / 46% / 12% |
| BTTS rate | 38% |
| Clean sheets / failed to score | 43% / 26% |
| Avg total goals, last 5 | 1.60 |
| xG for / against (last 10) | 1.28 / 0.72 |
| Shots on target for / against (last 10) | 4.4 / 2.5 |
| Last 5 | W 1-0 @ Sociedad B · W 2-0 v Sabadell · D 0-0 @ Eldense · W 3-0 v Ceuta · L 0-2 @ Granada |

**Almeria** (Away) — 40 matches used (weighted 14.8), 19 away

| Stat | Value |
|---|---|
| Goals for / against per game | 1.85 / 1.22 |
| Away goals for / against | 1.13 / 1.39 |
| Attack / defence strength (1.00 = league avg) | 1.07 / 0.98 |
| Over 1.5 / 2.5 / 3.5 rate | 79% / 59% / 34% |
| BTTS rate | 52% |
| Clean sheets / failed to score | 31% / 22% |
| Avg total goals, last 5 | 2.20 |
| xG for / against (last 10) | 1.41 / 0.98 |
| Shots on target for / against (last 10) | 4.8 / 3.8 |
| Last 5 | W 2-0 v Celta B · W 2-0 @ Cordoba · W 3-2 v Cadiz · L 0-1 @ Sabadell · L 0-1 @ Tenerife |

_No head-to-head data in the last two seasons._

</details>

<details><summary><b>Burgos v Eldense</b> — Spain · Segunda División, Sun 27 Sep 18:30 · O2.5 44% · BTTS 49%</summary>

* Final expected goals: **1.47 – 0.97** (total 2.44, market+model) · P(O1.5) **71%** · P(O2.5) **44%** · P(O3.5) 23% · P(BTTS) **49%**
* Team-form model alone: 1.45 – 1.01 · P(O2.5) 45% · P(BTTS) 49% · Market-implied: 1.48 – 0.97
* Market: Over 2.5 @ 2.10 / Under 2.5 @ 1.66 (implied O2.5 44%) · 1X2 1.90 / 3.25 / 3.83
* League context: avg 1.45 home + 1.19 away goals · O2.5 in 50% · BTTS in 53% of matches
* **1X2** (fair, market+Sportybet+model): home 49% · draw 28% · away 23% → fair odds 2.05 / 3.54 / 4.33 · **Double chance** 1X 77% · 12 72% · X2 51%
* **Team goals:** Burgos to score 77% (2+ 43%) · Eldense to score 62% (2+ 25%)
* **Corners:** expected 4.7 (home) + 4.7 (away) = **9.4** · total O8.5 **59%** · O9.5 **46%** · O10.5 **35%** · O11.5 **25%** · home O3.5 64% · O4.5 48% · O5.5 34% · away O3.5 64% · O4.5 48% · O5.5 34% _(team averages: Burgos 3.7 for / 5.6 against over 40 games, Eldense 6.8 / 4.0 over 6)_
* **Cards** (yellow + red): expected 2.3 + 2.7 = **5.0** · total O3.5 **71%** · O4.5 **54%** · O5.5 **38%** _(team averages: Burgos 2.5 received / 2.9 opponents booked, Eldense 1.8 / 2.4)_
* **Sportybet:** 1X2 2.00 / 3.30 / 3.90 · DC 1X/12/X2 1.25 / 1.32 / 1.72 · goals O1.5 1.38 / U 3.00 · O2.5 2.15 / U 1.67 · O3.5 3.90 / U 1.25 · BTTS 1.92 / 1.78 · Burgos goals O0.5 1.25 / U 3.70 · O1.5 2.15 / U 1.64 · Eldense goals O0.5 1.54 / U 2.40 · O1.5 3.50 / U 1.27
* **Sportybet corners / cards:** total corners O8.5 1.73 / U 2.00 · O9.5 2.15 / U 1.62 · 1st-half corners O3.5 1.56 / U 2.30 · O4.5 2.15 / U 1.63 · O5.5 3.20 / U 1.31 _(no model — market only)_

**Burgos** (Home) — 40 matches used (weighted 14.8), 20 home

| Stat | Value |
|---|---|
| Goals for / against per game | 1.27 / 0.82 |
| Home goals for / against | 1.65 / 0.87 |
| Attack / defence strength (1.00 = league avg) | 1.00 / 0.91 |
| Over 1.5 / 2.5 / 3.5 rate | 55% / 38% / 26% |
| BTTS rate | 42% |
| Clean sheets / failed to score | 43% / 32% |
| Avg total goals, last 5 | 2.40 |
| xG for / against (last 10) | 1.29 / 1.26 |
| Shots on target for / against (last 10) | 3.3 / 3.8 |
| Last 5 | W 2-1 @ Las Palmas · W 3-1 v Ceuta · D 0-0 @ Oviedo · D 2-2 v Sociedad B · L 0-1 @ Sp Gijon |

**Eldense** (Away) — 6 matches used (weighted 5.2), 3 away

| Stat | Value |
|---|---|
| Goals for / against per game | 0.67 / 1.30 |
| Away goals for / against | 0.36 / 1.26 |
| Attack / defence strength (1.00 = league avg) | 0.94 / 1.00 |
| Over 1.5 / 2.5 / 3.5 rate | 49% / 49% / 16% |
| BTTS rate | 34% |
| Clean sheets / failed to score | 35% / 48% |
| Avg total goals, last 5 | 1.80 |
| xG for / against (last 10) | 0.85 / 1.35 |
| Shots on target for / against (last 10) | 4.0 / 5.0 |
| Last 5 | L 1-2 v Eibar · W 1-0 @ Sp Gijon · D 0-0 v Mallorca · L 0-1 @ Leganes · D 2-2 v Cadiz |

_No head-to-head data in the last two seasons._

</details>

<details><summary><b>Eibar v Las Palmas</b> — Spain · Segunda División, Sun 27 Sep 18:30 · O2.5 49% · BTTS 52%</summary>

* Final expected goals: **1.56 – 1.06** (total 2.62, market+model) · P(O1.5) **74%** · P(O2.5) **49%** · P(O3.5) 27% · P(BTTS) **52%**
* Team-form model alone: 1.52 – 1.12 · P(O2.5) 49% · P(BTTS) 53% · Market-implied: 1.56 – 1.05
* Market: Over 2.5 @ 1.91 / Under 2.5 @ 1.80 (implied O2.5 49%) · 1X2 1.92 / 3.28 / 3.76
* League context: avg 1.45 home + 1.19 away goals · O2.5 in 50% · BTTS in 53% of matches
* **1X2** (fair, market+Sportybet+model): home 49% · draw 27% · away 23% → fair odds 2.03 / 3.64 / 4.28 · **Double chance** 1X 77% · 12 73% · X2 51%
* **Team goals:** Eibar to score 79% (2+ 46%) · Las Palmas to score 65% (2+ 29%)
* **Corners:** expected 4.7 (home) + 4.5 (away) = **9.2** · total O8.5 **56%** · O9.5 **43%** · O10.5 **32%** · O11.5 **22%** · home O3.5 64% · O4.5 48% · O5.5 34% · away O3.5 60% · O4.5 44% · O5.5 30% _(team averages: Eibar 3.6 for / 5.6 against over 40 games, Las Palmas 4.7 / 4.4 over 40)_
* **Cards** (yellow + red): expected 2.4 + 2.2 = **4.6** · total O3.5 **66%** · O4.5 **48%** · O5.5 **32%** _(team averages: Eibar 2.6 received / 2.5 opponents booked, Las Palmas 1.6 / 2.4)_
* **Sportybet:** 1X2 1.94 / 3.40 / 3.90 · DC 1X/12/X2 1.24 / 1.30 / 1.76 · goals O1.5 1.28 / U 3.60 · O2.5 1.89 / U 1.88 · O3.5 3.20 / U 1.35 · BTTS 1.74 / 1.98 · Eibar goals O0.5 1.20 / U 4.25 · O1.5 1.94 / U 1.80 · Las Palmas goals O0.5 1.45 / U 2.65 · O1.5 3.10 / U 1.34

**Eibar** (Home) — 40 matches used (weighted 14.8), 20 home

| Stat | Value |
|---|---|
| Goals for / against per game | 1.59 / 0.81 |
| Home goals for / against | 1.80 / 0.93 |
| Attack / defence strength (1.00 = league avg) | 1.06 / 0.91 |
| Over 1.5 / 2.5 / 3.5 rate | 63% / 57% / 23% |
| BTTS rate | 40% |
| Clean sheets / failed to score | 56% / 14% |
| Avg total goals, last 5 | 2.40 |
| xG for / against (last 10) | 0.92 / 0.82 |
| Shots on target for / against (last 10) | 3.7 / 5.0 |
| Last 5 | W 2-1 @ Eldense · W 4-0 @ Celta B · W 3-0 v Granada · W 1-0 @ Andorra · W 1-0 v Valladolid |

**Las Palmas** (Away) — 40 matches used (weighted 14.8), 21 away

| Stat | Value |
|---|---|
| Goals for / against per game | 1.42 / 1.21 |
| Away goals for / against | 1.39 / 1.63 |
| Attack / defence strength (1.00 = league avg) | 1.03 / 0.99 |
| Over 1.5 / 2.5 / 3.5 rate | 78% / 53% / 18% |
| BTTS rate | 60% |
| Clean sheets / failed to score | 36% / 15% |
| Avg total goals, last 5 | 2.60 |
| xG for / against (last 10) | 0.95 / 1.34 |
| Shots on target for / against (last 10) | 4.0 / 4.1 |
| Last 5 | L 1-2 v Burgos · W 1-0 @ Cadiz · D 0-0 v Leganes · L 2-5 @ Girona · W 2-0 @ Ceuta |

**Head-to-head** (last 2): avg 4.0 goals, O2.5 in 2/2, BTTS in 2/2  
29 Mar 26: Eibar 3-1 Las Palmas; 19 Oct 25: Las Palmas 3-1 Eibar

</details>

<details><summary><b>UNAM Pumas v Atl. San Luis</b> — Mexico · Liga MX, Sun 27 Sep 20:00 · O2.5 56% · BTTS 58%</summary>

* Final expected goals: **1.73 – 1.21** (total 2.94, model only) · P(O1.5) **80%** · P(O2.5) **56%** · P(O3.5) 34% · P(BTTS) **58%**
* Team-form model alone: 1.73 – 1.21 · P(O2.5) 56% · P(BTTS) 58%
* Market 1X2: 1.95 / 3.53 / 3.40 (no O/U odds published in feed)
* League context: avg 1.59 home + 1.23 away goals · O2.5 in 53% · BTTS in 58% of matches
* **1X2** (fair, market+Sportybet+model): home 48% · draw 26% · away 26% → fair odds 2.08 / 3.92 / 3.80 · **Double chance** 1X 74% · 12 74% · X2 52%
* **Team goals:** UNAM Pumas to score 82% (2+ 52%) · Atl. San Luis to score 70% (2+ 34%)
* **Sportybet:** 1X2 2.05 / 3.60 / 3.50 · DC 1X/12/X2 1.30 / 1.29 / 1.70 · goals O1.5 1.22 / U 4.10 · O2.5 1.71 / U 2.10 · O3.5 2.70 / U 1.45 · BTTS 1.61 / 2.25 · UNAM Pumas goals O0.5 1.18 / U 4.50 · O1.5 1.88 / U 1.86 · Atl. San Luis goals O0.5 1.34 / U 3.10 · O1.5 2.60 / U 1.47
* **Sportybet corners / cards:** total corners O8.5 1.61 / U 2.15 · O9.5 1.99 / U 1.73 · O10.5 2.55 / U 1.45 · O11.5 3.33 / U 1.28 · home corners O3.5 1.25 / U 3.75 · O4.5 1.53 / U 2.40 · O5.5 1.98 / U 1.77 · away corners O3.5 1.78 / U 1.96 · O4.5 2.65 / U 1.44 · O5.5 4.10 / U 1.21 · 1st-half corners O3.5 1.50 / U 2.45 · O4.5 2.05 / U 1.70 · O5.5 2.95 / U 1.35 _(no model — market only)_ · total cards O3.5 1.42 / U 2.65 · O4.5 1.92 / U 1.79 · O5.5 2.85 / U 1.37

**UNAM Pumas** (Home) — 40 matches used (weighted 16.5), 19 home

| Stat | Value |
|---|---|
| Goals for / against per game | 1.56 / 1.34 |
| Home goals for / against | 1.67 / 1.26 |
| Attack / defence strength (1.00 = league avg) | 1.03 / 0.99 |
| Over 1.5 / 2.5 / 3.5 rate | 81% / 52% / 34% |
| BTTS rate | 58% |
| Clean sheets / failed to score | 24% / 26% |
| Avg total goals, last 5 | 2.60 |
| Last 5 | D 1-1 @ Atlas · L 0-3 @ Guadalajara Chivas · W 3-1 v Club Leon · L 0-2 @ Club Tijuana · D 1-1 v Necaxa |

**Atl. San Luis** (Away) — 38 matches used (weighted 14.1), 18 away

| Stat | Value |
|---|---|
| Goals for / against per game | 1.31 / 1.69 |
| Away goals for / against | 1.26 / 1.92 |
| Attack / defence strength (1.00 = league avg) | 0.99 / 1.05 |
| Over 1.5 / 2.5 / 3.5 rate | 91% / 63% / 35% |
| BTTS rate | 60% |
| Clean sheets / failed to score | 13% / 31% |
| Avg total goals, last 5 | 3.00 |
| Last 5 | W 3-1 v Necaxa · L 0-2 @ Club Leon · L 0-3 v Guadalajara Chivas · W 3-1 @ Monterrey · D 1-1 v Pachuca |

**Head-to-head** (last 2): avg 1.5 goals, O2.5 in 0/2, BTTS in 0/2  
18 Apr 26: Atl. San Luis 0-2 UNAM Pumas; 23 Oct 25: UNAM Pumas 0-1 Atl. San Luis

</details>

<details><summary><b>Oviedo v Sp Gijon</b> — Spain · Segunda División, Sun 27 Sep 21:00 · O2.5 41% · BTTS 46%</summary>

* Final expected goals: **1.36 – 0.95** (total 2.31, market+model) · P(O1.5) **68%** · P(O2.5) **41%** · P(O3.5) 20% · P(BTTS) **46%**
* Team-form model alone: 1.20 – 1.14 · P(O2.5) 41% · P(BTTS) 48% · Market-implied: 1.37 – 0.93
* Market: Over 2.5 @ 2.29 / Under 2.5 @ 1.56 (implied O2.5 41%) · 1X2 1.98 / 3.13 / 3.74
* League context: avg 1.45 home + 1.19 away goals · O2.5 in 50% · BTTS in 53% of matches
* **1X2** (fair, market+Sportybet+model): home 46% · draw 30% · away 24% → fair odds 2.16 / 3.34 / 4.22 · **Double chance** 1X 76% · 12 70% · X2 54%
* **Team goals:** Oviedo to score 74% (2+ 39%) · Sp Gijon to score 61% (2+ 25%)
* **Corners:** expected 5.2 (home) + 4.0 (away) = **9.3** · total O8.5 **57%** · O9.5 **45%** · O10.5 **33%** · O11.5 **23%** · home O3.5 71% · O4.5 56% · O5.5 42% · away O3.5 54% · O4.5 37% · O5.5 24% _(team averages: Oviedo 4.4 for / 4.7 against over 40 games, Sp Gijon 4.1 / 5.3 over 40)_
* **Cards** (yellow + red): expected 2.4 + 2.4 = **4.8** · total O3.5 **69%** · O4.5 **52%** · O5.5 **35%** _(team averages: Oviedo 2.4 received / 1.9 opponents booked, Sp Gijon 2.3 / 2.6)_
* **Sportybet:** 1X2 2.10 / 3.10 / 3.80 · DC 1X/12/X2 1.26 / 1.34 / 1.67 · goals O1.5 1.46 / U 2.65 · O2.5 2.40 / U 1.54 · O3.5 4.50 / U 1.19 · BTTS 2.05 / 1.68 · Oviedo goals O0.5 1.30 / U 3.30 · O1.5 2.40 / U 1.53 · Sp Gijon goals O0.5 1.59 / U 2.25 · O1.5 3.80 / U 1.24
* **Sportybet corners / cards:** total corners O8.5 1.72 / U 2.00 · O9.5 2.15 / U 1.62 · 1st-half corners O3.5 1.56 / U 2.30 · O4.5 2.15 / U 1.63 · O5.5 3.20 / U 1.31 _(no model — market only)_

**Oviedo** (Home) — 40 matches used (weighted 14.3), 20 home

| Stat | Value |
|---|---|
| Goals for / against per game | 0.79 / 1.25 |
| Home goals for / against | 0.34 / 0.64 |
| Attack / defence strength (1.00 = league avg) | 0.87 / 0.94 |
| Over 1.5 / 2.5 / 3.5 rate | 55% / 41% / 16% |
| BTTS rate | 28% |
| Clean sheets / failed to score | 41% / 50% |
| Avg total goals, last 5 | 1.80 |
| xG for / against (last 10) | 0.95 / 0.90 |
| Shots on target for / against (last 10) | 2.8 / 3.6 |
| Last 5 | L 1-3 @ Sabadell · W 3-0 @ Valladolid · D 0-0 v Burgos · W 1-0 @ Albacete · L 0-1 v Leganes |

**Sp Gijon** (Away) — 40 matches used (weighted 14.8), 19 away

| Stat | Value |
|---|---|
| Goals for / against per game | 1.29 / 1.04 |
| Away goals for / against | 1.51 / 1.28 |
| Attack / defence strength (1.00 = league avg) | 1.02 / 0.95 |
| Over 1.5 / 2.5 / 3.5 rate | 58% / 45% / 28% |
| BTTS rate | 47% |
| Clean sheets / failed to score | 31% / 30% |
| Avg total goals, last 5 | 1.80 |
| xG for / against (last 10) | 1.08 / 1.02 |
| Shots on target for / against (last 10) | 4.2 / 3.5 |
| Last 5 | W 3-1 @ Andorra · L 0-1 v Eldense · L 0-2 v Girona · W 1-0 @ Tenerife · W 1-0 v Burgos |

_No head-to-head data in the last two seasons._

</details>

<details><summary><b>Columbus Crew v Inter Miami</b> — USA · MLS, Mon 28 Sep 01:00 · O2.5 66% · BTTS 67%</summary>

* Final expected goals: **1.76 – 1.62** (total 3.37, model only) · P(O1.5) **86%** · P(O2.5) **66%** · P(O3.5) 44% · P(BTTS) **67%**
* Team-form model alone: 1.76 – 1.62 · P(O2.5) 66% · P(BTTS) 67%
* Market 1X2: 2.66 / 3.91 / 2.19 (no O/U odds published in feed)
* League context: avg 1.75 home + 1.41 away goals · O2.5 in 63% · BTTS in 64% of matches
* **1X2** (fair, market+Sportybet+model): home 35% · draw 23% · away 42% → fair odds 2.86 / 4.36 / 2.38 · **Double chance** 1X 58% · 12 77% · X2 65%
* **Team goals:** Columbus Crew to score 83% (2+ 52%) · Inter Miami to score 80% (2+ 48%)
* **Sportybet:** 1X2 2.85 / 4.10 / 2.30 · DC 1X/12/X2 1.62 / 1.26 / 1.43 · goals O1.5 1.11 / U 7.40 · O2.5 1.36 / U 3.30 · O3.5 1.87 / U 1.98 · BTTS 1.35 / 3.25 · Columbus Crew goals O0.5 1.17 / U 5.00 · O1.5 1.82 / U 2.00 · Inter Miami goals O0.5 1.13 / U 6.10 · O1.5 1.63 / U 2.30
* **Sportybet corners / cards:** total corners O8.5 1.73 / U 1.99 · O9.5 2.15 / U 1.61 · O10.5 2.85 / U 1.38 · home corners O3.5 1.48 / U 2.60 · O4.5 1.98 / U 1.80 · O5.5 2.90 / U 1.40 · away corners O3.5 1.53 / U 2.45 · O4.5 2.12 / U 1.70 · O5.5 3.20 / U 1.34 · 1st-half corners O3.5 1.56 / U 2.30 · O4.5 2.15 / U 1.63 · O5.5 3.20 / U 1.31 _(no model — market only)_

**Columbus Crew** (Home) — 37 matches used (weighted 16.2), 17 home

| Stat | Value |
|---|---|
| Goals for / against per game | 1.46 / 1.61 |
| Home goals for / against | 1.42 / 1.24 |
| Attack / defence strength (1.00 = league avg) | 0.97 / 0.99 |
| Over 1.5 / 2.5 / 3.5 rate | 89% / 70% / 34% |
| BTTS rate | 68% |
| Clean sheets / failed to score | 20% / 15% |
| Avg total goals, last 5 | 2.60 |
| Last 5 | W 2-0 @ CF Montreal · L 0-1 v New York Red Bulls · L 1-2 @ DC United · W 3-0 v Colorado Rapids · L 1-3 v New England Revolution |

**Inter Miami** (Away) — 40 matches used (weighted 16.8), 18 away

| Stat | Value |
|---|---|
| Goals for / against per game | 2.53 / 1.78 |
| Away goals for / against | 2.10 / 1.66 |
| Attack / defence strength (1.00 = league avg) | 1.16 / 1.03 |
| Over 1.5 / 2.5 / 3.5 rate | 94% / 80% / 71% |
| BTTS rate | 84% |
| Clean sheets / failed to score | 15% / 4% |
| Avg total goals, last 5 | 4.40 |
| Last 5 | D 2-2 v San Diego FC · D 2-2 v Nashville SC · D 1-1 @ Chicago Fire · D 2-2 v Atlanta Utd · W 7-1 v CF Montreal |

**Head-to-head** (last 1): avg 4.0 goals, O2.5 in 1/1, BTTS in 1/1  
02 Aug 26: Inter Miami 2-2 Columbus Crew

</details>

<details><summary><b>Club Leon v Juarez</b> — Mexico · Liga MX, Mon 28 Sep 03:00 · O2.5 57% · BTTS 58%</summary>

* Final expected goals: **1.81 – 1.16** (total 2.98, model only) · P(O1.5) **80%** · P(O2.5) **57%** · P(O3.5) 35% · P(BTTS) **58%**
* Team-form model alone: 1.81 – 1.16 · P(O2.5) 57% · P(BTTS) 58%
* Market 1X2: 1.55 / 4.04 / 4.96 (no O/U odds published in feed)
* League context: avg 1.59 home + 1.23 away goals · O2.5 in 53% · BTTS in 58% of matches
* **1X2** (fair, market+Sportybet+model): home 61% · draw 22% · away 18% → fair odds 1.65 / 4.64 / 5.62 · **Double chance** 1X 82% · 12 78% · X2 39%
* **Team goals:** Club Leon to score 84% (2+ 54%) · Juarez to score 69% (2+ 32%)
* **Sportybet:** 1X2 1.56 / 4.40 / 5.50 · DC 1X/12/X2 1.16 / 1.21 / 2.25 · goals O1.5 1.18 / U 4.60 · O2.5 1.59 / U 2.35 · O3.5 2.45 / U 1.54 · BTTS 1.68 / 2.10 · Club Leon goals O0.5 1.10 / U 6.20 · O1.5 1.53 / U 2.40 · Juarez goals O0.5 1.49 / U 2.50 · O1.5 3.30 / U 1.30
* **Sportybet corners / cards:** total corners O8.5 1.32 / U 3.10 · O9.5 1.54 / U 2.35 · O10.5 1.85 / U 1.85 · O11.5 2.30 / U 1.55 · home corners O4.5 1.34 / U 3.10 · O5.5 1.63 / U 2.20 · away corners O3.5 1.70 / U 2.08 · O4.5 2.35 / U 1.55 · O5.5 3.50 / U 1.28 · 1st-half corners O3.5 1.32 / U 3.10 · O4.5 1.67 / U 2.05 · O5.5 2.25 / U 1.56 _(no model — market only)_ · total cards O4.5 1.66 / U 2.10

**Club Leon** (Home) — 38 matches used (weighted 14.2), 18 home

| Stat | Value |
|---|---|
| Goals for / against per game | 1.28 / 1.50 |
| Home goals for / against | 1.76 / 1.12 |
| Attack / defence strength (1.00 = league avg) | 0.99 / 1.00 |
| Over 1.5 / 2.5 / 3.5 rate | 85% / 48% / 27% |
| BTTS rate | 58% |
| Clean sheets / failed to score | 24% / 19% |
| Avg total goals, last 5 | 2.40 |
| Last 5 | D 1-1 @ Queretaro · W 2-0 v Atl. San Luis · L 1-3 @ UNAM Pumas · D 1-1 @ Atlante · W 2-0 v Monterrey |

**Juarez** (Away) — 40 matches used (weighted 14.6), 20 away

| Stat | Value |
|---|---|
| Goals for / against per game | 1.13 / 2.21 |
| Away goals for / against | 0.94 / 2.63 |
| Attack / defence strength (1.00 = league avg) | 0.94 / 1.16 |
| Over 1.5 / 2.5 / 3.5 rate | 87% / 66% / 38% |
| BTTS rate | 66% |
| Clean sheets / failed to score | 9% / 26% |
| Avg total goals, last 5 | 2.80 |
| Last 5 | W 2-0 v Tigres UANL · L 1-2 @ Santos Laguna · L 0-2 v Pachuca · L 0-4 @ Toluca · L 1-2 v Club America |

**Head-to-head** (last 2): avg 3.0 goals, O2.5 in 1/2, BTTS in 1/2  
19 Apr 26: Club Leon 3-1 Juarez; 27 Sep 25: Juarez 2-0 Club Leon

</details>

<details><summary><b>Necaxa v Club America</b> — Mexico · Liga MX, Mon 28 Sep 05:10 · O2.5 54% · BTTS 58%</summary>

* Final expected goals: **1.45 – 1.39** (total 2.84, model only) · P(O1.5) **78%** · P(O2.5) **54%** · P(O3.5) 32% · P(BTTS) **58%**
* Team-form model alone: 1.45 – 1.39 · P(O2.5) 54% · P(BTTS) 58%
* Market 1X2: 3.63 / 3.62 / 1.85 (no O/U odds published in feed)
* League context: avg 1.59 home + 1.23 away goals · O2.5 in 53% · BTTS in 58% of matches
* **1X2** (fair, market+Sportybet+model): home 26% · draw 25% · away 49% → fair odds 3.87 / 3.99 / 2.04 · **Double chance** 1X 51% · 12 75% · X2 74%
* **Team goals:** Necaxa to score 77% (2+ 43%) · Club America to score 75% (2+ 40%)
* **Sportybet:** 1X2 3.80 / 3.70 / 1.95 · DC 1X/12/X2 1.78 / 1.28 / 1.27 · goals O1.5 1.21 / U 4.25 · O2.5 1.68 / U 2.15 · O3.5 2.65 / U 1.47 · BTTS 1.61 / 2.25 · Necaxa goals O0.5 1.36 / U 3.00 · O1.5 2.70 / U 1.44 · Club America goals O0.5 1.16 / U 4.80 · O1.5 1.79 / U 1.96

**Necaxa** (Home) — 38 matches used (weighted 14.1), 19 home

| Stat | Value |
|---|---|
| Goals for / against per game | 1.13 / 1.71 |
| Home goals for / against | 1.15 / 1.33 |
| Attack / defence strength (1.00 = league avg) | 0.94 / 1.04 |
| Over 1.5 / 2.5 / 3.5 rate | 83% / 62% / 32% |
| BTTS rate | 74% |
| Clean sheets / failed to score | 8% / 23% |
| Avg total goals, last 5 | 2.60 |
| Last 5 | L 1-3 @ Atl. San Luis · L 0-1 v Puebla · D 1-1 @ Tigres UANL · L 1-3 v Cruz Azul · D 1-1 @ UNAM Pumas |

**Club America** (Away) — 40 matches used (weighted 14.4), 19 away

| Stat | Value |
|---|---|
| Goals for / against per game | 1.81 / 1.21 |
| Away goals for / against | 1.64 / 1.48 |
| Attack / defence strength (1.00 = league avg) | 1.08 / 0.97 |
| Over 1.5 / 2.5 / 3.5 rate | 82% / 57% / 29% |
| BTTS rate | 53% |
| Clean sheets / failed to score | 36% / 14% |
| Avg total goals, last 5 | 3.80 |
| Last 5 | D 2-2 v Guadalajara Chivas · L 3-4 @ Cruz Azul · W 2-0 v Puebla · W 2-1 @ Juarez · W 3-0 v Atl. San Luis |

**Head-to-head** (last 1): avg 2.0 goals, O2.5 in 0/1, BTTS in 0/1  
31 Jan 26: Club America 2-0 Necaxa

</details>

## 📈 Trackers (auto-settled from results)

### Shortlist tracker

| Market | Settled | Hits | Hit rate | Last 30 days | Pending | Avg odds | Flat-stake return |
|---|---|---|---|---|---|---|---|
| Over 1.5 goals | 5 | 4 | 80% | 4/5 (80%) | 6 | – | – |
| Over 2.5 goals | 9 | 6 | 67% | 6/9 (67%) | 8 | – | – |
| Both teams to score | 9 | 5 | 56% | 5/9 (56%) | 6 | – | – |

_Flat-stake return is for model evaluation only: 1 unit on every Over 2.5 pick at the average market odds._

### Parlay ledger

| Scope | Settled | Won | Hit rate | Expected | Avg odds | Flat-stake return |
|---|---|---|---|---|---|---|
| All time | 7 | 0 | 0% | 31% | 3.25 | -100.0% |
| Last 30 days | 7 | 0 | 0% | 31% | 3.25 | -100.0% |
| Run 17:00 | 6 | 0 | 0% | 30% | 3.27 | -100.0% |
| Run manual 18:27 | 1 | 0 | 0% | 31% | 3.14 | -100.0% |

| Id | Created | Run | Legs | Odds | Prob. | Status |
|---|---|---|---|---|---|---|
| `20260927-03` | 2026-09-27 07:01 | 07:00 | Oviedo v Sp Gijon — Home win @ 2.10; Club Leon v Juarez — Over 2.5 goals @ 1.59 | 3.34 | 28% | ⏳ pending |
| `20260927-02` | 2026-09-27 07:01 | 07:00 | Valladolid v Cordoba — Home win @ 2.35; Burgos v Eldense — Home or draw (1X) @ 1.25 | 2.94 | 32% | ⏳ pending |
| `20260927-01` | 2026-09-27 07:01 | 07:00 | UNAM Pumas v Atl. San Luis — Home win @ 2.05; Columbus Crew v Inter Miami — Over 2.5 goals @ 1.36 | 2.79 | 34% | ⏳ pending |
| `20260926-16` | 2026-09-26 18:27 | manual 18:27 | Atlanta Utd v New York City — Home win @ 2.45; Philadelphia Union v Orlando City — Over 2.5 goals @ 1.28 | 3.14 | 31% | ❌ lost |
| `20260926-15` | 2026-09-26 17:01 | 17:00 | Philadelphia Union v Orlando City — Home or away (12) @ 1.18; Real Salt Lake v New England Revolution — Away win @ 2.95 | 3.48 | 28% | ❌ lost |
| `20260926-14` | 2026-09-26 17:01 | 17:00 | CF Montreal v FC Cincinnati — Home win @ 2.75; Houston Dynamo v Sporting Kansas City — Home or draw (1X) @ 1.18 | 3.24 | 30% | ❌ lost |
| `20260926-13` | 2026-09-26 17:01 | 17:00 | Guadalajara Chivas v Queretaro — Home or draw (1X) @ 1.17; Charlotte v Chicago Fire — Home win @ 2.35 | 2.75 | 37% | ❌ lost |
| `20260926-11` | 2026-09-26 16:28 | 17:00 | Guadalajara Chivas v Queretaro — Home or draw (1X) @ 1.17; CF Montreal v FC Cincinnati — Home win @ 2.75 | 3.22 | 31% | ❌ lost |
| `20260926-12` | 2026-09-26 16:28 | 17:00 | Houston Dynamo v Sporting Kansas City — Home or draw (1X) @ 1.18; Real Salt Lake v New England Revolution — Away win @ 2.95 | 3.48 | 28% | ❌ lost |
| `20260926-10` | 2026-09-26 16:28 | 17:00 | Charlotte v Chicago Fire — Home win @ 2.30; Philadelphia Union v Orlando City — Home win @ 1.50 | 3.45 | 29% | ❌ lost |
| `20260926-09` | 2026-09-26 15:37 | manual 15:37 | Newport County v Grimsby — Away win @ 1.93; Bristol Rvs v Exeter — Home win @ 1.77 | 3.42 | 28% | ⏳ pending |
| `20260926-08` | 2026-09-26 15:37 | manual 15:37 | Cambridge v AFC Wimbledon — Under 2.5 goals @ 2.05; Boston Utd v Fylde — Over 2.5 goals @ 1.50 | 3.07 | 32% | ⏳ pending |

## ℹ️ Method

* **Team-form model:** attack/defence strengths from goals scored and conceded over the last two seasons, normalised by league averages, time-weighted (half-life 120 days) and strongly shrunk towards league average (K=40 matches — goal form is noisy; the backtest showed weak shrinkage made the old model over-confident by 5-10 points).
* **Market-implied expected goals:** where the feed publishes odds, the Over/Under 2.5 price fixes the expected total and the 1X2 prices fix the home/away split. The final expected goals are 90% market / 9% model (📈 market+model). Without odds the model is used alone (🧮 model only).
* Probabilities for every market come from a Dixon-Coles adjusted Poisson score matrix (ρ=-0.05).
* **Backtest (52,000 matches, 2023-26, no look-ahead):** final probabilities are calibrated to within ±3 points; the model alone beats league averages but never beats the market, and when the model is more bullish than the market those matches under-deliver — so 'Model' above is information, not a value signal. Full results: `backtest/RESULTS.md`.
* **Extra markets (v3):** 1X2 / double chance = score matrix blended 10/90 with the sharp market (Betfair Exchange, else market average), de-margined with the power method (removes the favourite-longshot bias). Corners and cards = team for/against rates, league-normalised and shrunk (K=40 / K=20), negative binomial totals; cards include a referee factor where the referee is published (UK leagues). Both are calibrated within ~2 points on the standard lines (`backtest/MARKETS_RESULTS.md`). Half-time corners have no free data source and are shown as Sportybet prices only, without a model.
* **Parlays:** legs only from 1X2, double chance and Over/Under 2.5 at real Sportybet prices; each parlay maximises calibrated probability × price inside the 2.70-3.50 band, 2-4 legs, distinct matches. Backtest 2023-26: win rate 30-33%, return −4% to −13% per unit — see the warning in the parlay section.
* **Sportybet prices** are display / payout information only; they never enter the probability model. Headlines in the parlay dossier come from Google News and are context only.
* Data: football-data.co.uk. All times are SAST (Africa/Johannesburg). ⚠️ marks teams with too little history (typically newly promoted from a division not covered) — they are never shortlisted.
* This is statistical information, not advice. Past hit-rates do not guarantee future results.
