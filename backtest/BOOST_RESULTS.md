# Boost studies — video takeaways (Liam Hartley / Systematic Sports)

_run 2026-10-01 07:36; gate: test mean must improve and no market may regress by >0.0005_
loaded 52,331 matches in 2s

## A. Parameter sweep (select on train ≤ 2025-06-30, confirm on test 25/26–26/27)

_base = production: HL=120, KV=20, K tempo=40, K strength=5, max_n=40, div_K=30, rho=-0.05, clamp 0.15–4.5_

  replay r_HL120.0_K40.0_KV20.0_K_s5.0_div_K30.0_max_days400_max_n40 in 27s
| variant | train n | train mean LL | test n | test O15 | test O25 | test BTTS | test HW | test AW | test mean LL |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| **base (production)** | 23,887 | 0.6299 | 14,213 | 0.5392 | 0.6808 | 0.6841 | 0.6510 | 0.5829 | 0.6276 |
_sanity vs backtest/RESULTS.md two-K row (n=14,135): O15 0.5395 O25 0.6808 BTTS 0.6842 HW 0.6507 AW 0.5825_

### rho (Dixon-Coles low-score correction)

| rho | train mean | test mean | test O15 | test O25 | test BTTS | test HW | test AW |
|:--|--:|--:|--:|--:|--:|--:|--:|
| +0.00 | 0.6300 | 0.6278 | 0.5394 | 0.6808 | 0.6846 | 0.6510 | 0.5831 |
| -0.03 | 0.6299 | 0.6276 | 0.5392 | 0.6808 | 0.6843 | 0.6510 | 0.5829 |
| -0.05 | 0.6299 | 0.6276 | 0.5392 | 0.6808 | 0.6841 | 0.6510 | 0.5829 |
| -0.08 | 0.6299 | 0.6275 | 0.5391 | 0.6808 | 0.6838 | 0.6511 | 0.5828 |
| -0.10 | 0.6299 | 0.6275 | 0.5391 | 0.6808 | 0.6837 | 0.6512 | 0.5827 |
train selects rho = -0.05 (production -0.05)

### HL (form half-life days)

| value | train mean | test mean | test O15 | test O25 | test BTTS | test HW | test AW | gate vs base |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
  replay r_HL60_K40.0_KV20.0_K_s5.0_div_K30.0_max_days400_max_n40 in 23s
| 60 | 0.6313 | 0.6287 | 0.5397 | 0.6818 | 0.6839 | 0.6530 | 0.5853 | FAIL: test mean not better (+0.0011); O25 regresses +0.0010; HW regresses +0.0019; AW regresses +0.0024 |
  replay r_HL90_K40.0_KV20.0_K_s5.0_div_K30.0_max_days400_max_n40 in 23s
| 90 | 0.6302 | 0.6277 | 0.5391 | 0.6811 | 0.6840 | 0.6513 | 0.5831 | FAIL: test mean not better (+0.0002) |
| 120 | 0.6299 | 0.6276 | 0.5392 | 0.6808 | 0.6841 | 0.6510 | 0.5829 | prod |
  replay r_HL150_K40.0_KV20.0_K_s5.0_div_K30.0_max_days400_max_n40 in 25s
| 150 | 0.6299 | 0.6276 | 0.5390 | 0.6807 | 0.6842 | 0.6511 | 0.5831 | FAIL: test mean not better (+0.0000) |
  replay r_HL180_K40.0_KV20.0_K_s5.0_div_K30.0_max_days400_max_n40 in 22s
| 180 | 0.6300 | 0.6278 | 0.5390 | 0.6807 | 0.6843 | 0.6514 | 0.5836 | FAIL: test mean not better (+0.0002); AW regresses +0.0007 |
train selects HL (form half-life days) = 150 (production 120.0)

### KV (venue blend K)

| value | train mean | test mean | test O15 | test O25 | test BTTS | test HW | test AW | gate vs base |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
  replay r_HL120.0_K40.0_KV10_K_s5.0_div_K30.0_max_days400_max_n40 in 29s
| 10 | 0.6304 | 0.6282 | 0.5393 | 0.6809 | 0.6843 | 0.6522 | 0.5841 | FAIL: test mean not better (+0.0006); HW regresses +0.0012; AW regresses +0.0012 |
| 20 | 0.6299 | 0.6276 | 0.5392 | 0.6808 | 0.6841 | 0.6510 | 0.5829 | prod |
  replay r_HL120.0_K40.0_KV30_K_s5.0_div_K30.0_max_days400_max_n40 in 32s
| 30 | 0.6297 | 0.6274 | 0.5391 | 0.6807 | 0.6840 | 0.6507 | 0.5824 | ok |
  replay r_HL120.0_K40.0_KV40_K_s5.0_div_K30.0_max_days400_max_n40 in 32s
| 40 | 0.6297 | 0.6273 | 0.5391 | 0.6807 | 0.6840 | 0.6505 | 0.5823 | ok |
train selects KV (venue blend K) = 40 (production 20.0)

### max_n (matches per team)

| value | train mean | test mean | test O15 | test O25 | test BTTS | test HW | test AW | gate vs base |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|
  replay r_HL120.0_K40.0_KV20.0_K_s5.0_div_K30.0_max_days400_max_n30 in 27s
| 30 | 0.6304 | 0.6280 | 0.5394 | 0.6811 | 0.6843 | 0.6518 | 0.5835 | FAIL: test mean not better (+0.0004); HW regresses +0.0007; AW regresses +0.0007 |
| 40 | 0.6299 | 0.6276 | 0.5392 | 0.6808 | 0.6841 | 0.6510 | 0.5829 | prod |
  replay r_HL120.0_K40.0_KV20.0_K_s5.0_div_K30.0_max_days400_max_n60 in 36s
| 60 | 0.6298 | 0.6275 | 0.5391 | 0.6808 | 0.6841 | 0.6508 | 0.5827 | ok |
train selects max_n (matches per team) = 60 (production 40)

### Composed candidate

  replay r_HL150_K40.0_KV40_K_s5.0_div_K30.0_max_days400_max_n60 in 26s
| variant | train n | train mean LL | test n | test O15 | test O25 | test BTTS | test HW | test AW | test mean LL |
|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| composed {'HL': 150, 'KV': 40, 'max_n': 60} rho=-0.05 | 23,887 | 0.6296 | 14,220 | 0.5389 | 0.6806 | 0.6841 | 0.6503 | 0.5822 | 0.6272 |
| base (production) | 23,887 | 0.6299 | 14,213 | 0.5392 | 0.6808 | 0.6841 | 0.6510 | 0.5829 | 0.6276 |
**GATE PASSED — adopt: {'HL': 150, 'KV': 40, 'max_n': 60}**


## B. Market-bias study (favorite-longshot / public money)

_proportional de-margin on opening average prices; every outcome of every priced match is one row; gap = actual − implied (percentage points). Robust = same sign in ≥3 seasons with n≥150 there._

### Over 2.5 market

| implied bucket | n | mean implied | actual | gap (pp) | robust? |
|:--|--:|--:|--:|--:|:--|
| 0.30–0.35 | 246 | 33.3% | 30.9% | -2.4 |  |
| 0.35–0.40 | 1,356 | 37.9% | 40.3% | +2.3 | YES |
| 0.40–0.45 | 3,751 | 42.9% | 42.3% | -0.5 |  |
| 0.45–0.50 | 5,701 | 47.6% | 48.4% | +0.8 |  |
| 0.50–0.55 | 5,871 | 52.4% | 52.7% | +0.3 |  |
| 0.55–0.60 | 4,017 | 57.2% | 58.9% | +1.6 |  |
| 0.60–0.65 | 2,130 | 62.1% | 64.5% | +2.4 | YES |
| 0.65–0.70 | 883 | 67.1% | 69.2% | +2.1 |  |
| 0.70–0.75 | 335 | 71.9% | 72.5% | +0.7 |  |
| 0.75–0.80 | 103 | 76.8% | 82.5% | +5.7 |  |

### 1X2 favorite-longshot (all outcomes pooled)

| implied bucket | n | mean implied | actual | gap (pp) | robust? |
|:--|--:|--:|--:|--:|:--|
| 0.05–0.10 | 1,168 | 8.0% | 4.1% | -3.8 | YES |
| 0.10–0.15 | 2,541 | 12.8% | 10.7% | -2.1 | YES |
| 0.15–0.20 | 4,899 | 17.8% | 16.6% | -1.2 | YES |
| 0.20–0.25 | 10,068 | 22.8% | 21.9% | -0.9 |  |
| 0.25–0.30 | 20,804 | 27.4% | 27.7% | +0.3 |  |
| 0.30–0.35 | 8,373 | 32.2% | 31.9% | -0.3 |  |
| 0.35–0.40 | 5,951 | 37.5% | 37.1% | -0.4 |  |
| 0.40–0.45 | 5,495 | 42.4% | 43.3% | +0.9 |  |
| 0.45–0.50 | 4,202 | 47.4% | 46.8% | -0.6 |  |
| 0.50–0.55 | 3,221 | 52.4% | 53.4% | +1.0 |  |
| 0.55–0.60 | 2,285 | 57.3% | 61.1% | +3.8 | YES |
| 0.60–0.65 | 1,432 | 62.3% | 61.7% | -0.6 |  |
| 0.65–0.70 | 1,065 | 67.4% | 71.3% | +3.8 | YES |
| 0.70–0.75 | 749 | 72.3% | 77.2% | +4.8 |  |
| 0.75–0.80 | 531 | 77.3% | 81.4% | +4.0 |  |
| 0.80–0.85 | 282 | 82.2% | 86.2% | +4.0 |  |

_interpretation: a positive gap in the low buckets = longshots win more than implied (public loves longshots); a negative gap there = classic favorite-longshot bias (longshots overpriced → value sits with favourites). Robust rows only feed a display note — odds never filter anything._


## C. xG ratings — 26/27 window check

_football-data publishes HxG/AxG from season 26/27 only (older seasons have none; Understat is blocked). Evaluation window = matches since 2026-07-01 with ≥4 time-weighted matches per team. Small n → the bar for adoption is high; anything inconclusive is NOT adopted._

matches with published xG in the pool: 1,089
| variant | n | O15 | O25 | BTTS | HW | AW | mean LL | gate vs base |
|:--|--:|--:|--:|--:|--:|--:|--:|:--|
| base (goals only) | 2,408 | 0.5237 | 0.6770 | 0.6814 | 0.6582 | 0.5953 | 0.6271 | — |
  replay xg_w=0.3 in 37s
| xg_w=0.3 | 2,408 | 0.5236 | 0.6770 | 0.6814 | 0.6576 | 0.5947 | 0.6269 | no gain |
  replay xg_w=0.5 in 36s
| xg_w=0.5 | 2,408 | 0.5236 | 0.6771 | 0.6815 | 0.6574 | 0.5945 | 0.6268 | no gain |
  replay xg_w=0.7 in 36s
| xg_w=0.7 | 2,408 | 0.5236 | 0.6771 | 0.6814 | 0.6573 | 0.5944 | 0.6268 | no gain |
  replay xg_w=1.0 in 42s
| xg_w=1.0 | 2,408 | 0.5235 | 0.6770 | 0.6811 | 0.6577 | 0.5951 | 0.6269 | no gain |
**No xG variant clears the gate — xG stays display-only (as today). Re-run when the 26/27 sample is bigger.**


_done in 458s._
