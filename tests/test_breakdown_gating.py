"""Daily match-breakdown gating: once a day, morning window only, retried after a failed send."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import scanner


class FakeBreakdown:
    DEFAULT_MATCHES = 6

    def __init__(self, n_matches=6):
        self.n = n_matches
        self.built = []

    def select_featured_matches(self, dossiers, prim, limit, day):
        return [{"home": f"H{i}", "away": f"A{i}"} for i in range(self.n)]

    def build_show_both(self, matches, v16, v9, assets, work, day):
        self.built.append(day)
        Path(v16).parent.mkdir(parents=True, exist_ok=True)
        Path(v16).write_bytes(b"x"); Path(v9).write_bytes(b"x")
        return Path(v16), Path(v9), SimpleNamespace(matches=matches)

    def credits_text(self, prep):
        return "Photo credits (Wikimedia Commons):\nTest Stadium: Photo: Jane / CC BY 4.0 / Wikimedia Commons"


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.delenv("FORCE_DAILY_BREAKDOWN", raising=False)
    monkeypatch.setattr(scanner, "APP_FILE", tmp_path / "app" / "latest.json")
    state = {"path": tmp_path / "telegram_state.json", "st": {"day": "2026-10-16", "sent": []}}
    monkeypatch.setattr(scanner, "_telegram_state", lambda now: (state["path"], state["st"]))
    fake = FakeBreakdown()
    monkeypatch.setattr(scanner, "breakdown_mod", fake)
    sent, texts = [], []
    ok = {"v": True}
    monkeypatch.setattr(scanner, "send_telegram_video", lambda p, cap, **k: (sent.append((Path(p).name, cap, k)), ok["v"])[1])
    monkeypatch.setattr(scanner, "send_telegram", lambda t: texts.append(t))
    return SimpleNamespace(fake=fake, state=state, sent=sent, texts=texts, ok=ok)


MORNING = datetime(2026, 10, 16, 6, 5)


def test_builds_and_sends_both_videos_once_in_the_morning_window(env):
    scanner.maybe_send_daily_breakdown({}, MORNING)
    assert env.fake.built == ["2026-10-16"]
    assert [(n, k["width"], k["height"]) for n, _c, k in env.sent] == [("match-breakdown-16x9.mp4", 1920, 1080), ("match-breakdown-9x16.mp4", 1080, 1920)]
    caps = " ".join(c for _n, c, _k in env.sent)
    assert "AI" not in caps.replace("PlayReport", "") and "TV" not in caps and "generated" not in caps.lower()
    assert env.texts and "Photo credits" in env.texts[0]                       # attribution follows the videos
    assert env.state["st"]["breakdown"] == "2026-10-16"
    assert json.loads(env.state["path"].read_text())["breakdown"] == "2026-10-16"


def test_outside_the_window_nothing_happens_unless_forced(env, monkeypatch):
    scanner.maybe_send_daily_breakdown({}, datetime(2026, 10, 16, 12, 0))
    assert env.fake.built == []
    monkeypatch.setenv("FORCE_DAILY_BREAKDOWN", "1")
    scanner.maybe_send_daily_breakdown({}, datetime(2026, 10, 16, 12, 0))
    assert env.fake.built == ["2026-10-16"]


@pytest.mark.parametrize("marker", ["breakdown", "tv_analysis"])
def test_already_sent_today_is_not_sent_again_including_the_legacy_marker(env, marker):
    env.state["st"][marker] = "2026-10-16"
    scanner.maybe_send_daily_breakdown({}, MORNING)
    assert env.fake.built == [] and env.sent == []


def test_failed_send_leaves_no_marker_so_the_next_scan_retries(env):
    env.ok["v"] = False
    scanner.maybe_send_daily_breakdown({}, MORNING)
    assert "breakdown" not in env.state["st"] and env.texts == []
    env.ok["v"] = True
    scanner.maybe_send_daily_breakdown({}, datetime(2026, 10, 16, 6, 35))
    assert env.state["st"]["breakdown"] == "2026-10-16"


def test_too_few_matches_skips_quietly(env):
    env.fake.n = 2
    scanner.maybe_send_daily_breakdown({}, MORNING)
    assert env.fake.built == [] and "breakdown" not in env.state["st"]


def test_independent_of_the_shortlist_video_marker(env):
    env.state["st"]["briefing"] = "2026-10-16"          # shortlist video already went out: breakdown must still run
    scanner.maybe_send_daily_breakdown({}, MORNING)
    assert env.fake.built == ["2026-10-16"]
