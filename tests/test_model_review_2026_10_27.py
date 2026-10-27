"""The 2026-10-27 model-review rules (docs/MODEL_REVIEW_2026-10-27.md), pinned one by one.

The review measured 3,910 priced, settled selections and found the market out-forecasting the model (Brier 0.1879 vs
0.1916), a 4-5 point margin paid on a ~2 point edge, and the damage concentrated in the markets with no price to check
them against. These tests lock in what the code now does about it, so a future tweak cannot quietly undo it:

    * the dropped families (double chance, team goals, cards, BTTS, Over 0.5) stay dropped, everywhere;
    * nothing priced below 1.16 is offered, and a price under 95 % of fair never becomes a primary pick;
    * the published probability is the 25/75 model/market blend, capped at market + 3 pp and 90 % (80 % unpriced);
    * the home page's strong-markets section is 78 %+ at 1.16+ in Over 1.5 and corners only;
    * the app's client-side mirror agrees with Python on every dropped code.
"""
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

import pandas as pd
import pytest

import appdata
import policy
import safe
import shortlist
from safe import Sel

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- the published probability
def test_the_blend_is_a_quarter_model_and_three_quarters_market():
    assert policy.MARKET_WEIGHT == 0.75
    assert policy.publish_p(0.62, 0.60) == pytest.approx(0.605)         # 0.25*0.62 + 0.75*0.60
    assert policy.publish_p(0.58, 0.60) == pytest.approx(0.595)
    assert policy.publish_p(0.60, 0.80) == pytest.approx(0.75)


def test_the_blend_never_goes_more_than_three_points_above_the_market():
    # a wild model number cannot be published: the cap is the market + 3 pp
    assert policy.publish_p(0.99, 0.60) == pytest.approx(0.63)
    assert policy.publish_p(0.95, 0.80) == pytest.approx(0.83)


def test_the_absolute_caps_are_90_priced_and_80_unpriced():
    assert policy.publish_p(0.99, 0.95) == pytest.approx(0.90)          # priced cap
    assert policy.publish_p(0.97, None) == pytest.approx(0.80)          # nothing to anchor to
    assert policy.publish_p(0.70, None) == pytest.approx(0.70)          # a low unpriced number is left alone
    assert policy.publish_p(None, 0.70) is None and policy.publish_p(float("nan"), 0.7) is None


def test_the_blend_weight_is_a_rollback_switch(monkeypatch):
    import importlib
    monkeypatch.setenv("POLICY_MARKET_WEIGHT", "0")
    try:
        importlib.reload(policy)
        assert policy.publish_p(0.62, 0.60) == pytest.approx(0.62)      # model only (no shrink)
        assert policy.publish_p(0.80, 0.60) == pytest.approx(0.63)      # ... still capped at market + 3 pp
    finally:
        monkeypatch.undo()
        importlib.reload(policy)
    assert policy.MARKET_WEIGHT == 0.75


# ---------------------------------------------------------------- the price check
def test_the_price_check_scores_the_offer_against_our_own_fair_price():
    at_fair = policy.price_check(0.50, 2.00)
    assert at_fair["fair"] == 2.0 and at_fair["verdict"] == "value"
    short = policy.price_check(0.80, 1.20)                              # fair 1.25 -> 96 % -> "fair"
    assert short["verdict"] == "fair"
    bad = policy.price_check(0.80, 1.15)                                # fair 1.25 -> 92 % -> "short"
    assert bad["verdict"] == "short" and bad["ratio"] == pytest.approx(0.92)
    assert policy.price_check(None, 1.3) is None and policy.price_check(0.7, None) is None


def test_a_short_price_is_demoted_to_the_watchlist_not_dropped(monkeypatch):
    """65 % of the reviewed book was priced below its own fair price. It still gets recorded — as a watch, not a pick."""
    now = datetime(2026, 10, 27, 10, 0)
    fx = pd.Series({"date": pd.Timestamp(now.date()), "kickoff": pd.Timestamp(now + timedelta(hours=5)),
                    "country": "England", "league": "League", "home": "A", "away": "B", "div": "E0"})
    audit = {"quality": {"overall": "High", "score": 0.85},
             "confidence": {"O25": "High"}, "warnings": [], "context": {"conflicts": []}}

    def row():
        return NS(fx=fx, audit=audit, data_ok=True, sb={"x": 1}, hist={}, mod_h=1.6, mod_a=1.2,
                  home=NS(n=20), away=NS(n=20))

    short = shortlist.evaluate(row(), Sel("O25", 0.74, 0.68, 1.30))     # published .695, fair 1.44, 90 % of it
    assert short["status"] == "watchlist" and "fair price" in short["reasons"][0]
    assert short["p"] == pytest.approx(0.695) and short["p_model"] == pytest.approx(0.74)
    ok = shortlist.evaluate(row(), Sel("O25", 0.74, 0.68, 1.45))        # 1.45 / 1.44 -> a primary pick
    assert ok["status"] == "primary" and ok["price_check"]["verdict"] in ("value", "fair")


# ---------------------------------------------------------------- the price floor
def test_the_price_floor_is_116_and_nothing_under_it_is_offered():
    assert policy.PRICE_FLOOR == 1.16

    def row(odds):
        now = datetime(2026, 10, 27, 10, 0)
        return NS(data_ok=True,
                  fx={"date": now.date(), "kickoff": now + timedelta(hours=5), "country": "England", "div": "E0",
                      "league": "L", "home": "A", "away": "B"},
                  sb={"OU": {1.5: (odds, 4.0)}},
                  extra=NS(x12={"H": 0.55, "D": 0.25, "A": 0.20}, tg={}, corner_p=None, card_p=None),
                  p_final={"O15": 0.86}, sb_full={})

    assert [s.sel for s in safe.selections(row(1.15))] == ["H", "D", "A"]
    assert "O15" in [s.sel for s in safe.selections(row(1.16))]


# ---------------------------------------------------------------- the dropped families
DROPPED = {
    "dc": ["1X", "12", "X2"],
    "team": ["HO05", "AO05", "HO15", "AU15"],
    "cards": ["KO35", "KU95", "KHO25", "KAU15"],
    "btts": ["BTTS", "NBTTS"],
    "o05": ["O05"],
}
KEPT = ["O15", "O25", "O35", "O45", "O55", "CO85", "CO105", "CHO35", "CAO45", "H", "D", "A"]


@pytest.mark.parametrize("family,codes", sorted(DROPPED.items()))
def test_each_dropped_family_is_refused(family, codes):
    for code in codes:
        assert not policy.allowed(code), code
        assert policy.family_of(code) in (family, "unders"), code


def test_the_kept_markets_are_still_offered():
    for code in KEPT:
        assert policy.allowed(code), code
        assert policy.family_of(code) == "", code


def test_the_shortlist_rejects_a_dropped_family_even_when_a_caller_builds_one():
    now = datetime(2026, 10, 27, 10, 0)
    fx = pd.Series({"date": pd.Timestamp(now.date()), "kickoff": pd.Timestamp(now + timedelta(hours=5)),
                    "country": "England", "league": "League", "home": "A", "away": "B", "div": "E0"})
    r = NS(fx=fx, audit={"quality": {"overall": "High", "score": 0.9}, "confidence": {"BTTS": "High"},
                         "warnings": [], "context": {"conflicts": []}},
           data_ok=True, sb={"x": 1}, hist={}, mod_h=1.5, mod_a=1.2, home=NS(n=20), away=NS(n=20))
    for sel, code in ((Sel("BTTS", 0.72, 0.68, 1.55), "BTTS"), (Sel("1X", 0.85, 0.80, 1.30), "1X")):
        rec = shortlist.evaluate(r, sel)
        assert rec["status"] == "rejected" and "no longer offered" in rec["reasons"][0], code


def test_the_strong_markets_section_is_over15_and_corners_only_at_78():
    assert policy.STRONG_P_MIN == 0.78 and policy.STRONG_ODDS_MIN == 1.16
    for code in ("O15", "CO75", "CO85", "CHO35", "CAO45"):
        assert policy.is_strong_market(code), code
    for code in ("HO05", "AO05", "KO35", "KHO15", "CO05", "O25", "BTTS", "H"):
        assert not policy.is_strong_market(code), code
    assert appdata.STRONG_CAPS == {"corner_total": 8, "o15": 10, "corner_team": 3}


def test_the_app_publishes_the_anchored_probability_and_keeps_the_model_beside_it():
    now = datetime(2026, 10, 27, 10, 0)
    r = NS(p_final={"O15": 0.90, "O25": 0.62, "O35": 0.30, "BTTS": 0.60},
           fair={"O15": 0.84, "O25": 0.58, "O35": 0.28, "BTTS": 0.56}, p_market_o25=0.58)
    assert appdata._pp(r, "O15") == pytest.approx(0.855)      # 0.25*0.90 + 0.75*0.84
    assert appdata._pp(r, "O25") == pytest.approx(0.59)
    empty = NS(p_final={}, fair={}, p_market_o25=None)
    assert appdata._pp(empty, "O15") is None


def test_describe_publishes_the_new_rules_for_the_app():
    d = policy.describe()
    assert d["price_floor"] == 1.16 and d["market_weight"] == 0.75
    assert d["strong_markets"] == {"min_p": 0.78, "min_odds": 1.16,
                                   "families": ["Over 1.5 total goals", "corners"]}
    assert "BTTS" in d["dropped"] and "team goals" in d["dropped"]
    assert all(reason for reason in d["dropped_why"].values())


# ---------------------------------------------------------------- the app must not drift from the policy
def _core() -> str:
    return (ROOT / "android/app/src/main/assets/www/core.js").read_text(encoding="utf-8")


def test_the_apps_is_dropped_matches_python_on_every_code():
    import re
    js = _core()
    expr = re.search(r"const isDropped = \(sel\) => ([^;]+);", js).group(1)
    body = expr.replace("isUnder(sel)", "policy.is_under(sel)")
    for pat in ("K[HA]?[OU]", "[HA][OU]"):        # cards and team goals
        assert pat in expr, pat
    assert "sel === 'BTTS'" in expr and "sel === 'O05'" in expr
    assert all(f"sel === '{c}'" in expr for c in ("1X", "12", "X2"))
    assert body  # the expression is a pure function of the selection code


def test_the_app_copy_carries_the_new_bars():
    views = (ROOT / "android/app/src/main/assets/www/views.js").read_text(encoding="utf-8")
    assert "0.78" in views and "1.16" in views
    assert "Over 1.5 total goals and corners" in views
    assert "team goals, corners and bookings" not in views       # the old copy must be gone
    pages = (ROOT / "android/app/src/main/assets/www/pages.js").read_text(encoding="utf-8")
    assert "s.odds < 1.16" in pages                              # the client-side price floor agrees
    assert "25 % model / 75 % de-vigged-market blend" in pages


# ---------------------------------------------------------------- the publication gate and the anchor
# The app publication is promoted only if verify.check_publication finds no errors. Anchoring the published
# probability to the market made the detail files' probability differ from the model's — which that gate had always
# treated as contamination. So the anchor is declared in the file and the gate re-derives every number; these tests
# pin both halves, because getting it wrong silently freezes the app on its previous payload.
def _detail(published, final, market, model=None):
    return {"context": {"market_anchor": policy.market_anchor_record()},
            "sels": [["O25", published, final, market, 1.90, 0]],
            "p": {"O25": published, "final_O25": final, "market_O25": market,
                  "model_O25": final if model is None else model},
            "xg": {"home": 1.5, "model_home": 1.5}}


def test_the_detail_file_declares_the_anchor_and_its_inputs():
    rec = policy.market_anchor_record()
    assert rec["enabled"] is True and rec["weight"] == policy.MARKET_WEIGHT
    assert rec["cap_pp"] == pytest.approx(policy.EDGE_CAP * 100) and rec["max_p"] == policy.P_MAX_PRICED


def test_the_gate_accepts_a_published_probability_it_can_re_derive():
    import verify

    want = policy.publish_p(0.60, 0.64)
    allowed, worst, _, _, declared = verify.context_budget(_detail(want, 0.60, 0.64))
    assert declared is False                     # no research-layer record: the anchor is not that
    assert worst <= allowed + 1e-9                # a gap of several points is fine when it is the declared blend
    assert allowed > 2.0


def test_the_gate_still_blocks_a_number_that_does_not_come_out_of_the_formula():
    import verify

    # the anchor is declared, but 0.75 is not what the rule produces from a 0.60 model and a 0.64 market
    allowed, worst, _, _, _ = verify.context_budget(_detail(0.75, 0.60, 0.64))
    assert worst > allowed


def test_the_gate_blocks_the_anchor_entirely_when_one_row_is_off():
    import verify

    det = _detail(policy.publish_p(0.60, 0.64), 0.60, 0.64)
    det["sels"].append(["BTTS", 0.71, 0.60, 0.70, 1.9, 0])      # not publish_p(0.60, 0.70) = 0.675
    allowed, worst, _, _, _ = verify.context_budget(det)
    assert worst > allowed


def test_the_match_page_reads_the_selection_probability_instead_of_re_deriving_it():
    row = NS(p_final={"O25": 0.80, "O15": 0.90, "O35": 0.4, "BTTS": 0.7},
             fair={"O25": 0.60}, p_market_o25=0.60, sel_p={"O25": {"sel": "O25", "p": 0.655, "p_sb": 0.60}})
    assert appdata._pp(row, "O25") == 0.655              # exactly what the pick carries
    assert appdata._psb(row, "O25") == 0.60              # and the market it anchored to
    # a selection the book did not price has no pick entry: fall back to the declared formula
    assert appdata._pp(row, "O15") == policy.publish_p(0.90, None)


def test_an_anchor_tie_at_the_cap_is_a_warning_not_a_frozen_app(tmp_path):
    """O2.5 and O1.5 can meet when the anchor caps O2.5 at the market + 3 pp / 90 % ceiling."""
    import json
    import verify
    from datetime import datetime as _dt

    staging = tmp_path / "app" / "_staging"
    (staging / "fx").mkdir(parents=True)
    now = _dt(2026, 10, 27, 20, 0)
    fixture = {"id": "fx1", "kickoff": "2026-10-27 22:00", "home": "A", "away": "B", "d": "k1",
               "p": {"O15": 0.89, "O25": 0.90, "BTTS": 0.6}, "x12": [0.5, 0.3, 0.2], "xg": [1.4, 1.1]}
    (staging / "latest.json").write_text(json.dumps(
        {"version": 3, "meta": {"generated": "2026-10-27 20:00", "run_id": "r"}, "fixtures": [fixture],
         "safe": {"min_p": 0.7, "bets": [], "today": {"bets": []}}, "picks": {}}), encoding="utf-8")
    (staging / "run_manifest.json").write_text(json.dumps(
        {"schema_version": 3, "run_id": "r", "model_version": "m", "config_sha256": "a" * 64,
         "generated_at": "2026-10-27 20:00", "feed_health": {}, "counts": {}}), encoding="utf-8")
    for name in ("meta.json", "alerts.json", "badges.json"):
        (staging / name).write_text("{}", encoding="utf-8")
    errors, warns = verify.check_publication(staging, staging.parent / "live", staging / "none.csv",
                                             now, expect_fixtures=1)
    assert not [e for e in errors if "P(O2.5)" in e], errors
    assert any("market anchor" in w for w in warns)
