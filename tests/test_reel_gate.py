"""The gate a match has to pass before it reaches a video (user rules, 2026-10-27).

    * recent results for BOTH clubs, with scores;
    * a head to head that is both present and recent;
    * an internet cross-check before the video is finalised — a contradiction drops the match, confirmed matches are
      used first, an unverified one is a last resort;
    * Over 1.5 only, and the same match never twice.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import reel_insights as ri
import reel_verify as rv
import shortlist_reel as reel

NOW = datetime(2026, 10, 27, 9, 0)


def _rows(n: int, *, newest_days_ago: int = 7) -> list[dict]:
    return [{"date": (NOW - timedelta(days=newest_days_ago + 7 * i)).strftime("%Y-%m-%d"),
             "venue": "H" if i % 2 else "A", "opp": f"Opp {i}", "gf": 2 if i % 3 else 0, "ga": 1} for i in range(n)]


def detail(*, home_rows: int = 5, away_rows: int = 5, h2h: int = 3, h2h_age_days: int = 200,
           newest_days_ago: int = 7, o15: float = 0.86, home: str = "Chiefs", away: str = "Pirates") -> dict:
    meetings = []
    for i in range(h2h):
        when = NOW - timedelta(days=h2h_age_days + 200 * i)
        meetings.append({"date": when.strftime("%Y-%m-%d"), "home": "Chiefs" if i % 2 else "Pirates",
                         "away": "Pirates" if i % 2 else "Chiefs", "hg": 2, "ag": 1})
    return {
        "home": home, "away": away,
        "sels": [["O15", o15, o15, 0.82, 1.19, 0, 4.0, 0.02]],
        "teams": {
            "home": {"o15": 0.81, "name": "Chiefs", "last5": _rows(home_rows, newest_days_ago=newest_days_ago)},
            "away": {"o15": 0.66, "name": "Pirates", "last5": _rows(away_rows, newest_days_ago=newest_days_ago)},
        },
        "h2h": meetings,
        "xg": {"home": 1.6, "away": 1.2},
    }


PICK = {"home": "Chiefs", "away": "Pirates", "sel": "O15", "label": "Over 1.5 goals", "market": "goals",
        "p": 0.86, "odds": 1.19, "p_sb": 0.82, "kickoff": "2026-10-27 20:00", "country": "South Africa",
        "league": "Premier League"}


@pytest.fixture(autouse=True)
def _clear():
    rv.reset_cache()
    yield
    rv.reset_cache()


def _search(titles):
    return lambda *_a, **_k: [{"title": t, "source": "Test", "when": NOW} for t in titles]


# ------------------------------------------------------------------ the stats
def test_a_match_with_both_teams_recent_and_a_recent_head_to_head_passes():
    assert rv.stats_problems(PICK, detail(), now=NOW) == []
    verdict = rv.check(PICK, detail(), now=NOW, search=_search([]))
    assert verdict["ok"] and verdict["verdict"] == "unverified"


def test_no_head_to_head_means_no_video():
    problems = rv.stats_problems(PICK, detail(h2h=0), now=NOW)
    assert any("head-to-head" in p for p in problems)


def test_one_meeting_is_not_a_record():
    assert any("head-to-head" in p for p in rv.stats_problems(PICK, detail(h2h=1), now=NOW))
    assert rv.stats_problems(PICK, detail(h2h=2), now=NOW) == []


def test_stale_head_to_head_means_no_video():
    problems = rv.stats_problems(PICK, detail(h2h=3, h2h_age_days=rv.H2H_MAX_DAYS + 50), now=NOW)
    assert any("no head-to-head for" in p for p in problems)


def test_short_or_stale_recent_form_means_no_video():
    assert any("recent result" in p for p in rv.stats_problems(PICK, detail(home_rows=3), now=NOW))
    assert any("recent result" in p for p in rv.stats_problems(PICK, detail(away_rows=4), now=NOW))
    stale = rv.stats_problems(PICK, detail(newest_days_ago=rv.MAX_RECENT_DAYS + 30), now=NOW)
    assert any("newest result is" in p for p in stale)


def test_a_detail_file_for_another_match_is_refused():
    wrong = {**detail(), "home": "Someone", "away": "Else"}
    problems = rv.stats_problems({**PICK, "home": "Chiefs", "away": "Pirates"}, wrong, now=NOW)
    assert any("detail belongs to" in p for p in problems)


def test_a_missing_detail_file_is_refused():
    assert rv.stats_problems(PICK, None, now=NOW) == ["no fixture detail — the stats cannot be checked"]


def test_impossible_rates_are_refused():
    d = detail()
    d["teams"]["home"]["o15"] = 1.4
    assert any("not a probability" in p for p in rv.stats_problems(PICK, d, now=NOW))


def test_a_finished_match_is_not_previewed():
    assert any("passed" in p for p in
               rv.stats_problems(PICK, detail(), now=NOW + timedelta(days=2)))


# ------------------------------------------------------------------ the internet check
def test_a_postponed_match_is_dropped():
    web = rv.web_check(PICK, search=_search(["Chiefs v Pirates postponed due to waterlogged pitch"]))
    assert web["verdict"] == "contradicted"
    verdict = rv.check(PICK, detail(), now=NOW, search=_search(["Chiefs v Pirates called off"]))
    assert not verdict["ok"] and any("internet says" in r for r in verdict["reasons"])


def test_a_confirmed_match_is_named_and_ranked_first():
    web = rv.web_check(PICK, search=_search(["Chiefs host Pirates in a top-of-the-table clash"]))
    assert web["verdict"] == "confirmed" and "Chiefs" in web["note"]


def test_unrelated_headlines_leave_a_match_unverified_not_rejected():
    web = rv.web_check(PICK, search=_search(["Chiefs sign a new goalkeeper on a free transfer"]))
    assert web["verdict"] == "unverified"
    assert rv.check(PICK, detail(), now=NOW, search=_search([]))["ok"] is True


def test_confirmation_can_be_made_mandatory():
    verdict = rv.check(PICK, detail(), now=NOW, search=_search([]), require_confirmation=True)
    assert not verdict["ok"] and "no online confirmation" in verdict["reasons"][0]


def test_a_dead_search_degrades_to_unverified_instead_of_raising():
    def boom(*_a, **_k):
        raise RuntimeError("no network")
    web = rv.web_check(PICK, search=boom)
    assert web["verdict"] == "unverified"


# ------------------------------------------------------------------ selecting for the video
def _pick(home, away, **kw):
    return {"home": home, "away": away, "sel": "O15", "label": "Over 1.5 goals", "market": "goals",
            "p": 0.82, "odds": 1.30, "p_sb": 0.78, "kickoff": "2026-10-27 20:00", "country": "South Africa",
            "league": "Premier League", **kw}


def test_select_keeps_only_verified_matches_and_reports_the_rest():
    picks = [_pick("Chiefs", "Pirates"), _pick("Ghost", "Town"), _pick("Lions", "Tigers")]
    details = {f"Chiefs|Pirates|2026-10-27 20:00": detail(),
               f"Lions|Tigers|2026-10-27 20:00": detail(h2h=0)}     # no head to head → out
    kept, skipped = rv.select(picks, details=details, now=NOW, search=_search([]))
    assert [p["home"] for p in kept] == ["Chiefs"]
    assert {s["home"] for s in skipped} == {"Ghost", "Lions"}
    assert all(s["reasons"] for s in skipped)


def test_confirmed_matches_are_used_first_when_there_are_enough():
    picks = [_pick("Alpha", "Beta"), _pick("Gamma", "Delta"), _pick("Eps", "Zeta"), _pick("Eta", "Theta")]
    details = {f"{p['home']}|{p['away']}|2026-10-27 20:00": detail(home=p["home"], away=p["away"]) for p in picks}

    def search(home, away, *_a, **_k):
        if home in ("Gamma", "Eps", "Eta"):
            return [{"title": f"{home} v {away} preview", "source": "Test", "when": NOW}]
        return []

    kept, _skipped = rv.select(picks, details=details, now=NOW, search=search)
    assert kept[0]["checked"] == "confirmed"                  # the confirmed one leads even though it was listed 2nd
    assert [p["home"] for p in kept[:3]] == ["Gamma", "Eps", "Eta"]


# ------------------------------------------------------------------ never twice, never another market
def test_the_same_match_is_never_in_the_video_twice():
    same = [_pick("Chiefs", "Pirates", kickoff="2026-10-27 20:00"),
            _pick("Chiefs", "Pirates", kickoff="2026-10-27 21:00")]     # same clubs, a data slip on the time
    assert len(reel.reel_picks(same)) == 1


def test_corners_are_video_markets_again():
    assert reel.reel_picks([{**_pick("Chiefs", "Pirates"), "sel": "CO95", "label": "Over 9.5 corners", "p": 0.9}])
    assert reel.is_reel_market({"sel": "O15"}) and reel.is_reel_market({"sel": "CO85"})
    assert not reel.is_reel_market({"sel": "HO05", "label": "Chiefs to score"})


def test_video_picks_reads_the_detail_files_and_logs_what_it_dropped(tmp_path, caplog):
    import json

    fx = tmp_path / "fx"
    fx.mkdir()
    good = _pick("Chiefs", "Pirates")
    bad = _pick("Lions", "Tigers")
    (fx / f"{reel._fx_key(good)}.json").write_text(json.dumps(detail()), encoding="utf-8")
    (fx / f"{reel._fx_key(bad)}.json").write_text(json.dumps(detail(**{"h2h": 0})), encoding="utf-8")

    with caplog.at_level("INFO"):
        kept, skipped = reel.video_picks([good, bad], fx_dir=fx, now=NOW, search=_search([]))
    assert kept == []  # a single valid fixture cannot form a five-match video
    assert [s["home"] for s in skipped] == ["Lions"]
    assert any("Video skipped" in r.message for r in caplog.records)


# ------------------------------------------------------------------ the slides are slower now
def test_a_slide_is_on_screen_long_enough_to_read_it():
    # 2026-10-27: the user could not read the stats before the next slide. Every slide now has a generous floor and
    # each line on it buys over a second more.
    assert reel.stage_seconds("pick", bars=2) >= 7.0
    assert reel.stage_seconds("evidence", lines=5) >= 10.0
    assert reel.stage_seconds("record", lines=10) >= 15.0
    assert reel.stage_seconds("record", lines=10) <= 16.0          # still bounded, never a still frame forever
    assert reel.stage_seconds("pick") >= reel.STAGE_FLOOR["pick"]
    assert reel.stage_seconds("evidence", lines=1) >= reel.STAGE_FLOOR["evidence"]
    assert reel.stage_seconds("record", lines=1) >= reel.STAGE_FLOOR["record"]


def test_the_reading_pace_is_slower_than_the_old_narration():
    import music

    assert music.READ_WPS <= 2.0                       # 2.6 was the narration pace and it read too fast
    assert music.MIN_SLIDE >= 4.0
    # 20 words at the new pace take longer than eleven seconds, so even a long line is not flashed
    assert music.reading_seconds(" ".join(["word"] * 20)) >= 10.0


# ------------------------------------------------------------------ the app mirrors the video
WWW = __import__("pathlib").Path(__file__).resolve().parent.parent / "android/app/src/main/assets/www"


def _js(name: str) -> str:
    return (WWW / name).read_text(encoding="utf-8")


def test_the_phone_player_carries_the_same_market_and_the_same_gate():
    pages = _js("pages.js")
    assert "=== 'O15'" in pages or '=== "O15"' in pages          # one market, straight comparison
    assert "GATE_MIN_RESULTS = 5" in pages and "GATE_MIN_H2H = 2" in pages
    assert "REEL_MAX_PICKS = 8" in pages
    assert "const seen = {};" in pages                          # never the same match twice
    assert "briefingVerified(x, briefingDetail(x))" in pages     # an unverifiable match never reaches a slide


def test_the_phone_player_reads_as_slowly_as_the_video():
    pages = _js("pages.js")
    hold = pages[pages.index("function briefingHold"):]
    hold = hold[:hold.index("function briefingBarsHtml")]
    assert "6.5 + 0.9 *" in hold and "4.5 + 1.3 *" in hold       # the video's stage timings
    assert "Math.min(16" in hold                                 # 16 s cap per stats slide
    assert "words / 1.85" in hold and "45000" in hold            # 1.85 words a second, 45 s longest card
    assert "words / 2.6" not in hold and "Math.min(11" not in hold


def test_the_briefing_lives_only_on_the_bet_advisor_tab():
    views, pages = _js("views.js"), _js("pages.js")
    assert "btn-briefing" not in views                           # the Shortlist tab no longer offers it
    advisor = pages[pages.index("PR.pages.advisor"):pages.index("PR.pages.briefing")]
    assert "btn-briefing" in advisor and "Today’s briefing" in advisor


# ------------------------------------------------------------------ one row per real match
def test_the_same_match_from_two_feeds_is_not_a_second_result():
    """Found on 2026-10-28: working down a live pick, Aberdeen's "last five" held Dundee United 2-3 twice.

    Both clubs had only three distinct results, so the match could not honestly be described on a video — and the
    inflated list would have made it look like five.
    """
    dup = _rows(3)
    dup = [dup[0], dict(dup[0]), dup[1], dict(dup[1]), dup[2]]
    d = detail()
    d["teams"]["home"]["last5"] = dup
    rows = rv._results(d["teams"]["home"], None)
    assert len(rows) == 3
    assert any("recent result" in p for p in rv.stats_problems(PICK, d, now=NOW))


def test_a_duplicated_head_to_head_is_one_meeting():
    d = detail(h2h=1)
    d["h2h"] = d["h2h"] * 2                                   # the same meeting twice from two feeds
    assert any("head-to-head" in p for p in rv.stats_problems(PICK, d, now=NOW))


def test_the_history_pool_drops_a_fixture_that_arrived_twice():
    import pandas as pd
    import scanner

    rows = [{"country": "Scotland", "date": "2026-10-24", "home": "Dundee United", "away": "Aberdeen", "hg": 3, "ag": 2},
            {"country": "Scotland", "date": "2026-10-24", "home": "Dundee United", "away": "Aberdeen", "hg": 3, "ag": 2},
            {"country": "scotland ", "date": "2026-10-17", "home": "Aberdeen", "away": "St Mirren", "hg": 3, "ag": 1}]
    out = scanner.dedupe_results(pd.DataFrame(rows))
    assert len(out) == 2                                       # the archived copy of the same match is gone
    assert list(out["date"]) == ["2026-10-24", "2026-10-17"]    # and the first (domestic) row wins
    # a corrected score is a different row, not a duplicate to be swallowed
    more = pd.DataFrame(rows[:2] + [{"country": "Scotland", "date": "2026-10-24", "home": "Dundee United",
                                     "away": "Aberdeen", "hg": 3, "ag": 1}])
    assert len(scanner.dedupe_results(more)) == 2
