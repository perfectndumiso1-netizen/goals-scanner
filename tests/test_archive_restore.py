"""When live feeds go empty, restore upcoming fixtures from the day archive; never wipe a live board."""
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import scanner
import verify


TZ = ZoneInfo("Africa/Johannesburg")
NOW = datetime(2026, 10, 20, 14, 0, tzinfo=TZ)


def _day(path: Path, date: str, rows: list) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{date}.json").write_text(
        __import__("json").dumps({"date": date, "fixtures": rows}), encoding="utf-8")


def test_archive_restores_tonight_skips_finished_and_past(tmp_path):
    days = tmp_path / "days"
    _day(days, "2026-10-20", [
        {"kickoff": "2026-10-20 11:00", "home": "Gone", "away": "FC", "country": "England",
         "league": "PL", "div": "E0", "score": {"hg": 1, "ag": 0, "status": "FT"}},
        {"kickoff": "2026-10-20 20:45", "home": "Arsenal", "away": "Leeds", "country": "England",
         "league": "PL", "div": "E0", "livescore_id": "1"},
        {"kickoff": "2026-10-20 21:00", "home": "Ajax", "away": "PSV", "country": "Netherlands",
         "league": "Eredivisie", "div": "LS:netherlands/eredivisie"},
    ])
    start = NOW - timedelta(minutes=5)
    end = NOW + timedelta(days=1)
    got = scanner.fixtures_from_archive(start, end, TZ, days_dir=days, latest_path=tmp_path / "nope.json")
    assert list(got["home"]) == ["Arsenal", "Ajax"]
    assert got.iloc[0]["kickoff"].hour == 20


def test_empty_publication_cannot_wipe_live_fixtures(tmp_path):
    live = tmp_path / "live"
    st = tmp_path / "st"
    live.mkdir(); st.mkdir()
    latest = {
        "version": 3,
        "meta": {"generated": "2026-10-20 14:00", "run_id": "x"},
        "fixtures": [],
    }
    (st / "latest.json").write_text(__import__("json").dumps(latest), encoding="utf-8")
    (st / "run_manifest.json").write_text(__import__("json").dumps({
        "schema_version": 3, "run_id": "x", "model_version": "1",
        "config_sha256": "a" * 64, "generated_at": "2026-10-20T14:00:00",
        "feed_health": {}, "counts": {},
    }), encoding="utf-8")
    (live / "latest.json").write_text(__import__("json").dumps({
        "version": 3, "fixtures": [
            {"id": "a", "kickoff": "2026-10-20 20:45", "home": "A", "away": "B"},
        ],
    }), encoding="utf-8")
    errors, _ = verify.check_publication(st, live, tmp_path / "nl.csv", NOW.replace(tzinfo=None), expect_fixtures=0)
    assert any("wipe" in e for e in errors)


def test_reel_slots_two_a_day():
    assert scanner._reel_slot(datetime(2026, 10, 20, 8, 0)) == "morning"
    assert scanner._reel_slot(datetime(2026, 10, 20, 12, 5)) is None
    assert scanner._reel_slot(datetime(2026, 10, 20, 16, 0)) == "evening"
    assert scanner._reel_slot(datetime(2026, 10, 20, 14, 0)) is None
