"""The daily acca builds: gates, the search, the ledger and the app payload shape.

These tests exist because the failure mode they guard against is quiet and expensive: a "value" leg that is
really a data fault (the model rating a friendly underdog 29% against a 0.6% price), or a "3.00 acca" padded
with six 1.20 legs that costs 40% in vig where two 1.73 legs costs 15%.
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import accas            # noqa: E402
import appdata          # noqa: E402
from safe import Bet    # noqa: E402


NOW = datetime(2026, 10, 3, 12, 0)


def bet(i: int, odds: float, p: float, p_sb: float | None, sel: str = "O15", ko: str = "2026-10-03 16:00",
        date: str = "2026-10-03", country: str = "Testland") -> Bet:
    return Bet((date, country, f"Home{i}", f"Away{i}"), "TL", "Test League", f"Home{i}", f"Away{i}",
               ko, sel, p, p, p_sb, odds)


# ------------------------------------------------------------------ gates
def test_gate_rejects_every_way_a_leg_can_be_wrong():
    assert accas.gate([bet(0, 1.73, 0.80, 0.79)]) == [], "1 pp edge (below MIN_EDGE): paying the vig for nothing"
    assert accas.gate([bet(1, 1.73, 0.80, 0.60)]) == [], "20 pp edge (above MAX_EDGE): a data fault, not value"
    assert accas.gate([bet(2, 1.73, 0.50, 0.40)]) == [], "model probability below MIN_MODEL_P"
    assert accas.gate([bet(3, 1.10, 0.95, 0.90)]) == [], "price below MIN_ODDS"
    assert accas.gate([bet(4, 4.00, 0.80, 0.70)]) == [], "price above MAX_LEG_ODDS"
    assert accas.gate([bet(5, 1.73, 0.80, None)]) == [], "no de-vigged market view to measure the edge against"
    assert len(accas.gate([bet(6, 1.73, 0.80, 0.74)])) == 1, "a legitimate leg must survive"


def test_pool_only_keeps_playable_gated_legs():
    """A real stub row: safe.selections() is allowed to do its normal work, so the gate is tested end to end.

    The OU 1.5 pair (1.55 / 4.41) de-margins to exactly 74% — against a model probability of 80% that is a
    6 pp edge, inside the gate. The same row priced at 1.10 is rejected for being too short to be a leg.
    """
    class Row:
        def __init__(self, i, ko, data_ok=True, over=1.55, under=4.41):
            self.data_ok = data_ok
            self.sb = {"OU": {1.5: (over, under)}}
            self.sb_full = {}
            self.audit = {}
            self.p_final = {"O15": 0.80}
            self.extra = type("X", (), {"x12": None, "xg": None, "tg": None,
                                        "corner_p": None, "card_p": None})()
            self.odds = self.p = None
            self.fx = {"date": pd.Timestamp("2026-10-03"), "country": "Testland", "home": f"H{i}", "away": f"A{i}",
                       "kickoff": pd.Timestamp(ko), "div": "TL", "league": "Test League"}

    window_end = pd.Timestamp("2026-10-04 03:00")
    good = accas.pool_from_rows([Row(0, "2026-10-03 16:00")], NOW, window_end)
    assert len(good) == 1 and good[0].sel == "O15" and good[0].odds == pytest.approx(1.55, abs=0.01)

    # the window bound is the APP window (the day the user sees), so a late-night leg is still buildable…
    late = accas.pool_from_rows([Row(5, "2026-10-04 01:30")], NOW, window_end)
    assert len(late) == 1, "a leg inside the app window but after the next report hour must still be buildable"
    # …and nothing beyond it is
    assert accas.pool_from_rows([Row(6, "2026-10-04 09:00")], NOW, window_end) == [], "beyond the app window"

    assert accas.pool_from_rows([Row(1, "2026-10-03 16:00", data_ok=False)], NOW, window_end) == [], "failed the data check"
    assert accas.pool_from_rows([Row(2, "2026-10-03 11:00")], NOW, window_end) == [], "already kicked off"
    assert accas.pool_from_rows([Row(3, "2026-10-09 16:00")], NOW, window_end) == [], "outside the window"
    assert accas.pool_from_rows([Row(4, "2026-10-03 16:00", over=1.10, under=8.0)], NOW, window_end) == [], "price too short"
    assert accas.pool_from_rows([], NOW, window_end) == []


# ------------------------------------------------------------------ the search
def test_build_prefers_two_legs_over_padding_with_six():
    """Same 3.00 payout, less vig: the builder must never reach the price with short legs."""
    pool = [bet(0, 1.73, 0.80, 0.74), bet(1, 1.73, 0.80, 0.74)] + [bet(i, 1.20, 0.75, 0.70) for i in range(2, 8)]
    plan = accas.plan(pool, target=3.00, n=1)
    assert plan and len(plan[0]) == 2, f"expected the 2-leg build, got {[round(b.odds, 2) for b in plan[0]] if plan else None}"
    assert all(b.odds > 1.5 for b in plan[0])
    assert abs(accas.acca_odds(plan[0]) - 3.00) <= accas.TOL


def test_build_maximises_combined_probability():
    """Two routes to ~3.00: the builder takes the one with the higher combined model probability."""
    safe_route = [bet(0, 1.732, 0.82, 0.76), bet(1, 1.732, 0.82, 0.76)]        # 0.6724
    worse_route = [bet(2, 1.50, 0.70, 0.64), bet(3, 2.00, 0.68, 0.62)]          # 0.476
    plan = accas.plan(safe_route + worse_route, target=3.00, n=1)
    got = accas.acca_p(plan[0])
    assert abs(got - 0.6724) < 1e-6, f"picked a {got:.3f} build instead of the 0.672 one"


def test_one_leg_per_match_and_disjoint_builds():
    twin = [bet(0, 1.73, 0.80, 0.74), bet(0, 1.73, 0.80, 0.74, sel="U15")]
    assert len(accas._one_per_match(twin)) == 1, "two markets of one match must never form an acca leg pair"
    plans = accas.plan([bet(i, 1.73, 0.80, 0.74) for i in range(6)], target=3.00, n=3)
    assert len(plans) == 3
    used = [b.key for p in plans for b in p]
    assert len(set(used)) == len(used), "accas share a match: one shock could take all three"


def test_build_lands_inside_tolerance_and_leg_bounds():
    plan = accas.plan([bet(i, 1.44, 0.78, 0.72) for i in range(6)], target=3.00, n=1)
    legs = plan[0]
    assert accas.MIN_LEGS <= len(legs) <= accas.MAX_LEGS
    assert abs(accas.acca_odds(legs) - 3.00) <= accas.TOL


def test_nothing_is_invented_when_the_pool_is_empty():
    assert accas.plan([], n=3) == []
    assert accas.best_combo([]) is None


# ------------------------------------------------------------------ ledger + settlement
def test_add_records_the_build_and_never_duplicates_it(tmp_path: Path):
    empty = pd.DataFrame(columns=accas.ACCA_COLS)
    legs = [bet(0, 1.73, 0.80, 0.74), bet(1, 1.73, 0.80, 0.74)]
    df, ids = accas.add(empty, [legs], NOW, "run 12:00", NOW + timedelta(hours=15))
    assert len(df) == 1 and ids == ["A20261003-01"]
    assert df.iloc[0]["status"] == "pending" and float(df.iloc[0]["odds"]) == 2.99
    # the same build seen again on the next run keeps its id and is not appended twice
    df2, ids2 = accas.add(df, [legs], NOW + timedelta(minutes=30), "run 12:30", NOW + timedelta(hours=15))
    assert len(df2) == 1 and ids2 == ids


def test_settlement_of_a_build_on_real_results():
    legs = [bet(0, 1.73, 0.80, 0.74), bet(1, 1.73, 0.80, 0.74)]
    df, _ = accas.add(pd.DataFrame(columns=accas.ACCA_COLS), [legs], NOW, "run", NOW + timedelta(hours=15))
    results = pd.DataFrame([{"country": "Testland", "home": "Home0", "away": "Away0", "date": pd.Timestamp("2026-10-03"), "hg": 2, "ag": 0},
                            {"country": "Testland", "home": "Home1", "away": "Away1", "date": pd.Timestamp("2026-10-03"), "hg": 2, "ag": 1}])
    settled = accas.settle(df, results, NOW + timedelta(days=1))
    assert settled.iloc[0]["status"] == "won", settled.iloc[0].to_dict()
    results.loc[1, "hg"] = 0          # 0-0: one leg loses, so the acca loses
    results.loc[1, "ag"] = 0
    lost = accas.settle(df, results, NOW + timedelta(days=1))
    assert lost.iloc[0]["status"] == "lost"


def test_summary_reports_the_scoreboard_in_units_per_unit():
    legs = [bet(0, 1.73, 0.80, 0.74), bet(1, 1.73, 0.80, 0.74)]
    df, _ = accas.add(pd.DataFrame(columns=accas.ACCA_COLS), [legs], NOW, "run", NOW + timedelta(hours=15))
    df.loc[0, ["status"]] = ["won"]
    summ = accas.summary(df, NOW)
    assert summ["all"]["n"] == 1 and summ["all"]["won"] == 1
    assert summ["all"]["roi"] == pytest.approx(2.99 - 1, abs=0.01)   # 1u staked, 3.00-ish returned
    assert "ROI" in summ["break_even_note"]


# ------------------------------------------------------------------ the app payload
class FakeBet(Bet):
    pass


def test_payload_shape_the_app_reads():
    plans = [[bet(0, 1.73, 0.80, 0.74), bet(1, 1.73, 0.82, 0.76)]]
    ctx = {"accas": {"target": 3.0, "pool": 17, "plans": plans, "ids": ["A20261003-01"],
                     "summary": {"all": {"n": 3, "won": 1}}, "recent": [], "legs_min": 2, "legs_max": 3,
                     "edge_range": (0.02, 0.12), "vig": 0.086}}
    ids_by_key = {b.key: f"2026-10-03|Testland|{b.home}|{b.away}" for b in plans[0]}
    tracked: set = set()
    out = appdata.accas_payload(ctx, ids_by_key, tracked, {"Home0": "b0.png"}, lambda d, c, h, a: f"{d}|{c}|{h}|{a}")
    assert out["target"] == 3.0 and out["pool"] == 17 and out["legs"] == [2, 3]
    assert len(out["bets"]) == 1
    b = out["bets"][0]
    assert b["id"] == "A20261003-01" and b["n_legs"] == 2
    assert b["odds"] == pytest.approx(2.99, abs=0.01)
    assert b["p"] == pytest.approx(0.80 * 0.82, abs=1e-4)
    assert b["p_market"] == pytest.approx(0.74 * 0.76, abs=1e-3)   # _f() rounds to 3 dp
    assert b["if_model_right"] < b["if_no_edge"] + 1          # the honest pair of numbers is rendered
    assert all(leg["fixture"] for leg in b["legs"])
    assert b["legs"][0]["badges"]["home"] == "b0.png"
    assert len(tracked) == 2, "the app must follow every acca leg in the live feed"


def test_payload_is_empty_and_harmless_when_there_is_no_plan():
    out = appdata.accas_payload({"accas": {}}, {}, set(), {}, lambda *a: "x")
    assert out["bets"] == [] and out["recent"] == []
    assert json.dumps(out)          # JSON-serialisable like the rest of the payload
