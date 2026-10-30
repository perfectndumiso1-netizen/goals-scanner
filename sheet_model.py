"""Google Sheet bookmaker model V1 — comparison only.

Faithful evaluation of Football_Bookmaker_Model_V1 (MATCH_INPUT → MODEL_ENGINE →
SCORE_MATRIX → MARKETS). Formulas are copied as written in the sheet; nothing is
tuned, shrunk, or blended with Mr 2 Odds's Dixon-Coles model.

Mr 2 Odds probabilities stay exactly as they are. This module only fills the
sheet's input cells from data we already have for the fixture, then runs the
sheet arithmetic so each match page can show the two side by side.
"""
from __future__ import annotations

import math
from datetime import datetime

# MATCH_INPUT cell map (column B). Labels are the sheet's own wording.
_V1_KEYS = (
    "home_gf_home",   # B13 Home goals scored / home game
    "home_ga_home",   # B14 Home goals conceded / home game
    "away_gf_away",   # B15 Away goals scored / away game
    "away_ga_away",   # B16 Away goals conceded / away game
    "lg_home",        # B17 League average home goals / game
    "lg_away",        # B18 League average away goals / game
)


def _f(x, n=4):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v else round(v, n)


def _mean(vals):
    xs = [float(v) for v in vals if v is not None and v == v]
    return (sum(xs) / len(xs)) if xs else None


def poisson_pmf(k: int, lam: float) -> float:
    """Excel POISSON.DIST(k, lam, FALSE)."""
    if lam < 0:
        return 0.0
    if lam == 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1))


def poisson_cdf(k: int, lam: float) -> float:
    """Excel POISSON.DIST(k, lam, TRUE)."""
    return sum(poisson_pmf(i, lam) for i in range(int(k) + 1))


def _fair(p):
    return None if p is None or p <= 0 else round(1.0 / p, 3)


def evaluate_v1(inp: dict) -> dict | None:
    """Run MODEL_ENGINE + SCORE_MATRIX + MARKETS on six V1 statistical inputs.

    Returns None when any of the six is missing or non-positive league averages
    would divide by zero (the sheet uses IFERROR(..., 0) for strengths; we still
    refuse to publish a market table from a broken baseline).
    """
    try:
        h_gf, h_ga = float(inp["home_gf_home"]), float(inp["home_ga_home"])
        a_gf, a_ga = float(inp["away_gf_away"]), float(inp["away_ga_away"])
        lg_h, lg_a = float(inp["lg_home"]), float(inp["lg_away"])
    except (TypeError, ValueError, KeyError):
        return None
    if any(v != v for v in (h_gf, h_ga, a_gf, a_ga, lg_h, lg_a)):
        return None
    if lg_h <= 0 or lg_a <= 0:
        return None

    # MODEL_ENGINE B4:B10
    home_att = h_gf / lg_h          # IFERROR(B13/B17, 0)
    home_def = h_ga / lg_a          # IFERROR(B14/B18, 0)
    away_att = a_gf / lg_a          # IFERROR(B15/B18, 0)
    away_def = a_ga / lg_h          # IFERROR(B16/B17, 0)
    lam_h = lg_h * home_att * away_def   # B17 * B4 * B7
    lam_a = lg_a * away_att * home_def   # B18 * B6 * B5
    lam_t = lam_h + lam_a

    # SCORE_MATRIX 0–7 (independent Poisson). 1X2 sums this truncated grid.
    M = [[poisson_pmf(i, lam_h) * poisson_pmf(j, lam_a) for j in range(8)] for i in range(8)]
    p_h = p_d = p_a = 0.0
    for i in range(8):
        for j in range(8):
            if i > j:
                p_h += M[i][j]
            elif i == j:
                p_d += M[i][j]
            else:
                p_a += M[i][j]
    residual = 1.0 - sum(M[i][j] for i in range(8) for j in range(8))

    p0h, p0a = poisson_pmf(0, lam_h), poisson_pmf(0, lam_a)
    btts_yes = 1.0 - p0h - p0a + p0h * p0a

    markets = [
        ("H", "Home Win", p_h),
        ("D", "Draw", p_d),
        ("A", "Away Win", p_a),
        ("O05", "Over 0.5 Goals", 1.0 - poisson_pmf(0, lam_t)),
        ("O15", "Over 1.5 Goals", 1.0 - poisson_cdf(1, lam_t)),
        ("O25", "Over 2.5 Goals", 1.0 - poisson_cdf(2, lam_t)),
        ("O35", "Over 3.5 Goals", 1.0 - poisson_cdf(3, lam_t)),
        ("BTTS", "BTTS Yes", btts_yes),
        ("BTTS_N", "BTTS No", 1.0 - btts_yes),
        ("H_o05", "Home Over 0.5", 1.0 - poisson_pmf(0, lam_h)),
        ("H_o15", "Home Over 1.5", 1.0 - poisson_cdf(1, lam_h)),
        ("A_o05", "Away Over 0.5", 1.0 - poisson_pmf(0, lam_a)),
        ("A_o15", "Away Over 1.5", 1.0 - poisson_cdf(1, lam_a)),
    ]
    return {
        "home_attack": round(home_att, 4),
        "home_defence": round(home_def, 4),
        "away_attack": round(away_att, 4),
        "away_defence": round(away_def, 4),
        "lambda_h": round(lam_h, 4),
        "lambda_a": round(lam_a, 4),
        "lambda_total": round(lam_t, 4),
        "matrix_residual": round(residual, 6),
        "x12_sum": round(p_h + p_d + p_a, 6),
        "markets": [{"id": i, "name": n, "p": round(p, 4), "fair": _fair(p)} for i, n, p in markets],
    }


def _rate(profile, venue_attr, overall_attr, used: list, label: str, fallback_label: str):
    """Prefer the sheet's venue rate; fall back to overall gf/ga when the venue sample is empty."""
    v = getattr(profile, venue_attr, float("nan"))
    if v == v:
        used.append(label)
        return float(v)
    o = getattr(profile, overall_attr, float("nan"))
    if o == o:
        used.append(fallback_label)
        return float(o)
    return None


def _from_matches(matches, key, n=10):
    rows = list(matches or [])[:n]
    return _mean([m.get(key) for m in rows])


def inputs_from_profiles(fx, home, away, div_avg) -> tuple[dict, list[str], list[str]]:
    """Map Mr 2 Odds team profiles onto MATCH_INPUT. Never invent a number."""
    used, missing = [], []
    h_gf = _rate(home, "venue_gf", "gf", used, "home goals scored / home game (venue)",
                 "home goals scored / game (overall — no home sample)")
    h_ga = _rate(home, "venue_ga", "ga", used, "home goals conceded / home game (venue)",
                 "home goals conceded / game (overall — no home sample)")
    a_gf = _rate(away, "venue_gf", "gf", used, "away goals scored / away game (venue)",
                 "away goals scored / game (overall — no away sample)")
    a_ga = _rate(away, "venue_ga", "ga", used, "away goals conceded / away game (venue)",
                 "away goals conceded / game (overall — no away sample)")
    lg_h = float(div_avg.mu_h) if div_avg and div_avg.mu_h == div_avg.mu_h else None
    lg_a = float(div_avg.mu_a) if div_avg and div_avg.mu_a == div_avg.mu_a else None
    if lg_h is not None:
        used.append("league average home goals")
    else:
        missing.append("league average home goals")
    if lg_a is not None:
        used.append("league average away goals")
    else:
        missing.append("league average away goals")
    for val, name in ((h_gf, "home goals scored / home game"), (h_ga, "home goals conceded / home game"),
                      (a_gf, "away goals scored / away game"), (a_ga, "away goals conceded / away game")):
        if val is None:
            missing.append(name)

    ko = fx.get("kickoff") if hasattr(fx, "get") else None
    date = fx.get("date") if hasattr(fx, "get") else None
    if hasattr(ko, "strftime"):
        date_s, season = ko.strftime("%Y-%m-%d"), ko.year
    elif hasattr(date, "strftime"):
        date_s, season = date.strftime("%Y-%m-%d"), date.year
    else:
        date_s, season = str(date or ko or ""), None
        if isinstance(date_s, str) and len(date_s) >= 4 and date_s[:4].isdigit():
            season = int(date_s[:4])

    h_matches = getattr(home, "matches", None) or []
    a_matches = getattr(away, "matches", None) or []
    info = {
        "competition": str(fx.get("league") or fx.get("competition") or ""),
        "season": season,
        "round": str(fx.get("round") or "") or None,
        "date": date_s,
        "home": str(fx.get("home") or home.name),
        "away": str(fx.get("away") or away.name),
        "venue": str(fx.get("venue") or fx.get("stadium") or "") or None,
        "home_gf_home": _f(h_gf, 3),
        "home_ga_home": _f(h_ga, 3),
        "away_gf_away": _f(a_gf, 3),
        "away_ga_away": _f(a_ga, 3),
        "lg_home": _f(lg_h, 3),
        "lg_away": _f(lg_a, 3),
        # Context / V2 cells — filled when the archive has them; V1 does not use them.
        "home_xg": _f(home.xg_for, 3),
        "home_xga": _f(home.xg_against, 3),
        "away_xg": _f(away.xg_for, 3),
        "away_xga": _f(away.xg_against, 3),
        "home_shots": _f(_from_matches(h_matches, "shots_for"), 2),
        "away_shots": _f(_from_matches(a_matches, "shots_for"), 2),
        "home_sot": _f(home.sot_for, 2),
        "away_sot": _f(away.sot_for, 2),
        "home_cs": _f(home.rate_cs, 3),
        "away_cs": _f(away.rate_cs, 3),
        "home_recent_gf": _f(_from_matches(h_matches, "gf", 6), 3),
        "home_recent_ga": _f(_from_matches(h_matches, "ga", 6), 3),
        "away_recent_gf": _f(_from_matches(a_matches, "gf", 6), 3),
        "away_recent_ga": _f(_from_matches(a_matches, "ga", 6), 3),
        "home_n": int(getattr(home, "n", 0) or 0),
        "away_n": int(getattr(away, "n", 0) or 0),
        "home_venue_n": int(getattr(home, "venue_n", 0) or 0),
        "away_venue_n": int(getattr(away, "venue_n", 0) or 0),
    }
    return info, used, missing


def _pr_p(extra_x12, extra_tg, p_model, mid):
    x12 = extra_x12 or {}
    tg = extra_tg or {}
    pm = p_model or {}
    m = {
        "H": x12.get("H"), "D": x12.get("D"), "A": x12.get("A"),
        "O15": pm.get("O15"), "O25": pm.get("O25"), "O35": pm.get("O35"),
        "BTTS": pm.get("BTTS"),
        "H_o05": tg.get("H_o05"), "H_o15": tg.get("H_o15"),
        "A_o05": tg.get("A_o05"), "A_o15": tg.get("A_o15"),
    }
    v = m.get(mid)
    return _f(v, 4) if v is not None else None


def build(fx, home, away, div_avg, extra_x12=None, extra_tg=None, p_model=None) -> dict:
    """Per-match payload for the app. Comparison only — never a Mr 2 Odds input."""
    info, used, missing = inputs_from_profiles(fx, home, away, div_avg)
    eng = evaluate_v1(info) if not any(k in missing for k in (
        "home goals scored / home game", "home goals conceded / home game",
        "away goals scored / away game", "away goals conceded / away game",
        "league average home goals", "league average away goals")) else None
    markets = []
    if eng:
        for m in eng["markets"]:
            markets.append({**m, "playreport": _pr_p(extra_x12, extra_tg, p_model, m["id"])})
    return {
        "engine": "Football_Bookmaker_Model_V1",
        "note": "Your Google Sheet V1 bookmaker model, filled with this match's available data. "
                "Mr 2 Odds's own model is unchanged — this is a comparison only.",
        "ok": eng is not None,
        "inputs": info,
        "used": used,
        "missing": missing,
        "model": eng,
        "markets": markets,
    }
