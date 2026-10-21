"""Settlement: every market code is graded from the number it actually names (2026-10-21)."""
from __future__ import annotations

import pandas as pd

import safe


def test_team_corner_markets_use_that_teams_corners_not_the_match_total():
    # Bromley 0-4 Leicester, corners 5-4. "Bromley over 3.5 corners" won; it used to be graded as a match under.
    assert safe.settle("CHO35", 0, 4, 5, 4) is True
    assert safe.settle("CAO35", 0, 4, 5, 4) is True
    assert safe.settle("CAU35", 0, 4, 5, 4) is False
    assert safe.settle("CHO45", 0, 4, 5, 4) is True
    assert safe.settle("CHO55", 0, 4, 5, 4) is False
    # Walsall 3-0 Oldham, corners 8-1
    assert safe.settle("CHO35", 3, 0, 8, 1) is True
    assert safe.settle("CAO35", 3, 0, 8, 1) is False


def test_total_corner_markets_still_use_the_match_total():
    assert safe.settle("CO85", 2, 1, 6, 4) is True
    assert safe.settle("CU85", 2, 1, 6, 4) is False
    assert safe.settle("CU105", 2, 1, 5, 4) is True


def test_team_card_markets_use_that_teams_cards_and_totals_use_both():
    assert safe.settle("KHO25", 1, 0, None, None, 3, 2) is True
    assert safe.settle("KHU25", 1, 0, None, None, 3, 2) is False
    assert safe.settle("KAO15", 1, 0, None, None, 1, 2) is True
    assert safe.settle("KO35", 1, 0, None, None, 3, 2) is True      # 5 cards
    assert safe.settle("KU35", 1, 0, None, None, 3, 2) is False


def test_goal_markets_are_unchanged():
    assert safe.settle("O15", 2, 1) is True
    assert safe.settle("U25", 1, 0) is True
    assert safe.settle("HO05", 1, 0) is True
    assert safe.settle("AO05", 1, 0) is False
    assert safe.settle("HU15", 1, 1) is True and safe.settle("HU15", 2, 1) is False
    assert safe.settle("BTTS", 1, 1) is True and safe.settle("NBTTS", 0, 1) is True
    assert safe.settle("H", 2, 1) is True and safe.settle("A", 2, 1) is False and safe.settle("D", 1, 1) is True


def test_a_statistic_the_feed_never_published_is_never_a_loss():
    assert safe.settle("CHO35", 2, 1, None, 4) is None          # home corners missing
    assert safe.settle("CO85", 2, 1, None, None) is None
    assert safe.settle("KO35", 2, 1, None, None, None, None) is None
    assert safe.settle("KAO15", 2, 1, None, None, 3, None) is None          # away cards missing
    assert safe.settle("KAO15", 2, 1, None, None, 3, 2) is True                    # away cards known
    assert safe.settle("NOPE", 2, 1) is None


def test_labels_and_groups_agree_with_the_grading_parser():
    assert safe.label("CHO35", "Bromley", "Leicester") == "Bromley over 3.5 corners"
    assert safe.label("CAU55", "Bromley", "Leicester") == "Leicester under 5.5 corners"
    assert safe.label("KHO25", "Bromley", "Leicester") == "Bromley over 2.5 cards"
    assert safe.group("CHO35") == "corners" and safe.group("KHO25") == "cards"


def _results():
    return pd.DataFrame([
        {"country": "England", "home": "Bromley", "away": "Leicester", "date": pd.Timestamp("2026-10-20"),
         "hg": 0, "ag": 4, "hc": 5, "ac": 4, "hy": 2, "ay": 2, "hr": 0, "ar": 0},
    ])


def test_regrade_repairs_past_rows_settled_the_wrong_way_round():
    df = pd.DataFrame([
        {"country": "England", "home": "Bromley", "away": "Leicester", "match_date": "2026-10-20",
         "sel": "CHO35", "status": "miss", "score": "0-4", "settled_on": "2026-10-21", "odds": 1.42},
        {"country": "England", "home": "Bromley", "away": "Leicester", "match_date": "2026-10-20",
         "sel": "O25", "status": "miss", "score": "0-4", "settled_on": "2026-10-21", "odds": 1.9},
    ])
    out, fixed = safe.regrade_settled(df, _results(), pd.Timestamp("2026-10-21").to_pydatetime())
    assert fixed == 1
    assert out.loc[0, "status"] == "hit"           # team corners 5 > 3.5
    assert out.loc[1, "status"] == "miss"          # goals were always graded correctly, untouched


def test_regrade_leaves_rows_alone_when_the_statistic_is_missing():
    res = _results().assign(hc=None)
    df = pd.DataFrame([{"country": "England", "home": "Bromley", "away": "Leicester", "match_date": "2026-10-20",
                        "sel": "CHO35", "status": "miss", "score": "0-4", "settled_on": "2026-10-21"}])
    out, fixed = safe.regrade_settled(df, res, pd.Timestamp("2026-10-21").to_pydatetime())
    assert fixed == 0 and out.loc[0, "status"] == "miss"


def test_settle_bets_self_heals_a_wrongly_settled_row():
    df = pd.DataFrame([{"country": "England", "home": "Bromley", "away": "Leicester", "match_date": "2026-10-20",
                        "sel": "CHO35", "status": "miss", "score": "0-4", "settled_on": "2026-10-21",
                        "odds": 1.42, "p": 0.79, "label": "Bromley over 3.5 corners"}])
    out = safe.settle_bets(df, _results(), pd.Timestamp("2026-10-21").to_pydatetime())
    assert out.loc[0, "status"] == "hit"


def test_every_market_code_the_policy_can_emit_is_gradable():
    """Guard against the 2026-10-21 class of bug: a code that is offered but read as the opposite direction."""
    import itertools
    codes = []
    for line in ("05", "15", "25", "35", "45", "55", "65", "75", "85", "95", "105", "115"):
        codes += [f"O{line}", f"U{line}", f"HO{line}", f"HU{line}", f"AO{line}", f"AU{line}",
                  f"CO{line}", f"CU{line}", f"CHO{line}", f"CHU{line}", f"CAO{line}", f"CAU{line}",
                  f"KO{line}", f"KU{line}", f"KHO{line}", f"KHU{line}", f"KAO{line}", f"KAU{line}"]
    stats = dict(hg=2, ag=1, hc=6, ac=4, hcards=3, acards=2)
    for sel in codes + ["BTTS", "NBTTS", "H", "D", "A", "1X", "12", "X2"]:
        out = safe.settle(sel, stats["hg"], stats["ag"], stats["hc"], stats["ac"], stats["hcards"], stats["acards"])
        assert isinstance(out, bool), f"{sel} is not gradable"
    # A team market must use the team's own number, so the two sides can disagree on the same line
    assert safe.settle("CHO85", 2, 1, 6, 4) is False and safe.settle("CAO85", 2, 1, 6, 4) is False
    assert safe.settle("CHO55", 2, 1, 6, 4) is True and safe.settle("CHO65", 2, 1, 6, 4) is False
