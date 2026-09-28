"""PlayReport's own notification sounds, synthesised from scratch (no third-party samples, no licences).

Writes android/app/src/main/res/raw/pr_*.ogg (notification channel sounds) and the same files under
www/sounds/ (in-app previews on the Settings page).  Run:  python3 android/tools/make_sounds.py
Needs numpy + ffmpeg.
"""
import pathlib, subprocess, tempfile, wave
import numpy as np

SR = 44100
ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "app/src/main/res/raw"
WWW = ROOT / "app/src/main/assets/www/sounds"


def t(sec):
    return np.arange(int(SR * sec)) / SR


def env(n, a=0.005, d=0.05, s=1.0, r=0.08, hold=None):
    """ADSR-ish envelope over n samples."""
    x = np.zeros(n)
    ia, idd, ir = int(a * SR), int(d * SR), int(r * SR)
    ia, idd, ir = max(ia, 1), max(idd, 1), max(ir, 1)
    x[:ia] = np.linspace(0, 1, ia)
    x[ia:ia + idd] = np.linspace(1, s, idd)[:max(0, min(idd, n - ia))]
    x[ia + idd:] = s
    if ir < n:
        x[-ir:] *= np.linspace(1, 0, ir)
    return x


def tone(freq, sec, harm=(1.0, 0.5, 0.25, 0.12), vib=0.0, vib_hz=6.0, detune=0.0):
    tt = t(sec)
    f = freq * (1 + vib * np.sin(2 * np.pi * vib_hz * tt))
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = sum(a * np.sin(k * ph) for k, a in enumerate(harm, start=1))
    if detune:
        ph2 = 2 * np.pi * np.cumsum(f * (1 + detune)) / SR
        y = 0.6 * y + 0.4 * sum(a * np.sin(k * ph2) for k, a in enumerate(harm, start=1))
    return y / max(1e-9, np.abs(y).max())


def whistle(sec, freq=2750.0, trill_hz=38.0, depth=0.55):
    """Pea-whistle: bright carrier, fast trill (amplitude + slight pitch modulation), breathy noise."""
    tt = t(sec)
    trill = 1 - depth * (0.5 + 0.5 * np.sin(2 * np.pi * trill_hz * tt))
    f = freq * (1 + 0.012 * np.sin(2 * np.pi * trill_hz * tt))
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.sin(ph) + 0.35 * np.sin(2 * ph) + 0.12 * np.sin(3 * ph)
    noise = np.random.default_rng(7).normal(0, 1, len(tt))
    # band-limit the breath noise around the carrier with a crude one-pole pair
    noise = np.convolve(noise, np.ones(6) / 6, mode="same") - np.convolve(noise, np.ones(40) / 40, mode="same")
    y = y * trill + 0.08 * noise
    return y * env(len(tt), a=0.012, d=0.03, s=0.95, r=0.06)


def crowd(sec, seed=3):
    """Crowd-roar swell: shaped noise with a slow rise, band-passed by moving averages."""
    rng = np.random.default_rng(seed)
    n = int(SR * sec)
    x = rng.normal(0, 1, n)
    lo = np.convolve(x, np.ones(9) / 9, mode="same")          # low-pass ~2.5 kHz
    hi = np.convolve(x, np.ones(220) / 220, mode="same")       # low-pass ~100 Hz
    y = lo - hi                                                 # band-pass
    tt = t(sec)
    shape = np.clip(tt / (0.45 * sec), 0, 1) ** 1.6 * np.exp(-np.clip(tt - 0.55 * sec, 0, None) * 2.4)
    return y / np.abs(y).max() * shape


def place(canvas, y, at, gain=1.0):
    i = int(at * SR)
    j = min(len(canvas), i + len(y))
    canvas[i:j] += gain * y[:j - i]


def finish(y, peak=0.89):
    y = np.tanh(1.3 * y / max(1e-9, np.abs(y).max()))          # soft limiter
    return (y / np.abs(y).max() * peak)


def goal():
    """GOAL: thump, rising three-note fanfare into a held top note with vibrato, crowd swell underneath."""
    total = 2.3
    c = np.zeros(int(SR * total))
    place(c, crowd(2.2), 0.0, 0.55)
    thump = np.sin(2 * np.pi * np.cumsum(np.linspace(140, 45, int(SR * 0.25))) / SR) * env(int(SR * 0.25), a=0.002, d=0.05, s=0.6, r=0.15)
    place(c, thump, 0.0, 0.9)
    brass = (1.0, 0.7, 0.5, 0.35, 0.22, 0.14, 0.08)
    for i, (f, at, dur) in enumerate([(523.25, 0.08, 0.20), (659.25, 0.26, 0.20), (783.99, 0.44, 0.22)]):
        y = tone(f, dur, brass, detune=0.004) * env(int(SR * dur), a=0.01, d=0.05, s=0.85, r=0.05)
        place(c, y, at, 0.75)
    top = tone(1046.5, 1.35, brass, vib=0.012, vib_hz=6.5, detune=0.005) * env(int(SR * 1.35), a=0.015, d=0.2, s=0.8, r=0.55)
    place(c, top, 0.64, 0.8)
    fifth = tone(783.99, 1.35, brass, vib=0.01, vib_hz=6.5) * env(int(SR * 1.35), a=0.015, d=0.2, s=0.7, r=0.55)
    place(c, fifth, 0.64, 0.45)
    return finish(c)


def blasts(n, blast=0.42, gap=0.14, last_long=False):
    total = n * (blast + gap) + (0.5 if last_long else 0.1)
    c = np.zeros(int(SR * total))
    at = 0.0
    for i in range(n):
        d = blast + (0.5 if (last_long and i == n - 1) else 0)
        place(c, whistle(d), at, 1.0)
        at += d + gap
    return finish(c, 0.8)


def chime(notes, sec_each=0.55, gap=0.12, peak=0.8):
    total = len(notes) * gap + sec_each + 0.3
    c = np.zeros(int(SR * total))
    glass = (1.0, 0.0, 0.33, 0.0, 0.12, 0.0, 0.05)
    for i, f in enumerate(notes):
        y = tone(f, sec_each, glass) * np.exp(-t(sec_each) * 5.5) * env(int(SR * sec_each), a=0.003, d=0.02, s=1.0, r=0.05)
        place(c, y, i * gap, 0.9)
    return finish(c, peak)


def write(name, y):
    RAW.mkdir(parents=True, exist_ok=True)
    WWW.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        wav = pathlib.Path(td) / f"{name}.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((y * 32767).astype(np.int16).tobytes())
        for out in (RAW / f"{name}.ogg", WWW / f"{name}.ogg"):
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libvorbis", "-q:a", "4", str(out)], check=True)
        print(name, f"{len(y) / SR:.2f}s", (RAW / f"{name}.ogg").stat().st_size, "bytes")


if __name__ == "__main__":
    write("pr_goal", goal())                                   # goals in tracked matches
    write("pr_kickoff", blasts(1, blast=0.75))                 # kick-off reminders: one long whistle
    write("pr_fulltime", blasts(3, last_long=True))            # half-time / full-time: three blasts, last one long
    write("pr_selection", chime([783.99, 1046.5, 1318.5]))     # new high-probability selection / ticket settled
    write("pr_report", chime([659.25, 523.25], sec_each=0.7, gap=0.16, peak=0.7))   # new analysis published
