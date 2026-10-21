"""Unit tests for the daily match breakdown (16:9 YouTube + 9:16 TikTok, one shared voice track)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

import breakdown_script as bs
import match_breakdown as mb
import shortlist_reel as reel

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "reel"


def _team(n, gf, ga, vgf, vga, o15, form):
    return {
        "n": n, "gf": gf, "ga": ga, "fts": 0.1, "venue_n": n // 2, "venue_gf": vgf, "venue_ga": vga,
        "venue_o15": o15, "venue_o25": 0.6, "venue_btts": 0.6,
        "last5": [{"date": f"2026-10-{10 - i:02d}", "venue": "H" if i % 2 else "A", "opp": f"Opp {i}", "gf": g, "ga": a}
                  for i, (g, a) in enumerate(form)],
    }


def dossier(home="Eintracht Frankfurt", away="FC Cologne", country="Germany", league="Bundesliga",
            kickoff="2026-10-16 20:30", label="FC Cologne over 0.5 goals", odds=1.23):
    return {
        "kickoff": kickoff, "country": country, "league": league, "home": home, "away": away,
        "badges": {"home": "enet/1.png", "away": "enet/2.png"},
        "teams": {
            "home": _team(45, 1.6, 2.35, 1.51, 2.07, 0.89, [(0, 6), (2, 2), (3, 1), (1, 4), (3, 3)]),
            "away": _team(38, 1.44, 2.03, 1.11, 2.37, 0.94, [(2, 1), (1, 2), (1, 1), (1, 4), (3, 2)]),
        },
        "h2h": [{"date": "2026-04-05", "home": home, "away": away, "hg": 2, "ag": 2, "league": league},
                {"date": "2025-11-22", "home": away, "away": home, "hg": 3, "ag": 4, "league": league}],
        "h2h_meta": {"n": 2, "avg_goals": 5.5, "o15": 2, "btts": 2},
        "context": {"facts": [
            {"category": "fatigue", "subject": home, "text": "last match 2026-10-10, 6 day(s) before kick-off", "stale": False},
            {"category": "fatigue", "subject": away, "text": "last match 2026-10-11, 5 day(s) before kick-off", "stale": False},
            {"category": "weather", "subject": "stadium", "text": "11°C, rain 0.0 mm/h, wind 7 km/h — normal conditions", "stale": False},
        ]},
        "trends": {"home": {"all": [], "venue": []},
                   "away": {"all": [{"t": f"{away} scored in 19 consecutive matches", "k": 19, "n": 19, "r": 1.0, "kind": "goals", "s": 1.2}],
                            "venue": []}},
        "news": {"home": [], "away": [], "match": [
            {"title": "Eintracht Frankfurt vs FC Cologne - Live Score", "source": "FOX Sports", "when": "2026-10-15 20:00", "bucket": "24h"},
            {"title": "Frankfurt vs Cologne betting preview: prediction, tips", "source": "The Independent", "when": "2026-10-15 10:00", "bucket": "24h"},
            {"title": "Frankfurt striker ruled out of Cologne clash with hamstring injury", "source": "BBC Sport", "when": "2026-10-15 16:00", "bucket": "24h"},
            {"title": "Cologne snatch late win in old fixture", "source": "Goal.com", "when": "2026-10-01 16:00", "bucket": "14d"},
        ]},
        "sels": [{"sel": "AO05", "label": label, "odds": odds, "market": "team_goals"}],
    }


def _featured(n=6):
    leagues = [("Spain", "LaLiga"), ("Italy", "Serie A"), ("Germany", "Bundesliga"), ("France", "Ligue 1"),
               ("Netherlands", "Eredivisie"), ("England", "Championship"), ("Turkiye", "Süper Lig")]
    out = []
    for i in range(n):
        c, lg = leagues[i]
        d = dossier(home=f"Home{i}", away=f"Away{i}", country=c, league=lg, label=f"Home{i} over 0.5 goals")
        d["_best_market"] = {"label": f"Home{i} over 0.5 goals", "odds": 1.2 + i / 100, "sel": "AO05", "market": "team_goals"}
        out.append(d)
    return out


# ------------------------------------------------------------------ selection

def test_select_keeps_today_only_orders_by_league_and_respects_limit():
    ds = [dossier(home=f"H{i}", away=f"A{i}", country=c, league=lg, label=f"H{i} over 0.5 goals", kickoff=ko)
          for i, (c, lg, ko) in enumerate([("France", "Ligue 1", "2026-10-16 20:45"), ("Spain", "LaLiga", "2026-10-16 21:00"),
                                           ("Italy", "Serie A", "2026-10-17 18:00"), ("England", "Championship", "2026-10-16 21:00")])]
    got = mb.select_featured_matches(ds, None, limit=7, day="2026-10-16")
    assert [m["league"] for m in got] == ["LaLiga", "Ligue 1", "Championship"]      # tomorrow's Serie A is out
    assert len(mb.select_featured_matches(ds, None, limit=2, day="2026-10-16")) == 2
    assert all(m["_best_market"]["label"].endswith("over 0.5 goals") for m in got)


def test_select_needs_enough_data_and_a_qualifying_market():
    thin = dossier()
    thin["teams"]["home"]["n"] = 6
    under = dossier(label="Under 2.5 goals")
    assert mb.select_featured_matches([thin, under], None, day="2026-10-16") == []


# ------------------------------------------------------------------ language

def test_headlines_drop_tipster_scores_old_news_and_bare_fixture_names():
    got = mb.reputable_headlines(dossier(), limit=5)
    assert [h["text"] for h in got] == ["Frankfurt striker ruled out of Cologne clash with hamstring injury"]
    assert got[0]["source"].startswith("BBC Sport")


def test_auto_pack_never_advertises_how_it_was_made_and_never_spoils_the_picks():
    ms = _featured(6)
    pack = mb.auto_pack(ms, day="2026-10-16")
    spoken = [pack["intro"], pack["closer"]] + [pm[k] for pm in pack["matches"] for k in ("a", "b", "v")]
    assert not [t for t in spoken if mb.FORBIDDEN_PUBLIC.search(t)]
    intro = pack["intro"].lower()
    assert "eighteen" in intro and "not betting advice" in intro and "sure bet" in intro      # disclaimer read aloud
    assert not re.search(r"over \d|\d\.\d\d|at least once", intro)                           # no picks up front
    lead = re.compile(r"my pick|i'm going with|the one i like", re.I)
    assert all(lead.search(pm["v"]) for pm in pack["matches"])
    assert not any(lead.search(pm["a"] + " " + pm["b"]) for pm in pack["matches"])           # the reveal comes last
    assert not any(re.search(r"at least once|over (one|two) and a half|\d\.\d\d", pm["a"] + " " + pm["b"]) for pm in pack["matches"])
    assert re.search(r"\b(subscribe)\b", pack["closer"]) and "All rights reserved" in pack["closer"]


def test_every_part_names_country_and_league_and_budgets_hold():
    ms = _featured(6)
    pack = mb.auto_pack(ms, day="2026-10-16")
    ba, bb, bv = mb.part_budgets(6)
    for m, pm in zip(ms, pack["matches"]):
        assert bs.league_name(m["league"]) in pm["a"]
        assert len(pm["a"]) <= ba + 90 and len(pm["b"]) <= bb + 110 and len(pm["v"]) <= bv + 90


@pytest.mark.parametrize("n", [3, 5, 6, 7])
def test_budgets_keep_the_show_under_eight_minutes_at_the_house_pace(n):
    ba, bb, bv = mb.part_budgets(n)
    chars = mb.INTRO_CHARS + mb.CLOSER_CHARS + n * (ba + bb + bv)
    slides = 2 + 3 * n
    assert chars / 14.7 + slides * reel.TAIL < mb.MAX_SECONDS


def test_team_to_score_pick_is_spoken_plainly_and_with_a_data_backed_reason():
    d = _featured(1)[0]
    d["home"], d["away"] = "Eintracht Frankfurt", "FC Cologne"
    d["_best_market"] = {"label": "FC Cologne over 0.5 goals", "odds": 1.23}
    txt, why = mb._v_text(d, 400)
    assert "Cologne to score at least once" in txt and "1.23" in txt and "FC Cologne" not in txt
    assert any("19 matches in a row" in w for w in why)


def test_overrides_fill_odds_and_pick_from_the_live_snapshot():
    ms = _featured(2)
    pack = mb.auto_pack(ms, day="2026-10-16")
    ov = {"matches": [{"key": "Home0|Away0", "v": "So, my pick for this one: {pick}, at {odds}. Fine.", "why": ["x"]}]}
    out = mb.apply_overrides(pack, ov, ms)
    assert out["matches"][0]["v"] == "So, my pick for this one: Home0 to score at least once, at 1.20. Fine."
    assert "to score at least once, at 1.21" in out["matches"][1]["v"]          # untouched match keeps its auto text


# ------------------------------------------------------------------ slide timing

def test_slide_timing_comes_from_each_slides_own_words():
    """No voice: a slide lasts as long as its words take to read, so length matches the narrated cut."""
    ms = _featured(5)
    pack = mb.auto_pack(ms, day="2026-10-16")
    slides = mb._slides_for(ms, pack)
    holds = mb._holds(slides)
    assert len(holds) == len(slides) == 2 + 3 * len(ms)
    for s, h in zip(slides, holds):
        assert h >= mb.reel.hold_seconds(0, 0) - 1e-6
        assert h == pytest.approx(mb.reel.frame_hold(h), abs=1e-6)
    assert holds[0] >= mb.reel.INTRO_MIN                     # logo sting keeps its floor
    order = sorted(range(len(slides)), key=lambda i: len(slides[i]["text"]))
    assert holds[order[-1]] >= holds[order[0]]


def test_prepare_records_holds_and_no_audio(monkeypatch, tmp_path):
    """prepare() must not record anything: no wavs, just per-slide seconds."""
    ms = _featured(3)
    monkeypatch.setattr(mb.reel, "fetch_badge", lambda *a, **k: tmp_path / "none.png")
    monkeypatch.setattr(mb, "_gather_photos", lambda *a, **k: [[], [], []])
    (tmp_path / "none.png").write_bytes(b"x")
    prep = mb.prepare(ms, assets=tmp_path, work=tmp_path / "w", day="2026-10-16")
    assert not hasattr(prep, "wavs")
    assert len(prep.holds) == len(prep.slides)
    assert sum(prep.holds) <= mb.MAX_SECONDS
    assert prep.holds == mb._holds(prep.slides)


def test_render_muxes_one_music_bed_over_the_silent_slides(tmp_path, monkeypatch):
    """The finished breakdown is picture + one track: no wavs, no voice, picture copied."""
    try:
        ff = mb.reel._ffmpeg()
    except Exception:  # noqa: BLE001
        pytest.skip("ffmpeg not available")
    from PIL import Image

    assets = tmp_path / "assets"
    assets.mkdir()
    slide_a, slide_b = tmp_path / "a.jpg", tmp_path / "b.jpg"
    Image.new("RGB", (640, 360), (7, 17, 29)).save(slide_a)
    Image.new("RGB", (640, 360), (8, 22, 38)).save(slide_b)
    monkeypatch.setattr(mb.reel, "_ACTIVE_SIZE", (640, 360))
    prep = mb.Prepared(
        matches=[], pack={"matches": []},
        slides=[{"kind": "intro", "i": None, "text": "Short intro."},
                {"kind": "closer", "i": None, "text": "That is the list, take them as singles."}],
        holds=[3.0, 3.0], work=tmp_path / "w", assets=assets, ff=ff,
    )
    for sub in ("slides", "crests", "venues"):
        (prep.work / sub).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mb, "render_slides", lambda *_a, **_k: [slide_a, slide_b])
    monkeypatch.setattr(mb.music, "music_path", lambda _assets: tmp_path / "track.mp3")
    import shutil
    shutil.copy(Path(__file__).resolve().parent.parent / "assets" / "reel" / "under_the_stadium_lights.mp3",
                tmp_path / "track.mp3")

    out = tmp_path / "breakdown.mp4"
    mb.render(prep, out, "16:9")
    assert out.exists() and out.stat().st_size > 1000
    assert abs(mb.reel._probe(out, ff) - 6.0) < 0.6


# ------------------------------------------------------------------ slides

def _assets_for_render(tmp_path: Path):
    crest = tmp_path / "crest.png"
    Image.new("RGBA", (96, 96), (200, 30, 30, 255)).save(crest)
    photo = tmp_path / "photo.jpg"
    Image.new("RGB", (1600, 1000), (30, 90, 40)).save(photo)
    return crest, photo


@pytest.mark.parametrize("aspect,size", [("16:9", (1920, 1080)), ("9:16", (1080, 1920))])
def test_all_slide_types_render_in_both_aspects_without_forbidden_wording(tmp_path, monkeypatch, aspect, size):
    crest, photo = _assets_for_render(tmp_path)
    ms = _featured(6)
    pack = mb.auto_pack(ms, day="2026-10-16")
    pm = pack["matches"][0]
    pm.update({"table": {"home": "8th · 10 pts", "away": "17th · 6 pts"}, "cards": [
        {"team": "Home0", "text": "Out: A Player (injured). Another Player suspended after a red card last week.", "source": "Sports Mole · 14 Oct"},
        {"team": "Away0", "text": "No fresh concerns.", "source": "BBC Sport · 15 Oct"}], "facts": [{"text": "A fact", "source": "BBC Sport"}]})
    ph = [{"path": photo, "credit": "Photo: Jane Doe / CC BY-SA 4.0 / Wikimedia Commons", "stadium": "Test Stadium"}]
    seen: list[str] = []
    real_text = ImageDraw.ImageDraw.text
    monkeypatch.setattr(ImageDraw.ImageDraw, "text", lambda self, xy, text, *a, **k: (seen.append(str(text)), real_text(self, xy, text, *a, **k))[1])
    prev = reel._ACTIVE_SIZE
    reel._ACTIVE_SIZE = reel._resolve_size(aspect)
    try:
        logo, bg = ASSETS / "logo.png", ASSETS / "bg_stadium.jpg"
        out = tmp_path / aspect.replace(":", "x")
        out.mkdir()
        crests = [(crest, crest)] * 6
        photos = [ph] * 6
        mb.render_intro(ms, pack["matches"], logo, bg, out / "i.jpg", crests=crests, photos=photos, day_text="Fri 16 Oct", aspect=aspect)
        intro_text = " ".join(seen)
        mb.render_board_a(ms[0], pm, 1, 6, photo, crest, crest, out / "a.jpg", stadium="Test Stadium", aspect=aspect)
        mb.render_board_b(ms[0], pm, 1, 6, photo, crest, crest, out / "b.jpg", photo=ph[0], aspect=aspect)
        mb.render_verdict(ms[0], pm, 1, 6, photo, crest, crest, out / "v.jpg", aspect=aspect)
        mb.render_closer(ms, pack["matches"], logo, bg, out / "c.jpg", credits_line="Stadium photos via Wikimedia Commons", aspect=aspect)
    finally:
        reel._ACTIVE_SIZE = prev
    for f in ("i", "a", "b", "v", "c"):
        assert Image.open(out / f"{f}.jpg").size == size
    assert not [t for t in seen if mb.FORBIDDEN_PUBLIC.search(t)]
    assert not re.search(r"over 0\.5|\d\.\d\d\b|sportybet", intro_text, re.I)               # nothing about picks on the opening slide
    assert any("MY PICK" in t for t in seen) and any("Photo: Jane Doe" in t for t in seen)


def test_a_missing_photo_never_breaks_a_slide(tmp_path):
    crest, _ = _assets_for_render(tmp_path)
    ms = _featured(1)
    pack = mb.auto_pack(ms, day="2026-10-16")
    prev = reel._ACTIVE_SIZE
    reel._ACTIVE_SIZE = reel._resolve_size("16:9")
    try:
        mb.render_board_b(ms[0], pack["matches"][0], 1, 1, ASSETS / "bg_pitch.jpg", crest, crest, tmp_path / "b.jpg", photo=None, aspect="16:9")
    finally:
        reel._ACTIVE_SIZE = prev
    assert (tmp_path / "b.jpg").exists()
