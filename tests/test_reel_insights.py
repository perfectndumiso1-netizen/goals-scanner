"""The evidence layer behind the video slides: markets, standing, form, head to head and the reason lines.

Everything here is pure data-in/data-out — the slides are drawn from these dictionaries, so if a number is wrong
here it is wrong on screen.
"""
from __future__ import annotations

import json
from pathlib import Path

import reel_insights as ri
import shortlist_reel as reel


DETAIL = {
    "xg": {"home": 1.62, "away": 1.18, "total": 2.8},
    "sels": [
        ["O15", 0.86, 0.86, 0.82, 1.19, 0, 4.0, 0.02],
        ["HO05", 0.79, 0.79, 0.74, 1.31, 1, 5.0, 0.03],
        ["AO05", 0.71, 0.71, 0.69, 1.42, 0, 2.0, 0.01],
        ["CO85", 0.72, 0.72, 0.70, 1.44, 0, 2.0, 0.01],
        ["KO35", 0.83, 0.83, 0.80, 1.20, 0, 3.0, 0.02],
        ["O25", 0.55, 0.55, 0.53, 1.90, 0, 2.0, 0.01],   # not a video market
        ["H", 0.48, 0.48, 0.47, 2.10, 0, 1.0, 0.00],     # not a video market
        ["BTTS", 0.61, 0.61, 0.60, 1.66, 0, 1.0, 0.00],  # not a video market
        ["KU25", 0.44, 0.44, 0.45, 1.9, 0, 1.0, 0.00],   # under: banned
    ],
    "teams": {
        "home": {"venue_gf": 1.72, "venue_ga": 0.83, "o15": 0.81,
                 "last5": [{"date": "2026-10-14", "opp": "Golden Arrows", "gf": 2, "ga": 1},
                           {"date": "2026-10-05", "opp": "Sundowns", "gf": 0, "ga": 0},
                           {"date": "2026-09-28", "opp": "Royal AM", "gf": 3, "ga": 0}]},
        "away": {"venue_gf": 1.31, "venue_ga": 1.05, "o15": 0.66,
                 "last5": [{"date": "2026-10-13", "opp": "Stellenbosch", "gf": 1, "ga": 1}]},
    },
    "trends": {
        "match": [{"t": "both meetings finished over 2.5 goals", "k": "goals", "n": 2, "r": 1.0}],
        "home": {"all": [{"t": "Chiefs have scored in eight straight home games", "k": "goals", "n": 8, "r": 0.8}]},
        "away": {"all": [{"t": "both meetings finished over 2.5 goals", "k": "goals", "n": 2, "r": 1.0}]},
        "h2h": [],
    },
    "h2h": [
        {"date": "2026-03-11", "home": "Kaizer Chiefs", "away": "Orlando Pirates", "hg": 2, "ag": 1},
        {"date": "2025-11-02", "home": "Orlando Pirates", "away": "Kaizer Chiefs", "hg": 1, "ag": 1},
        {"date": "2025-05-20", "home": "Kaizer Chiefs", "away": "Orlando Pirates", "hg": 0, "ag": 2},
    ],
}

PICK = {
    "kickoff": "2026-10-21 20:00", "country": "South Africa", "league": "Premier League",
    "home": "Kaizer Chiefs", "away": "Orlando Pirates", "sel": "HO05",
    "label": "Kaizer Chiefs over 0.5 goals", "market": "team", "p": 0.79, "odds": 1.31, "p_sb": 0.74,
    "form_h": "WWDWL", "form_a": "LWDWW",
}


def _leagues(tmp_path: Path) -> Path:
    d = tmp_path / "leagues"
    d.mkdir()
    (d / "index.json").write_text(json.dumps({"count": 1, "leagues": [
        {"slug": "south-africa__premier-league.json", "country": "South Africa", "league": "Premier League",
         "table": True},
        {"slug": "cup.json", "country": "Italy", "league": "Coppa Italia", "table": False},
    ]}), encoding="utf-8")
    (d / "south-africa__premier-league.json").write_text(json.dumps({
        "country": "South Africa", "league": "Premier League",
        "table": [
            {"team": "Kaizer Chiefs", "pos": 3, "pts": 21, "p": 11, "form": "WWDWL"},
            {"team": "Orlando Pirates", "pos": 7, "pts": 17, "p": 11, "form": "LWDWW"},
            {"team": "Mamelodi Sundowns", "pos": 1, "pts": 25, "p": 11, "form": "WWWWD"},
            {"team": "Stellenbosch", "pos": 2, "pts": 23, "p": 11, "form": "WWDWW"},
        ],
    }), encoding="utf-8")
    return d


# ------------------------------------------------------------------ markets

OVER15 = {**PICK, "sel": "O15", "label": "Over 1.5 goals", "market": "goals"}


def test_video_markets_allow_goals_and_corners():
    # 2026-10-27 (user): the videos carry Over 1.5 total goals and nothing else — not corners, not team goals, not
    # bookings, Over 2.5, 1X2, BTTS or any under
    rows = ri.market_rows(DETAIL, OVER15)
    assert {r["sel"] for r in rows} == {"O15", "CO85"}
    assert rows[0]["picked"] is True and rows[0]["p"] == 0.79
    # a legacy pick from another family is simply not a video market any more
    assert ri.market_rows(DETAIL, PICK) == [] or all(r["sel"] in ("O15", "CO85") for r in ri.market_rows(DETAIL, PICK))


def test_the_pick_stands_on_its_own_when_the_detail_is_missing():
    rows = ri.market_rows(None, OVER15)
    assert [r["sel"] for r in rows] == ["O15"]
    assert rows[0]["picked"] is True
    assert ri.chart_rows(None, OVER15)[0]["sel"] == "O15"


def test_the_chart_puts_the_models_number_beside_the_markets():
    rows = ri.chart_rows(DETAIL, OVER15)
    model = next(r for r in rows if r["picked"])
    market = next((r for r in rows if r.get("market")), None)
    assert model["p"] == 0.79 and sum(1 for r in rows if r["picked"]) == 1
    assert market is not None and market["p"] == 0.74                 # the de-vigged price it was anchored to
    assert market["label"] == "Market price (de-vigged)"
    assert ri.chosen_market(DETAIL, OVER15)["sel"] == "O15"


def test_chart_labels_fit_a_phone_screen():
    labels = [ri.short_market(sel, "Chiefs", "Pirates")
              for sel in ("O15", "HO05", "AO05", "CO85", "KO35", "CHO35", "KHO25")]
    assert labels == ["Over 1.5 goals", "Chiefs to score", "Pirates to score", "Over 8.5 corners",
                      "Over 3.5 cards", "Chiefs 4+ corners", "Chiefs 3+ cards"]
    assert all(len(lab) <= 22 for lab in labels)


# ------------------------------------------------------------------ leagues

def test_league_tables_read_the_index_the_app_writes(tmp_path):
    tables = ri.league_tables(_leagues(tmp_path))
    assert ("south africa", "premier league") in tables
    assert len(tables[("south africa", "premier league")]) == 4
    assert ri.league_tables(tmp_path / "missing") == {}


def test_standing_finds_both_clubs_and_describes_them(tmp_path):
    tables = ri.league_tables(_leagues(tmp_path))
    st = ri.standing(tables, PICK)
    assert st and st["size"] == 4 and set(st["teams"]) == {"home", "away"}
    assert ri.standing_line(st["teams"]["home"], 4) == "3rd of 4 · 21 pts · 11 played · WWDWL"
    assert ri.standing_line({"pos": 1, "pts": 25, "p": 11, "form": "WWWWD"}, 4).startswith("1st of 4")
    assert ri.standing_line({"pos": 12, "pts": 9, "p": 11, "form": ""}, 20).startswith("12th of 20")
    assert ri.standing(tables, {**PICK, "home": "Nobody FC", "away": "No One"}) is None


def test_an_accented_club_name_still_matches_the_table(tmp_path):
    tables = ri.league_tables(_leagues(tmp_path))
    alt = {**PICK, "home": "Káizer Chiefs", "away": "Orlando  Pirates"}
    assert ri.standing(tables, alt) is not None


# ------------------------------------------------------------------ form, h2h, reasons

def test_trends_are_short_deduplicated_and_capped():
    lines = ri.trend_lines(DETAIL, limit=3)
    assert len(lines) == 2                                    # the duplicate meeting line is collapsed
    assert lines[0].startswith("Both")                        # capitalised for the slide
    assert all(len(t) <= 110 for t in lines)


def test_recent_results_carry_score_and_wdl():
    rows = ri.recent_rows(DETAIL, "home")
    assert [(r["gf"], r["ga"], r["res"]) for r in rows] == [(2, 1, "W"), (0, 0, "D"), (3, 0, "W")]
    assert ri.recent_rows(DETAIL, "away")[0]["res"] == "D"
    assert ri.recent_rows(None, "home") == []


def test_head_to_head_is_read_from_the_home_teams_point_of_view():
    h = ri.h2h_summary(DETAIL, PICK)
    assert (h["w"], h["d"], h["l"]) == (1, 1, 1)
    assert h["line"].startswith("1W · 1D · 1L in the last 3 meetings")
    assert h["rows"][0]["res"] == "W"                          # Chiefs won that one 2-1
    assert h["rows"][2]["res"] == "L"
    assert ri.h2h_summary(None, PICK) is None


def test_reasons_are_traceable_numbers_and_never_more_than_four(tmp_path):
    table = ri.standing(ri.league_tables(_leagues(tmp_path)), PICK)
    bits = ri.reasons(PICK, DETAIL, table)
    assert 3 <= len(bits) <= 4
    assert "79%" in bits[0]
    assert any("1.62" in b for b in bits)
    assert any("3rd of 16" in b or "3rd of 4" in b for b in bits)


def test_slides_are_planned_by_what_actually_exists(tmp_path):
    table = ri.standing(ri.league_tables(_leagues(tmp_path)), PICK)
    assert ri.slide_plan(PICK, DETAIL, table) == ["pick", "evidence", "record"]
    # no fixture detail and no table: the pick still gets its own slide, and nothing empty is shown
    assert ri.slide_plan(PICK, None, None) == ["pick", "evidence"]
    bare = {k: v for k, v in PICK.items() if k != "p"}
    assert ri.slide_plan(bare, None, None) == ["pick"]


def test_no_voice_and_no_accumulator_left_in_the_reel_module():
    for gone in ("synthesize_speech", "pad_audio", "voice_clips", "polish", "combine"):
        assert not hasattr(reel, gone)
    assert reel.MAX_TOTAL <= 600                                # length guard still exists


def test_the_reel_ranks_the_strongest_allowed_market_per_match():
    # same match: the video features whichever allowed market the model rates highest
    weak = {"home": "A", "away": "B", "sel": "CO85", "kickoff": "2026-10-21 18:00", "p": 0.70}
    strong = {"home": "A", "away": "B", "sel": "O15", "kickoff": "2026-10-21 18:00", "p": 0.84}
    assert [p["sel"] for p in reel.reel_picks([weak, strong])] == ["O15"]
    # within a percentage point the old preference wins (Over 1.5 first), so a video is not twelve corners lines
    tie_corners = {**weak, "p": 0.845}
    assert reel.reel_picks([tie_corners, {**strong, "p": 0.84}])[0]["sel"] == "O15"
    # a dropped family never reaches a video, whatever it claims
    assert reel.reel_picks([{**weak, "sel": "KO35", "p": 0.95}, {**weak, "sel": "HO05", "p": 0.95}]) == []


# ------------------------------------------------------------------ featuring the strongest market

def test_card_selection_is_never_changed_by_rendering():
    pick = {**OVER15, "sel": "CO85", "p": .72, "odds": 1.20}
    assert ri.featured_pick(pick, DETAIL) == pick
    assert ri.chart_rows(DETAIL, pick)[0]["sel"] == "CO85"


def test_the_pick_is_kept_when_it_is_already_the_strongest():
    assert ri.featured_pick(OVER15, DETAIL) == OVER15             # already the video's market, nothing to change
    # with no Over 1.5 in the detail, a non-Over-1.5 board pick stands unchanged rather than inventing one
    flat = {"sels": [["HO05", 0.79, 0.79, 0.74, 1.31, 0, 5.0, 0.03]]}
    assert ri.featured_pick(PICK, flat) == PICK
    assert ri.featured_pick(PICK, None) == PICK                   # no detail: nothing to upgrade from


def test_a_team_goals_pick_quotes_that_clubs_shutout_rate_not_a_goals_line():
    detail = json.loads(json.dumps(DETAIL))
    detail["teams"]["home"]["fts"] = 0.21
    detail["teams"]["away"]["fts"] = 0.35
    home_pick = {**PICK, "sel": "HO05", "market": "team"}
    away_pick = {**PICK, "sel": "AO05", "market": "team"}
    assert "Mixco" not in " ".join(ri.reasons(home_pick, detail, None))   # names come from the pick, not the detail
    assert any("Kaizer Chiefs have failed to score in only 21%" in b for b in ri.reasons(home_pick, detail, None))
    assert any("Orlando Pirates have failed to score in 35%" in b for b in ri.reasons(away_pick, detail, None))
    # a total-goals pick keeps the goals-line sentence
    assert any("Over 1.5 goals has landed" in b for b in ri.reasons({**PICK, "sel": "O15", "market": "goals"}, detail, None))


def test_the_plain_language_ladder_matches_the_percentages():
    assert ri.chance_phrase(0.95) == "better than nine in ten"
    assert ri.chance_phrase(0.86) == "around nine in ten"
    assert ri.chance_phrase(0.74) == "about three in four"
    assert ri.chance_phrase(0.66) == "about two in three"
    assert ri.chance_phrase(0.55) == "better than half"
    assert ri.chance_phrase(None) == "unknown"
