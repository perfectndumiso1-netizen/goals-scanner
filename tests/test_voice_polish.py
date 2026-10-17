"""Voice polish: pauses re-timed by punctuation, pace and level drift, one loudness, room tone. Synthetic audio only."""
from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pytest

import shortlist_reel as reel
import voice_polish as vp

SR = vp.SR


@pytest.fixture(scope="module")
def ff():
    try:
        path = reel._ffmpeg()
        import subprocess
        subprocess.run([path, "-version"], capture_output=True, check=True)
        return path
    except Exception:  # noqa: BLE001
        pytest.skip("ffmpeg not available")


def speech_like(dur: float, seed: int = 0) -> np.ndarray:
    rnd = np.random.default_rng(seed)
    t = np.arange(int(dur * SR)) / SR
    carrier = sum(np.sin(2 * np.pi * f * t) for f in (140, 280, 420, 560, 700))
    env = 0.35 + 0.65 * np.abs(np.sin(2 * np.pi * 3.2 * t))
    return (carrier * env * 0.05 + rnd.normal(0, 0.0015, len(t))).astype(np.float32)


def quiet(dur: float, seed: int = 1) -> np.ndarray:
    return np.random.default_rng(seed).normal(0, 0.00005, int(dur * SR)).astype(np.float32)


def narration(script: str, gap: float = 0.42, seg: float = 1.1) -> np.ndarray:
    n = len(vp.internal_marks(script))
    parts = []
    for i in range(n + 1):
        parts.append(speech_like(seg + 0.15 * (i % 3), seed=i))
        if i < n:
            parts.append(quiet(gap, seed=100 + i))
    return np.concatenate(parts)


# ------------------------------------------------------------------ punctuation

def test_marks_ignore_decimals_and_hyphenated_words_and_drop_the_final_stop():
    assert vp.internal_marks("My pick is Deportivo, at 1.24.") == ["comma"]
    assert vp.internal_marks("They lost three-two. Next, Paris Saint-Germain: a big one.") == ["sentence", "comma", "colon"]
    assert vp.internal_marks("One. Two! Three?") == ["sentence", "sentence"]
    assert vp.internal_marks("No final stop, just this") == ["comma"]


def test_pauses_pair_with_marks_in_order_and_fall_back_sensibly():
    script = "A b, c d. E f, g h."
    marks = vp.internal_marks(script)
    pauses = [(1.0, 1.4), (2.0, 2.4), (3.0, 3.4)]
    assert vp.assign_pauses(pauses, script) == marks == ["comma", "sentence", "comma"]
    # one pause missing: no recogniser -> the longest pause is taken to be the sentence end
    kinds = vp.assign_pauses([(1.0, 1.3), (2.0, 2.6)], script)
    assert kinds == ["comma", "sentence"]
    # recogniser words let the script line up even when a pause was missed
    words = [("A", 0.1, 0.4), ("b", 0.5, 0.8), ("c", 1.4, 1.7), ("d", 1.8, 2.0), ("E", 2.7, 3.0), ("f", 3.1, 3.3), ("g", 3.9, 4.2), ("h", 4.3, 4.6)]
    kinds = vp.assign_pauses([(0.8, 1.4), (2.0, 2.7), (3.3, 3.9)], script + " ", words)
    assert kinds == ["comma", "sentence", "comma"]


def test_gaps_are_short_at_commas_longer_at_stops_and_never_identical():
    rnd = random.Random(5)
    commas = [vp.gap_seconds("comma", 2.0, rnd) for _ in range(200)]
    stops = [vp.gap_seconds("sentence", 3.0, rnd) for _ in range(200)]
    assert 0.12 < np.mean(commas) < 0.27 and 0.40 < np.mean(stops) < 0.62
    assert max(commas) < min(stops) + 0.3 and len(set(round(g, 3) for g in commas)) > 50
    assert vp.gap_seconds("sentence", 7.0, random.Random(1)) > vp.gap_seconds("sentence", 0.8, random.Random(1))   # a breath after a long one


# ------------------------------------------------------------------ one long clip -> polished slides

def test_a_long_clip_is_re_timed_and_returned_slide_by_slide(ff):
    slides = ["Alpha beta, gamma delta.", "Epsilon zeta, eta theta. Iota kappa lambda."]
    x = narration(" ".join(slides))
    before = vp.pause_report(x)
    out = vp.polish_clip(x, slides, ff, seed=3)
    assert out is not None and len(out) == 2
    p1, p2 = vp.find_pauses(out[0], min_len=0.1), vp.find_pauses(out[1], min_len=0.1)
    assert len(p1) == 1 and len(p2) == 2
    assert 0.10 <= p1[0][1] - p1[0][0] <= 0.34                         # a comma is now a short pause
    assert (p2[0][1] - p2[0][0]) < 0.34 and (p2[1][1] - p2[1][0]) > 0.33   # ...a full stop is a longer one
    assert before["mean"] > 0.38                                      # they were all the same long pause before
    for a in out:
        assert abs(vp.lufs(a, ff) - vp.TARGET_LUFS) < 1.3              # every slide on one loudness
        assert float(np.abs(a).max()) <= 0.9                           # never clipped
    assert sum(len(a) for a in out) / SR < len(x) / SR                 # tighter than the original


def test_speech_is_never_clipped_by_the_cuts(ff):
    slides = ["Alpha beta, gamma delta."]
    x = narration(slides[0])
    out = vp.polish_clip(x, slides, ff, seed=1)[0]
    def active(a):
        return float((vp.frame_db(a) > -45).sum()) * 0.01
    assert abs(active(out) - active(x)) / active(x) < 0.07             # same amount of speech, within the tempo drift


def test_it_gives_up_cleanly_when_slides_cannot_be_placed(ff):
    x = speech_like(4.0)                                             # no pauses at all, but two slides are claimed
    assert vp.polish_clip(x, ["One, two, three.", "Four, five, six."], ff, seed=1) is None
    one = vp.polish_clip(x, ["One two three four five six."], ff, seed=1)   # a single slide is simply mastered
    assert one is not None and len(one) == 1 and abs(vp.lufs(one[0], ff) - vp.TARGET_LUFS) < 1.3


def test_polish_sentences_joins_clips_with_shaped_gaps(ff):
    clips = [speech_like(1.5, 1), speech_like(2.0, 2), speech_like(1.2, 3)]
    track = vp.polish_sentences(clips, ["sentence", "colon", "sentence"], ff, seed=2)
    total_speech = sum(len(c) for c in clips) / SR
    assert total_speech < len(track) / SR < total_speech + 1.6          # gaps added, nothing lost
    assert abs(vp.lufs(track, ff) - vp.TARGET_LUFS) < 1.3
    assert len(vp.find_pauses(track, min_len=0.12)) == 2


def test_wav_export_is_44k_mono(ff, tmp_path):
    dest = vp.to_wav44(speech_like(1.0), tmp_path / "x.wav", ff)
    assert abs(reel._probe(dest, ff) - 1.0) < 0.05
    import wave
    with wave.open(str(dest)) as w:
        assert w.getframerate() == 44100 and w.getnchannels() == 1


# ------------------------------------------------------------------ the held tail

def test_the_hold_after_speech_has_a_quiet_room_tone_not_dead_silence(ff, tmp_path):
    src = vp.write_wav(tmp_path / "s.wav", speech_like(1.0), SR)
    dest = tmp_path / "padded.wav"
    reel.pad_audio(src, dest, 2.5, ff)
    assert abs(reel._probe(dest, ff) - 2.5) < 0.03                      # exact hold, speech never trimmed
    y = vp.read_audio(dest, ff)
    tail = y[int(1.4 * SR):]
    db = 20 * np.log10(np.sqrt((tail.astype(np.float64) ** 2).mean()) + 1e-12)
    assert -72 < db < -52                                              # present, but far below any speech


# ------------------------------------------------------------------ the daily build

def test_the_daily_voice_is_spoken_sentence_by_sentence_and_polished(monkeypatch, tmp_path, ff):
    spoken = []

    def fake_sentence(sentence, edge_py, dest):
        spoken.append(sentence)
        vp.write_wav(dest, speech_like(0.9 + 0.1 * len(spoken), seed=len(spoken)), SR)
        return True

    monkeypatch.setenv("EDGE_TTS_PYTHON", str(Path(__file__)))
    monkeypatch.setattr(reel, "_edge_sentence", fake_sentence)
    monkeypatch.setattr(reel, "_ffmpeg", lambda: ff)
    out = tmp_path / "slide.wav"
    reel.synthesize_speech("First sentence here. Second one follows, with a comma. Third and last.", out)
    assert len(spoken) == 3 and out.exists()
    assert abs(vp.lufs(vp.read_audio(out, ff), ff) - vp.TARGET_LUFS) < 1.3
    assert len(vp.find_pauses(vp.read_audio(out, ff), min_len=0.12)) == 2


def test_a_failed_sentence_falls_back_to_the_plain_voice(monkeypatch, tmp_path, ff):
    monkeypatch.setenv("EDGE_TTS_PYTHON", str(Path(__file__)))
    monkeypatch.setattr(reel, "_edge_sentence", lambda s, e, d: False)
    monkeypatch.setattr(reel, "_ffmpeg", lambda: ff)
    assert reel._polished_edge("One. Two.", tmp_path / "x.wav", str(Path(__file__))) is False
