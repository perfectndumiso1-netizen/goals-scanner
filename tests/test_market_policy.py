"""Market policy: which selections may be offered, from what probability and at what price.

2026-10-27 (docs/MODEL_REVIEW_2026-10-27.md): double chance, team goals, cards, BTTS and Over 0.5 joined the unders
on the dropped list; nothing priced below 1.16 is offered; the published probability is a 25/75 model/market blend.
Older assertions below are kept where they still describe the policy (labels, settlement, the 55 % Over-2.5 start)."""
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

import pytest

import policy
import safe
from safe import Sel

UNDERS = ["U15", "U25", "U35", "U45", "U55", "NBTTS", "HU15", "AU15", "CU85", "CU105", "CHU35", "CAU55", "KU35", "KHU25", "KAU25"]
OVERS = ["O05", "O15", "O25", "O35", "O45", "O55", "BTTS", "H", "D", "A", "CO85", "CO105", "CHO35", "CAO35", "KO35", "KHO25", "KAO25"]
TEAM_GOALS = ["HO05", "AO05", "HO15", "AO15", "HU15", "AU15"]
DOUBLE_CHANCE = ["1X", "12", "X2"]
CARDS = ["KO35", "KU95", "KHO25", "KAU25", "KCO15" if False else "KO55"]
BTTS = ["BTTS", "NBTTS"]
DROPPED_2026_10_27 = TEAM_GOALS + DOUBLE_CHANCE + CARDS + BTTS + ["O05"]


def test_every_under_in_every_market_is_recognised():
    # the old regexes missed the team-level corner / card unders (CAU55, KHU25 ...), which is how they reached bets of the day
    for code in UNDERS:
        assert policy.is_under(code), code
        assert safe.is_under(code), code
    for code in OVERS + DOUBLE_CHANCE + ["HO05", "AO15"]:
        assert not policy.is_under(code), code


def test_team_goals_are_not_confused_with_team_corners_or_cards():
    assert all(policy.is_team_goal(c) for c in TEAM_GOALS)
    assert not any(policy.is_team_goal(c) for c in ("CHO35", "CAU55", "KHO25", "KAU25", "H", "A", "O15"))


def test_policy_allows_exactly_the_focus_markets():
    # 2026-10-27: unders, double chance, cards, BTTS, Over 0.5 and team goals are all refused by default
    assert [c for c in UNDERS + DOUBLE_CHANCE + CARDS + BTTS + TEAM_GOALS + ["O05"] if policy.allowed(c)] == []
    for code in ("O15", "O25", "O35", "O45", "O55", "H", "D", "A", "CO85", "CO105", "CHO35", "CAO35"):
        assert policy.allowed(code), code


def test_every_dropped_family_is_named_by_family_of():
    assert policy.family_of("1X") == "dc" and policy.family_of("KO35") == "cards"
    assert policy.family_of("BTTS") == "btts"
    assert policy.family_of("NBTTS") in ("btts", "unders")      # still refused either way
    assert policy.family_of("HO05") == "team" and policy.family_of("O05") == "o05"
    assert policy.family_of("U25") == "unders" and policy.family_of("CO85") == "" and policy.family_of("H") == ""


def test_rollback_switch_restores_a_family(monkeypatch):
    monkeypatch.setattr(policy, "ALLOW", frozenset(("dc",)))
    assert policy.allowed("1X") and not policy.allowed("HO05") and not policy.allowed("U25")
    monkeypatch.setattr(policy, "ALLOW", frozenset(("unders", "team", "dc")))
    assert all(policy.allowed(c) for c in UNDERS + TEAM_GOALS + DOUBLE_CHANCE)
    assert not policy.allowed("BTTS") and not policy.allowed("KO35")
    monkeypatch.setattr(policy, "ALLOW", frozenset(policy.FAMILIES))
    assert all(policy.allowed(c) for c in DROPPED_2026_10_27)


def test_over25_and_btts_start_from_55_everything_else_keeps_its_floor():
    # BTTS keeps its entry in SEL_MIN_P so a historical row still labels itself, even though the family is gone
    assert policy.min_p("O25", 0.70) == 0.55 and policy.min_p("BTTS", 0.70) == 0.55
    assert policy.min_p("O15", 0.70) == 0.70 and policy.min_p("O35", 0.70) == 0.70
    assert policy.min_p("CO85", 0.65) == 0.65 and policy.min_p("H", 0.60) == 0.55


# ---------------------------------------------------------------- the single source: safe.selections()
def _full_row():
    now = datetime(2026, 10, 17, 12, 0)
    return NS(
        data_ok=True,
        fx={"date": now.date(), "kickoff": now + timedelta(hours=3), "country": "England", "div": "E0",
            "league": "Premier League", "home": "Alpha", "away": "Beta"},
        sb={"1X2": (1.90, 3.60, 4.20), "DC": {"1X": 1.25, "12": 1.30, "X2": 2.10},
            "OU": {0.5: (1.04, 9.0), 1.5: (1.28, 3.6), 2.5: (1.85, 1.95), 3.5: (3.0, 1.35)},
            "BTTS": (1.80, 1.95), "TGH": {0.5: (1.30, 3.2), 1.5: (2.1, 1.7)}, "TGA": {0.5: (1.45, 2.6)},
            "CORN": {9.5: (1.90, 1.85)}, "CARDS": {3.5: (1.80, 1.90)}},
        extra=NS(x12={"H": 0.50, "D": 0.26, "A": 0.24, "1X": 0.76, "12": 0.74, "X2": 0.50},
                 tg={"H_o05": 0.80, "H_o15": 0.45, "A_o05": 0.70, "A_o15": 0.30},
                 corner_p={"total": {9.5: 0.55}, "home": {4.5: 0.5}, "away": {3.5: 0.5}},
                 card_p={"total": {3.5: 0.58}, "home": {1.5: 0.6}, "away": {1.5: 0.5}}),
        p_final={"O05": 0.97, "O15": 0.82, "O25": 0.60, "O35": 0.33, "O45": 0.15, "O55": 0.06, "BTTS": 0.58},
        sb_full={"CORNH": {4.5: (2.0, 1.7)}, "CARDSH": {1.5: (1.6, 2.2)}},
    )


def test_selections_carry_only_the_families_that_survived_the_review():
    codes = [s.sel for s in safe.selections(_full_row())]
    assert codes, "the kept markets must still be there"
    for bad in DROPPED_2026_10_27:
        assert bad not in codes, bad
    for good in ("H", "D", "A", "O15", "O25", "O35", "CO95", "CHO45"):
        assert good in codes, good


def test_old_codes_still_label_and_settle():
    """Bets placed before the change must keep grading and displaying."""
    assert safe.label("HO05", "A", "B") == "A over 0.5 goals"
    assert safe.label("1X", "A", "B") == "A or draw"
    assert safe.label("U25") == "Under 2.5 goals"
    assert safe.settle("HO05", 1, 0) is True and safe.settle("1X", 0, 1) is False and safe.settle("U25", 1, 1) is True


# ---------------------------------------------------------------- Bets of the day, safest: the 55% start
def _bet_row(code_p: dict, odds: dict | None = None):
    r = _full_row()
    r.p_final.update(code_p)
    # a market view close enough to the model that the published blend can clear a floor (the 2026-10-27 publication
    # is capped at market + 3 pp, so with a 1.85/1.95 Over-2.5 price nothing can ever reach 55 %)
    r.sb = dict(r.sb, OU={0.5: (1.04, 9.0), 1.5: (1.28, 3.6), 2.5: (1.72, 2.10), 3.5: (3.0, 1.35)})
    return r


def _cands(row, signal=None):
    return safe.botd_candidates([row], datetime(2026, 10, 17, 12, 0), signal=signal)


def test_botd_over25_starts_from_55_and_btts_is_no_longer_offered():
    r = _bet_row({"O25": 0.58, "BTTS": 0.56})
    sels = {b.sel: b for b in _cands(r, signal=lambda row, sel: True)}
    assert "O25" in sels                                   # 58% — would have been refused at 70%
    assert "BTTS" not in sels                              # dropped 2026-10-27 (-7.0 % ROI, 15 pp optimistic unpriced)
    r = _bet_row({"O25": 0.54, "BTTS": 0.54})
    sels = {b.sel for b in _cands(r, signal=lambda row, sel: True)}
    assert "O25" not in sels and "BTTS" not in sels        # below 55% / not offered


def test_botd_over15_keeps_its_70_percent_and_never_carries_team_goals():
    # the 70 % bar now applies to the PUBLISHED probability (25/75 blend with the de-vigged market), which is what the
    # card claims: a 0.55 model view against a 0.74 market publishes at 0.69 and stays out
    sels = {b.sel for b in _cands(_bet_row({"O15": 0.55}))}
    assert "O15" not in sels
    sels = {b.sel for b in _cands(_bet_row({"O15": 0.80}))}
    assert "O15" in sels and not (sels & set(TEAM_GOALS))
    # the section list itself is unchanged (it is a display map); the dropped families simply never reach it
    assert [g[0] for g in safe.BOTD_GROUPS] == ["o15", "o25", "btts", "result", "corners", "cards"]
    assert safe.botd_group("HO05") is None


def test_botd_signal_gate_still_applies_to_over25_and_btts():
    r = _bet_row({"O25": 0.62, "BTTS": 0.60})
    sels = {b.sel for b in _cands(r, signal=lambda row, sel: False)}
    assert "O25" not in sels and "BTTS" not in sels


def test_botd_section_floors_are_what_the_card_shows():
    assert safe.botd_floor("o25") == 0.55 and safe.botd_floor("btts") == 0.55
    assert safe.botd_floor("o15") == 0.70 and safe.botd_floor("cards") == 0.65


def test_safest_uses_the_per_selection_floor():
    now = datetime(2026, 10, 17, 12, 0)
    r = _bet_row({"O15": 0.50, "O25": 0.60})       # Over 1.5 below its bar, Over 2.5 above its 55 % start
    for k in ("O05", "O35", "O45", "O55"):
        r.p_final[k] = 0.10
    out = safe.safest([r], now, now + timedelta(days=1), groups=("goals",))
    assert [b.sel for b in out["bets"]] == ["O25"]              # most probable of the eligible ones, one per match
    assert out["floors"]["O25"] == out["floors"]["H"] == 0.55 and out["min_p"] == 0.70
    r2 = _bet_row({"O25": 0.54, "O15": 0.50})
    for k in ("O05", "O35", "O45", "O55"):
        r2.p_final[k] = 0.10
    assert safe.safest([r2], now, now + timedelta(days=1), groups=("goals",))["bets"] == []


def test_corners_and_1x2_stay_on_by_default_and_can_be_switched_off(monkeypatch):
    # the user did not ask for these to go — they stay, with a one-line switch (MODEL_DROP=corners,result)
    assert policy.allowed("CO85") and policy.allowed("CHO35") and policy.allowed("H") and policy.allowed("D")
    assert policy.describe()["kept_by_default"] == ["corners (overs)", "1X2 (home / away)"]
    monkeypatch.setattr(policy, "DROP", frozenset(("corners",)))
    assert not policy.allowed("CO85") and not policy.allowed("CAO35") and policy.allowed("O15") and policy.allowed("H")
    monkeypatch.setattr(policy, "DROP", frozenset(("result",)))
    assert not policy.allowed("H") and not policy.allowed("A") and policy.allowed("CO85") and policy.allowed("O15")


# ---------------------------------------------------------------- the sticky card on the day the policy lands
def _ledger(rows):
    import pandas as pd
    cols = safe.SAFE_BET_COLS
    out = []
    for r in rows:
        base = {c: "" for c in cols}
        base.update({"match_date": "2026-10-17", "kickoff": "2026-10-17 20:00", "country": "England", "div": "E0",
                     "league": "Premier League", "p": "0.8", "p_model": "0.8", "odds": "1.30", "status": "pending", "kind": "safe"})
        base.update(r)
        out.append(base)
    return pd.DataFrame(out, columns=cols)


def test_pending_card_picks_the_policy_dropped_leave_the_sticky_card_but_history_stays():
    now = datetime(2026, 10, 17, 12, 0)
    df = _ledger([
        {"home": "A", "away": "B", "sel": "1X", "botd": "o15", "kind": "botd"},              # card-only row, pending, dropped market
        {"home": "C", "away": "D", "sel": "CAU55", "botd": "corners", "kind": "safe"},          # also a safest-record row
        {"home": "E", "away": "F", "sel": "HO05", "botd": "o15", "kind": "botd", "status": "hit", "score": "2-0"},   # settled: history
        {"home": "G", "away": "H", "sel": "O15", "botd": "o15", "kind": "botd"},                # still allowed
    ])
    out = safe.pick_bets_of_the_day(df, now, candidates=[])
    rows = {(r.home, r.sel): r for r in out.itertuples()}
    assert ("A", "1X") not in rows                                  # card-only, pending -> removed
    assert ("C", "CAU55") in rows and rows[("C", "CAU55")].botd == ""  # kept for the safest record, off the card
    assert rows[("E", "HO05")].botd == "o15" and rows[("E", "HO05")].status == "hit"   # settled stays on the record
    assert rows[("G", "O15")].botd == "o15"
    card = safe.bets_of_the_day(out, now)
    assert [b["sel"] for b in card["bets"]] == ["O15", "HO05"] or {b["sel"] for b in card["bets"]} == {"O15", "HO05"}
    assert all(b["status"] != "pending" or policy.allowed(b["sel"]) for b in card["bets"])


def test_a_match_whose_old_ledger_row_was_a_dropped_market_can_still_get_a_new_card_pick():
    now = datetime(2026, 10, 17, 12, 0)
    df = _ledger([{"home": "A", "away": "B", "sel": "1X", "botd": "", "kind": "safe"}])    # old safest row, dropped market
    cand = safe.Bet(("2026-10-17", "England", "A", "B"), "E0", "Premier League", "A", "B", "2026-10-17 20:00", "O15", 0.82, 0.82, None, 1.25)
    out = safe.pick_bets_of_the_day(df, now, candidates=[cand])
    assert any(r.sel == "O15" and r.botd == "o15" for r in out.itertuples())


# ---------------------------------------------------------------- the app repeats the policy client-side: it must not drift
def _core_js() -> str:
    from pathlib import Path
    return (Path(__file__).resolve().parents[1] / "android/app/src/main/assets/www/core.js").read_text(encoding="utf-8")


def test_the_apps_isunder_matches_the_python_policy_on_every_code():
    import re
    js = _core_js()
    pat = re.search(r"const isUnder = \(sel\) => /(.+?)/\.test\(sel \|\| ''\);", js)
    assert pat, "isUnder moved — update this test"
    rx = re.compile(pat.group(1))
    for code in UNDERS + OVERS + TEAM_GOALS + DOUBLE_CHANCE:
        assert bool(rx.search(code)) == policy.is_under(code), code


def test_the_apps_dropped_set_and_floors_match_the_python_policy():
    import re
    js = _core_js()
    dropped = re.search(r"const isDropped = \(sel\) => ([^;]+);", js)
    assert dropped, "isDropped moved — update this test"
    expr = dropped.group(1)
    # 2026-10-27: the client mirror also hides team goals, cards, BTTS and Over 0.5, not just unders and double chance
    assert "isUnder(sel)" in expr
    for dc in DOUBLE_CHANCE:
        assert f"sel === '{dc}'" in js
    for code in ("BTTS", "O05"):
        assert f"sel === '{code}'" in expr
    assert "^K[HA]?[OU]" in expr and "^[HA][OU]" in expr
    floors = re.search(r"const SEL_FLOOR = \{ O25: ([0-9.]+), BTTS: ([0-9.]+)", js)
    assert floors and float(floors.group(1)) == policy.SEL_MIN_P["O25"] and float(floors.group(2)) == policy.SEL_MIN_P["BTTS"]


def test_the_55_floor_ignores_the_scan_workflows_older_min_p_variables(monkeypatch):
    """Regression (2026-10-17): scan.yml sets MIN_P_O25 / MIN_P_BTTS = 0.60 for the older Goals-shortlist star
    thresholds. The first version of the policy read the same names, so production quietly ran at 60%, not 55%
    (local tests passed because the variables are not set locally)."""
    import importlib
    monkeypatch.setenv("MIN_P_O25", "0.60")
    monkeypatch.setenv("MIN_P_BTTS", "0.60")
    monkeypatch.setenv("MIN_P_O15", "0.84")
    try:
        importlib.reload(policy)
        assert policy.SEL_MIN_P == {"O25": 0.55, "BTTS": 0.55, "H": 0.55, "D": 0.55, "A": 0.55}
        monkeypatch.setenv("POLICY_MIN_P_O25", "0.58")
        importlib.reload(policy)
        assert policy.SEL_MIN_P["O25"] == 0.58 and policy.SEL_MIN_P["BTTS"] == 0.55
        assert policy.SEL_MIN_P["H"] == policy.SEL_MIN_P["A"] == 0.55          # the policy's own lever still works
    finally:
        monkeypatch.undo()
        importlib.reload(policy)
    assert policy.SEL_MIN_P == {"O25": 0.55, "BTTS": 0.55, "H": 0.55, "D": 0.55, "A": 0.55}


def test_no_workflow_sets_the_policy_levers_by_accident():
    from pathlib import Path
    for wf in (Path(__file__).resolve().parents[1] / ".github/workflows").glob("*.yml"):
        text = wf.read_text(encoding="utf-8")
        assert "POLICY_MIN_P" not in text and "MODEL_MARKETS" not in text and "MODEL_DROP" not in text, wf.name


# ---------------------------------------------------------------- Safest lanes: every market gets its own slots
def _match(i, o15, o25=None, btts=None):
    r = _full_row()
    # a live price view for the goals lines (the published probability is anchored to it, see policy.publish_p)
    r.sb = dict(r.sb, OU={0.5: (1.04, 9.0), 1.5: (1.18, 5.0), 2.5: (1.62, 2.25), 3.5: (3.0, 1.35)})
    r.fx = dict(r.fx, home=f"H{i}", away=f"A{i}")
    r.extra.corner_p = None
    r.extra.card_p = None
    r.sb_full = {}
    r.p_final = {"O05": 0.97, "O15": o15, "O25": o25 if o25 is not None else 0.30, "O35": 0.10, "O45": 0.05, "O55": 0.02,
                 "BTTS": btts if btts is not None else 0.30}
    return r


def _safest(rows, **kw):
    now = datetime(2026, 10, 17, 12, 0)
    return safe.safest(rows, now, now + timedelta(days=1), **kw)["bets"]


def test_safest_gives_over25_its_own_lane_and_btts_is_gone():
    rows = [_match(i, 0.88, 0.70, 0.66) for i in range(14)] + [_match(20 + i, 0.88) for i in range(8)]
    bets = _safest(rows)
    mix = {k: sum(1 for b in bets if b.sel == k) for k in ("O25", "BTTS", "O15")}
    assert mix["O25"] == 10 and mix["BTTS"] == 0 and mix["O15"] == 12, mix      # O2.5 claims 10, O1.5 takes the rest
    assert len({b.key for b in bets}) == len(bets)                                # ONE market per match, still
    assert bets == sorted(bets, key=lambda b: (-b.p, -b.odds))                    # displayed by probability, as before


def test_safest_without_lanes_is_the_old_most_probable_per_match(monkeypatch):
    monkeypatch.setattr(safe, "SAFE_LANES", False)
    rows = [_match(i, 0.88, 0.70, 0.66) for i in range(14)]
    assert {b.sel for b in _safest(rows)} == {"O15"}                              # Over 1.5 always wins on probability


def test_safest_lane_caps_hold_and_the_total_is_bounded():
    rows = [_match(i, 0.88, 0.70, 0.66) for i in range(80)]
    bets = _safest(rows)
    assert len(bets) <= safe.MAX_BETS
    assert sum(1 for b in bets if b.sel == "O25") == safe.SAFE_LANE_CAP["o25"]
    assert sum(1 for b in bets if b.sel == "BTTS") == 0                            # dropped 2026-10-27
    assert sum(1 for b in bets if b.sel == "O15") == safe.MAX_BETS - 10            # the rest of the board
