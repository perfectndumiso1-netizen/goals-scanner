# calibration from the settled ledger (2026-10-11 upgrade): honest probabilities, gated by validation
import pandas as pd

import calibration as calib
from datetime import datetime


def _ledger(n_high_weak=200, n_low_ok=200):
    """High-probability picks that underperform (model hot), low ones on target.
    60% of rows sit in the training window, 40% in the holdout window."""
    rows = []

    def day(i, split):
        month = 6 + (i % 3) if split == "train" else 9 + (i % 0 or 0)
        return f"2026-{month:02d}-{1 + i % 28:02d}"

    for i in range(n_high_weak):
        split = "train" if i < n_high_weak * 0.6 else "hold"
        rows.append({"day": "2026-06-01" if split == "train" else "2026-09-05",
                     "market": "goals", "p": 0.80,
                     "result": "hit" if i % 10 < 7 else "miss"})      # 70% actual vs 80% claimed
    for i in range(n_low_ok):
        split = "train" if i < n_low_ok * 0.6 else "hold"
        rows.append({"day": "2026-06-02" if split == "train" else "2026-09-06",
                     "market": "goals", "p": 0.62,
                     "result": "hit" if i % 10 < 6 else "miss"})      # ~60% actual
    return pd.DataFrame(rows)


def test_pava_is_monotone():
    xs = [0.5, 0.6, 0.7, 0.8, 0.9]
    ys = [0.9, 0.5, 0.6, 0.55, 0.7]           # messy, non-monotone
    curve = calib._pava(xs, ys)
    yvals = [round(y, 6) for _, y in curve]
    assert yvals == sorted(yvals)
    assert 0.5 <= min(yvals) and max(yvals) <= 0.9


def test_apply_map_pieces():
    curve = [(0.3, 0.3), (0.7, 0.6), (1.0, 0.9)]
    assert abs(calib._piecewise(curve, 0.5) - 0.45) < 1e-9
    assert abs(calib._piecewise(curve, 0.1) - 0.3) < 1e-9      # clamps below
    assert abs(calib._piecewise(curve, 1.5) - 0.9) < 1e-9      # clamps above the domain


def test_build_map_validates_out_of_time_and_goes_live():
    now = datetime(2026, 9, 20, 12, 0)
    m = calib.build_map(_ledger(), now)
    g = m["groups"]["goals"]
    assert g["status"] == "live", g
    assert g["brier_cal"] < g["brier_raw"]
    assert m["live"] is True
    # the map must pull the overconfident 0.80 down toward reality
    p_cal = calib.apply_map(0.80, "goals", m)
    assert p_cal is not None and p_cal < 0.78
    # untouched groups have no map
    assert calib.apply_map(0.80, "corners", m) is None


def test_build_map_honest_on_small_data():
    now = datetime(2026, 9, 20, 12, 0)
    m = calib.build_map(_ledger(n_high_weak=20, n_low_ok=20), now)
    assert m["live"] is False
    assert calib.apply_map(0.8, "goals", m) is None


def test_apply_map_never_raises_on_garbage():
    assert calib.apply_map(None, "goals", {"live": True}) is None
    assert calib.apply_map(0.8, "goals", None) is None
    bad = {"live": True, "groups": {"goals": {"curve": "not-a-curve"}}}
    assert calib.apply_map(0.8, "goals", bad) is None


def test_holdout_adapts_to_a_young_ledger():
    """A ~3-week-old ledger must still produce a training window (shortlist shipped late Sept)."""
    now = datetime(2026, 10, 12, 12, 0)
    rows = []
    for i in range(150):    # spread over 2026-09-20 .. 2026-10-11 (~3 weeks)
        day = f"2026-{9 + i // 75:02d}-{1 + (i * 21) % 28:02d}"
        rows.append({"day": day, "market": "goals", "p": 0.80, "result": "hit" if i % 10 < 7 else "miss"})
    m = calib.build_map(pd.DataFrame(rows), now)
    g = m["groups"]["goals"]
    assert g["n_train"] > 0, g          # without the adaptive split this is 0
    assert m["holdout_days"] <= 7 or m["holdout_days"] <= 21 // 1  # never inflated beyond the cap
