"""v1.6.34 market rules: model+market both < 1.15 dropped everywhere; safest board drops O0.5 / U5.5."""
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

import safe


def _row(p_over05=0.97, odds_over05=1.03, p_o15=0.72, odds_o15=1.55, kickoff_days=2):
    now = datetime(2026, 10, 1, 12, 0)
    return NS(
        data_ok=True,
        fx={"date": now.date(), "kickoff": now + timedelta(days=kickoff_days),
            "country": "England", "div": "E0", "league": "EPL", "home": "Alpha", "away": "Beta"},
        sb={"OU": {0.5: (odds_over05, 9.0), 1.5: (odds_o15, 2.6)}},
        extra=NS(x12={"H": 0.55, "D": 0.25, "A": 0.20}, tg={}, corner_p=None, card_p=None),
        p_final={"O05": p_over05, "O15": p_o15},
        sb_full={},
    )


def _codes(r):
    return [s.sel for s in safe.selections(r)]


def test_both_under_115_dropped_everywhere():
    # model odds 1/0.97 = 1.03 AND market 1.03 — both under 1.15 -> the selection disappears entirely
    r = _row(p_over05=0.97, odds_over05=1.03)
    assert "O05" not in _codes(r)
    # the same match keeps its other markets
    assert "O15" in _codes(r)
    assert "H" in _codes(r)


def test_market_at_or_above_115_survives():
    # model odds 1.03 but the market prices it 1.20 -> kept (rule needs BOTH under 1.15)
    r = _row(p_over05=0.97, odds_over05=1.20)
    assert "O05" in _codes(r)


def test_unpriced_selection_survives():
    # no market price at all -> cannot be "market under 1.15" -> kept
    r = _row(p_over05=0.97, odds_over05=None)
    assert "O05" in _codes(r)


def test_normal_priced_selections_untouched():
    r = _row()
    codes = _codes(r)
    assert "O15" in codes and "H" in codes
    assert {"H", "D", "A"} <= set(codes)


def test_safest_drops_over05_and_under55(monkeypatch):
    # disable the legacy overs-only flag so the assertions prove the EXPLICIT O05/U55 skips
    monkeypatch.setattr(safe, "OVERS_ONLY", False)
    r = _row(p_over05=0.90, odds_over05=1.19)   # market 1.19 -> survives the <1.15 rule
    r.p_final["O55"] = 0.08                      # -> U55 p = 0.92, priced 4.5 -> survives too
    r.sb["OU"][5.5] = (1.18, 4.5)
    out = safe.safest([r], now=datetime(2026, 10, 1, 12, 0),
                      window_end=datetime(2026, 10, 1, 12, 0) + timedelta(days=1))
    codes = [b.sel for b in out["bets"]]
    assert "O05" not in codes
    assert "U55" not in codes
    assert "O15" in codes  # the valuable market still represents the match
