# Half-life / shrinkage grid (auto-run 2026-10-11)

Sweep of the `backtest/backtest.py --grid` harness (football-data main divisions, chronological replay,
train/test split, Brier score — lower is better). Best rows:

| HL | K | test_O25 | test_BTTS |
|----|-----|----------|-----------|
| 120 | 32 | 0.6824 | 0.6842 |
| 240 | 32 | 0.6827 | 0.6850 |
| 400 | 4 | 0.6944 | 0.6966 |
| 120 | 4 (harness default) | 0.6922 | 0.6941 |

**Decision: no production change.** This harness runs its own toy defaults (HL=120, K=4); the production
model uses different, individually validated parameters (HALF_LIFE_DAYS=150 — BOOST_RESULTS.md 2026-10-01;
SHRINK_K_STRENGTH=5 — model_variants 2026-09-28; SHRINK_K=40). Re-tuning production on a mismatched
harness would break the "never break anything" rule; the sweep machinery runs in ~4 minutes whenever a
re-check is wanted (`python backtest/backtest.py --grid`), and the shrinkage direction it shows (stronger
shrinkage helps) matches what production already does more aggressively than the toy default.
