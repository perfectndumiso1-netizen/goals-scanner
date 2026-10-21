"""Strong markets for the day (2026-10-21): 75%+, price 1.16+, and only Over 1.5 / team goals / corners / bookings.

Also covers the two changes that let total corners reach the board at all: the wider total-corner lines in the count
model, and the separate lane that gives the match-total corner and card markets their own slots.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace as NS

import appdata
import markets
import policy
import safe
import shortlist


# ---------------------------------------------------------------- the policy definition
def test_strong_market_codes_are_the_four_families_the_user_named():
    keep = ["O15", "HO05", "AO05", "HO15", "AO15", "CO75", "CO85", "CO95", "CHO35", "CAO45",
            "KO25", "KO35", "KHO15", "KAO25"]
    for code in keep:
        assert policy.is_strong_market(code), code
    # everything else the model still lists is NOT a strong market: no Over 2.5, no BTTS, no result, no unders
    for code in ("O25", "O35", "BTTS", "NBTTS", "H", "D", "A", "1X", "12", "X2", "U15", "U25",
                 "CU85", "CHU35", "KU35", "KAU25", "HU15"):
        assert not policy.is_strong_market(code), code


def test_the_strong_bar_is_75_percent_at_116_or_longer():
    assert policy.STRONG_P_MIN == 0.75
    assert policy.STRONG_ODDS_MIN == 1.16


# ---------------------------------------------------------------- total corners are no longer blind below 8.5
def test_the_corner_model_prices_total_lines_from_7_5_up():
    assert 7.5 in markets.CORNERS["lines_total"]
    assert min(markets.CORNERS["lines_total"]) == 7.5
    assert markets.CORNERS["lines_team"] == (3.5, 4.5, 5.5)


def test_a_ten_corner_match_gets_a_strong_total_corner_probability():
    # two balanced sides at ~5 corners each: the match total over 7.5 clears the 75% bar, which the old line set
    # (8.5 and above) could never show
    exp = markets.CountExpectation(eh=5.0, ea=5.0, h_neff=30, a_neff=30)
    probs = markets.count_lines(exp, markets.CORNERS)
    assert probs["total"][7.5] >= 0.75
    assert probs["total"][7.5] > probs["total"][8.5] > probs["total"][9.5]


# ---------------------------------------------------------------- the board gives totals their own lane
def _row(i: int, corner_total=None, corner_team=None, card_total=None, card_team=None):
    now = datetime(2026, 10, 21, 12, 0)
    corner_p = None
    sb_full = {}
    if corner_total or corner_team:
        corner_p = {"total": {}, "home": {}, "away": {}}
        if corner_total:
            corner_p["total"][7.5] = corner_total
            sb_full["CORN"] = {7.5: (1.30, 3.20)}
        if corner_team:
            corner_p["home"][4.5] = corner_team
            corner_p["away"][4.5] = corner_team
            sb_full["CORNH"] = {4.5: (1.25, 3.50)}
            sb_full["CORNA"] = {4.5: (1.25, 3.50)}
    card_p = None
    if card_total or card_team:
        card_p = {"total": {}, "home": {}, "away": {}}
        if card_total:
            card_p["total"][3.5] = card_total
            sb_full["CARDS"] = {3.5: (1.30, 3.20)}
        if card_team:
            card_p["home"][1.5] = card_team
            card_p["away"][1.5] = card_team
            sb_full["CARDSH"] = {1.5: (1.25, 3.50)}
            sb_full["CARDSA"] = {1.5: (1.25, 3.50)}
    return NS(
        data_ok=True,
        fx={"date": now.date(), "kickoff": now + timedelta(hours=3), "country": "England", "div": "E0",
            "league": "Premier League", "home": f"H{i}", "away": f"A{i}"},
        sb={"OU": {1.5: (1.28, 3.60)}, "CORN": {7.5: (1.30, 3.20)} if corner_total else {},
            "CARDS": {3.5: (1.30, 3.20)} if card_total else {}},
        extra=NS(x12=None, tg={}, corner_p=corner_p, card_p=card_p),
        p_final={"O05": 0.97, "O15": 0.82, "O25": 0.30, "O35": 0.10, "O45": 0.05, "O55": 0.02, "BTTS": 0.30},
        sb_full=sb_full,
    )


def test_total_corners_and_team_corners_have_separate_lanes():
    assert safe.safe_lane("CO85") == "corners" and safe.safe_lane("CO75") == "corners"
    assert safe.safe_lane("CHO35") == "corners_team" and safe.safe_lane("CAO45") == "corners_team"
    assert safe.safe_lane("KO35") == "cards" and safe.safe_lane("KHO25") == "cards_team"


def test_the_shortlist_lanes_split_totals_from_team_lines_too():
    assert shortlist.lane_of({"sel": "CO85", "market": "corners"}) == "corners"
    assert shortlist.lane_of({"sel": "CHO35", "market": "corners"}) == "corners_team"
    assert shortlist.lane_of({"sel": "KO35", "market": "cards"}) == "cards"
    assert shortlist.lane_of({"sel": "KHO25", "market": "cards"}) == "cards_team"
    order = list(shortlist.LANE_ORDER)
    assert order.index("corners") < order.index("corners_team")
    assert order.index("cards") < order.index("cards_team")
    assert shortlist.LANE_CAP["corners_team"] < shortlist.MAX_PER_MARKET


def test_the_board_fills_the_total_corner_lane_before_the_team_lines_and_never_without_it():
    now = datetime(2026, 10, 21, 12, 0)
    rows = [_row(i, corner_total=0.80, corner_team=0.88, card_total=0.78, card_team=0.86) for i in range(20)]
    bets = safe.safest(rows, now, now + timedelta(days=1))["bets"]
    totals = [b for b in bets if b.sel.startswith("CO")]
    teams = [b for b in bets if b.sel[:2] in ("CH", "CA")]
    cards_t = [b for b in bets if b.sel.startswith("KO")]
    cards_team = [b for b in bets if b.sel[:2] in ("KH", "KA")]
    assert len(totals) == safe.SAFE_LANE_CAP["corners"] == 4        # the total market always gets its slots
    assert len(teams) == safe.SAFE_LANE_CAP["corners_team"]         # team corners cannot swallow them any more
    assert len(cards_t) == safe.SAFE_LANE_CAP["cards"] and len(cards_team) == safe.SAFE_LANE_CAP["cards_team"]
    assert len({b.key for b in bets}) == len(bets)                  # still one market per match
    # a board with only team-corner candidates must not borrow the total lane's slots
    only_team = safe.safest([_row(i, corner_team=0.88) for i in range(10)], now, now + timedelta(days=1))["bets"]
    assert len([b for b in only_team if b.sel[:2] in ("CH", "CA")]) == safe.SAFE_LANE_CAP["corners_team"]


# ---------------------------------------------------------------- the home-page section
def _item(sel, p, odds, fid="fx1", **over):
    base = {"id": fid, "sel": sel, "label": sel, "home": "Alpha", "away": "Beta", "kickoff": "2026-10-21 18:00",
            "league": "Premier League", "country": "England", "p": p, "odds": odds, "g": "corners"}
    base.update(over)
    return base


def test_strong_markets_keeps_only_75_plus_at_116_plus_in_the_four_families():
    items = [
        _item("O15", 0.80, 1.20, fid="a"),
        _item("O15", 0.74, 1.20, fid="b"),          # below the probability bar
        _item("O15", 0.90, 1.10, fid="c"),          # below the price bar
        _item("O25", 0.90, 1.30, fid="d"),          # not a named market
        _item("BTTS", 0.90, 1.30, fid="e"),         # not a named market
        _item("H", 0.90, 1.30, fid="f"),            # not a named market
        _item("CHO35", 0.88, 1.25, fid="g"),
        _item("CO75", 0.79, 1.16, fid="h"),         # exactly on both bars: in
    ]
    out = appdata.strong_markets_payload(items)
    got = {(x["sel"], x["p"]) for x in out}
    assert ("O15", 0.80) in got and ("CHO35", 0.88) in got and ("CO75", 0.79) in got
    assert len(out) == 3
    assert [x["p"] for x in out] == sorted((x["p"] for x in out), reverse=True)


def test_strong_markets_gives_total_lines_room_and_caps_the_team_ones():
    items = [_item(f"CO75", 0.95, 1.20, fid=f"c{i}") for i in range(10)]
    items += [_item(f"CHO45", 0.94, 1.20, fid=f"t{i}") for i in range(10)]
    items += [_item("KO35", 0.93, 1.25, fid=f"k{i}") for i in range(10)]
    out = appdata.strong_markets_payload(items)
    fams = [x["family"] for x in out]
    assert fams.count("corner_total") == appdata.STRONG_CAPS["corner_total"]
    assert fams.count("corner_team") == appdata.STRONG_CAPS["corner_team"]
    assert fams.count("card_total") == appdata.STRONG_CAPS["card_total"]
    assert "corner_total" in fams, "the totals must not be crowded out by team corners"


def test_strong_markets_shows_at_most_two_markets_per_match():
    items = [_item("CO75", 0.95, 1.20, fid="same"), _item("KO35", 0.94, 1.20, fid="same"),
             _item("O15", 0.93, 1.20, fid="same"), _item("CO85", 0.92, 1.20, fid="other")]
    out = appdata.strong_markets_payload(items)
    assert sum(1 for x in out if x["id"] == "same") == appdata.STRONG_PER_MATCH
    assert any(x["id"] == "other" for x in out)


def test_strong_family_mapping_and_the_unknown_fallback():
    assert appdata.strong_family("CO75") == "corner_total"
    assert appdata.strong_family("CAO45") == "corner_team"
    assert appdata.strong_family("KO35") == "card_total"
    assert appdata.strong_family("KHO25") == "card_team"
    assert appdata.strong_family("O15") == "o15"
    assert appdata.strong_family("AO15") == "team_goal"
    assert appdata.strong_family("BTTS") == ""


# ---------------------------------------------------------------- no accumulators anywhere
def test_the_app_payload_no_longer_carries_acca_builds():
    assert not hasattr(appdata, "accas_payload")
    assert not hasattr(appdata, "acca_odds_of")
