"""Boost-study adoption + scoreline extraction (video takeaways, 2026-10-01)."""
import numpy as np

from scanner import CONFIG, probs_from_matrix, score_matrix, top_scorelines


def test_boost_params_adopted():
    # backtest/BOOST_RESULTS.md (2026-10-01): these beat the old values on train AND test with no market regression
    assert CONFIG["HALF_LIFE_DAYS"] == 150
    assert CONFIG["VENUE_K"] == 40.0
    assert CONFIG["MAX_MATCHES_PER_TEAM"] == 60
    # untouched by the adoption
    assert CONFIG["SHRINK_K"] == 40.0
    assert CONFIG["SHRINK_K_STRENGTH"] == 5.0
    assert CONFIG["DC_RHO"] == -0.05


def test_top_scorelines_order_and_bounds():
    M = score_matrix(1.4, 1.1, -0.05)
    top = top_scorelines(M, 3)
    assert len(top) == 3
    ps = [p for _, _, p in top]
    assert ps == sorted(ps, reverse=True)
    for i, j, p in top:
        assert 0 <= i < M.shape[0] and 0 <= j < M.shape[1]
        assert 0 < p <= 1
        assert p == round(float(M[i, j]), 4)
    # the three entries are exactly the matrix cells they claim to be
    assert abs(sum(p for _, _, p in top) - sum(float(M[i, j]) for i, j, _ in top)) < 1e-3  # entries are 4-dp rounded
    # plausible scorelines dominate a 1.4-1.1 expectation
    assert (1, 1) == (top[0][0], top[0][1]) or (1, 0) == (top[0][0], top[0][1])


def test_scorelines_share_matrix_totals():
    M = score_matrix(2.2, 0.8, -0.05)
    top = top_scorelines(M, 5)
    assert sum(p for _, _, p in top) <= 1.0
    # matrix probabilities already sum to 1 (Dixon-Coles normalised)
    assert abs(float(M.sum()) - 1.0) < 1e-9
    probs = probs_from_matrix(M)
    assert abs(probs["HW"] + probs["AW"] + float(np.trace(M)) - 1.0) < 1e-6  # HW + draws + AW = 1


def test_performance_snapshots_present_and_sane():
    bench, bias = CONFIG["BENCH"], CONFIG["BIAS"]
    assert bench["rows"] and all(len(r) == 3 for r in bench["rows"])
    for _, model, mkt in bench["rows"]:
        assert 0 < model < 1.5
        assert mkt is None or 0 < mkt < 1.5
    assert bias["fl"] and bias["o25"]
    for row in bias["fl"] + bias["o25"]:
        assert len(row) == 4
        assert 0 < row[1] <= 100 and 0 < row[2] <= 100  # implied/actual as percentages
    assert bias["n"] > 10000
