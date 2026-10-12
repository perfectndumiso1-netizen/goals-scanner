# safer-doubles family (2026-10-11): 2 legs at ~2.00, same gates, own record, own contract
import json
from datetime import datetime
from pathlib import Path

import verify
import appdata
from accas import Bet


NOW = datetime(2026, 10, 3, 12, 0)


def _bet(i: int) -> Bet:
    return Bet(key=("2026-10-03", "Testland", f"H{i}", f"A{i}"), div="TL", league="Test League",
               home=f"H{i}", away=f"A{i}", kickoff="2026-10-03 16:00", sel="O15",
               p=0.72, p_model=0.72, p_sb=0.65, odds=1.45)


def _ctx(doubles_plans, cal=None):
    return {"accas": {"target": 3.0, "pool": 10, "plans": [], "ids": [],
                      "summary": {}, "recent": [], "legs_min": 2, "legs_max": 3,
                      "edge_range": (0.02, 0.12), "vig": 0.06,
                      "doubles_plans": doubles_plans, "doubles_ids": ["D1"], "doubles_target": 2.00,
                      "doubles_summary": {"all": {"n": 12, "won": 5, "rate": 0.417, "exp_rate": 0.40, "roi": -0.05}},
                      "doubles_recent": [], "cal": cal}}


def test_doubles_published_in_own_family():
    out = appdata.accas_payload(_ctx([[_bet(1), _bet(2)]]), {}, set(), {}, lambda *k: "fx1")
    d = out.get("doubles") or {}
    assert d.get("target") == 2.0 and len(d.get("bets") or []) == 1
    b = d["bets"][0]
    assert b["n_legs"] == 2 and abs(b["odds"] - 2.1) < 0.03 and b["id"] == "D1"
    assert len({(l["country"], l["home"], l["away"]) for l in b["legs"]}) == 2
    assert d["summary"]["all"]["n"] == 12


def test_doubles_composite_calibration():
    cal = {"live": True, "groups": {"goals": {"status": "live", "curve": [[0.3, 0.3], [1.0, 0.9]]}}}
    out = appdata.accas_payload(_ctx([[_bet(1), _bet(2)]], cal=cal), {}, set(), {}, lambda *k: "fx1")
    b = out["doubles"]["bets"][0]
    assert b["p_cal"] is not None and b["p_cal"] < b["p"]       # pulled toward reality


def test_verify_accepts_clean_doubles(tmp_path):
    latest = {"version": 3, "meta": {"generated": NOW.strftime("%Y-%m-%d %H:%M")}, "fixtures": [],
              "safe": {"min_p": 0.7, "bets": [], "today": {"bets": []}}, "picks": {},
              "accas": {"target": 3.0, "bets": [], "doubles": {"target": 2.0, "bets": [{
                  "id": "D1", "odds": 2.02, "p": 0.5, "p_market": 0.48, "n_legs": 2,
                  "legs": [{"fixture": "f1", "country": "C", "home": "A", "away": "B", "label": "x", "edge_pp": 7},
                           {"fixture": "f2", "country": "D", "home": "E", "away": "F", "label": "y", "edge_pp": 5}]}]}}}
    st = tmp_path / "app"
    st.mkdir()
    (st / "fx").mkdir()
    (tmp_path / "days").mkdir()    # _archive_ids reads staging.parent / "days"
    (tmp_path / "days" / "2026-10-20.json").write_text(json.dumps(
        {"date": "2026-10-20", "fixtures": [{"id": "f1"}, {"id": "f2"}]}), encoding="utf-8")
    for name in ("meta.json", "alerts.json", "badges.json"):
        (st / name).write_text("{}", encoding="utf-8")
    (st / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
    errors, _ = verify.check_publication(st, st, tmp_path / "nl.csv", NOW, expect_fixtures=1)
    assert not [e for e in errors if "doubles" in e.lower()], errors


def test_verify_rejects_broken_doubles(tmp_path):
    latest = {"version": 3, "meta": {"generated": NOW.strftime("%Y-%m-%d %H:%M")}, "fixtures": [],
              "safe": {"min_p": 0.7, "bets": [], "today": {"bets": []}}, "picks": {},
              "accas": {"target": 3.0, "bets": [], "doubles": {"target": 2.0, "bets": [{
                  "id": "D1", "odds": 3.4, "p": 0.5, "p_market": 0.48, "n_legs": 3,
                  "legs": [{"fixture": "f1", "country": "C", "home": "A", "away": "B", "label": "x", "edge_pp": 7},
                           {"fixture": "f1", "country": "C", "home": "A", "away": "B", "label": "z", "edge_pp": 7},
                           {"fixture": "f2", "country": "D", "home": "E", "away": "F", "label": "y", "edge_pp": 5}]}]}}}
    st = tmp_path / "app"
    st.mkdir()
    (st / "fx").mkdir()
    (st / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
    errors, _ = verify.check_publication(st, st, tmp_path / "nl.csv", NOW, expect_fixtures=1)
    joined = " | ".join(errors).lower()
    assert "3 legs" in joined and "priced 3.4" in joined and "two markets from one match" in joined
