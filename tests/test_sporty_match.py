"""Sportybet events must belong to the fixture they are attached to.

The 2026-10-13 bug: attach_prices zipped todays.index onto analysed rows. Fixtures the
depth gate skipped (thin squads) shifted every later event — Kaizer Chiefs landed on
Bristol City, and the match page painted the bookmaker names via home_long.
"""
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import math
import pandas as pd
import pytest

import sporty
from scanner import attach_prices


NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def _fx(home, away, country="England", hour=20):
    ko = pd.Timestamp(f"2026-10-13 {hour:02d}:45")
    return pd.Series({
        "date": pd.Timestamp("2026-10-13"),
        "country": country,
        "home": home,
        "away": away,
        "kickoff": ko,
    })


def _ev(eid, home, away, country="England", markets=None):
    return {
        "id": eid, "home": home, "away": away, "country": country,
        "tournament": "test", "ko": NOW,
        "markets": markets or {"1X2": (2.0, 3.3, 3.6)},
    }


def _row(fx, **kw):
    extra = NS(p_o25_fair=float("nan"))
    return NS(fx=fx, extra=extra, sb=None, sb_event=None, sb_full=None,
              mkt_h=float("nan"), mkt_a=float("nan"), mkt_source="", x12_market=None, fair={}, **kw)


def test_event_fits_same_club_long_name():
    fx = _fx("Bristol City", "Blackburn")
    assert sporty.event_fits(fx, _ev("ok", "Bristol City", "Blackburn Rovers"))
    assert sporty.event_fits(fx, _ev("ok", "Bristol City", "Blackburn"))


def test_event_fits_rejects_a_different_match():
    fx = _fx("Bristol City", "Blackburn")
    assert not sporty.event_fits(fx, _ev("no", "Kaizer Chiefs", "Stellenbosch FC", "South Africa"))
    assert not sporty.event_fits(fx, None)


def test_attach_prices_does_not_zip_skipped_fixtures():
    """todays has Chiefs then Bristol; only Bristol was analysed. Bristol must get Bristol's event."""
    todays = pd.DataFrame([
        _fx("Kaizer Chiefs", "Stellenbosch FC", "South Africa"),
        _fx("Bristol City", "Blackburn"),
    ])
    chiefs = _ev("sr:chiefs", "Kaizer Chiefs", "Stellenbosch FC", "South Africa",
                 {"1X2": (1.7, 3.5, 5.0)})
    bristol = _ev("sr:bristol", "Bristol City", "Blackburn Rovers",
                  markets={"1X2": (2.2, 3.2, 3.4)})
    sbmap = {0: chiefs, 1: bristol}
    r = _row(todays.iloc[1])
    attach_prices([r], sbmap, todays)
    assert r.sb_event["id"] == "sr:bristol"
    assert r.sb_event["home"] == "Bristol City"
    assert r.sb["1X2"][0] == 2.2


def test_attach_prices_never_paints_a_foreign_event_on_a_row():
    todays = pd.DataFrame([_fx("Bristol City", "Blackburn")])
    # wrongly keyed as if the matcher had aligned by position
    sbmap = {0: _ev("sr:chiefs", "Kaizer Chiefs", "Stellenbosch FC", "South Africa")}
    r = _row(todays.iloc[0])
    attach_prices([r], sbmap, todays)
    assert r.sb_event is None
    assert r.sb is None


def test_attach_prices_drops_a_carried_mismatched_event():
    todays = pd.DataFrame([_fx("Bristol City", "Blackburn")])
    r = _row(todays.iloc[0])
    r.sb_event = {"id": "sr:chiefs", "home": "Kaizer Chiefs", "away": "Stellenbosch FC"}
    r.sb = {"1X2": (1.5, 4.0, 6.0)}
    attach_prices([r], {}, todays)
    assert r.sb_event is None
    assert r.sb is None


def test_match_fixtures_is_exclusive():
    ko = pd.Timestamp("2026-10-13 20:45")
    fixtures = pd.DataFrame([
        {"date": pd.Timestamp("2026-10-13"), "country": "England", "home": "Bristol City",
         "away": "Blackburn", "kickoff": ko},
        {"date": pd.Timestamp("2026-10-13"), "country": "England", "home": "Burnley",
         "away": "Charlton", "kickoff": ko},
    ])
    events = [
        _ev("e-bristol", "Bristol City", "Blackburn Rovers"),
        _ev("e-burnley", "Burnley FC", "Charlton Athletic"),
    ]
    # give both events the same kick-off so they share the time window
    for e in events:
        e["ko"] = ko.to_pydatetime().replace(tzinfo=timezone.utc)
    out = sporty.match_fixtures(fixtures, events)
    ids = {e["id"] for e in out.values()}
    assert ids == {"e-bristol", "e-burnley"}
    assert out[0]["id"] == "e-bristol"
    assert out[1]["id"] == "e-burnley"


def test_club_long_rejects_foreign_bookmaker_name():
    from appdata import _club_long
    assert _club_long("Bristol City", "Kaizer Chiefs", "Bristol City") == "Bristol City"
    assert _club_long("Blackburn", "Stellenbosch FC") == "Blackburn"
    assert _club_long("Blackburn", "Blackburn Rovers") == "Blackburn Rovers"
    assert _club_long("Wolves", "Wolverhampton Wanderers") == "Wolverhampton Wanderers"
