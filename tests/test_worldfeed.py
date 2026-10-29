"""Tests for worldfeed archive stage discovery (full-worldwide coverage). Run: python3 -m pytest tests -q"""
from __future__ import annotations

import json
from pathlib import Path

import worldfeed


def test_known_stages_round_trip(tmp_path):
    stages = tmp_path / "stages"
    stages.mkdir()
    for key in ("england/premier-league", "south-africa/premier-soccer-league",
                "africa-cup-of-nations-qualification/qualification-group-a", "brazil/serie-a-2026"):
        (stages / (key.replace("/", "__") + ".json")).write_text(json.dumps({"key": key}))
    keys = worldfeed.known_stages(stages)
    assert keys == {"england/premier-league", "south-africa/premier-soccer-league",
                    "africa-cup-of-nations-qualification/qualification-group-a", "brazil/serie-a-2026"}
    assert worldfeed.known_stages(tmp_path / "missing") == set()


def test_stage_key_and_div_code():
    assert worldfeed.stage_key("england", "premier-league") == "england/premier-league"
    assert worldfeed.div_code("england", "premier-league") == "LS:england/premier-league"


def test_calendar_backfill_fetches_prior_years_and_ignores_obsolete_attempt_labels(monkeypatch,tmp_path):
    from datetime import datetime
    archive=worldfeed.Archive(tmp_path)
    data=archive.load('sweden/allsvenskan')
    # State left by the old off-by-one calendar-year loop: it never tried 2024.
    data['backfill']={'2025-2026':-1,'2026':-1,'2024-2025':-1,'2025':240}
    calls=[]
    def fetch(ccd,scd,*a,**kw):
        calls.append(scd)
        return None,[]
    monkeypatch.setattr(worldfeed,'fetch_stage',fetch)
    archive.backfill({'sweden/allsvenskan':100},datetime(2026,10,29),seasons=2)
    assert calls==['allsvenskan-2024']
    assert 'allsvenskan-2026' not in calls


def test_calendar_backfill_uses_calendar_anchor_even_in_january(monkeypatch,tmp_path):
    from datetime import datetime
    archive=worldfeed.Archive(tmp_path)
    calls=[]
    monkeypatch.setattr(worldfeed,'fetch_stage',lambda c,s,*a,**kw:(calls.append(s) or (None,[])))
    archive.backfill({'sweden/allsvenskan':100},datetime(2026,1,29),seasons=2)
    assert 'allsvenskan-2025' in calls and 'allsvenskan-2024' in calls
    assert 'allsvenskan-2026' not in calls
