# predicted line-ups (user rule 2026-10-12): our own projection from archived confirmed XIs.
# Never invented: the archive stores ONLY line-ups the research layer actually collected (eid-deduped),
# and the projection is a plain deterministic computation over that history.
from datetime import datetime, timezone
from pathlib import Path

from research import lineups as L


def _arch(tmp_path):
    return L.XiArchive(Path(tmp_path) / "xi_archive.json")


NOW = datetime(2026, 10, 12, 18, 0, tzinfo=timezone.utc)


def _fx(home="Malmo", away="Coventry", country="Sweden"):
    return {"home": home, "away": away, "country": country,
            "kickoff": datetime(2026, 10, 12, 19, 0, tzinfo=timezone.utc)}


def _got(shapers=("4-3-3", "4-3-3"), names_h=None):
    h = [("K%" + str(i) if False else f"H{i}", 1 if i == 0 else (2 if i <= 4 else (3 if i <= 7 else 4))) for i in range(11)]
    a = [("A0", 1)] + [(f"A{i}", 2 if i <= 4 else (3 if i <= 7 else 4)) for i in range(1, 11)]
    def side(nm, names, fo):
        return {"side": nm, "formation": fo, "players": [{"name": n, "position": pg, "starter": True, "sub": False} for n, pg in names]
                + [{"name": n + "S", "position": 3, "starter": False, "sub": True} for n in ("x", "y", "z", "w", "v")]}
    return {"home": side("home", h, shapers[0]), "away": side("away", a, shapers[1])}


def test_harvest_is_once_per_fixture(tmp_path):
    a = _arch(tmp_path)
    for _ in range(3):                      # scanner re-runs hit the same eid repeatedly
        a.harvest("e1", _fx(), _got(), NOW)
    assert len(a.data["teams"]["Sweden|Malmo"]) == 1
    assert len(a.data["teams"]["Sweden|Coventry"]) == 1
    assert list(a.data["eids"]) == ["e1"]
    assert (tmp_path / "xi_archive.json").exists()   # persisted for the next run


def test_slot_counts_handles_four_two_three_one_and_fallback():
    assert L._slot_counts("4-3-3", {2: 4, 3: 4, 4: 2}) == {2: 4, 3: 3, 4: 3}
    assert L._slot_counts("4-2-3-1", {}) == {2: 4, 3: 5, 4: 1}     # mid = n2 + n3
    assert L._slot_counts("", {2: 4, 3: 4, 4: 2}) == {2: 4, 3: 4, 4: 2}  # no formation -> last XI shape
    assert L._slot_counts("nonsense", {2: 3}) == {2: 3}


def test_predict_honestly_collecting_below_three(tmp_path):
    a = _arch(tmp_path)
    a.harvest("e1", _fx(), _got(), NOW)
    r = a.predict_team("Sweden", "Malmo")
    assert r["status"] == "collecting" and r["have"] == 1 and r["need"] == 3


def test_predict_ok_is_deterministic_and_shape_correct(tmp_path):
    a = _arch(tmp_path)
    g1, g2 = _got(("4-3-3", "4-3-3")), _got(("4-2-3-1", "4-2-3-1"))
    a.harvest("e1", _fx(), g1, NOW)
    a.harvest("e2", _fx(), g2, NOW)
    a.harvest("e3", _fx(), _got(("4-3-3", "4-3-3")), NOW)
    r1, r2 = a.predict_team("Sweden", "Malmo"), a.predict_team("Sweden", "Malmo")
    assert r1 == r2 and r1["status"] == "ok"
    assert len(r1["xi"]) == 11 and len(set(r1["xi"])) == 11
    assert r1["formation"] == "4-3-3"        # 2 of 3 archived XIs; weighted vote beats the single 4-2-3-1
    proj = a.projection("Sweden", "Malmo", "Coventry")
    assert proj and proj["home"]["xi"] and proj["away"]["xi"]
    assert "never official" in proj["note"]
    assert a.projection("Nowhere", "Ghost", "Phantom") is None


def test_facts_for_harvests_into_archive(tmp_path):
    arch = L.XiArchive(tmp_path / "xi.json")
    fx = _fx()
    fx["eid"] = "e9"
    class FakeClient:
        def fetch(self, eid, now):
            return _got()
    facts = L.facts_for(fx, NOW, FakeClient(), lead_min=120, eid="e9", match_started=False, archive=arch)
    assert isinstance(facts, list)
    assert len(arch.data["teams"].get("Sweden|Malmo", [])) == 1
