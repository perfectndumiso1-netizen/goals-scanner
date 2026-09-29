"""60-day coverage window: Sportybet deep links, league fixture window, world-feed window math."""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import leagues
import sporty
import worldfeed


def test_sporty_event_url_format():
    ev = {"id": "sr:match:72221292", "country": "England", "tournament": "Premier League",
          "home": "Arsenal FC", "away": "Leeds United"}
    u = sporty.event_url(ev)
    assert u == "https://www.sportybet.com/za/sport/sr:sport:1/england/premier_league/arsenal_fc_v_leeds_united/sr:match:72221292/"
    # symbols become underscores, accents drop
    ev2 = {"id": "e1", "country": "Côte d'Ivoire", "tournament": "Ligue 1", "home": "Café FC", "away": "Naïve SC"}
    u2 = sporty.event_url(ev2)
    assert "/cote_d_ivoire/ligue_1/cafe_fc_v_naive_sc/" in u2
    assert sporty.event_url(None) is None
    assert sporty.event_url({}) is None


def test_sporty_share_url():
    assert sporty.share_url("82J2ZU") == "https://www.sportybet.com/za/?shareCode=82J2ZU"
    assert sporty.share_url("abc def") == "https://www.sportybet.com/za/?shareCode=abcdef"
    assert sporty.share_url("") is None


def test_window_events_grouping_and_filtering():
    now = datetime(2026, 9, 30, 12, 0)
    events = [
        {"eid": "1", "status": "NS", "kickoff": now + timedelta(hours=2), "ccd": "eng", "scd": "epl", "home": "A", "away": "B"},
        {"eid": "2", "status": "NS", "kickoff": now + timedelta(days=59), "ccd": "eng", "scd": "epl", "home": "C", "away": "D"},
        {"eid": "3", "status": "FT", "kickoff": now + timedelta(hours=2), "ccd": "eng", "scd": "epl", "home": "E", "away": "F"},
        {"eid": "4", "status": "NS", "kickoff": now + timedelta(days=90), "ccd": "eng", "scd": "epl", "home": "G", "away": "H"},
        {"eid": "5", "status": "NS", "kickoff": now + timedelta(minutes=10), "ccd": "fra", "scd": "l1", "home": "I", "away": "J"},
    ]
    out = leagues._window_events(events, now, days=60)
    assert [e["eid"] for e in out["eng/epl"]] == ["1", "2"]   # 59 days in, 90 days out and finished dropped
    assert [e["eid"] for e in out["fra/l1"]] == ["5"]
    assert leagues._window_events([], now) == {}
    assert leagues._window_events(None, now) == {}


def test_worldfeed_window_days_60():
    start = datetime(2026, 9, 30, 0, 0)
    end = start + timedelta(days=60)
    days = worldfeed.window_days(start, end)
    assert len(days) == 61
    assert (days[-1] - days[0]).days == 60


def test_config_defaults():
    import scanner
    assert scanner.CONFIG["COVER_DAYS"] == 60
    assert scanner.CONFIG["APP_WINDOW_HOURS"] == 24.0
    assert scanner.CONFIG["NEWS_HOURS"] == 72.0
    assert 0 < scanner.CONFIG["APP_WINDOW_HOURS"] < scanner.CONFIG["COVER_DAYS"] * 24
