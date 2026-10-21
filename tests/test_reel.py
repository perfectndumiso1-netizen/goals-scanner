"""Reel timing: one voice clip per slide, no music, goals/corners/bookings only."""
from __future__ import annotations

from pathlib import Path

import pytest

import shortlist_reel as reel


def test_reel_picks_carry_only_over15_team_goals_corners_and_bookings():
    picks = [
        {"label": "Over 1.5 goals", "sel": "O15", "home": "A", "away": "Z", "kickoff": "1", "p": 0.82},
        {"label": "Under 2.5 cards", "sel": "KU25", "home": "B", "away": "Z", "kickoff": "2", "p": 0.80},
        {"label": "Home or draw", "sel": "1X", "home": "C", "away": "Z", "kickoff": "3", "p": 0.80},
        {"label": "Home win", "sel": "H", "home": "E", "away": "Z", "kickoff": "4", "p": 0.70},
        {"label": "BTTS", "sel": "BTTS", "home": "F", "away": "Z", "kickoff": "5", "p": 0.78},
        {"label": "Over 2.5 goals", "sel": "O25", "home": "G", "away": "Z", "kickoff": "6", "p": 0.60},
        {"label": "Over 3.5 cards", "sel": "KO35", "home": "H", "away": "Z", "kickoff": "7", "p": 0.71},
        {"label": "Over 9.5 corners", "sel": "CO95", "home": "I", "away": "Z", "kickoff": "8", "p": 0.74},
        {"label": "Home over 0.5 goals", "sel": "HO05", "home": "J", "away": "Z", "kickoff": "9", "p": 0.90},
    ] + [{"label": "Over 1.5 goals", "sel": "O15", "home": f"X{i}", "away": "Z", "kickoff": str(10 + i), "p": 0.70}
         for i in range(12)]
    out = reel.reel_picks(picks)
    homes = [p["home"] for p in out]
    assert all(reel.is_reel_market(p) for p in out)
    assert all((p.get("p") or 0) >= reel.REEL_MIN_P for p in out)
    # no BTTS, no Over 2.5, no 1X2, no match result, no under — never in the video
    for gone in ("B", "C", "E", "F", "G"):
        assert gone not in homes, gone
    assert {"A", "I", "J"} <= set(homes)
    assert len(out) == reel.MAX_PICKS
    assert reel.MAX_PICKS >= 12
    skipped = reel.reel_picks(picks, used={("A", "Z"), ("I", "Z")})
    assert "A" not in [p["home"] for p in skipped] and "I" not in [p["home"] for p in skipped]


def test_hold_never_cuts_speech_and_intro_is_five_seconds():
    assert reel.hold_seconds(0, 3.0) == 5.0
    assert reel.hold_seconds(0, 6.2) == 6.2 + reel.TAIL
    assert reel.hold_seconds(1, 9.81) == 9.81 + reel.TAIL
    assert reel.hold_seconds(7, 12.4) == 12.4 + reel.TAIL


def test_frame_hold_rounds_up_so_video_is_never_shorter_than_voice():
    assert reel.frame_hold(5.0) == 5.0
    # 9.81 + 0.70 = 10.51; 10.51 * 30 = 315.3 frames → 316/30
    h = reel.frame_hold(9.81 + reel.TAIL)
    assert h >= 9.81 + reel.TAIL
    assert abs(h * reel.FPS - round(h * reel.FPS)) < 1e-6


def test_pick_script_has_competition_and_a_reason():
    s = reel.pick_script({
        "home": "Lyon", "away": "Crystal Palace", "label": "Lyon over 0.5 goals",
        "odds": 1.2, "p": 0.91, "kickoff": "2026-10-15 18:45",
        "country": "Europa League", "league": "League Stage",
    })
    assert "Europa League" in s and "league stage" in s              # country / competition on every pick
    assert "Lyon" in s and "Crystal Palace" in s
    assert "Lyon to score at least once" in s and "1.20" in s
    assert "quarter to seven tonight" in s                           # kick-off, said the way people say it
    assert "around nine in ten" in s                                 # the reason, not a stats table
    assert "percent" not in s.lower() and "%" not in s
    assert "versus" not in s.lower() and "Kick-off," not in s       # no table-reading


def test_pick_reason_is_built_from_the_picks_own_evidence():
    pick = {
        "home": "Villarreal", "away": "Getafe", "label": "Over 1.5 goals", "market": "goals",
        "odds": 1.85, "p": 0.74, "kickoff": "2026-10-20 18:45", "country": "Spain", "league": "LaLiga",
        "form_h": "WWDWL", "form_a": "LDLWW", "support": ["model xG 1.84–1.12", "both teams' historical O25 rate 62%"],
    }
    said = reel.pick_reason_script(pick)
    assert "about two in three" in said
    assert "Villarreal" in said and "getting on for two" in said
    assert "have won three of their last five" in said
    screen = reel.pick_reason_bits(pick)
    assert any("74%" in b for b in screen) and any("1.84" in b for b in screen)
    # Nothing is invented when the evidence is absent
    bare = reel.pick_reason_script({"home": "A", "away": "B", "p": 0.7})
    assert bare and "model" in bare.lower() and "xG" not in bare


def test_pick_scripts_vary_from_one_pick_to_the_next():
    picks = [{"home": f"H{i}", "away": f"A{i}", "label": "Over 1.5 goals", "odds": 1.2, "kickoff": "2026-10-15 18:45",
              "country": "Spain", "league": "LaLiga"} for i in range(5)]
    lines = [reel.pick_script(p, i, 5) for i, p in enumerate(picks, 1)]
    openers = [x.split(" Spain")[0] for x in lines]
    assert all(a != b for a, b in zip(openers, openers[1:]))
    assert lines[0].startswith(("First up", "To start", "Let's begin")) and lines[-1].startswith(("And finally", "Last one", "And to finish"))


def test_disclaimer_and_closer_scripts():
    d = reel.DISCLAIMER_SCRIPT.lower()
    assert "eighteen" in d and "sure bet" in d and "afford to lose" in d and "not betting advice" in d
    assert "like" in reel.CLOSER_SCRIPT.lower()
    assert "subscribe" in reel.CLOSER_SCRIPT.lower()
    assert "All rights reserved" in reel.CLOSER_SCRIPT


def test_raw_shortlist_key_resolves_both_club_badges():
    fixture = {
        "id": "fixture-id", "date": "2026-10-15", "country": "USA",
        "home": "CF Montreal", "away": "Atlanta United",
        "badges": {"home": "team/cf-montreal.png", "away": "team/atlanta.png"},
    }
    pick = {"key": ("2026-10-15", "USA", "CF Montreal", "Atlanta United"),
            "home": "CF Montreal", "away": "Atlanta United"}
    assert reel.fixture_for_pick(pick, [fixture]) == fixture
    assert reel.badges_for_pick(pick, [fixture]) == fixture["badges"]


def test_espeak_fallback_uses_male_voice(monkeypatch, tmp_path):
    captured = {}

    monkeypatch.setenv("PLAYREPORT_ALLOW_ESPEAK", "1")
    monkeypatch.delenv("EDGE_TTS_PYTHON", raising=False)
    monkeypatch.delenv("PIPER_MODEL_PATH", raising=False)
    monkeypatch.delenv("PIPER_CONFIG_PATH", raising=False)

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        with open(cmd[cmd.index("-w") + 1], "wb") as wav:
            wav.write(b"RIFF test")
        return type("Result", (), {"returncode": 0, "stdout": ""})()

    monkeypatch.setattr(reel.shutil, "which", lambda _name: "/usr/bin/espeak-ng")
    monkeypatch.setattr(reel.subprocess, "run", fake_run)
    reel.synthesize_speech("Good morning.", tmp_path / "voice.wav")
    cmd = captured["cmd"]
    assert cmd[cmd.index("-v") + 1] == "en-gb"
    assert "f3" not in cmd[cmd.index("-v") + 1]
    assert cmd[cmd.index("-s") + 1] == str(reel.ESPEAK_SPEED)
    assert cmd[cmd.index("-p") + 1] == str(reel.ESPEAK_PITCH)
    assert reel.ESPEAK_PITCH <= 50


def test_a_robotic_voice_is_never_published_by_accident(monkeypatch, tmp_path):
    """No neural voice and no explicit opt-in: the build fails loudly instead of shipping eSpeak."""
    monkeypatch.delenv("PLAYREPORT_ALLOW_ESPEAK", raising=False)
    monkeypatch.delenv("EDGE_TTS_PYTHON", raising=False)
    monkeypatch.delenv("PIPER_MODEL_PATH", raising=False)
    monkeypatch.delenv("PIPER_CONFIG_PATH", raising=False)
    monkeypatch.setattr(reel.shutil, "which", lambda _name: "/usr/bin/espeak-ng")
    with pytest.raises(reel.VoiceUnavailable):
        reel.synthesize_speech("Good morning.", tmp_path / "voice.wav")


def test_one_voice_and_one_pacing_seed_for_every_slide(monkeypatch, tmp_path):
    """Every clip in every video of the run uses the same voice and the same pacing seed."""
    reel.set_voice_seed()
    seed = reel.voice_identity()["seed"]
    reel.set_voice_seed(seed)
    assert reel.voice_identity()["seed"] == seed

    seen = []

    def fake_sentence(sentence, edge_py, dest, voice=None):
        seen.append(voice)
        import numpy as np
        import voice_polish as vp
        vp.write_wav(dest, np.zeros(24000, dtype=np.float32) + 0.01, vp.SR)
        return True

    monkeypatch.setenv("EDGE_TTS_PYTHON", str(Path(__file__)))
    monkeypatch.setattr(reel, "_edge_sentence", fake_sentence)
    monkeypatch.setattr(reel, "_ffmpeg", lambda: "/usr/bin/ffmpeg")
    assert reel._edge_voice_candidates()[0] == reel.EDGE_TTS_VOICE
    assert len(set(reel._edge_voice_candidates())) == len(reel._edge_voice_candidates())
    assert "en-GB-RyanNeural" in reel.EDGE_TTS_VOICES      # the CI voice stays first, never eSpeak


def test_piper_neural_voice_is_used_when_configured(monkeypatch, tmp_path):
    from pathlib import Path

    model = tmp_path / "voice.onnx"
    config = tmp_path / "voice.onnx.json"
    model.write_bytes(b"model")
    config.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("EDGE_TTS_PYTHON", raising=False)
    monkeypatch.setenv("PIPER_PYTHON", "/tmp/piper-venv/bin/python")
    monkeypatch.setenv("PIPER_MODEL_PATH", str(model))
    monkeypatch.setenv("PIPER_CONFIG_PATH", str(config))
    captured = {}

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        Path(cmd[cmd.index("-f") + 1]).write_bytes(b"wav")
        return type("Result", (), {"returncode": 0, "stdout": ""})()

    monkeypatch.setattr(reel.subprocess, "run", fake_run)
    out = tmp_path / "neural.wav"
    reel.synthesize_speech("Good morning.", out)

    cmd = captured["cmd"]
    assert cmd[0] == "/tmp/piper-venv/bin/python"
    assert cmd[cmd.index("-m", 2) + 1] == str(model)
    assert cmd[cmd.index("-c") + 1] == str(config)
    assert cmd[cmd.index("-f") + 1] == str(out)
    assert cmd[-2:] == ["--", "Good morning."]
    assert out.exists()


def test_short_reel_does_not_add_trailing_silence(monkeypatch, tmp_path):
    from pathlib import Path

    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "logo.png").write_bytes(b"logo")
    for name in ("bg_stadium.jpg", "bg_pitch.jpg", "bg_lights.jpg"):
        (assets / name).write_bytes(b"background")

    def touch_render(*args):
        args[-1].parent.mkdir(parents=True, exist_ok=True)
        args[-1].write_bytes(b"image")

    monkeypatch.setattr(reel, "render_intro", touch_render)
    monkeypatch.setattr(reel, "render_disclaimer", touch_render)
    monkeypatch.setattr(reel, "render_pick", touch_render)
    monkeypatch.setattr(reel, "render_closer", touch_render)
    monkeypatch.setattr(reel, "synthesize_speech", lambda _text, wav: wav.write_bytes(b"audio"))
    monkeypatch.setattr(reel, "_probe", lambda _path, _ff: 1.0)
    padded_calls = []

    def pad(src, dest, _duration, _ff):
        assert src != dest, "FFmpeg must never pad a WAV file in place"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"audio")
        padded_calls.append((src, dest))

    monkeypatch.setattr(reel, "pad_audio", pad)
    video_holds = []

    def touch_still(_img, dest, _duration, _ff):
        video_holds.append(_duration)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"video")

    monkeypatch.setattr(reel, "still_clip", touch_still)

    def fake_run(cmd, _label):
        Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(cmd[-1]).write_bytes(b"video")

    monkeypatch.setattr(reel, "_run", fake_run)
    monkeypatch.setattr(reel, "_ffmpeg", lambda: "/usr/bin/ffmpeg")
    outfile = tmp_path / "short-reel.mp4"
    reel.build(
        [{"home": "Home FC", "away": "Away FC", "label": "Over 1.5 goals", "sel": "O15", "odds": 1.5, "p": 0.7, "kickoff": "2026-10-19 18:00"}],
        outfile,
        assets=assets,
        work=tmp_path / "work",
        fixtures=[],
    )

    assert outfile.exists()
    assert not any(dest.name == "a-final-padded.wav" for _, dest in padded_calls)
    # intro 5s + disclaimer/pick/closer each 1s speech + 0.70 tail
    expected = reel.frame_hold(5.0) + 3 * reel.frame_hold(1.0 + reel.TAIL)
    assert abs(sum(video_holds) - expected) < 0.01
    assert len(video_holds) == 4


def test_workflows_match_actions_lock_and_scan_keeps_male_ci_voice():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    wf_dir = root / ".github" / "workflows"
    lock_text = (wf_dir / "actions.lock").read_text(encoding="utf-8")

    # Parse workflow action lists from actions.lock without requiring pyyaml in runtime deps
    locked: dict[str, set[str]] = {}
    current_wf = None
    in_workflows = False
    for line in lock_text.splitlines():
        if line.startswith("workflows:"):
            in_workflows = True
            continue
        if in_workflows and not line.startswith(" "):
            break
        m_wf = re.match(r"^\s{4}'([^']+)':\s*$", line)
        if m_wf:
            current_wf = m_wf.group(1)
            locked[current_wf] = set()
            continue
        m_dep = re.match(r"^\s{8}-\s*'([^']+)'\s*$", line)
        if m_dep and current_wf:
            locked[current_wf].add(m_dep.group(1))

    for yml in sorted(wf_dir.glob("*.yml")):
        rel = f".github/workflows/{yml.name}"
        assert rel in locked, f"{rel} missing from actions.lock"
        text = yml.read_text(encoding="utf-8")
        used = set()
        for raw in re.findall(r"^\s*(?:-\s*)?uses:\s*([^\s#]+)", text, flags=re.MULTILINE):
            # Normalize sub-action paths like gradle/actions/setup-gradle@v3.5.0 -> gradle/actions@v3.5.0
            repo_part, _, ref_part = raw.partition("@")
            parts = repo_part.split("/")
            norm = f"{parts[0]}/{parts[1]}@{ref_part}" if len(parts) >= 2 and ref_part else raw
            used.add(norm)
        assert used == locked[rel], f"{rel} uses {sorted(used)} != actions.lock {sorted(locked[rel])}"

    scan_text = (wf_dir / "scan.yml").read_text(encoding="utf-8")
    assert "en_US-amy-medium" not in scan_text
    assert "en_GB-alan-medium.onnx" in scan_text
    assert "en-GB-RyanNeural" in scan_text


def test_widescreen_16x9_dimensions_and_slide_renders(tmp_path):
    from PIL import Image

    assert (reel.W, reel.H) == (1920, 1080)
    assert reel.W * 9 == reel.H * 16

    logo = tmp_path / "logo.png"
    bg = tmp_path / "bg.jpg"
    Image.new("RGBA", (256, 256), (0, 200, 111, 255)).save(logo)
    Image.new("RGB", (640, 360), (7, 17, 29)).save(bg)

    intro = tmp_path / "intro.jpg"
    disc = tmp_path / "disclaimer.jpg"
    res = tmp_path / "results.jpg"
    pick = tmp_path / "pick.jpg"
    closer = tmp_path / "closer.jpg"

    reel.render_intro(logo, bg, intro)
    reel.render_disclaimer(logo, bg, disc)
    reel.render_results(
        [{"home": "Arsenal", "away": "Chelsea", "country": "England", "league": "Premier League",
          "label": "Over 1.5 goals", "odds": 1.24, "result": "hit", "score": "2-1"}],
        logo, bg, res, day_label="2026-10-14",
    )
    reel.render_pick(
        {"home": "Lyon", "away": "Crystal Palace", "country": "Europa League", "league": "League Stage",
         "label": "Over 1.5 goals", "odds": 1.25, "kickoff": "2026-10-15 18:45", "form_h": "WWDWL", "form_a": "WDWLW"},
        1, 3, bg, logo, logo, pick,
    )
    reel.render_closer(logo, bg, closer)

    for p in (intro, disc, res, pick, closer):
        with Image.open(p) as im:
            assert im.size == (1920, 1080)


def test_yesterday_results_recap_starts_before_todays_selections(monkeypatch, tmp_path):
    from pathlib import Path

    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "logo.png").write_bytes(b"logo")
    for name in ("bg_stadium.jpg", "bg_pitch.jpg", "bg_lights.jpg"):
        (assets / name).write_bytes(b"background")

    slide_order = []

    def rec_render(tag):
        def _fn(*args, **_kwargs):
            slide_order.append(tag)
            dest = args[-1]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"image")
        return _fn

    monkeypatch.setattr(reel, "render_intro", rec_render("intro"))
    monkeypatch.setattr(reel, "render_disclaimer", rec_render("disclaimer"))
    monkeypatch.setattr(reel, "render_results", rec_render("results"))
    monkeypatch.setattr(reel, "render_pick", rec_render("pick"))
    monkeypatch.setattr(reel, "render_closer", rec_render("closer"))

    spoken_scripts = []
    monkeypatch.setattr(reel, "synthesize_speech", lambda text, wav: (spoken_scripts.append(text), wav.write_bytes(b"audio")))
    monkeypatch.setattr(reel, "_probe", lambda _path, _ff: 1.0)
    monkeypatch.setattr(reel, "pad_audio", lambda _src, dest, _dur, _ff: dest.write_bytes(b"audio"))
    monkeypatch.setattr(reel, "still_clip", lambda _img, dest, _dur, _ff: dest.write_bytes(b"video"))
    monkeypatch.setattr(reel, "_run", lambda cmd, _label: Path(cmd[-1]).write_bytes(b"video"))
    monkeypatch.setattr(reel, "_ffmpeg", lambda: "/usr/bin/ffmpeg")

    yres = {
        "day": "2026-10-14",
        "items": [
            {"home": "Flamengo", "away": "Botafogo", "sel": "O15", "label": "Over 1.5 goals", "market": "goals", "odds": 1.28, "result": "hit", "score": "2-1"},
            {"home": "Santos", "away": "Corinthians", "sel": "CO95", "label": "Over 9.5 corners", "market": "corners", "odds": 1.85, "result": "miss", "score": "7 corners"},
        ],
    }
    outfile = tmp_path / "briefing-16x9.mp4"
    reel.build(
        [{"home": "Lyon", "away": "Crystal Palace", "sel": "O15", "label": "Over 1.5 goals", "odds": 1.25, "kickoff": "2026-10-15 18:45", "p": 0.72}],
        outfile,
        assets=assets,
        work=tmp_path / "work",
        fixtures=[],
        yesterday_results=yres,
    )

    assert slide_order == ["intro", "disclaimer", "results", "pick", "closer"]
    assert len(spoken_scripts) == 5
    assert "look back at yesterday" in spoken_scripts[2] and "We went one from two." in spoken_scripts[2]
    assert "Flamengo against Botafogo" in spoken_scripts[2] and "two-one" in spoken_scripts[2]
    assert "Now, today's shortlist." in spoken_scripts[2]
    assert "percent" not in spoken_scripts[2].lower() and "%" not in spoken_scripts[2]
    assert "Lyon" in spoken_scripts[3] and "Crystal Palace" in spoken_scripts[3]


def test_shortlist_yesterday_results_extraction():
    from datetime import datetime
    import pandas as pd
    import shortlist

    df = pd.DataFrame([
        {"day": "2026-10-14", "kickoff": "2026-10-14 20:00", "country": "Brazil", "league": "Serie A",
         "home": "Flamengo", "away": "Botafogo", "sel": "O15", "label": "Over 1.5 goals", "market": "goals",
         "odds": "1.28", "status": "primary", "result": "hit", "score": "2-1"},
        {"day": "2026-10-14", "kickoff": "2026-10-14 21:00", "country": "Brazil", "league": "Serie A",
         "home": "Santos", "away": "Corinthians", "sel": "CO85", "label": "Over 8.5 corners", "market": "corners",
         "odds": "1.35", "status": "primary", "result": "miss", "score": "0-0"},
    ])
    res = shortlist.yesterday_results(df, datetime(2026, 10, 15, 7, 0))
    assert res["day"] == "2026-10-14"
    assert res["total"] == 2
    assert res["settled"] == 2
    assert res["hits"] == 1
    assert res["misses"] == 1
    assert res["hit_rate"] == 0.5
    assert len(res["items"]) == 2


def test_yesterday_results_strictly_matches_yesterdays_video_picks():
    from datetime import datetime
    import pandas as pd
    import scanner
    import shortlist

    # Simulate 2026-10-15 ledger with early-morning MLS rows (not in video) + the 7 UEFA video rows + trailing rows
    rows = [
        {"day": "2026-10-15", "kickoff": "2026-10-15 02:30", "country": "USA", "league": "MLS",
         "home": "St. Louis City", "away": "Vancouver Whitecaps", "sel": "O15", "label": "Over 1.5 goals",
         "market": "goals", "odds": "1.16", "status": "primary", "result": "miss", "score": "0-0"},
        {"day": "2026-10-15", "kickoff": "2026-10-15 02:30", "country": "USA", "league": "MLS",
         "home": "FC Dallas", "away": "Seattle Sounders FC", "sel": "HO05", "label": "FC Dallas over 0.5 goals",
         "market": "team_goals", "odds": "1.16", "status": "primary", "result": "hit", "score": "1-0"},
        {"day": "2026-10-15", "kickoff": "2026-10-15 01:30", "country": "USA", "league": "MLS",
         "home": "CF Montreal", "away": "Atlanta United", "sel": "HO05", "label": "CF Montreal over 0.5 goals",
         "market": "team_goals", "odds": "1.20", "status": "primary", "result": "miss", "score": "0-3"},
        {"day": "2026-10-15", "kickoff": "2026-10-15 21:00", "country": "Conference League", "league": "League Stage",
         "home": "Hearts", "away": "FC Nordsjaelland", "sel": "HO05", "label": "Hearts over 0.5 goals",
         "market": "team_goals", "odds": "1.25", "status": "primary", "result": "hit", "score": "1-1"},
        {"day": "2026-10-15", "kickoff": "2026-10-15 18:45", "country": "Europa League", "league": "League Stage",
         "home": "Lyon", "away": "Crystal Palace", "sel": "HO05", "label": "Lyon over 0.5 goals",
         "market": "team_goals", "odds": "1.20", "status": "primary", "result": "hit", "score": "3-2"},
        {"day": "2026-10-15", "kickoff": "2026-10-15 18:45", "country": "Europa League", "league": "League Stage",
         "home": "Union St.Gilloise", "away": "Real Sociedad", "sel": "O15", "label": "Over 1.5 goals",
         "market": "goals", "odds": "1.21", "status": "primary", "result": "hit", "score": "1-1"},
        {"day": "2026-10-15", "kickoff": "2026-10-15 21:00", "country": "Europa League", "league": "League Stage",
         "home": "Ferencvaros", "away": "Viktoria Plzen", "sel": "HO05", "label": "Ferencvaros over 0.5 goals",
         "market": "team_goals", "odds": "1.18", "status": "primary", "result": "hit", "score": "2-1"},
        {"day": "2026-10-15", "kickoff": "2026-10-15 18:45", "country": "Conference League", "league": "League Stage",
         "home": "Riga FC", "away": "Kairat Almaty", "sel": "HO05", "label": "Riga FC over 0.5 goals",
         "market": "team_goals", "odds": "1.23", "status": "primary", "result": "hit", "score": "1-1"},
        {"day": "2026-10-15", "kickoff": "2026-10-15 18:45", "country": "Europa League", "league": "League Stage",
         "home": "FC Salzburg", "away": "AC Milan", "sel": "HO05", "label": "FC Salzburg over 0.5 goals",
         "market": "team_goals", "odds": "1.31", "status": "primary", "result": "miss", "score": "0-4"},
        {"day": "2026-10-15", "kickoff": "2026-10-15 18:45", "country": "Conference League", "league": "League Stage",
         "home": "PFC CSKA Sofia", "away": "AS Monaco", "sel": "O15", "label": "Over 1.5 goals",
         "market": "goals", "odds": "1.22", "status": "primary", "result": "hit", "score": "1-2"},
        {"day": "2026-10-15", "kickoff": "2026-10-15 18:45", "country": "Europa League", "league": "League Stage",
         "home": "Sparta Prague", "away": "Lillestroem", "sel": "O15", "label": "Over 1.5 goals",
         "market": "goals", "odds": "1.18", "status": "primary", "result": "hit", "score": "1-1"},
    ]
    df = pd.DataFrame(rows)
    res = shortlist.yesterday_results(df, datetime(2026, 10, 16, 6, 0))
    assert res["day"] == "2026-10-15"
    assert [x["home"] for x in res["items"]] == [
        "Hearts", "Lyon", "Union St.Gilloise", "Ferencvaros", "Riga FC", "FC Salzburg", "PFC CSKA Sofia"
    ]
    assert res["total"] == 7
    assert res["settled"] == 7
    assert res["hits"] == 6
    assert res["misses"] == 1

    # Also verify multi-video day merging in record_briefing_picks
    hist = scanner.record_briefing_picks({}, "2026-10-16", [{"home": "A", "away": "B", "sel": "O15"}])
    hist = scanner.record_briefing_picks(hist, "2026-10-16", [
        {"home": "A", "away": "B", "sel": "O15"},
        {"home": "C", "away": "D", "sel": "HO05"},
    ])
    assert hist["2026-10-16"] == [
        {"home": "A", "away": "B", "sel": "O15"},
        {"home": "C", "away": "D", "sel": "HO05"},
    ]


def test_spoken_kickoff_and_spoken_text_naturalness():
    assert reel.spoken_kickoff({"kickoff": "2026-10-16 18:45"}) == "6:45 PM"
    assert reel.spoken_kickoff({"kickoff": "2026-10-16 20:45"}) == "8:45 PM"
    assert reel.spoken_kickoff({"kickoff": "2026-10-16 21:00"}) == "9 PM"
    clean = reel.spoken_text(
        "Union St.Gilloise versus Real Sociedad, Over 2.5 goals, won, 1 to 1. "
        "Turkiye, Süper Lig. Kick-off, 7 PM."
    )
    assert "Union Saint Gilloise" in clean
    assert "landed, finishing 1 to 1." in clean
    assert "Turkey, Super Lig." in clean
    assert "Kick-off at 7 PM." in clean


def test_dual_resolutions_16x9_and_9x16_share_single_consistent_voice(monkeypatch, tmp_path):
    from pathlib import Path
    from PIL import Image

    logo = tmp_path / "logo.png"
    bg = tmp_path / "bg.jpg"
    Image.new("RGBA", (256, 256), (0, 200, 111, 255)).save(logo)
    Image.new("RGB", (640, 360), (7, 17, 29)).save(bg)

    # Verify 9:16 (1080x1920) vertical reel slide dimensions
    intro9 = tmp_path / "intro9.jpg"
    disc9 = tmp_path / "disc9.jpg"
    res9 = tmp_path / "res9.jpg"
    pick9 = tmp_path / "pick9.jpg"
    closer9 = tmp_path / "closer9.jpg"
    reel.render_intro(logo, bg, intro9, aspect="9:16")
    reel.render_disclaimer(logo, bg, disc9, aspect="9:16")
    reel.render_results(
        [{"home": "Hearts", "away": "FC Nordsjaelland", "country": "Conference League", "league": "League Stage",
          "label": "Hearts over 0.5 goals", "odds": 1.25, "result": "hit", "score": "1-1"}],
        logo, bg, res9, day_label="2026-10-15", aspect="9:16",
    )
    reel.render_pick(
        {"home": "Deportivo A Coruna", "away": "Levante", "country": "Spain", "league": "LaLiga",
         "label": "Deportivo A Coruna over 0.5 goals", "odds": 1.24, "kickoff": "2026-10-16 21:00",
         "form_h": "LDLDW", "form_a": "DLLDW"},
        1, 7, bg, logo, logo, pick9, aspect="9:16",
    )
    reel.render_closer(logo, bg, closer9, aspect="9:16")
    for p in (intro9, disc9, res9, pick9, closer9):
        with Image.open(p) as im:
            assert im.size == (1080, 1920)

    # Verify build_both synthesizes speech ONCE and reuses the exact audio for the 9:16 reel
    assets = tmp_path / "assets"
    assets.mkdir()
    Image.new("RGBA", (256, 256), (0, 200, 111, 255)).save(assets / "logo.png")
    for name in ("bg_stadium.jpg", "bg_pitch.jpg", "bg_lights.jpg"):
        Image.new("RGB", (640, 360), (7, 17, 29)).save(assets / name)

    synth_calls = []
    monkeypatch.setattr(reel, "synthesize_speech", lambda text, wav: (synth_calls.append(text), wav.write_bytes(b"RIFFvoice")))
    monkeypatch.setattr(reel, "_probe", lambda _path, _ff: 1.0)
    monkeypatch.setattr(reel, "pad_audio", lambda _src, dest, _dur, _ff: dest.write_bytes(b"audio"))
    monkeypatch.setattr(reel, "still_clip", lambda _img, dest, _dur, _ff: dest.write_bytes(b"video"))
    monkeypatch.setattr(reel, "_run", lambda cmd, _label: Path(cmd[-1]).write_bytes(b"out"))
    monkeypatch.setattr(reel, "_ffmpeg", lambda: "/usr/bin/ffmpeg")

    out16 = tmp_path / "out-16x9.mp4"
    out9 = tmp_path / "out-9x16.mp4"
    reel.build_both(
        [{"home": "Lyon", "away": "Crystal Palace", "sel": "O15", "label": "Over 1.5 goals", "odds": 1.20, "kickoff": "2026-10-15 18:45", "p": 0.72}],
        out16,
        out9,
        assets=assets,
        work=tmp_path / "dual_work",
        fixtures=[],
    )
    assert out16.exists() and out9.exists()
    # Intro + Disclaimer + 1 Pick + Closer = 4 slides; synthesized ONCE for 16:9 and reused for 9:16
    assert len(synth_calls) == 4






def _capture_build(monkeypatch, tmp_path, picks, *, yesterday=None, recap=True, name="b.mp4"):
    """Run build() with fakes and return (slide order, spoken texts, recap rows per slide)."""
    assets = tmp_path / "assets"
    assets.mkdir(exist_ok=True)
    (assets / "logo.png").write_bytes(b"logo")
    for bg in ("bg_stadium.jpg", "bg_pitch.jpg", "bg_lights.jpg"):
        (assets / bg).write_bytes(b"background")

    order, texts, recap_pages = [], [], []

    def rec(tag):
        def _fn(*args, **kwargs):
            dest = args[-1]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"image")
            order.append(tag)
            if tag == "results":
                recap_pages.append(list(args[0]))
        return _fn

    monkeypatch.setattr(reel, "render_intro", rec("intro"))
    monkeypatch.setattr(reel, "render_disclaimer", rec("disclaimer"))
    monkeypatch.setattr(reel, "render_results", rec("results"))
    monkeypatch.setattr(reel, "render_pick", rec("pick"))
    monkeypatch.setattr(reel, "render_closer", rec("closer"))
    monkeypatch.setattr(reel, "synthesize_speech", lambda text, wav: (texts.append(text), wav.write_bytes(b"audio")))
    monkeypatch.setattr(reel, "_probe", lambda _path, _ff: 1.0)
    monkeypatch.setattr(reel, "pad_audio", lambda _src, dest, _dur, _ff: dest.write_bytes(b"audio"))
    monkeypatch.setattr(reel, "still_clip", lambda _img, dest, _dur, _ff: dest.write_bytes(b"video"))
    monkeypatch.setattr(reel, "_run", lambda cmd, _label: Path(cmd[-1]).write_bytes(b"video"))
    monkeypatch.setattr(reel, "_ffmpeg", lambda: "/usr/bin/ffmpeg")
    out = tmp_path / name
    reel.build(picks, out, assets=assets, work=tmp_path / f"work-{name}", fixtures=[],
               yesterday_results=yesterday, recap=recap)
    return order, texts, recap_pages


def _pick(i, **over):
    p = {"home": f"Home {i}", "away": f"Away {i}", "sel": "O15", "label": "Over 1.5 goals", "market": "goals",
         "odds": 1.5 + i / 100, "p": 0.72, "kickoff": f"2026-10-20 1{i}:00", "country": "Spain", "league": "LaLiga"}
    p.update(over)
    return p


def test_only_the_first_video_of_the_day_carries_the_recap(monkeypatch, tmp_path):
    yesterday = {"day": "2026-10-19", "items": [
        {"home": "A", "away": "B", "sel": "O15", "label": "Over 1.5 goals", "result": "hit", "score": "2-1", "odds": 1.8},
    ]}
    picks = [_pick(i) for i in range(1, 4)]
    order_recap, texts_recap, _ = _capture_build(monkeypatch, tmp_path, picks, yesterday=yesterday,
                                                 recap=True, name="recap.mp4")
    assert order_recap[:3] == ["intro", "disclaimer", "results"]
    assert "look back at yesterday" in texts_recap[2]
    order_noon, texts_noon, pages_noon = _capture_build(monkeypatch, tmp_path, picks, yesterday=yesterday,
                                                        recap=False, name="noon.mp4")
    assert "results" not in order_noon and not pages_noon
    assert "yesterday" not in " ".join(texts_noon).lower()


def test_the_morning_recap_covers_every_video_from_yesterday_across_pages(monkeypatch, tmp_path):
    items = []
    for i in range(22):
        items.append({"home": f"T{i}", "away": f"U{i}", "sel": "O15", "label": "Over 1.5 goals", "market": "goals",
                      "odds": 1.7, "result": "hit" if i % 3 else "miss", "score": "2-1" if i % 3 else "0-0"})
    yesterday = {"day": "2026-10-19", "items": items}
    order, texts, pages = _capture_build(monkeypatch, tmp_path, [_pick(1), _pick(2), _pick(3)],
                                         yesterday=yesterday, recap=True, name="long.mp4")
    assert order.count("results") == 3                              # 22 rows over RECAP_ROWS (9) per slide
    assert [len(p) for p in pages] == [9, 9, 4]
    assert sum(len(p) for p in pages) == 22                         # every selection, nothing truncated
    first = texts[2]
    assert "across all of yesterday's videos" in first
    assert "We went" in first and "The standout" in first
    # Later pages are one line each — the card is on screen, not read match by match
    assert all(len(t) < 120 for t in texts[3:5])


def test_no_combine_slide_and_each_match_said_once(monkeypatch, tmp_path):
    picks = [_pick(i) for i in range(1, 7)]
    order, texts, _ = _capture_build(monkeypatch, tmp_path, picks, name="order.mp4")
    assert order.count("pick") == 6
    assert order[0] == "intro" and order[1] == "disclaimer" and order[-1] == "closer"
    assert "combine" not in order                                  # accumulators are gone from the video
    assert not any("combine" in t.lower() or "treble" in t.lower() for t in texts)
    for i in range(1, 7):
        said = [t for t in texts if f"Home {i}" in t and "The model has that at" in t]
        assert len(said) == 1, said
