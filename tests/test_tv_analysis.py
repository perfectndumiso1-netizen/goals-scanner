"""Unit tests for the TV-style Match Analysis Show (16:9 YouTube & 9:16 TikTok)."""
from pathlib import Path
from PIL import Image
import tv_analysis as tv

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "reel"

SAMPLE_DOSSIER = {
    "id": "2026-10-16 20:30|Germany|Eintracht Frankfurt|FC Cologne",
    "kickoff": "2026-10-16 20:30",
    "country": "Germany",
    "league": "Bundesliga",
    "home": "Eintracht Frankfurt",
    "away": "FC Cologne",
    "mxg": [1.85, 1.32],
    "quality": {"overall": "High", "score": 88},
    "teams": {
        "home": {
            "n": 45, "gf": 1.60, "ga": 2.35, "o15": 0.90, "o25": 0.72, "btts": 0.65, "cs": 0.14, "fts": 0.12,
            "venue_n": 22, "venue_gf": 1.51, "venue_ga": 2.07, "venue_o15": 0.888, "venue_o25": 0.747, "venue_btts": 0.684,
            "last5": [
                {"date": "2026-10-10", "venue": "A", "opp": "RB Leipzig", "gf": 0, "ga": 6},
                {"date": "2026-10-04", "venue": "H", "opp": "Freiburg", "gf": 2, "ga": 2},
                {"date": "2026-09-21", "venue": "A", "opp": "Mainz 05", "gf": 3, "ga": 1},
            ],
        },
        "away": {
            "n": 38, "gf": 1.44, "ga": 2.03, "o15": 0.87, "o25": 0.68, "btts": 0.84, "cs": 0.03, "fts": 0.0,
            "venue_n": 18, "venue_gf": 1.11, "venue_ga": 2.37, "venue_o15": 0.935, "venue_o25": 0.695, "venue_btts": 0.854,
            "last5": [
                {"date": "2026-10-11", "venue": "H", "opp": "Borussia M'gladbach", "gf": 2, "ga": 1},
                {"date": "2026-10-03", "venue": "A", "opp": "Hamburger SV", "gf": 1, "ga": 2},
            ],
        },
    },
    "h2h": [
        {"date": "2026-04-05", "home": "Eintracht Frankfurt", "away": "FC Cologne", "hg": 2, "ag": 2, "league": "Bundesliga"},
        {"date": "2025-11-22", "home": "FC Cologne", "away": "Eintracht Frankfurt", "hg": 3, "ag": 4, "league": "Bundesliga"},
    ],
    "h2h_meta": {"n": 2, "avg_goals": 5.5, "o15": 2, "o25": 2, "btts": 2},
    "context": {
        "facts": [
            {"category": "fatigue", "subject": "Eintracht Frankfurt", "text": "last match 2026-10-10, 6 day(s) before kick-off; 2 match(es) in the last 7 days", "stale": False},
            {"category": "fatigue", "subject": "FC Cologne", "text": "last match 2026-10-11, 5 day(s) before kick-off; 2 match(es) in the last 7 days", "stale": False},
        ],
    },
    "sels": [
        {"sel": "AO05", "label": "FC Cologne over 0.5 goals", "odds": 1.23, "market": "team_goals"},
    ],
}


def test_select_featured_matches_prioritises_big_leagues():
    sl = [{"home": "Eintracht Frankfurt", "away": "FC Cologne", "sel": "AO05", "label": "FC Cologne over 0.5 goals", "odds": 1.23, "market": "team_goals"}]
    featured = tv.select_featured_matches([SAMPLE_DOSSIER], sl, limit=4)
    assert len(featured) == 1
    assert featured[0]["_best_market"]["label"] == "FC Cologne over 0.5 goals"
    assert featured[0]["_best_market"]["odds"] == 1.23


def test_tv_boards_render_16x9_and_9x16(tmp_path):
    featured = tv.select_featured_matches([SAMPLE_DOSSIER], None, limit=4)
    logo = ASSETS / "logo.png"
    bg = ASSETS / "bg_stadium.jpg"
    for aspect, expected_size in (("16:9", (1920, 1080)), ("9:16", (1080, 1920))):
        intro = tmp_path / f"intro_{aspect.replace(':', 'x')}.jpg"
        ba = tmp_path / f"ba_{aspect.replace(':', 'x')}.jpg"
        bb = tmp_path / f"bb_{aspect.replace(':', 'x')}.jpg"
        closer = tmp_path / f"closer_{aspect.replace(':', 'x')}.jpg"
        tv.render_show_intro(featured, logo, bg, intro, aspect=aspect)
        tv.render_match_board_a(featured[0], 1, 1, bg, logo, logo, ba, aspect=aspect)
        tv.render_match_board_b(featured[0], 1, 1, bg, logo, logo, bb, aspect=aspect)
        tv.render_show_closer(featured, logo, bg, closer, aspect=aspect)
        for p in (intro, ba, bb, closer):
            assert Image.open(p).size == expected_size


def test_tv_scripts_contain_no_model_probabilities():
    featured = tv.select_featured_matches([SAMPLE_DOSSIER], None, limit=4)
    s0 = tv.show_intro_script(featured)
    sa = tv.board_a_script(featured[0], 1, 1)
    sb = tv.board_b_script(featured[0], 1)
    sc = tv.show_closer_script(featured)
    assert "eighteen" in s0.lower()
    assert "Eintracht Frankfurt" in sa and "FC Cologne" in sa
    assert "1.23" in sb and "head-to-head" in sb.lower()
    assert "eighteen plus" in sc.lower()
