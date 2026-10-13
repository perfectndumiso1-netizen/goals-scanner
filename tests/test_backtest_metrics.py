from __future__ import annotations

import pandas as pd

from backtest.backtest import cluster_bootstrap_ci, pick_stats, season_forward_scorecard


def test_cluster_bootstrap_ci_is_deterministic_and_date_clustered():
    values = [1.0, -1.0, 1.0, -1.0]
    dates = pd.to_datetime(["2026-01-01", "2026-01-01", "2026-01-02", "2026-01-02"])
    first = cluster_bootstrap_ci(values, dates, reps=300, seed=7)
    second = cluster_bootstrap_ci(values, dates, reps=300, seed=7)
    assert first == second
    assert first[0] <= 0 <= first[1]


def test_pick_stats_reports_positive_no_vig_closing_line_value():
    picks = pd.DataFrame({
        "date": pd.to_datetime(["2026-01-01", "2026-01-02"]),
        "y25": [1, 0], "p": [0.7, 0.7],
        "oo": [2.0, 2.0], "ou": [2.0, 2.0],
        "coo": [1.6, 1.6], "cou": [2.4, 2.4],
    })
    stats = pick_stats(picks, "y25", "p", ("oo", "coo"))
    assert abs(stats["clv_pp"] - 10.0) < 1e-9
    assert stats["clv_pp_ci_low"] <= stats["clv_pp"] <= stats["clv_pp_ci_high"]
    assert "roi_open_ci_low" in stats and "roi_close_ci_high" in stats


def test_season_forward_scorecard_splits_by_july_to_june_seasons():
    results = pd.DataFrame({
        "date": pd.to_datetime(["2025-08-01", "2026-01-01", "2026-08-01", "2027-01-01"]),
        "fin_O25": [0.7, 0.4, 0.6, 0.3], "y25": [1, 0, 1, 0],
    })
    scorecard = season_forward_scorecard(results)
    assert scorecard["season"].tolist() == ["25/26", "26/27"]
    assert scorecard["matches"].tolist() == [2, 2]
    assert (scorecard["log_loss_ci_low"] <= scorecard["log_loss"]).all()
