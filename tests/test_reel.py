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

