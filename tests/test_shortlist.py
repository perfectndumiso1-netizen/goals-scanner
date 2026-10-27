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


def test_odds_band_116_to_190_and_na_odds_are_never_assumed():
    r = row()
    assert sl.evaluate(r, Sel("O15", 0.90, 0.86, 1.14))["status"] == "rejected"     # under the 1.16 floor
    assert sl.evaluate(r, Sel("O15", 0.90, 0.86, 1.15))["status"] == "rejected"     # 2026-10-27: 1.15 is out too
    assert sl.evaluate(r, Sel("O15", 0.90, 0.86, 1.16))["status"] == "primary"      # floor is inclusive
    rec = sl.evaluate(r, Sel("O15", 0.86, 0.84, 1.95))
    assert rec["status"] == "rejected" and "ceiling" in rec["reasons"][0]           # over the 1.90 ceiling
    assert sl.evaluate(r, Sel("O15", 0.90, 0.86, 1.90))["status"] == "primary"      # ceiling is inclusive
    rec = sl.evaluate(r, Sel("O15", 0.90, None, None))
    assert rec["status"] == "rejected" and rec["odds"] is None and "N/A" in rec["reasons"][0]


def test_a_clean_value_selection_qualifies():
    rec = sl.evaluate(row(), Sel("O25", 0.74, 0.68, 1.45))     # EV +7.3 %, edge +6 pp
    assert rec["status"] == "primary", rec["reasons"]
    assert rec["p_cal"] is None                                # calibration is N/A, never invented


def test_high_probability_qualifies_even_without_an_edge():
    """User rule (2026-10-11): EV/edge no longer gate the shortlist — strength + data support decide."""
    rec = sl.evaluate(row(), Sel("O15", 0.86, 0.855, 1.17))
    assert rec["status"] == "primary", rec["reasons"]
    assert rec["ev"] is not None                       # still displayed, never gating


def test_a_price_below_95_percent_of_fair_goes_to_the_watchlist_and_a_data_fault_still_rejects():
    """2026-10-27: the price check replaces "EV is never a gate". 0.72 / 0.70 publishes 0.705, fair is 1.42, and 1.30
    is 92 % of it — real but badly bought, so watchlist, not a primary pick."""
    rec = sl.evaluate(row(), Sel("O25", 0.72, 0.70, 1.30))
    assert rec["status"] == "watchlist" and "fair price" in rec["reasons"][0]
    rec = sl.evaluate(row(), Sel("H", 0.75, 0.55, 1.75))                                   # 20 pp gap = data fault
    assert rec["status"] == "rejected" and "data fault" in rec["reasons"][0]


def test_market_bars_are_per_market():
    assert sl.evaluate(row(), Sel("H", 0.62, 0.58, 1.70))["status"] == "primary"           # 1X2 bar 60 %
    assert sl.evaluate(row(), Sel("O15", 0.66, 0.62, 1.60))["status"] == "rejected"        # goals lines other than Over 2.5: 70 %
    assert sl.evaluate(row(), Sel("CO85", 0.71, 0.67, 1.55))["status"] == "primary"        # corners bar 65 %


def test_over_25_starts_from_55_percent_and_btts_is_no_longer_offered():
    """User rule 2026-10-17: Over 2.5 starts from a 55 % published probability (was 70 %); BTTS is dropped (2026-10-27)."""
    ok = sl.evaluate(row(), Sel("O25", 0.64, 0.60, 1.70))
    assert ok["status"] == "primary", ok["reasons"]
    assert ok["bar"] == 0.55                                       # the bar shown with the pick is the real one
    no = sl.evaluate(row(), Sel("O25", 0.54, 0.52, 1.80))
    assert no["status"] == "rejected" and "below the 55% bar" in no["reasons"][0]
    gone = sl.evaluate(row(), Sel("BTTS", 0.72, 0.66, 1.50))
    assert gone["status"] == "rejected" and "no longer offered" in gone["reasons"][0]
    # the stricter bars did not move
    assert sl.evaluate(row(), Sel("O15", 0.69, 0.66, 1.55))["status"] == "rejected"
    assert sl.evaluate(row(), Sel("O35", 0.60, 0.57, 1.70))["status"] == "rejected"
    assert sl.BARS["goals"] == 0.70 and sl.BARS["corners"] == 0.65 and sl.BARS["cards"] == 0.65


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
    good = [Sel("O25", 0.74, 0.68, 1.45), Sel("CO85", 0.72, 0.68, 1.45)]
    rows, b = _board(monkeypatch, [good] * 8)                               # lanes: Over 2.5 claims 3, corners claim 3 of the rest
    assert b["counts"]["primary"] == 6 and len(b["primary"]) == 6
    assert len({(x["home"], x["away"]) for x in b["primary"]}) == 6          # still ONE selection per match
    assert sorted(x["sel"] for x in b["primary"]) == ["CO85"] * 3 + ["O25"] * 3
    assert all(x["status"] == "primary" for x in b["primary"])
    assert b["primary"][0]["correlated"], "the second selection of the match is named as correlated"
    assert sum("outside the top 3" in x["reasons"][0] for x in b["watchlist"]) == 2
    assert all(x["rank"] in (1, 2, 3) for x in b["primary"])
    assert b["rules"]["band"].startswith("1.16")


def test_the_old_one_best_per_match_behaviour_is_one_switch_away(monkeypatch):
    monkeypatch.setattr(sl, "LANES", False)
    good = [Sel("O25", 0.74, 0.68, 1.45), Sel("CO85", 0.72, 0.68, 1.45)]
    rows, b = _board(monkeypatch, [good] * 5)
    assert b["counts"]["primary"] == 3 and len(b["primary"]) == 3          # one per match first, then cap 3
    assert any("outside the top 3" in x["reasons"][0] for x in b["watchlist"])


# ---------------------------------------------------------------- lanes (2026-10-17): every market gets its own slots
def _o15(): return Sel("O15", 0.86, 0.84, 1.18)
def _o25(): return Sel("O25", 0.70, 0.66, 1.55)
def _co(): return Sel("CO85", 0.72, 0.68, 1.45)      # stands where BTTS used to: its own lane, claimed after Over 2.5


def test_each_market_claims_its_own_matches_instead_of_losing_every_match_to_over15(monkeypatch):
    """Over 1.5 is always the likelier of the three, so 'the best-scored candidate wins the match' gave it 286 of 303
    matches and Over 2.5 could never appear whatever its floor. Each market now claims its own, Over 1.5 takes the rest."""
    rows, b = _board(monkeypatch, [[_o15(), _o25(), _co()]] * 4 + [[_o15()]] * 4 + [[_o15(), _co()]] * 2, cap=10)
    mix = {k: sum(1 for x in b["primary"] if x["sel"] == k) for k in ("O25", "CO85", "O15")}
    assert mix == {"O25": 4, "CO85": 2, "O15": 4}, mix                       # 10 matches, 10 primaries, one selection each
    assert len({(x["home"], x["away"]) for x in b["primary"]}) == len(b["primary"]) == 10
    assert b["counts"]["watchlist"] == 0


def test_a_match_cut_from_one_lane_can_still_be_claimed_by_a_later_one(monkeypatch):
    rows, b = _board(monkeypatch, [[_o15(), _o25()]] * 4, cap=2)           # Over 2.5 takes 2; the other two matches go to Over 1.5
    mix = sorted(x["sel"] for x in b["primary"])
    assert mix == ["O15", "O15", "O25", "O25"] and b["counts"]["watchlist"] == 0


def test_a_lane_never_pads_and_the_cap_still_applies_per_lane(monkeypatch):
    rows, b = _board(monkeypatch, [[_o15(), _o25()]] * 30, cap=10)          # 10 Over 2.5 + 10 Over 1.5, ten matches left over
    assert sorted({x["sel"] for x in b["primary"]}) == ["O15", "O25"] and b["counts"]["primary"] == 20
    assert sum("outside the top 10" in x["reasons"][0] for x in b["_watch_all"]) == 10
    rows, b = _board(monkeypatch, [[_o15()]] * 3, cap=10)
    assert b["counts"]["primary"] == 3                                      # nothing padded to fill a lane
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
    assert b["rejected_patterns"][0][0] == "odds under the 1.16 floor"
    assert "NO QUALIFYING SELECTIONS" in "\n".join(sl.markdown(sl.public(b)))


def test_the_published_probability_is_the_market_anchored_blend_and_the_model_is_kept(monkeypatch):
    """2026-10-27: the board publishes 25 % model / 75 % de-vigged market, and the raw model number is still in the
    record as `p_model` — the filter never throws the model away, it anchors it."""
    s = Sel("O25", 0.74, 0.68, 1.45)
    rows, b = _board(monkeypatch, [[s]])
    assert (s.p_model, s.p_sb, s.odds) == (0.74, 0.68, 1.45)          # the selection itself is untouched
    rec = b["primary"][0]
    assert rec["p"] == 0.695 and rec["p_model"] == 0.74               # 0.25*0.74 + 0.75*0.68 = 0.695
    assert rec["edge_pp"] == 1.5                                      # published edge, not the raw 6 pp


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


def test_cap_overflow_sends_the_rest_to_the_watchlist(monkeypatch):
    """With EV out of the gates, strength still fills the list only to the per-market cap."""
    rows, b = _board(monkeypatch, [[Sel("O25", 0.74, 0.68, 1.45)]] * 13, cap=10)
    assert b["counts"]["primary"] == 10 and b["counts"]["watchlist"] == 3
    assert any("outside the top 10" in x["reasons"][0] for x in b["watchlist"])
    assert b["rules"]["ev"].startswith("not a gate")


def test_unders_are_ignored_overs_only(monkeypatch):
    """User rule (2026-10-10): Under selections are never candidates in any market."""
    rows, b = _board(monkeypatch, [[Sel("U25", 0.80, 0.72, 1.30)], [Sel("CU85", 0.75, 0.70, 1.35)]])
    assert b["counts"]["candidates"] == 0 and b["counts"]["primary"] == 0
    assert b["rules"]["unders"].startswith("none in any market")
    overs = [[Sel("O25", 0.74, 0.68, 1.45)]]
    rows, b = _board(monkeypatch, overs)
    assert b["counts"]["candidates"] == 1 and b["counts"]["primary"] == 1


def test_shortlist_covers_today_only(monkeypatch):
    """User rule (2026-10-10): matches from tomorrow or later never enter the day's shortlist."""
    r_today = row(home="T1", away="T2", ko_h=5)
    r_tomorrow = row(home="T3", away="T4", ko_h=24 + 5)
    table = {id(r_today): [Sel("O25", 0.74, 0.68, 1.45)], id(r_tomorrow): [Sel("O25", 0.74, 0.68, 1.45)]}
    monkeypatch.setattr(sl.safe_mod, "selections", lambda r: table[id(r)])
    end_of_day = datetime.combine(NOW.date(), datetime.min.time()).replace(hour=23, minute=59)
    b = sl.build([r_today, r_tomorrow], NOW, end_of_day)
    assert b["counts"]["analysed"] == 1
    assert all(x["home"] != "T3" for x in b["primary"])
    assert b["rules"]["day"] == "today's matches only (nothing from tomorrow or later)"
