"""High-conviction shortlist: every gate, the cap, one-per-match, the ledger, and that nothing is mutated."""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import safe as safe_mod  # noqa: E402
import shortlist as sl  # noqa: E402
from safe import Sel  # noqa: E402

NOW = datetime(2026, 10, 9, 10, 0)


def row(home="A", away="B", ok=True, quality="High", qscore=0.85, conf="High", warns=None, conflicts=None, ko_h=5):
    ko = NOW + timedelta(hours=ko_h)
    fx = pd.Series({"date": pd.Timestamp(ko.date()), "kickoff": pd.Timestamp(ko), "country": "England",
                    "league": "League", "home": home, "away": away, "div": "E0"})
    audit = {"quality": {"overall": quality, "score": qscore},
             "confidence": {"O15": conf, "O25": conf, "O35": conf, "BTTS": conf, "X12": conf, "TG": conf},
             "warnings": warns or [], "context": {"conflicts": conflicts or []}}
    return NS(fx=fx, audit=audit, data_ok=ok, sb={"x": 1}, hist={"O25": 0.7}, mod_h=1.6, mod_a=1.2,
              home=NS(n=20), away=NS(n=20))


def test_odds_band_115_to_190_and_na_odds_are_never_assumed():
    r = row()
    assert sl.evaluate(r, Sel("O15", 0.90, 0.86, 1.14))["status"] == "rejected"     # under the 1.15 floor
    assert sl.evaluate(r, Sel("O15", 0.90, 0.86, 1.15))["status"] == "primary"      # floor is inclusive
    rec = sl.evaluate(r, Sel("O15", 0.86, 0.84, 1.95))
    assert rec["status"] == "rejected" and "ceiling" in rec["reasons"][0]           # over the 1.90 ceiling
    assert sl.evaluate(r, Sel("O15", 0.90, 0.86, 1.90))["status"] == "primary"      # ceiling is inclusive
    rec = sl.evaluate(r, Sel("O15", 0.90, None, None))
    assert rec["status"] == "rejected" and rec["odds"] is None and "N/A" in rec["reasons"][0]


def test_a_clean_value_selection_qualifies():
    rec = sl.evaluate(row(), Sel("O25", 0.74, 0.68, 1.45))     # EV +7.3 %, edge +6 pp
    assert rec["status"] == "primary", rec["reasons"]
    assert rec["p_cal"] is None                                # calibration is N/A, never invented


def test_high_probability_without_edge_is_watchlist_not_shortlist():
    rec = sl.evaluate(row(), Sel("O15", 0.86, 0.855, 1.17))
    assert rec["status"] == "watchlist" and "not value" in rec["reasons"][0]


def test_negative_ev_and_implausible_gaps_are_rejected():
    assert sl.evaluate(row(), Sel("O25", 0.72, 0.70, 1.30))["status"] == "rejected"        # 0.72*1.30 < 1
    rec = sl.evaluate(row(), Sel("H", 0.75, 0.55, 1.75))                                   # 20 pp gap
    assert rec["status"] == "rejected" and "data fault" in rec["reasons"][0]


def test_market_bars_are_per_market():
    assert sl.evaluate(row(), Sel("H", 0.62, 0.58, 1.70))["status"] == "primary"           # 1X2 bar 60 %
    assert sl.evaluate(row(), Sel("O25", 0.66, 0.62, 1.60))["status"] == "rejected"        # goals bar 70 %
    assert sl.evaluate(row(), Sel("CO85", 0.67, 0.63, 1.58))["status"] == "primary"        # corners bar 65 %


def test_weak_data_warnings_and_conflicts_send_it_to_the_watchlist_with_a_reason():
    s = Sel("O25", 0.74, 0.68, 1.45)
    for r, word in ((row(quality="Low", qscore=0.4), "quality"), (row(conf="Low"), "confidence"),
                    (row(warns=[{"level": "warn", "text": "model far above raw rate"}]), "warning"),
                    (row(conflicts=[{"a": 1}]), "conflict")):
        rec = sl.evaluate(r, s)
        assert rec["status"] == "watchlist" and word in rec["reasons"][0].lower()
    assert sl.evaluate(row(ok=False), s)["status"] == "rejected"


def _board(monkeypatch, rows_sels, cap=3):
    rows = []
    table = {}
    for i, sels in enumerate(rows_sels):
        r = row(home=f"H{i}", away=f"A{i}")
        rows.append(r)
        table[id(r)] = sels
    monkeypatch.setattr(sl.safe_mod, "selections", lambda r: table[id(r)])
    return rows, sl.build(rows, NOW, NOW + timedelta(hours=24), max_per_market=cap)


def test_cap_is_per_market_and_correlated_are_named(monkeypatch):
    good = [Sel("O25", 0.74, 0.68, 1.45), Sel("BTTS", 0.72, 0.66, 1.50)]
    rows, b = _board(monkeypatch, [good] * 5)
    assert b["counts"]["primary"] == 3 and len(b["primary"]) == 3          # one per match first, then cap 3
    assert len({(x["home"], x["away"]) for x in b["primary"]}) == 3
    assert all(x["status"] == "primary" for x in b["primary"])
    assert b["primary"][0]["correlated"], "the second selection of the match is named as correlated"
    assert any("outside the top 3" in x["reasons"][0] for x in b["watchlist"])
    assert all(x["rank"] in (1, 2, 3) for x in b["primary"])
    assert b["rules"]["band"].startswith("1.15")


def test_per_market_cap_keeps_the_best_ten(monkeypatch):
    rows, b = _board(monkeypatch, [[Sel("O25", 0.74, 0.68, 1.45)]] * 13, cap=10)
    assert b["counts"]["primary"] == 10
    assert b["counts"]["watchlist"] == 3
    assert all(x["market"] == "goals" for x in b["primary"])
    ranks = sorted(x["rank"] for x in b["primary"])
    assert ranks == list(range(1, 11))                                     # rank = position in its market


def test_no_qualifying_selections_is_reported_honestly(monkeypatch):
    rows, b = _board(monkeypatch, [[Sel("O15", 0.90, 0.88, 1.10)]] * 3)
    assert b["primary"] == [] and "NO QUALIFYING SELECTIONS" in b["verdict"]
    assert b["rejected_patterns"][0][0] == "odds under the 1.15 floor"
    assert "NO QUALIFYING SELECTIONS" in "\n".join(sl.markdown(sl.public(b)))


def test_the_filter_never_changes_a_probability(monkeypatch):
    s = Sel("O25", 0.74, 0.68, 1.45)
    rows, b = _board(monkeypatch, [[s]])
    assert (s.p_model, s.p_sb, s.odds) == (0.74, 0.68, 1.45)
    assert b["primary"][0]["p"] == 0.74


def test_ledger_writes_first_decision_once_and_settles(monkeypatch, tmp_path):
    rows, b = _board(monkeypatch, [[Sel("O25", 0.74, 0.68, 1.45)], [Sel("O15", 0.9, 0.88, 1.10)]])
    df, n = sl.record(sl.load(tmp_path / "x.csv"), b, NOW)
    assert n == 2 and set(df["status"]) == {"primary", "rejected"}
    df2, n2 = sl.record(df, b, NOW + timedelta(minutes=30))
    assert n2 == 0, "a later run never rewrites the pre-match decision"
    res = pd.DataFrame([{"home": "H0", "away": "A0", "country": "England", "date": pd.Timestamp(NOW.date()),
                         "hg": 2, "ag": 1}, {"home": "H1", "away": "A1", "country": "England",
                                             "date": pd.Timestamp(NOW.date()), "hg": 0, "ag": 0}])
    df3 = sl.settle(df2, res, NOW + timedelta(days=1))
    assert list(df3["result"]) == ["hit", "miss"]
    tr = sl.track_record(df3)
    assert tr["primary"]["n"] == 1 and tr["primary"]["hit_rate"] == 1.0
    df3.to_csv(tmp_path / "x.csv", index=False)
    assert len(sl.load(tmp_path / "x.csv")) == 2


def test_a_gap_the_model_shows_on_every_match_is_not_value(monkeypatch):
    """Spec rule 7: an edge that is just the model's systematic gap on a market is an artifact."""
    common = [[Sel("U55", 0.90, 0.80, 1.20)] for _ in range(20)]          # +10 pp on every match
    special = [[Sel("U55", 0.91, 0.795, 1.21)]]                            # +11.5 pp vs median +10 -> excess 1.5
    rows, b = _board(monkeypatch, common + special)
    assert b["counts"]["primary"] == 0, "nothing stands out from the model's usual gap"
    assert any("usual gap" in x["reasons"][0] for x in b["watchlist"])
    real = [[Sel("U55", 0.91, 0.82, 1.18)] for _ in range(20)] + [[Sel("U55", 0.93, 0.82, 1.18)]]   # +9 vs +11 -> excess 2
    rows, b = _board(monkeypatch, real)
    assert b["counts"]["primary"] == 1 and b["primary"][0]["excess_pp"] >= 2.0
