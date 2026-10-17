"""Natural narration for the match breakdown: no stat soup, no double counting, sourced facts only."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import breakdown_script as bs
import match_breakdown as mb
import spoken as sp

FIX = Path(__file__).resolve().parent / "fixtures" / "breakdown_dossiers.json"


def dossiers():
    return json.loads(FIX.read_text(encoding="utf-8"))


def _row(date, venue, opp, gf, ga):
    return {"date": date, "venue": venue, "opp": opp, "gf": gf, "ga": ga}


def _dos(rows, **kw):
    d = {"home": "Union Berlin", "away": "Dortmund", "country": "Germany", "league": "Bundesliga", "kickoff": "2026-10-17 15:30",
         "teams": {"home": {"n": 40, "venue_gf": 1.6, "venue_ga": 1.7, "last5": rows}, "away": {"n": 30, "last5": []}}}
    d.update(kw)
    return d


# ------------------------------------------------------------------ the same match twice in a team's history

def test_a_match_the_feed_lists_twice_is_counted_once():
    rows = [_row("2026-10-10", "H", "Elversberg", 1, 0), _row("2026-10-10", "H", "SV Elversberg", 1, 0),
            _row("2026-09-18", "A", "Bayern Munich", 0, 7), _row("2026-09-18", "A", "Bayern", 0, 7),
            _row("2026-09-11", "H", "Schalke 04", 1, 3)]
    d = _dos(rows)
    got = bs.last_results(d, "home")
    assert len(got) == 3
    text = bs.form_unit("Union Berlin", got, sp.Chooser(1))
    assert "two wins" not in text and "two" not in text.split(",")[0]          # one win must never become "a run of two"
    assert "last three league games" in text
    assert bs.suspect_history(d, "home")


def test_streaks_from_the_feed_are_not_trusted_for_a_team_whose_history_repeats():
    rows = [_row("2026-10-10", "H", "A", 1, 0), _row("2026-10-10", "H", "A FC", 1, 0), _row("2026-09-18", "A", "B", 2, 1),
            _row("2026-09-11", "H", "C", 3, 0), _row("2026-09-04", "A", "D", 1, 1)]
    d = _dos(rows, trends={"home": {"all": [{"t": "Union Berlin scored in 12 consecutive matches"}]}, "away": {"all": []}})
    assert bs.trend_unit(d, "home", sp.Chooser(1)) is None
    clean = _dos([_row(f"2026-10-{10 - i:02d}", "H", f"X{i}", 1, 0) for i in range(5)],
                 trends={"home": {"all": [{"t": "Union Berlin scored in 12 consecutive matches"}]}, "away": {"all": []}})
    assert "twelve games in a row" in bs.trend_unit(clean, "home", sp.Chooser(1))


def test_head_to_head_meetings_are_deduplicated_before_averaging():
    d = _dos([], h2h=[{"date": "2025-03-02", "home": "Sparta", "away": "Willem II", "hg": 4, "ag": 0},
                      {"date": "2025-03-02", "home": "Sparta Rotterdam", "away": "Willem II", "hg": 4, "ag": 0}])
    assert len(bs.meetings(d)) == 1
    assert "They last met in March 2025" in bs.h2h_unit(d, sp.Chooser(1))


# ------------------------------------------------------------------ plain speech

def test_results_and_form_are_phrased_like_a_pundit():
    ch = sp.Chooser(3)
    assert bs.result_phrase(_row("d", "H", "Elversberg", 1, 0), ch) in ("beat Elversberg one-nil at home", "saw off Elversberg one-nil at home", "got past Elversberg one-nil at home")
    assert "hammered" in bs.result_phrase(_row("d", "A", "RB Leipzig", 0, 6), sp.Chooser(3))
    rows = [_row("2026-10-10", "A", "Napoli", 0, 3), _row("2026-10-03", "H", "Como", 2, 0), _row("2026-09-27", "A", "Genoa", 1, 1),
            _row("2026-09-20", "H", "Venezia", 3, 2), _row("2026-09-13", "A", "Fiorentina", 3, 0)]
    text = bs.form_unit("Frosinone", rows, sp.Chooser(5))
    assert "three wins from their last five league games" in text and "three-nil at Napoli" in text and not re.search(r"\d", text)
    assert "last time out" not in text                                                # a European night could sit in between


def test_team_news_cards_are_spoken_in_plain_words_with_one_source():
    cards = [{"team": "Deportivo A Coruna", "out": ["Aubameyang", "Marc Casadó", "Eddahchouri"], "susp": ["Amatucci"], "source": "Sports Mole · 14 Oct"},
             {"team": "Levante", "out": ["Etta Eyong", "Primo", "Sotelo"], "source": "Sports Mole · 14 Oct"}]
    say = " ".join(bs.card_speech(cards, {}, sp.Chooser(2)))
    assert "Sports Mole" in say and say.count("Sports Mole") == 1
    assert "Deportivo La Coruna" in say and "Casado" in say and "Amatucci is suspended" in say and "Levante" in say
    assert "Casadó" not in say                                             # accents never reach the voice


def test_a_stream_listing_is_not_news():
    d = {"home": "Villarreal", "away": "Elche", "news": {"match": [
        {"title": "Villarreal CF vs. Elche CF (Matchday #9) 10/17/26 - Stream the Match Live", "source": "ESPN", "when": "2026-10-15 10:00", "bucket": "24h"}]}}
    assert mb.reputable_headlines(d) == []


def test_over_picks_give_rounded_reasons_not_percentages():
    d = dossiers()[0]
    d["_best_market"] = {"label": "Over 1.5 goals", "odds": 1.17}
    items, bullets = bs.v_units(d, sp.Chooser(4))
    spoken = " ".join(t for _, t in items)
    assert "over one and a half goals, at 1.17" in spoken
    assert "%" not in spoken and not re.search(r"\b\d{2}\b", re.sub(r"\d\.\d\d", "", spoken))
    assert bullets and any("%" in b or "1.5" in b for b in bullets)         # the screen may carry the numbers


def test_the_pick_is_one_plain_sentence():
    d = dossiers()[2]
    d["_best_market"] = {"label": f"{d['home']} over 0.5 goals", "odds": 1.17}
    assert bs.spoken_market(d["_best_market"], d) == f"{sp.team(d['home'])} to score at least once"
    assert bs.spoken_market({"label": "Over 9.5 corners"}, d) == "over nine and a half corners"


# ------------------------------------------------------------------ a lint over real-shaped data

def _sentences(text: str):
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def test_every_script_over_real_data_reads_like_speech():
    ms = dossiers()
    pack = mb.auto_pack(ms[:6], day="2026-10-17")
    pack2 = mb.auto_pack(ms[6:12], day="2026-10-16")
    contractions = 0
    for pk in (pack, pack2):
        texts = [pk["intro"], pk["closer"]] + [pm[k] for pm in pk["matches"] for k in ("a", "b", "v")]
        for t in texts:
            assert t.strip() and not re.search(r"\bNone\b|N/A|\bnan\b|  | \.|\.\.|\bper game\b|%|\bvs\.?\b|/|\(|\)", t), t
            assert not mb.FORBIDDEN_PUBLIC.search(t), t
            for s in _sentences(t):
                assert s[0].isupper() or s[0].isdigit(), s
                assert len(s.split()) <= 38, s
            digits = re.findall(r"\d+(?:\.\d+)?", t)
            assert all(re.fullmatch(r"\d\.\d\d|(19|20)\d\d", x) for x in digits), (digits, t)      # only odds and years keep digits
            contractions += len(re.findall(r"\b\w+'(?:t|s|re|ve|ll|m|d)\b", t))
    assert contractions >= 20                                                                   # it is spoken, not written


def test_consecutive_matches_do_not_share_an_opener_or_a_pick_lead():
    pack = mb.auto_pack(dossiers()[:6], day="2026-10-17")
    firsts = [pm["a"].split(",")[0].split(".")[0] for pm in pack["matches"]]
    assert all(a != b for a, b in zip(firsts, firsts[1:])), firsts
    leads = [re.split(r"[:,]| at ", pm["v"])[0] for pm in pack["matches"]]
    assert all(a != b for a, b in zip(leads, leads[1:])), leads


def test_the_same_day_always_gives_the_same_script_and_a_new_day_gives_a_new_one():
    ms = dossiers()[:6]
    assert mb.auto_pack(ms, day="2026-10-17") == mb.auto_pack(ms, day="2026-10-17")
    assert mb.auto_pack(ms, day="2026-10-17") != mb.auto_pack(ms, day="2026-10-18")


def test_sourced_extras_feed_the_same_natural_voice():
    ms = dossiers()[:2]
    key = f"{ms[0]['home']}|{ms[0]['away']}"
    extras = {key: {"cards": [{"team": ms[0]["home"], "out": ["Ngankam"], "doubt": ["Pimpong"], "source": "The Stats Zone · 15 Oct"},
                              {"team": ms[0]["away"], "out": ["Ache", "Hübers"], "back": ["Castro-Montes"], "source": "The Stats Zone · 15 Oct"}],
                      "table": {"home": "14th · 5 pts", "away": "10th · 7 pts", "source": "BBC Sport"},
                      "facts": [{"text": "Cologne winless in 15 away league games", "source": "Flashscore",
                                 "spoken": "Cologne haven't won away from home in the league for fifteen games."}]}}
    pm = mb.auto_pack(ms, day="2026-10-17", extras=extras)["matches"][0]
    assert "Ngankam" in pm["b"] and "Pimpong" in pm["b"] and "doubtful" in pm["b"] and "Hubers" in pm["b"]
    assert "Castro-Montes is back in the squad" in pm["b"] and "fifteen games" in pm["b"]
    assert pm["cards"][0]["text"].startswith("Out: Ngankam") and pm["table"]["home"].startswith("14th")


def test_form_is_league_form_and_ignores_cup_games():
    d = _dos([_row("2026-10-10", "A", "Bodo", 1, 3), _row("2026-09-19", "H", "Rosenborg", 1, 3),
              {**_row("2026-09-16", "A", "Brattvaag", 2, 1), "league": "NM Cup: Round 2"},
              _row("2026-09-13", "A", "Viking", 1, 8), _row("2026-09-06", "H", "Tromsoe", 2, 0)])
    for r in d["teams"]["home"]["last5"]:
        r.setdefault("league", "Bundesliga")
    got = bs.last_results(d, "home")
    assert [m["opp"] for m in got] == ["Bodo", "Rosenborg", "Viking", "Tromsoe"] and bs.is_league_form(d, "home")


def test_a_midweek_european_game_is_said_and_stops_streak_claims():
    fatigue = {"category": "fatigue", "subject": "Dortmund", "stale": False,
               "text": "last match 2026-10-14, 3 day(s) before kick-off; 1 match(es) in the last 7 days (last 1-0 v Champions League · League Stage)"}
    d = _dos([], context={"facts": [fatigue]}, trends={"home": {"all": []}, "away": {"all": [{"t": "Dortmund scored in 7 consecutive matches"}]}})
    d["teams"]["away"]["last5"] = [{**_row(f"2026-10-{9 - i:02d}", "H", f"X{i}", 2, 0), "league": "Bundesliga"} for i in range(5)]
    note = bs.midweek_unit(d, "away", sp.Chooser(1), other_days=7)
    assert "Champions League" in note and "one-nil" in note and "Wednesday" in note and "three days" in note
    assert bs.incomplete(d, "away") and bs.trend_unit(d, "away", sp.Chooser(1)) is None
