# deep-analysis articles, telegram shortlist push, leagues diet browser (user rules 2026-10-11)
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import shortlist
import scanner
import leagues


def _fake_profile(name, n, gf, ga, last5, venue_n=4, venue_gf=1.9, venue_ga=0.8):
    return SimpleNamespace(name=name, n=n, gf=gf, ga=ga, last5=last5, venue_n=venue_n,
                           venue_gf=venue_gf, venue_ga=venue_ga)


def _fake_row():
    m = lambda gf, ga: {"gf": gf, "ga": ga}
    return SimpleNamespace(
        home=_fake_profile("Arsenal", 22, 2.1, 0.9, [m(2, 0), m(1, 1), m(3, 1), m(0, 1), m(2, 2)]),
        away=_fake_profile("Chelsea", 19, 1.4, 1.2, [m(1, 0), m(0, 2), m(2, 1), m(1, 1), m(1, 0)]),
        hist={"O25": 0.61}, mod_h=1.8, mod_a=1.1,
        h2h=[{"home": "Arsenal", "away": "Chelsea", "hg": 2, "ag": 1},
             {"home": "Chelsea", "away": "Arsenal", "hg": 0, "ag": 0},
             {"home": "Arsenal", "away": "Chelsea", "hg": 3, "ag": 1}])


PICK = {"home": "Arsenal", "away": "Chelsea", "kickoff": "2026-10-11 17:30", "label": "Arsenal to win",
        "odds": 1.55, "p": 0.71, "bar": 0.6, "p_sb": 0.62, "edge_pp": 9.0, "ev": 0.10,
        "quality": "High", "confidence": "High", "risk": "one-in-3 miss rate"}


def test_match_article_uses_real_numbers_and_na_never_invents():
    a = shortlist.match_article(_fake_row(), PICK)
    assert a["id"] == "Arsenal|Chelsea|2026-10-11 17:30"
    assert "22 tracked matches" in a["paras"][0] and "WDWLD" in a["paras"][0].replace(" ", "")
    assert "71%" in a["paras"][1] and "60%" in a["paras"][1] and "9.0 pp" in a["paras"][1]
    assert "2\u20131\u20130" in a["paras"][2].replace(" ", "")  # h2h W-D-L for Arsenal
    assert "never a gate" in a["paras"][1]
    # missing pieces degrade to N/A instead of being invented
    row = _fake_row()
    row.h2h = []
    row.hist = {}
    a2 = shortlist.match_article(row, {**PICK, "p_sb": None, "edge_pp": None, "ev": None})
    assert "No verified price view" in a2["paras"][1]
    assert "Head to head" not in a2["paras"][2]


def test_build_article_maps_rows_and_intro():
    row = _fake_row()
    row.fx = {"country": "England", "home": "Arsenal", "away": "Chelsea"}
    from collections import Counter
    pick = {**PICK, "country": "England", "league": "Premier League"}
    art = shortlist.build_article([row], [pick], Counter({"goals": 1}), datetime(2026, 10, 11, 12, 0))
    assert art and len(art["items"]) == 1 and "1 selections" in art["intro"]
    assert art["items"][0]["stats"]["p"] == 0.71


def test_telegram_shortlist_sends_each_pick_once_per_day(monkeypatch, tmp_path):
    sent = []
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    monkeypatch.setattr(scanner, "send_telegram", lambda text: sent.append(text))
    monkeypatch.setattr(scanner, "DATA_DIR", tmp_path)
    now = datetime(2026, 10, 11, 9, 0)
    board = {"primary": [dict(PICK, key=("2026-10-11", "England", "Arsenal", "Chelsea"), country="England",
                                league="Premier League")]}
    scanner.telegram_shortlist(board, now)
    assert len(sent) == 1 and "Arsenal v Chelsea" in sent[0]
    # second run, same day: deduped, nothing sent
    scanner.telegram_shortlist(board, now)
    assert len(sent) == 1
    state = json.loads((tmp_path / "app" / "telegram_state.json").read_text())
    assert state["day"] == "2026-10-11" and len(state["sent"]) == 1


def test_telegram_shortlist_silent_without_config(monkeypatch, tmp_path):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(scanner, "DATA_DIR", tmp_path)
    scanner.telegram_shortlist({"primary": [dict(PICK, key=("d", "c", "h", "a"))]},
                               datetime(2026, 10, 11, 9, 0))
    assert not (tmp_path / "app" / "telegram_state.json").exists()  # unconfigured: nothing recorded, nothing sent


def test_leagues_build_honours_the_diet_allow(tmp_path):
    day = "20261011000000"
    for country, slugf in (("Japan", "japan__j1.json"), ("England", "england__premier-league.json")):
        (tmp_path / slugf).write_text(json.dumps(
            {"key": slugf[:-5], "country": country, "league": "X", "fetched": "2026-10-11 06:00",
             "events": {"1": [day, None, "A", None, "B", 2, 1, 1, 0], "2": [day, None, "C", None, "D", 0, 0, 0, 0]}}),
            encoding="utf-8")
    out = tmp_path / "out"
    n = leagues.build(tmp_path, datetime(2026, 10, 11, 12, 0), out, allow=lambda c, l: c == "England")
    idx = json.loads((out / "index.json").read_text())
    assert n == 1 and [e["country"] for e in idx["leagues"]] == ["England"]
    assert not (out / "japan__j1.json").exists()       # stale detail file pruned
    assert (out / "england__premier-league.json").exists()
