"""Reel timing: one voice clip per slide, no music, goals/corners/bookings only."""
from __future__ import annotations

import shortlist_reel as reel


def test_reel_picks_goals_corners_bookings_only():
    picks = [
        {"label": "Over 1.5 goals", "home": "A"},
        {"label": "Under 2.5 cards", "home": "B"},
        {"label": "Home or draw", "home": "C", "sel": "1X"},
        {"label": "Over 10.5 corners", "home": "E"},
        {"label": "Over 3.5 cards", "home": "F"},
        {"label": "Away under 1.5", "home": "D"},
    ] + [{"label": "Over 1.5 goals", "home": f"X{i}"} for i in range(10)]
    out = reel.reel_picks(picks)
    assert all(reel.is_reel_market(p) for p in out)
    assert all("under" not in (p.get("label") or "").lower() for p in out)
    assert [p["home"] for p in out[:3]] == ["A", "E", "F"]
    assert len(out) == reel.MAX_PICKS


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


def test_pick_script_has_competition_not_model():
    s = reel.pick_script({
        "home": "Lyon", "away": "Crystal Palace", "label": "Lyon over 0.5 goals",
        "odds": 1.2, "p": 0.91, "kickoff": "2026-10-15 18:45",
        "country": "Europa League", "league": "League Stage",
    })
    assert "Europa League, League Stage" in s
    assert "Lyon versus Crystal Palace" in s
    assert "1.20" in s
    assert "Kick-off" in s
    assert "percent" not in s.lower()
    assert "model" not in s.lower()


def test_disclaimer_and_closer_scripts():
    assert "18" in reel.DISCLAIMER_SCRIPT
    assert "sure bet" in reel.DISCLAIMER_SCRIPT.lower()
    assert "afford to lose" in reel.DISCLAIMER_SCRIPT
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
        [{"home": "Home FC", "away": "Away FC", "label": "Over 1.5 goals", "odds": 1.5, "p": 0.7}],
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
            {"home": "Flamengo", "away": "Botafogo", "label": "Over 1.5 goals", "market": "goals", "odds": 1.28, "result": "hit", "score": "2-1"},
            {"home": "Santos", "away": "Corinthians", "label": "Over 8.5 corners", "market": "corners", "odds": 1.35, "result": "miss", "score": "0-0"},
        ],
    }
    outfile = tmp_path / "briefing-16x9.mp4"
    reel.build(
        [{"home": "Lyon", "away": "Crystal Palace", "label": "Over 1.5 goals", "odds": 1.25, "kickoff": "2026-10-15 18:45"}],
        outfile,
        assets=assets,
        work=tmp_path / "work",
        fixtures=[],
        yesterday_results=yres,
    )

    assert slide_order == ["intro", "disclaimer", "results", "pick", "closer"]
    assert len(spoken_scripts) == 5
    assert "Yesterday's shortlist results. 1 of 2 selections won." in spoken_scripts[2]
    assert "Flamengo versus Botafogo, Over 1.5 goals, won, 2 to 1." in spoken_scripts[2]
    assert "Now, today's shortlist." in spoken_scripts[2]
    assert "percent" not in spoken_scripts[2].lower()
    assert "Lyon versus Crystal Palace" in spoken_scripts[3]


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


