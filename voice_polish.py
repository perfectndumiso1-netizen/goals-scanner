"""Make a synthetic narration sound like a person talking.

What makes text-to-speech sound artificial is rarely the voice itself. It is the timing: every comma and full stop gets
the same pause, every sentence the same pace and loudness, and the gaps are perfect digital silence. This module fixes
the timing and the "recorded in a room" feel, using only ffmpeg and numpy (no models):

  pauses  short at commas, longer at full stops, never the same twice, a longer breath after a long sentence
  pace    a tiny sentence-to-sentence tempo drift (a person is never a metronome)
  level   a touch of loudness drift per sentence, then every slide lands on one loudness target
  tone    warmth, presence, a gentle de-ess, light compression and a hint of room

Two ways in:
  polish_sentences()  the daily build: one synthesised clip per sentence, joined with shaped gaps
  polish_clip()       a single long clip (several slides read in one go) is cut at its real pauses, every pause is
                      re-timed according to the punctuation that caused it, and the slides come back separately

Nothing here may ever break a build: callers fall back to the unpolished audio when anything raises.
"""
from __future__ import annotations

import difflib
import json
import logging
import random
import re
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

log = logging.getLogger("scanner")

SR = 24000                      # working sample rate
TARGET_LUFS = -16.0
GAP = {                         # seconds: (centre, jitter) for each kind of pause
    "comma": (0.19, 0.06), "colon": (0.30, 0.07), "dash": (0.27, 0.06), "sentence": (0.50, 0.12), "ellipsis": (0.60, 0.10),
}

CHAIN = ("highpass=f=70,equalizer=f=140:t=q:w=0.9:g=1.6,equalizer=f=320:t=q:w=1.2:g=-1.0,equalizer=f=3200:t=q:w=1.2:g=1.2,"
         "equalizer=f=7600:t=q:w=2:g=-2.2,acompressor=threshold=0.125:ratio=2.2:attack=12:release=220:makeup=2,"
         "aecho=in_gain=1.0:out_gain=1.0:delays=17|29:decays=0.08|0.05")


# ----------------------------------------------------------------------------- audio io

def read_audio(path, ff: str, sr: int = SR) -> np.ndarray:
    raw = subprocess.run([ff, "-v", "quiet", "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                         capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float32).copy()


def write_wav(path, x: np.ndarray, sr: int = SR) -> Path:
    """16-bit mono WAV with the standard library (no soundfile needed)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


def _ff(ff: str, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([ff, "-y", "-v", "error", *args], capture_output=True, text=True)


# ----------------------------------------------------------------------------- level and pause detection

def frame_db(x: np.ndarray, sr: int = SR, hop: float = 0.01) -> np.ndarray:
    h = max(1, int(hop * sr))
    n = len(x) // h
    if n == 0:
        return np.full(1, -120.0)
    f = x[: n * h].reshape(n, h).astype(np.float64)
    return 20 * np.log10(np.sqrt((f ** 2).mean(axis=1)) + 1e-9)


def find_pauses(x: np.ndarray, sr: int = SR, min_len: float = 0.16, margin_db: float = 28.0, hop: float = 0.01) -> list[tuple[float, float]]:
    """Internal pauses (start, end) in seconds: stretches well below the speech level that last at least `min_len`."""
    db = frame_db(x, sr, hop)
    speech = np.percentile(db, 90)
    thr = max(-70.0, speech - margin_db)
    quiet = db < thr
    out, i, n = [], 0, len(quiet)
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            if (j - i) * hop >= min_len and i > 0 and j < n:          # leading / trailing silence is not a pause
                out.append((i * hop, j * hop))
            i = j
        else:
            i += 1
    return out


def trim(x: np.ndarray, sr: int = SR, margin_db: float = 36.0, pad: float = 0.03) -> np.ndarray:
    """Cut leading and trailing silence, keeping a short natural margin, with tiny fades."""
    db = frame_db(x, sr)
    thr = max(-72.0, np.percentile(db, 90) - margin_db)
    idx = np.where(db > thr)[0]
    if len(idx) == 0:
        return x
    a, b = max(0, int((idx[0] * 0.01 - pad) * sr)), min(len(x), int(((idx[-1] + 1) * 0.01 + pad) * sr))
    return fade(x[a:b].copy(), sr)


def fade(x: np.ndarray, sr: int = SR, ms: float = 6.0) -> np.ndarray:
    n = min(len(x) // 2, int(ms / 1000 * sr))
    if n > 1:
        x[:n] *= np.linspace(0, 1, n, dtype=np.float32)
        x[-n:] *= np.linspace(1, 0, n, dtype=np.float32)
    return x


# ----------------------------------------------------------------------------- punctuation

_TOKEN = re.compile(r"[A-Za-z0-9']+(?:[-.][A-Za-z0-9']+)*|[.,;:!?]|[—–]|\s-\s")


def internal_marks(text: str) -> list[str]:
    """The punctuation inside a text that a voice turns into a pause, in reading order, as kinds.

    Decimals ("1.24") and hyphenated words ("three-two") are not punctuation. The very last mark is dropped: it ends the
    narration and is followed by the slide change, not by a pause inside the clip.
    """
    kinds: list[str] = []
    t = str(text or "").strip()
    for m in _TOKEN.finditer(t):
        tok = m.group(0)
        if tok in (".", "!", "?"):
            kinds.append("sentence")
        elif tok in (",", ";"):
            kinds.append("comma")
        elif tok == ":":
            kinds.append("colon")
        elif tok.strip() in ("—", "–", "-"):
            kinds.append("dash")
    if re.search(r"[.!?]\s*$", t) and kinds:
        kinds.pop()
    return kinds


def _norm_words(text: str) -> list[str]:
    return [w for w in re.sub(r"[^a-z0-9' ]+", " ", str(text or "").lower().replace("-", " ")).split() if w]


# ----------------------------------------------------------------------------- assigning pauses to punctuation

def asr_words(path, ff: str):
    """Word timestamps with faster-whisper (tiny.en) when it is installed; None otherwise."""
    try:
        from faster_whisper import WhisperModel
    except Exception:  # noqa: BLE001
        return None
    try:
        audio = read_audio(path, ff, 16000)
        model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
        segs, _ = model.transcribe(audio, word_timestamps=True, language="en", beam_size=1, vad_filter=False)
        return [(w.word.strip(), float(w.start), float(w.end)) for sg in segs for w in (sg.words or [])]
    except Exception as exc:  # noqa: BLE001
        log.warning("speech alignment unavailable: %s", exc)
        return None


def _mark_times(script: str, words) -> list[float | None]:
    """Predicted time of each internal mark, from aligning the script to the recognised words."""
    toks: list[tuple[str, str | None]] = []      # (word, kind of mark right after it)
    for m in re.finditer(r"([A-Za-z0-9']+(?:[-.][A-Za-z0-9']+)*)|([.,;:!?]|[—–])", script):
        if m.group(1):
            for w in _norm_words(m.group(1)):
                toks.append((w, None))
        elif toks:
            toks[-1] = (toks[-1][0], "mark")
    s_words = [w for w, _ in toks]
    a_words = [(_norm_words(w[0]) or [""])[0] for w in words]
    sm = difflib.SequenceMatcher(None, s_words, a_words, autojunk=False)
    mp: dict[int, int] = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            mp[blk.a + k] = blk.b + k
    times: list[float | None] = []
    for i, (_, mark) in enumerate(toks):
        if mark is None:
            continue
        j = None
        for d in range(0, 4):
            if i - d in mp:
                j = mp[i - d] + d
                break
        times.append(words[min(j, len(words) - 1)][2] if j is not None else None)
    # the script's own last mark has no pause after it inside the clip
    ends_with_stop = bool(re.search(r"[.!?]\s*$", script.strip()))
    return times[:-1] if ends_with_stop and times else times


def assign_pauses(pauses: list[tuple[float, float]], script: str, words=None, words_fn=None) -> list[str]:
    """A kind ("comma", "sentence", ...) for every detected pause, from the punctuation that caused it.

    When the number of pauses equals the number of marks they pair up in order. Otherwise the script is aligned to the
    recognised words (`words`, or `words_fn()` called only when needed) and, failing that, the longest pauses are
    taken to be the sentence ends.
    """
    marks = internal_marks(script)
    if len(pauses) == len(marks):
        return marks
    if words is None and words_fn is not None:
        words = words_fn()
    if words:
        times = _mark_times(script, words)
        if len(times) == len(marks):
            kinds: list[str | None] = [None] * len(pauses)
            used: set[int] = set()
            last = -1
            for kind, t in zip(marks, times):
                if t is None:
                    continue
                best, bd = None, 9.0
                for k, (s, e) in enumerate(pauses):
                    if k in used or k <= last:
                        continue
                    d = abs(s - t)
                    if -0.4 <= s - t <= 0.7 and d < bd:
                        best, bd = k, d
                if best is not None:
                    kinds[best] = kind
                    used.add(best)
                    last = best
            for k, (s, e) in enumerate(pauses):                    # a pause nobody asked for: keep it short unless it is long
                if kinds[k] is None:
                    kinds[k] = "comma" if (e - s) < 0.45 else "sentence"
            return [str(k) for k in kinds]
    # last resort: the longest pauses are the sentence ends
    n_sent = sum(1 for k in marks if k == "sentence")
    order = sorted(range(len(pauses)), key=lambda i: -(pauses[i][1] - pauses[i][0]))
    sent = set(order[:n_sent])
    return ["sentence" if i in sent else "comma" for i in range(len(pauses))]


# ----------------------------------------------------------------------------- re-timing

def gap_seconds(kind: str, prev_len: float, rnd: random.Random) -> float:
    centre, jit = GAP.get(kind, GAP["comma"])
    g = centre + rnd.uniform(-jit, jit)
    if kind == "sentence":
        if prev_len > 5.0:
            g += 0.07                  # a breath after a long sentence
        elif prev_len < 1.2:
            g -= 0.08                  # a short line needs less room
    return float(min(0.9, max(0.09, g)))


def _segments(x: np.ndarray, pauses: list[tuple[float, float]], sr: int = SR) -> list[np.ndarray]:
    """Speech between pauses, cut inside the silence so no word is ever clipped."""
    cuts = [0]
    for s, e in pauses:
        keep_end = s + min(0.05, (e - s) * 0.30)
        keep_start = e - min(0.04, (e - s) * 0.25)
        cuts += [int(keep_end * sr), int(keep_start * sr)]
    cuts.append(len(x))
    segs = []
    for a, b in zip(cuts[0::2], cuts[1::2]):
        if b > a:
            segs.append(fade(x[a:b].copy(), sr))
    return segs


def _tempo(x: np.ndarray, factor: float, ff: str, sr: int = SR) -> np.ndarray:
    if abs(factor - 1.0) < 0.004:
        return x
    with tempfile.TemporaryDirectory() as d:
        a, b = Path(d) / "a.wav", Path(d) / "b.wav"
        write_wav(a, x, sr)
        r = _ff(ff, ["-i", str(a), "-filter:a", f"atempo={factor:.4f}", "-ar", str(sr), "-ac", "1", str(b)])
        if r.returncode != 0 or not b.exists():
            return x
        return read_audio(b, ff, sr)


def _drift(rnd: random.Random) -> tuple[float, float]:
    """(tempo factor, gain dB) for one sentence: a person drifts, a machine does not."""
    tempo = min(1.045, max(0.985, rnd.gauss(1.02, 0.014)))
    return tempo, rnd.uniform(-0.7, 0.7)


def _join(parts: list[np.ndarray], gaps: list[float], sr: int = SR) -> np.ndarray:
    out: list[np.ndarray] = []
    for i, p in enumerate(parts):
        out.append(p)
        if i < len(gaps):
            out.append(np.zeros(int(gaps[i] * sr), dtype=np.float32))
    return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)


def _sentence_audio(segs: list[np.ndarray], kinds: list[str], rnd: random.Random, ff: str, sr: int = SR, drift: bool = True) -> np.ndarray:
    """One sentence: its phrases joined with comma-sized gaps, then a little tempo and level drift."""
    gaps = [gap_seconds(k, float(len(s)) / sr, rnd) for s, k in zip(segs, kinds)]
    x = _join(segs, gaps, sr)
    if drift:
        t, db = _drift(rnd)
        x = _tempo(x, t, ff, sr) * float(10 ** (db / 20))
    return x.astype(np.float32)


# ----------------------------------------------------------------------------- mastering

def lufs(x: np.ndarray, ff: str, sr: int = SR) -> float | None:
    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / "a.wav"
        write_wav(a, x, sr)
        r = subprocess.run([ff, "-v", "info", "-i", str(a), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr or "", re.S)
    try:
        return float(json.loads(m.group(0))["input_i"]) if m else None
    except (ValueError, KeyError):
        return None


def master(x: np.ndarray, ff: str, sr: int = SR, target: float = TARGET_LUFS) -> np.ndarray:
    """Tone chain, then a fixed gain so every slide sits on the same loudness, then a safety limiter."""
    if len(x) < sr // 4:
        return x
    with tempfile.TemporaryDirectory() as d:
        a, b, c = Path(d) / "a.wav", Path(d) / "b.wav", Path(d) / "c.wav"
        write_wav(a, x, sr)
        if _ff(ff, ["-i", str(a), "-af", CHAIN, "-ar", str(sr), "-ac", "1", str(b)]).returncode != 0 or not b.exists():
            return x
        y = read_audio(b, ff, sr)
        i = lufs(y, ff, sr)
        gain = 0.0 if i is None else max(-12.0, min(14.0, target - i))
        write_wav(b, y, sr)
        r = _ff(ff, ["-i", str(b), "-af", f"volume={gain:.2f}dB,alimiter=limit=0.84:level=disabled", "-ar", str(sr), "-ac", "1", str(c)])
        return read_audio(c, ff, sr) if r.returncode == 0 and c.exists() else y


# ----------------------------------------------------------------------------- public: the daily build

def polish_sentences(clips: list[np.ndarray], kinds_after: list[str], ff: str, *, seed=0, sr: int = SR) -> np.ndarray:
    """Join one clip per sentence into a single narration with shaped gaps, drift and mastering.

    `kinds_after[i]` is the pause kind that follows clip i (the last entry is ignored).
    """
    rnd = random.Random(seed)
    parts = []
    for c in clips:
        t, db = _drift(rnd)
        parts.append((_tempo(trim(c, sr), t, ff, sr) * float(10 ** (db / 20))).astype(np.float32))
    gaps = [gap_seconds(kinds_after[i] if i < len(kinds_after) else "sentence", float(len(p)) / sr, rnd) for i, p in enumerate(parts[:-1])]
    return master(_join(parts, gaps, sr), ff, sr)


# ----------------------------------------------------------------------------- public: one clip, several slides

def polish_clip(x: np.ndarray, slide_texts: list[str], ff: str, *, words=None, words_fn=None, seed=0, sr: int = SR) -> list[np.ndarray] | None:
    """Re-time a long narration and hand back one polished array per slide, or None if it cannot be done safely."""
    slide_texts = [t.strip() if re.search(r"[.!?]$", t.strip()) else t.strip() + "." for t in slide_texts]
    script = " ".join(slide_texts)
    pauses = find_pauses(x, sr)
    kinds = assign_pauses(pauses, script, words, words_fn)
    if len(kinds) != len(pauses):
        return None
    # which pauses end a slide: the sentence mark that closes each slide's text (all marks of a slide, then its last stop)
    per_slide = [len(internal_marks(t)) for t in slide_texts]
    boundary_after: list[int] = []
    run = 0
    for k, t in enumerate(slide_texts[:-1]):
        run += per_slide[k] + 1               # the slide's internal marks plus the stop that closes it
        boundary_after.append(run - 1)
    if boundary_after and boundary_after[-1] >= len(pauses):
        return None
    segs = _segments(x, pauses, sr)
    if len(segs) != len(pauses) + 1:
        return None
    rnd = random.Random(seed)
    slides: list[np.ndarray] = []
    sentence_segs: list[np.ndarray] = []
    sentence_kinds: list[str] = []
    parts: list[np.ndarray] = []          # finished sentences of the current slide

    def close_sentence() -> None:
        nonlocal sentence_segs, sentence_kinds
        if sentence_segs:
            parts.append(_sentence_audio(sentence_segs, sentence_kinds, rnd, ff, sr))
        sentence_segs, sentence_kinds = [], []

    def close_slide() -> None:
        nonlocal parts
        close_sentence()
        if parts:
            gaps = [gap_seconds("sentence", float(len(p)) / sr, rnd) for p in parts[:-1]]
            slides.append(master(_join(parts, gaps, sr), ff, sr))
        parts = []

    for i, seg in enumerate(segs):
        sentence_segs.append(seg)
        if i == len(pauses):
            break
        kind = kinds[i]
        if i in boundary_after:
            close_slide()
        elif kind in ("sentence", "ellipsis"):
            close_sentence()
        else:
            sentence_kinds.append(kind)
    close_slide()
    return slides if len(slides) == len(slide_texts) else None


# ----------------------------------------------------------------------------- diagnostics

def pause_report(x: np.ndarray, sr: int = SR) -> dict:
    ps = find_pauses(x, sr, min_len=0.1)
    d = np.array([e - s for s, e in ps]) if ps else np.zeros(1)
    return {"n": len(ps), "mean": float(d.mean()), "cv": float(d.std() / d.mean()) if d.mean() else 0.0,
            "short": int((d < 0.3).sum()), "long": int((d >= 0.3).sum()), "dur": len(x) / sr}


def to_wav44(x: np.ndarray, dest, ff: str, sr: int = SR) -> Path:
    """Export a polished track as the 44.1 kHz mono WAV the video builders expect."""
    dest = Path(dest)
    with tempfile.TemporaryDirectory() as d:
        tmp = write_wav(Path(d) / "t.wav", x, sr)
        r = _ff(ff, ["-i", str(tmp), "-ar", "44100", "-ac", "1", str(dest)])
        if r.returncode != 0 or not dest.exists():
            raise RuntimeError(f"wav export failed: {r.stderr[-200:]}")
    return dest


def enabled() -> bool:
    """Polish is on unless PLAYREPORT_POLISH=0 (a switch for debugging only)."""
    import os
    return os.environ.get("PLAYREPORT_POLISH", "1").strip().lower() not in ("0", "false", "no", "off")
