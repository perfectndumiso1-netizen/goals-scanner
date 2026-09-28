"""Focused tests for the tennis engine (no network; synthetic data only).
Run: python3 -m pytest tennis/tests -q
"""
from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# isolate all file output before importing the package
_TMP = tempfile.mkdtemp(prefix="tennis-test-")
os.environ["TENNIS_STATE_DIR"] = _TMP
os.environ["TENNIS_CACHE_DIR"] = str(Path(_TMP) / "cache")

from tennis import config as C          # noqa: E402
from tennis import data as D            # noqa: E402
from tennis import history as H         # noqa: E402
from tennis import markets as MK        # noqa: E402
from tennis import model as M           # noqa: E402
from tennis import quality as Q         # noqa: E402
from tennis import report as REP        # noqa: E402
from tennis import stats as S           # noqa: E402
from tennis.scanner import dedupe_fixtures, analyse   # noqa: E402

PLAYERS = pd.DataFrame([
    {"pid": "1", "name": "Felix Auger Aliassime", "ioc": "CAN", "tour": "atp"},
    {"pid": "2", "name": "Alex De Minaur", "ioc": "AUS", "tour": "atp"},
    {"pid": "3", "name": "Alexander Zverev", "ioc": "GER", "tour": "atp"},
    {"pid": "4", "name": "Mischa Zverev", "ioc": "GER", "tour": "atp"},
    {"pid": "7", "name": "Andrey Zverev", "ioc": "GER", "tour": "atp"},
    {"pid": "5", "name": "Iga Swiatek", "ioc": "POL", "tour": "wta"},
    {"pid": "6", "name": "Juan Martin Del Potro", "ioc": "ARG", "tour": "atp"},
])


# ------------------------------------------------------------------ identity & names
def test_player_identity_variations():
    idx = D.PlayerIndex(PLAYERS)
    assert idx.resolve("Félix Auger-Aliassime", "CAN")["pid"] == "1"          # accents + hyphen
    assert idx.resolve("Auger-Aliassime, Felix")["pid"] == "1"                 # 'Last, First' (Sportybet)
    assert idx.resolve("Alex de Minaur", "AUS")["pid"] == "2"                  # particle capitalisation
    assert idx.resolve("Świątek, Iga")["pid"] == "5"
    r = idx.resolve("A. Zverev", "GER")                                        # initial + surname: two candidates → never guess
    assert r["how"] == "new" and r.get("ambiguous") is True
    assert idx.resolve("M. Zverev", "GER")["pid"] == "4"                       # unique initial → fuzzy match
    assert idx.resolve("Juan Martin del Potro")["pid"] == "6"
    new = idx.resolve("Nobody Known", "XXX", ls_id="999")
    assert new["how"] == "new" and new["pid"] == "ls999"                       # unmatched → own identity, no borrowed data
    assert idx.resolve("whatever", ls_id="999")["pid"] == "ls999"              # remembered by Livescore id


def test_names_match_scores():
    assert D.names_match("Carlos Alcaraz", "Alcaraz, Carlos") == 1.0
    assert D.names_match("C. Alcaraz", "Carlos Alcaraz") == 0.9
    assert D.names_match("Carlos Alcaraz", "Carlos Moya") == 0.0


# ------------------------------------------------------------------ fixtures
def _stage(cnm="ATP 250", snm="Chengdu Open"):
    return {"Cnm": cnm, "Snm": snm, "Sid": "1"}


def _event(eid="10", t1="Jannik Sinner", t2="Carlos Alcaraz", eps="NS", sets=(), sw=None, esd=20260928100000):
    ev = {"Eid": eid, "Eps": eps, "Esd": esd, "T1": [{"ID": "a", "Nm": t1, "CoId": "ITA"}], "T2": [{"ID": "b", "Nm": t2, "CoId": "ESP"}]}
    for i, (a, b) in enumerate(sets, 1):
        ev[f"Tr1S{i}"], ev[f"Tr2S{i}"] = str(a), str(b)
    if sw:
        ev["Tr1"], ev["Tr2"] = str(sw[0]), str(sw[1])
    return ev


def test_invalid_fixtures_are_rejected():
    st = D.classify_stage(_stage())
    assert st and st["tour"] == "atp"
    assert D.classify_stage(_stage("ITF Men", "M15 Monastir")) is None
    assert D.classify_stage(_stage("ATP 250", "Chengdu Open Doubles")) is None
    assert D.classify_stage(_stage("Billie Jean King Cup", "Finals")) is None
    ev = _event()
    ev["T1"] = [{"ID": "a", "Nm": "X"}, {"ID": "c", "Nm": "Y"}]                 # doubles pairing → not a singles match
    assert D.parse_event(ev, st) is None
    rec = D.parse_event(_event(eps="Canc."), st)
    assert rec["cancelled"] and not rec["finished"] and rec["winner"] is None
    rec = D.parse_event(_event(eps="FT", sets=((6, 4), (3, 6), (7, 6)), sw=(2, 1)), st)
    assert rec["finished"] and rec["winner"] == 1 and rec["sets"] == [[6, 4], [3, 6], [7, 6]] and rec["start"] == "2026-09-28 10:00"
    rec = D.parse_event(_event(eps="Ret.", sets=((6, 4), (2, 1)), sw=(1, 0)), st)
    assert rec["finished"] and rec["retired"] and rec["winner"] == 1


def test_duplicate_matches_collapse():
    a = {"day": "2026-09-28", "p1": {"name": "Jannik Sinner"}, "p2": {"name": "Carlos Alcaraz"}}
    b = {"day": "2026-09-28", "p1": {"name": "Alcaraz, Carlos"}, "p2": {"name": "Sinner, Jannik"}}
    c = {"day": "2026-09-29", "p1": {"name": "Jannik Sinner"}, "p2": {"name": "Carlos Alcaraz"}}
    assert len(dedupe_fixtures([a, b, c])) == 2


def test_score_parsing():
    s = D.parse_score("6-4 5-7 7-6(4)")
    assert (s["w_games"], s["l_games"], s["w_sets"], s["l_sets"], s["tiebreaks"], s["retired"]) == (18, 17, 2, 1, 1, False)
    assert D.parse_score("6-7(4) 6-5 RET")["retired"] is True
    assert D.parse_score("W/O")["walkover"] is True and D.parse_score("W/O")["w_games"] is None
    assert D.parse_score(None)["w_games"] is None
    assert S.tiebreaks_won("7-6(4) 6-7(3) 6-3") == (1, 1)


# ------------------------------------------------------------------ surface
def test_surface_handling():
    base = pd.DataFrame([{"tourney_name": "St. Tropez CH", "date": "2025-09-08", "surface": "Hard"},
                         {"tourney_name": "St. Tropez CH", "date": "2024-09-09", "surface": "Hard"}])
    sr = D.SurfaceResolver(base)
    assert sr.resolve("St. Tropez, France", 9)["surface"] == "Hard"
    assert sr.resolve("Wimbledon", 7)["surface"] == "Grass"                    # override
    assert sr.resolve("Completely Unknown Trophy", 9)["surface"] is None        # never guessed
    R = M.Ratings()
    R.update("a", "b", "Hard", "2026-01-01")
    R.update("a", "b", "Hard", "2026-01-02")
    R.update("b", "a", "Clay", "2026-01-03")                                       # a leads overall, b leads on clay
    p_clay, p_none = R.predict("a", "b", "Clay", 3), R.predict("a", "b", None, 3)
    assert p_none["diff_surface"] is None and p_clay["diff_surface"] is not None
    assert p_clay["p_match"] != p_none["p_match"]


# ------------------------------------------------------------------ probabilities: bounds, sums, formats
def test_probability_bounds_and_sums():
    R = M.Ratings()
    R.r["a"], R.r["b"] = 2600.0, 1200.0
    p = R.predict("a", "b", None, 3)["p_match"]
    assert 0.0 < p < 1.0
    for pa, pb, bo in ((0.64, 0.64, 3), (0.70, 0.58, 3), (0.62, 0.61, 5)):
        d = M.match_distribution(pa, pb, bo, bo == 5)
        assert abs(sum(d["total_games"].values()) - 1) < 1e-9
        assert abs(sum(d["set_scores"].values()) - 1) < 1e-9
        assert abs(sum(d["handicap"].values()) - 1) < 1e-9
        win, lose, push = M.handicap_probs(d["handicap"], -2.5)
        assert abs(win + lose + push - 1) < 1e-9 and push == 0
        assert abs(M.over_prob(d["total_games"], 22.5) + (1 - M.over_prob(d["total_games"], 22.5)) - 1) < 1e-12
    for p_set in (0.3, 0.5, 0.64, 0.9):
        assert abs(sum(M.set_scores(p_set, 3).values()) - 1) < 1e-9
        assert abs(sum(M.set_scores(p_set, 5).values()) - 1) < 1e-9
    assert abs(M.match_distribution(0.64, 0.64, 3)["p_match"] - 0.5) < 1e-9        # symmetry


def test_best_of_3_and_5_differ():
    p_set = 0.6
    p3, p5 = M.match_from_set(p_set, 3), M.match_from_set(p_set, 5)
    assert p5 > p3 > p_set                                                        # longer format favours the better player
    assert abs(M.set_from_match(p3, 3) - p_set) < 1e-6 and abs(M.set_from_match(p5, 5) - p_set) < 1e-6
    assert set(M.set_scores(0.6, 5)) == {"3-0", "3-1", "3-2", "0-3", "1-3", "2-3"}
    assert set(M.set_scores(0.6, 3)) == {"2-0", "2-1", "0-2", "1-2"}
    d3, d5 = M.match_distribution(0.66, 0.60, 3), M.match_distribution(0.66, 0.60, 5, True)
    assert d5["expected_total"] > d3["expected_total"] * 1.4
    assert d5["p_match"] > d3["p_match"]
    R = M.Ratings()
    R.r["a"], R.r["b"] = 1700.0, 1500.0
    assert R.predict("a", "b", None, 5)["p_match"] > R.predict("a", "b", None, 3)["p_match"]
    pa, pb = M.solve_serve_split(0.7, 1.26, 5, True)
    assert abs(M.match_distribution(pa, pb, 5, True)["p_match"] - 0.7) < 0.003
    # day-form spread mixture: still pinned to the target, still a proper distribution, shorter matches than the fixed chain
    mx = M.match_distribution_mixture(0.7, 1.26, 3, False, 0.10)
    fixed = M.match_distribution_mixture(0.7, 1.26, 3, False, 0.0)
    assert abs(mx["p_match"] - 0.7) < 0.003 and abs(fixed["p_match"] - 0.7) < 0.003
    assert abs(sum(mx["total_games"].values()) - 1) < 1e-6 and abs(sum(mx["set_scores"].values()) - 1) < 1e-6
    assert set(mx["set_scores"]) == {"2-0", "2-1", "0-2", "1-2"} and mx["expected_total"] < fixed["expected_total"]


# ------------------------------------------------------------------ no look-ahead
def _rec(day, w, l, surface="Hard", **kw):
    r = {"date": day, "surface": surface, "tour": "atp", "level": "A", "best_of": 3, "tournament": "T", "round": "R32", "w": w, "l": l,
         "opp_name_w": l, "opp_name_l": w, "w_name": w, "l_name": l, "score": "6-4 6-4", "retired": False, "w_games": 12, "l_games": 8,
         "w_sets": 2, "l_sets": 0, "tiebreaks": 0, "src": "test", "w_rank": None, "l_rank": None}
    for c in D.STAT_COLS:
        r[f"w_{c}"] = kw.get(f"w_{c}")
        r[f"l_{c}"] = kw.get(f"l_{c}")
    return r


def test_no_look_ahead_bias():
    recs = [_rec("2026-01-01", "a", "b"), _rec("2026-01-02", "a", "b"), _rec("2026-01-03", "a", "b")]
    got = []
    H.replay(list(recs), M.Ratings(), S.PlayerStats(), lambda rec, pred: got.append(pred["p_match"]))
    assert got[0] == 0.5                                                          # nothing known before the first match
    assert got[1] > 0.5 and got[2] > got[1]
    got2 = []
    H.replay(list(recs) + [_rec("2026-01-04", "b", "a")] * 5, M.Ratings(), S.PlayerStats(), lambda rec, pred: got2.append(pred["p_match"]))
    assert got2[:3] == got                                                        # later results never change earlier predictions


def test_features_only_from_earlier_matches():
    PS = S.PlayerStats()
    PS.observe(dict(_rec("2026-01-01", "a", "b"), exp_w=0.5, rating_w=1500, rating_l=1500))
    f = PS.features("a", "2026-01-02", "Hard", "atp")
    assert f["form"]["last5"] == {"n": 1, "wins": 1, "rate": 1.0}
    assert f["form"]["last10"]["n"] == 1                                          # incomplete sample reported as such
    assert f["serve"] is None and f["traits"] is None                             # no stats → N/A, not zero


# ------------------------------------------------------------------ missing / stale statistics
def test_missing_statistics_stay_na():
    PS = S.PlayerStats({"atp|Hard": 0.63})
    PS.observe(dict(_rec("2026-01-01", "a", "b", w_svpt=80, w_1stIn=50, w_1stWon=38, w_2ndWon=15, w_SvGms=12, w_bpSaved=2, w_bpFaced=3,
                         l_svpt=70, l_1stIn=45, l_1stWon=30, l_2ndWon=10, l_SvGms=11, l_bpSaved=3, l_bpFaced=6), exp_w=0.5, rating_w=1500, rating_l=1500))
    fa = PS.features("a", "2026-01-10", "Hard", "atp")
    assert fa["serve"]["n"] == 1 and abs(fa["serve"]["spw"] - 53 / 80) < 1e-9
    assert fa["traits"]["low_confidence"] is True                                 # one match → low confidence
    assert fa["serve"]["stale"] is False
    fb = PS.features("a", "2027-06-01", "Hard", "atp")
    assert fb["serve"]["stale"] is True and fb["serve"]["age_days"] > C.SERVE_FRESH_DAYS
    fc = PS.features("zzz", "2026-01-10", "Hard", "atp")
    assert fc["n"] == 0 and fc["serve"] is None and fc["profile"] is None


def test_quality_is_not_a_probability_and_flags_insufficient_history():
    fx = {"start": "2026-09-28 10:00", "day": "2026-09-28", "p1": {"name": "A", "ls_id": "1"}, "p2": {"name": "B", "ls_id": "2"},
          "tournament": "T", "category": "ATP 250", "qualifying": False, "tour": "atp", "level": "A", "status": "NS"}
    R = M.Ratings()
    pred = R.predict("x", "y", None, 3)
    empty = S.PlayerStats().features("x", "2026-09-28", None, "atp")
    q = Q.assess(fx, pred, empty, empty, {"surface": None, "how": "unresolved"}, {"how": "new"}, {"how": "new"}, None, {"complete": True, "to": "2026-09-27"})
    assert q["overall"] == "Low" and 0 <= q["score"] <= 100 and "note" in q
    assert any(i["check"] == "ratings" and i["status"] == "N/A" for i in q["items"])
    assert any(i["check"] == "serve_data" and i["status"] == "N/A" for i in q["items"])
    # same fixture, different model probability → identical quality score (quality never depends on p)
    R.r["x"] = 1900.0
    q2 = Q.assess(fx, R.predict("x", "y", None, 3), empty, empty, {"surface": None, "how": "unresolved"}, {"how": "new"}, {"how": "new"}, None, {"complete": True})
    assert q2["score"] == q["score"]


# ------------------------------------------------------------------ odds & markets
def test_invalid_odds_ignored_and_market_sums():
    mk = D.parse_sporty_markets([
        {"id": "186", "outcomes": [{"desc": "Home", "odds": "1.00"}, {"desc": "Away", "odds": "3.10"}]},           # 1.00 is not a price
        {"id": "186", "outcomes": [{"desc": "Home", "odds": "1.45"}, {"desc": "Away", "odds": "abc"}]},            # non-numeric
        {"id": "189", "specifier": "total=22.5", "outcomes": [{"desc": "Over 22.5", "odds": "1.85"}, {"desc": "Under 22.5", "odds": "1.95"}]},
        {"id": "187", "specifier": "hcp=-3.5", "outcomes": [{"desc": "Home", "odds": "1.90"}, {"desc": "Away", "odds": "1.90"}]},
    ])
    assert "winner" not in mk and mk["total_games"][22.5]["over"] == 1.85 and mk["game_handicap"][-3.5]["p1"] == 1.9
    assert MK.implied(None, 2.0) == (None, None, None)
    fx = {"p1": {"name": "A"}, "p2": {"name": "B"}}
    pred = {"p_match": 0.64, "set_scores": M.set_scores(0.59, 3), "best_of": 3}
    dist = M.match_distribution_mixture(0.64, 1.26, 3, False, 0.10)
    rows = MK.build(fx, pred, dist, {"markets": mk, "swapped": False}, low_conf_games=False)
    by = {(r["market"], r["selection"], r["line"]): r for r in rows}
    assert abs(by[("winner", "player_a", None)]["model_p"] + by[("winner", "player_b", None)]["model_p"] - 1) < 1e-6
    assert abs(by[("total_games", "over", 22.5)]["model_p"] + by[("total_games", "under", 22.5)]["model_p"] - 1) < 1e-6
    assert abs(by[("game_handicap", "player_a", -3.5)]["model_p"] + by[("game_handicap", "player_b", 3.5)]["model_p"] - 1) < 1e-6
    assert all(0 <= r["model_p"] <= 1 for r in rows)
    r = by[("total_games", "over", 22.5)]
    assert r["book_odds"] == 1.85 and abs(r["implied_fair"] - (1 / 1.85) / (1 / 1.85 + 1 / 1.95)) < 1e-4
    assert r["fair_odds"] == round(1 / r["model_p"], 2)
    # prices never change the model probability
    rows_no_odds = MK.build(fx, pred, dist, None, low_conf_games=False)
    assert rows_no_odds[0]["model_p"] == rows[0]["model_p"]


def test_highlights_respect_thresholds_and_language():
    rows = [{"market": "winner", "selection": "player_a", "line": None, "model_p": 0.70, "fair_odds": 1.43, "book_odds": 1.70, "implied": 0.588,
             "implied_fair": 0.56, "edge_pp": 14.0, "ev": 0.19, "low_confidence": False, "label": "A to win"}]
    assert MK.highlights(rows, 85, 60)[0]["flag"] == "Model above market"
    assert MK.highlights(rows, 50, 60) == []                                      # low data quality → no highlight
    assert MK.highlights(rows, 85, 12) == []                                      # thin history → no highlight
    assert MK.highlights([dict(rows[0], edge_pp=28.0)], 85, 60) == []             # implausibly large gap → warning, not highlight
    assert MK.highlights([dict(rows[0], low_confidence=True)], 85, 60) == []
    assert MK.highlights([dict(rows[0], book_odds=1.20)], 85, 60) == []
    game = dict(rows[0], market="total_games", selection="under", line=22.5, edge_pp=7.0, label="Under 22.5 games")
    assert MK.highlights([game], 85, 60) == []                                    # game markets need the larger gap
    assert MK.highlights([dict(game, edge_pp=11.0)], 85, 60)[0]["market"] == "total_games"
    both = MK.highlights([rows[0], dict(game, edge_pp=16.0)], 85, 60)             # one highlight per match: the larger edge
    assert len(both) == 1 and both[0]["market"] == "total_games"


# ------------------------------------------------------------------ tracker settlement
def test_tracker_settlement():
    H._write_tracker([])
    H.record_selections([
        {"date": "2026-09-28", "match_id": "m1", "market": "winner", "selection": "player_a", "line": "", "model_probability": 0.7},
        {"date": "2026-09-28", "match_id": "m1", "market": "total_games", "selection": "over", "line": 22.5, "model_probability": 0.55},
        {"date": "2026-09-28", "match_id": "m1", "market": "game_handicap", "selection": "player_a", "line": -3.5, "model_probability": 0.5},
        {"date": "2026-09-28", "match_id": "m2", "market": "total_games", "selection": "under", "line": 20.5, "model_probability": 0.5},
        {"date": "2026-09-28", "match_id": "m1", "market": "winner", "selection": "player_a", "line": "", "model_probability": 0.7},   # duplicate
    ])
    assert len(H._read_tracker()) == 4
    n = H.settle({"m1": {"finished": True, "winner": 1, "sets": [[6, 4], [7, 6]], "retired": False},
                  "m2": {"finished": True, "winner": 2, "sets": [[3, 6], [1, 2]], "retired": True}})
    assert n == 4
    rows = {(r["match_id"], r["market"]): r for r in H._read_tracker()}
    assert rows[("m1", "winner")]["won"] == "1"
    assert rows[("m1", "total_games")]["won"] == "1"                              # 23 games > 22.5
    assert rows[("m1", "game_handicap")]["won"] == "0"                            # margin +3 does not cover −3.5
    assert rows[("m2", "total_games")]["won"] == "void"                           # retirement → game market void


# ------------------------------------------------------------------ end-to-end analysis with synthetic state
def test_analyse_and_report_language():
    R, PS = M.Ratings(), S.PlayerStats({"atp|Hard": 0.63})
    recs = [_rec(f"2026-0{1 + i // 20}-{1 + i % 20:02d}", "a" if i % 3 else "b", "b" if i % 3 else "a") for i in range(40)]
    H.replay(recs, R, PS)
    idx = D.PlayerIndex(pd.DataFrame([{"pid": "a", "name": "Anna Alpha", "ioc": "AAA", "tour": "atp"}, {"pid": "b", "name": "Bea Beta", "ioc": "BBB", "tour": "atp"}]))
    fx = {"ls_id": "77", "start": "2026-09-28 12:00", "day": "2026-09-28", "status": "NS", "tour": "atp", "level": "A", "category": "ATP 250",
          "tournament": "Chengdu Open", "qualifying": False, "p1": {"name": "Anna Alpha", "ls_id": "1", "ioc": "AAA"}, "p2": {"name": "Bea Beta", "ls_id": "2", "ioc": "BBB"}}
    m = analyse(fx, R, PS, idx, D.SurfaceResolver(None), None, {"complete": True, "to": "2026-09-27"})
    assert abs(m["p"]["a"] + m["p"]["b"] - 1) < 1e-6 and m["surface"] == "Hard" and m["best_of"] == 3
    assert m["games"]["low_confidence"] is True                                    # no serve statistics → flagged
    assert m["explain"]["steps"] and m["quality"]["score"] <= 100
    md = REP.markdown("2026-09-28", [m], [], {}, {"generated": "now", "priced": 0, "backfill": {"to": "2026-09-27"}})
    low = md.lower()
    for bad in ("safe bet", "banker", "guaranteed", "sure win", "lock"):
        assert bad not in low
    assert "TENNIS SCANNER" in md and "not a probability" in md
