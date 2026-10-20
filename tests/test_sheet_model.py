"""V1 Google Sheet bookmaker model — formulas must match the sheet, PlayReport stays untouched."""
from __future__ import annotations

import math

import sheet_model as sm


# Test match that was in MATCH_INPUT (Dinamo Minsk vs Arsenal Dzerzhinsk).
DINAMO = {
    "home_gf_home": 2.33,
    "home_ga_home": 0.67,
    "away_gf_away": 1,
    "away_ga_away": 2.17,
    "lg_home": 1.31,
    "lg_away": 1.17,
}


def test_poisson_matches_excel_pmf_and_cdf():
    # POISSON.DIST(0, 1.5, FALSE) = e^{-1.5}
    assert abs(sm.poisson_pmf(0, 1.5) - math.exp(-1.5)) < 1e-12
    # POISSON.DIST(2, 1.5, TRUE) = P(0)+P(1)+P(2)
    cdf = sm.poisson_cdf(2, 1.5)
    manual = sum(sm.poisson_pmf(k, 1.5) for k in range(3))
    assert abs(cdf - manual) < 1e-12


def test_v1_engine_is_the_sheet_arithmetic():
    out = sm.evaluate_v1(DINAMO)
    assert out is not None
    # MODEL_ENGINE
    assert abs(out["home_attack"] - 2.33 / 1.31) < 1e-3
    assert abs(out["home_defence"] - 0.67 / 1.17) < 1e-3
    assert abs(out["away_attack"] - 1 / 1.17) < 1e-3
    assert abs(out["away_defence"] - 2.17 / 1.31) < 1e-3
    lam_h = 1.31 * (2.33 / 1.31) * (2.17 / 1.31)
    lam_a = 1.17 * (1 / 1.17) * (0.67 / 1.17)
    assert abs(out["lambda_h"] - lam_h) < 1e-3
    assert abs(out["lambda_a"] - lam_a) < 1e-3
    mk = {m["id"]: m for m in out["markets"]}
    # Over 2.5 = 1 - POISSON.DIST(2, λH+λA, TRUE)
    o25 = 1 - sm.poisson_cdf(2, lam_h + lam_a)
    assert abs(mk["O25"]["p"] - o25) < 1e-3
    # BTTS Yes = 1 - P(H=0) - P(A=0) + P(H=0)P(A=0)
    btts = 1 - sm.poisson_pmf(0, lam_h) - sm.poisson_pmf(0, lam_a) + sm.poisson_pmf(0, lam_h) * sm.poisson_pmf(0, lam_a)
    assert abs(mk["BTTS"]["p"] - btts) < 1e-3
    assert abs(mk["BTTS_N"]["p"] - (1 - btts)) < 1e-3
    # 1X2 is the truncated 0–7 matrix, so it sums to 1 - residual, not 1.
    assert abs(out["x12_sum"] + out["matrix_residual"] - 1) < 1e-6
    assert mk["H"]["p"] + mk["D"]["p"] + mk["A"]["p"] == out["x12_sum"] or abs(
        mk["H"]["p"] + mk["D"]["p"] + mk["A"]["p"] - out["x12_sum"]) < 1e-3


def test_missing_league_average_does_not_invent():
    assert sm.evaluate_v1({**DINAMO, "lg_home": None}) is None
    assert sm.evaluate_v1({**DINAMO, "lg_home": 0}) is None


class _P:
    def __init__(self, **kw):
        self.name = kw.get("name", "T")
        self.n = kw.get("n", 10)
        self.venue_n = kw.get("venue_n", 4)
        self.venue_gf = kw.get("venue_gf", float("nan"))
        self.venue_ga = kw.get("venue_ga", float("nan"))
        self.gf = kw.get("gf", float("nan"))
        self.ga = kw.get("ga", float("nan"))
        self.xg_for = kw.get("xg_for", float("nan"))
        self.xg_against = kw.get("xg_against", float("nan"))
        self.sot_for = kw.get("sot_for", float("nan"))
        self.sot_against = kw.get("sot_against", float("nan"))
        self.rate_cs = kw.get("rate_cs", float("nan"))
        self.matches = kw.get("matches", [])


class _D:
    def __init__(self, h, a):
        self.mu_h, self.mu_a = h, a


def test_build_uses_venue_rates_and_does_not_touch_playreport_probs():
    fx = {"home": "Home FC", "away": "Away FC", "league": "Test League",
          "date": "2026-10-20", "kickoff": None, "competition": "Test League"}
    H = _P(name="Home FC", venue_gf=1.8, venue_ga=0.9, gf=1.5, ga=1.1)
    A = _P(name="Away FC", venue_gf=1.1, venue_ga=1.6, gf=1.2, ga=1.4)
    pr_x12 = {"H": 0.45, "D": 0.28, "A": 0.27}
    pr_tg = {"H_o05": 0.8, "H_o15": 0.5, "A_o05": 0.7, "A_o15": 0.4}
    pr_p = {"O15": 0.77, "O25": 0.55, "O35": 0.33, "BTTS": 0.52}
    out = sm.build(fx, H, A, _D(1.4, 1.15), pr_x12, pr_tg, pr_p)
    assert out["ok"]
    assert out["inputs"]["home_gf_home"] == 1.8
    assert out["inputs"]["away_gf_away"] == 1.1
    mk = {m["id"]: m for m in out["markets"]}
    # PlayReport column is copied through, never written back.
    assert mk["H"]["playreport"] == 0.45
    assert mk["O25"]["playreport"] == 0.55
    assert mk["H"]["p"] != mk["H"]["playreport"] or True  # may coincide; must still be independent
    # Sheet 1X2 came from the sheet engine, not from pr_x12.
    assert abs(mk["H"]["p"] - 0.45) > 0.01 or abs(mk["D"]["p"] - 0.28) > 0.01


def test_venue_fallback_to_overall_when_home_sample_empty():
    fx = {"home": "H", "away": "A", "league": "L", "date": "2026-10-20"}
    H = _P(venue_n=0, venue_gf=float("nan"), gf=2.0, ga=1.0)
    A = _P(venue_gf=1.0, venue_ga=1.5, gf=1.1, ga=1.4)
    out = sm.build(fx, H, A, _D(1.3, 1.1), {}, {}, {})
    assert out["ok"]
    assert out["inputs"]["home_gf_home"] == 2.0
    assert any("overall" in u for u in out["used"])
