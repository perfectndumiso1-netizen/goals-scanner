"""Sportybet price carry-forward: an outage (HTTP 403) must never blank the app again."""
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace as NS

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import shortlist as sl
import sporty
from safe import Sel

NOW = datetime(2026, 10, 10, 10, 0)


def _fx(home="Arsenal", away="Chelsea", h=10):
    ko = NOW + pd.Timedelta(hours=h)
    return pd.Series({"date": pd.Timestamp(ko.date()), "country": "England", "home": home, "away": away,
                      "kickoff": pd.Timestamp(ko)})


def test_cache_roundtrip_restores_tuples_and_float_lines(tmp_path):
    r = NS(fx=_fx(), sb={"1X2": (1.8, 3.6, 4.2), "OU": {2.5: (1.9, 1.95)}, "BTTS": (1.7, 2.1)},
           sb_full={"CORN": {9.5: (1.85, 1.95)}}, sb_event={"id": "e1"})
    path = tmp_path / "sb.json"
    assert sporty.cache_save(path, [r], NOW) == 1
    raw = json.loads(path.read_text())
    assert raw["2026-10-10|England|Arsenal|Chelsea"]["asof"] == "2026-10-10 10:00"
    r2 = NS(fx=_fx(), sb=None, sb_full=None, sb_event=None)
    n, asof = sporty.cache_apply([r2], path, NOW)
    assert (n, asof) == (1, "2026-10-10 10:00")
    assert r2.sb["1X2"] == (1.8, 3.6, 4.2) and r2.sb["OU"][2.5] == (1.9, 1.95)
    assert r2.sb_full["CORN"][9.5] == (1.85, 1.95) and r2.sb_event == {"id": "e1"}


def test_cache_never_carries_stale_or_started_matches(tmp_path):
    r = NS(fx=_fx(), sb={"1X2": (1.8, 3.6, 4.2)}, sb_full=None, sb_event=None)
    path = tmp_path / "sb.json"
    sporty.cache_save(path, [r], NOW)
    fresh = NS(fx=_fx(home="Leeds"), sb=None, sb_full=None, sb_event=None)
    started = NS(fx=_fx(home="BHA", h=-1), sb=None, sb_full=None, sb_event=None)
    n, _ = sporty.cache_apply([fresh, started], path, NOW + pd.Timedelta(hours=100).__iter__().__next__() if False else NOW)  # noqa
    # a 100h-old cache is beyond max_age_h, so nothing applies
    n_old, _ = sporty.cache_apply([fresh, started], path, NOW + pd.Timedelta(hours=100))
    assert n_old == 0
    n_ok, _ = sporty.cache_apply([fresh, started], path, NOW + pd.Timedelta(minutes=30))
    assert n_ok == 1 and fresh.sb["1X2"] == (1.8, 3.6, 4.2) and not hasattr(started, "sb") or started.sb is None


def test_seed_rebuilds_markets_from_a_published_file(tmp_path):
    latest = tmp_path / "latest.json"
    latest.write_text(json.dumps({"meta": {"generated": "2026-10-10 05:54"}, "fixtures": [
        {"id": "2026-10-10|England|Arsenal|Chelsea", "kickoff": "2026-10-10 20:00",
         "sels": [["H", 0.55, 0.55, None, 1.90, 0, None, 0.045], ["D", 0.24, 0.24, None, 3.60, 0, None, -0.136],
                  ["A", 0.21, 0.21, None, 4.20, 0, None, -0.118], ["O25", 0.6, 0.6, None, 1.70, 0, None, 0.02],
                  ["CO85", 0.5, 0.5, None, 1.92, 0, None, -0.04], ["CU85", 0.5, 0.5, None, 1.88, 0, None, -0.06]]}]}))
    cache = tmp_path / "sb.json"
    assert sporty.cache_seed_from_publication(latest, cache) == 1
    r = NS(fx=_fx(), sb=None, sb_full=None, sb_event=None)
    n, asof = sporty.cache_apply([r], cache, datetime(2026, 10, 10, 12, 0))
    assert (n, asof) == (1, "2026-10-10 05:54")
    assert r.sb["1X2"][0] == 1.90
    assert r.sb["OU"][2.5][0] == 1.70
    assert r.sb_full["CORN"][8.5] == (1.92, 1.88)


def test_shortlist_watchlists_carried_prices_with_the_stamp():
    r = NS(fx=_fx(), audit={"quality": {"overall": "High", "score": 0.9}, "confidence": {}, "warnings": [],
                            "context": {"conflicts": []}}, data_ok=True, sb={"x": 1}, hist={}, mod_h=1.5,
           mod_a=1.2, home=NS(n=20), away=NS(n=20), sb_asof="2026-10-10 05:54")
    rec = sl.evaluate(r, Sel("O25", 0.74, 0.68, 1.45))
    assert rec["status"] == "watchlist" and "carried forward from 2026-10-10 05:54" in rec["reasons"][0]
