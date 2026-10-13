"""Reel timing: one voice clip per slide, no music, Overs only."""
from __future__ import annotations

import shortlist_reel as reel


def test_overs_only_drops_unders_and_caps():
    picks = [
        {"label": "Over 1.5 goals", "home": "A"},
        {"label": "Under 2.5 cards", "home": "B"},
        {"label": "Home or draw", "home": "C", "sel": "1X"},
        {"label": "Away under 1.5", "home": "D"},
    ] + [{"label": "Over 1.5 goals", "home": f"X{i}"} for i in range(10)]
    out = reel.overs_only(picks)
    assert all("under" not in (p.get("label") or "").lower() for p in out)
    assert len(out) == reel.MAX_PICKS
    assert out[0]["home"] == "A"
    assert out[1]["home"] == "C"


def test_hold_never_cuts_speech_and_intro_is_five_seconds():
    # intro: 3s of speech still holds 5s (logo sting)
    assert reel.hold_seconds(0, 3.0) == 5.0
    # intro longer than 5s: wait for the line to finish
    assert reel.hold_seconds(0, 6.2) == 6.2 + reel.TAIL
    # pick: duration is exactly that clip + tail — next match cannot appear mid-sentence
    assert reel.hold_seconds(1, 9.81) == 9.81 + reel.TAIL
    assert reel.hold_seconds(7, 12.4) == 12.4 + reel.TAIL


def test_pick_script_is_spoken_not_dumped():
    s = reel.pick_script({
        "home": "Cardiff", "away": "Watford", "label": "Cardiff or draw",
        "odds": 1.2, "p": 0.91, "kickoff": "2026-10-13 20:45",
    })
    assert "Cardiff versus Watford" in s
    assert "1.20" in s
    assert "91 percent" in s
    assert "Kick-off" in s
