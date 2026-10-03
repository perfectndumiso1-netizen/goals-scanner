"""The publication contract for the daily acca builds.

The whole point of publishing a 3.00 acca is that it is built under a rule the punter cannot see being broken:
fewest legs to the price, one leg per match, three builds that never share a match, and every leg inside the
edge gate. The publisher must refuse anything else, so these tests break each rule on purpose.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path

import verify

NOW = datetime(2026, 10, 3, 12, 0)


def _leg(i: int, edge_pp: float = 8.0) -> dict:
    return {"fixture": f"fx{i}", "home": f"H{i}", "away": f"A{i}", "country": "Testland", "div": "TL",
            "league": "Test League", "kickoff": "2026-10-03 16:00", "sel": "O15", "label": f"Over 1.5 · H{i} v A{i}",
            "p": 0.7, "p_model": 0.7, "p_sb": 0.7 - edge_pp / 100, "edge_pp": edge_pp, "odds": 1.44,
            "fair": 1.43, "badges": {"home": None, "away": None}}


def _acca(i: int, n: int = 3, odds: float = 3.0) -> dict:
    return {"id": f"A20261003-0{i}", "odds": odds, "p": 0.34, "p_market": 0.28, "n_legs": n,
            "status": "pending", "legs": [_leg(i * 10 + k) for k in range(n)],
            "if_model_right": 0.02, "if_no_edge": -0.16}


def build(tmp: Path, accas: dict | None = None) -> tuple[Path, Path]:
    staging, live = tmp / "app" / "_staging", tmp / "app"
    for sub in (staging / "fx", tmp / "app" / "days"):
        sub.mkdir(parents=True, exist_ok=True)
    (staging / "fx" / "k1.json").write_text(json.dumps({"id": "f1", "quality": {"overall": "High"},
                                                        "xg": {"home": 1.4, "model_home": 1.4}, "sels": []}), encoding="utf-8")
    fixtures = [{"id": f"fx{i}", "d": "k1", "kickoff": "2026-10-03 16:00", "home": f"H{i}", "away": f"A{i}",
                 "p": {"O15": 0.7}, "x12": [0.4, 0.3, 0.3], "xg": [1.4, 1.0]}
                for i in range(300) if i % 10 in (0, 1, 2)]
    latest = {"version": 3, "meta": {"generated": NOW.strftime("%Y-%m-%d %H:%M")}, "fixtures": fixtures,
              "safe": {"min_p": 0.7, "bets": [], "today": {"bets": []}}, "picks": {},
              "tracker": {},
              "accas": accas if accas is not None else {"target": 3.0, "pool": 120, "edge_pp": [2.0, 12.0],
                                                        "ids": ["A20261003-01"], "bets": [_acca(1)], "recent": [],
                                                        "summary": {}}}
    (staging / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
    for name in ("meta.json", "alerts.json", "badges.json"):
        (staging / name).write_text(json.dumps({}), encoding="utf-8")
    return staging, live


def errors_for(tmp: Path, accas: dict) -> list[str]:
    staging, live = build(tmp, accas)
    errors, _ = verify.check_publication(staging, live, tmp / "no-ledger.csv", NOW, expect_fixtures=1)
    return errors


def test_a_clean_build_publishes(tmp_path):
    assert errors_for(tmp_path, None) == []


def test_two_legs_is_fine_and_three_is_the_limit(tmp_path):
    accas = {"target": 3.0, "edge_pp": [2.0, 12.0], "ids": ["A20261003-01"], "bets": [_acca(1, n=2)], "recent": [], "summary": {}}
    assert errors_for(tmp_path, accas) == []
    accas["bets"] = [_acca(1, n=4)]
    assert any("the plan is 2-3" in e for e in errors_for(tmp_path, accas))


def test_off_target_price_is_refused(tmp_path):
    accas = {"target": 3.0, "edge_pp": [2.0, 12.0], "ids": ["A20261003-01"], "bets": [_acca(1, odds=3.9)], "recent": [], "summary": {}}
    assert any("target" in e for e in errors_for(tmp_path, accas)), "a 3.90 build is not a 3.00 build"


def test_a_fantasy_leg_is_refused(tmp_path):
    accas = {"target": 3.0, "edge_pp": [2.0, 12.0], "ids": ["A20261003-01"], "bets": [_acca(1)], "recent": [], "summary": {}}
    accas["bets"][0]["legs"][1]["edge_pp"] = 29.0          # the India v Brazil shape
    assert any("outside the" in e for e in errors_for(tmp_path, accas))
    accas["bets"][0]["legs"][1]["edge_pp"] = 0.4           # below the gate: paying the vig
    assert any("outside the" in e for e in errors_for(tmp_path, accas))


def test_two_markets_from_one_match_in_one_build_is_refused(tmp_path):
    accas = {"target": 3.0, "edge_pp": [2.0, 12.0], "ids": ["A20261003-01"], "bets": [_acca(1)], "recent": [], "summary": {}}
    accas["bets"][0]["legs"][1]["home"] = accas["bets"][0]["legs"][0]["home"]
    accas["bets"][0]["legs"][1]["away"] = accas["bets"][0]["legs"][0]["away"]
    assert any("two markets from one match" in e for e in errors_for(tmp_path, accas))


def test_builds_sharing_a_match_are_refused(tmp_path):
    first = _acca(1)
    second = copy.deepcopy(_acca(2))
    second["legs"][0] = copy.deepcopy(first["legs"][0])          # one shock would take both builds
    second["legs"][1] = _leg(99)
    second["legs"][2] = _leg(98)
    accas = {"target": 3.0, "edge_pp": [2.0, 12.0], "ids": ["A20261003-01", "A20261003-02"],
             "bets": [first, second], "recent": [], "summary": {}}
    assert any("shares a match" in e for e in errors_for(tmp_path, accas))


def test_a_build_without_its_ledger_id_is_refused(tmp_path):
    accas = {"target": 3.0, "edge_pp": [2.0, 12.0], "ids": [], "bets": [_acca(1)], "recent": [], "summary": {}}
    assert any("ledger ids" in e for e in errors_for(tmp_path, accas))


def test_a_build_with_a_leg_on_an_unknown_fixture_is_refused(tmp_path):
    accas = {"target": 3.0, "edge_pp": [2.0, 12.0], "ids": ["A20261003-01"], "bets": [_acca(1)], "recent": [], "summary": {}}
    accas["bets"][0]["legs"][2]["fixture"] = "not-a-real-fixture"
    assert any("unknown fixture" in e for e in errors_for(tmp_path, accas))


def test_a_build_missing_its_market_probability_is_refused(tmp_path):
    accas = {"target": 3.0, "edge_pp": [2.0, 12.0], "ids": ["A20261003-01"], "bets": [_acca(1)], "recent": [], "summary": {}}
    del accas["bets"][0]["p_market"]
    assert any("market probability" in e for e in errors_for(tmp_path, accas))
