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
