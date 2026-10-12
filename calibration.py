"""Probability calibration from the settled shortlist ledger (2026-10-11 upgrade).

The walk-forward record shows the raw model is systematically overconfident (primary picks:
model says 80%, reality 73%). This module learns a per-market-group correction from the
settled ledger and validates it out-of-time BEFORE it is allowed to touch anything:

  build/validate  — isotonic regression (pool-adjacent-violators) on banded raw probabilities,
                    trained on everything older than a holdout window, scored by Brier score
                    on the holdout. The map goes live ONLY if it beats raw on the holdout.
  apply           — raw p in, calibrated p out (None where no validated map exists).

Nothing here changes which selections qualify: calibration is applied AFTER the gates, to the
number that is DISPLAYED and COMPOSED (accas). The filters stay exactly as the user built them.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

# a market group needs at least this many settled, priced picks before it gets a map
MIN_TRAIN = 60
MIN_HOLDOUT = 30
HOLDOUT_DAYS = 21          # most recent days = the out-of-time test set
BAND = 0.05                # raw-probability band width
P_MIN, P_MAX = 0.30, 1.00  # banding range (shortlist picks live well above 0.3, ledger covers the rest)


def _pava(xs: list[float], ys: list[float]) -> list[tuple[float, float]]:
    """Isotonic regression (increasing) via pool-adjacent-violators on x-aggregated means.

    Duplicate x values are averaged first (weighted by count) — the fit is a function of x,
    so the same raw probability must map to one calibrated value.
    """
    agg: dict[float, list[float]] = {}
    for x, y in sorted(zip(xs, ys)):
        a = agg.setdefault(x, [0.0, 0.0])
        a[0] += y
        a[1] += 1.0
    blocks = []                                   # each: [x, sum_y, n]
    for x, (sy, n) in sorted(agg.items()):
        blocks.append([x, sy, n])
        while len(blocks) >= 2 and blocks[-2][1] / blocks[-2][2] > blocks[-1][1] / blocks[-1][2] + 1e-12:
            b2 = blocks.pop()
            b1 = blocks.pop()
            blocks.append([b2[0], b1[1] + b2[1], b1[2] + b2[2]])   # pooled block keeps the larger x
    return [(b[0], b[1] / b[2]) for b in blocks]


def _piecewise(curve: list[tuple[float, float]], x: float) -> float:
    if not curve:
        return x
    if x <= curve[0][0]:
        return curve[0][1]
    for i in range(1, len(curve)):
        if x <= curve[i][0]:
            x0, y0 = curve[i - 1]
            x1, y1 = curve[i]
            return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return curve[-1][1]


def _brier(ps, outs) -> float:
    if not len(ps):
        return float("nan")
    return sum((p - o) ** 2 for p, o in zip(ps, outs)) / len(ps)


def build_map(df: pd.DataFrame, today: datetime, groups: tuple[str, ...] = ("result", "dc", "goals", "btts", "team", "corners", "cards"),
              min_train: int = MIN_TRAIN, min_holdout: int = MIN_HOLDOUT, holdout_days: int = HOLDOUT_DAYS) -> dict:
    """Learn + validate per-group calibration maps from the settled ledger. Never raises."""
    out: dict = {"generated": today.strftime("%Y-%m-%d %H:%M"), "method": "isotonic (PAVA) on banded raw probability, per market group",
                 "holdout_days": holdout_days, "groups": {}, "live": False}
    try:
        if df is None or df.empty:
            out["status"] = "no ledger yet"
            return out
        d = df[df["result"].isin(["hit", "miss"])].copy()
        d["pv"] = pd.to_numeric(d["p"], errors="coerce")
        d = d[d["pv"].between(0.01, 0.99)]
        d["out"] = (d["result"] == "hit").astype(float)
        d["dayv"] = d["day"].astype(str)
        # the holdout adapts to the ledger's actual history: a young ledger cannot afford a
        # 21-day holdout — take at most a third of the span (floor 1 day; the MIN_TRAIN /
        # MIN_HOLDOUT gates below still decide whether a map is allowed to go live)
        span = (pd.to_datetime(d["dayv"]).max() - pd.to_datetime(d["dayv"]).min()).days
        holdout_days = min(holdout_days, max(1, span // 3))
        out["holdout_days"] = holdout_days
        cut = (today - timedelta(days=holdout_days)).strftime("%Y-%m-%d")
        for g in groups:
            gd = d[d["market"] == g]
            train, hold = gd[gd["dayv"] < cut], gd[gd["dayv"] >= cut]
            info = {"n_train": int(len(train)), "n_holdout": int(len(hold))}
            if len(train) < min_train or len(hold) < min_holdout:
                info["status"] = "collecting"
                out["groups"][g] = info
                continue
            xs = [round(min(max(v, P_MIN), P_MAX), 4) for v in train["pv"]]
            ys = list(train["out"])
            curve = _pava(xs, ys)
            hp = [min(max(v, P_MIN), P_MAX) for v in hold["pv"]]
            b_raw = _brier(hp, list(hold["out"]))
            b_cal = _brier([_piecewise(curve, v) for v in hp], list(hold["out"]))
            info.update({"brier_raw": round(b_raw, 4), "brier_cal": round(b_cal, 4),
                         "status": "live" if b_cal < b_raw else "no gain — raw stays"})
            if b_cal < b_raw:
                info["curve"] = [[round(x, 3), round(y, 3)] for x, y in curve]
                out["live"] = True
            out["groups"][g] = info
        n_live = sum(1 for v in out["groups"].values() if v.get("status") == "live")
        out["status"] = (f"{n_live} of {len(out['groups'])} market group(s) validated — "
                         "calibrated probability shown where live, raw everywhere else")
        return out
    except Exception as exc:  # noqa: BLE001 — calibration must never break the shortlist
        out["status"] = f"unavailable ({exc})"
        return out


def apply_map(p: float | None, group: str, cal: dict | None) -> float | None:
    """Calibrated probability for one pick, or None when no validated map covers it."""
    if p is None or not cal or not cal.get("live"):
        return None
    g = (cal.get("groups") or {}).get(group) or {}
    curve = g.get("curve")
    if not curve:
        return None
    try:
        return round(min(max(_piecewise([(x, y) for x, y in curve], min(max(float(p), P_MIN), P_MAX)), 0.01), 0.99), 3)
    except Exception:  # noqa: BLE001
        return None
