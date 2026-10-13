"""PlayReport shortlist reel — 9:16, 5s logo intro, 1–2 min, no bed music.

Each slide lasts exactly as long as its own voice clip (plus a short tail),
so the next match never appears while the previous one is still being read.
Background music is not mixed in — add your own after if you want it.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

log = logging.getLogger("scanner")

W, H, FPS = 1080, 1920, 30
GREEN = (0, 200, 111)
WHITE = (242, 248, 255)
MUTED = (170, 190, 210)
GOLD = (251, 191, 36)
NAVY = (7, 17, 29)
BADGE_BASE = "https://lsm-static-prod.livescore.com/medium/"
TAIL = 0.45          # silence after each line so the cut is never early
INTRO_MIN = 5.0      # logo sting, seconds
MAX_PICKS = 7
MIN_TOTAL = 60.0
MAX_TOTAL = 120.0


def hold_seconds(index: int, speech: float) -> float:
    """Slide length = this clip's speech. Intro never shorter than 5s. Never trim speech."""
    speech = max(0.0, float(speech or 0.0))
    if index == 0:
        return max(INTRO_MIN, speech + TAIL)
    return speech + TAIL


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("ffmpeg is required to build the reel") from exc


def _probe(path: Path, ff: str) -> float:
    out = subprocess.run([ff, "-i", str(path)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", out)
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def _run(ff_cmd: list, label: str) -> None:
    r = subprocess.run(ff_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{label} failed:\n{r.stdout[-1500:]}")


def _font(size: int, bold: bool = True):
    from PIL import ImageFont
    names = (
        ["DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"]
        + (["LiberationSans-Bold.ttf"] if bold else ["LiberationSans-Regular.ttf"])
    )
    roots = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation", "/usr/share/fonts/truetype"]
    for root in roots:
        for n in names:
            p = Path(root) / n
            if p.exists():
                return ImageFont.truetype(str(p), size)
            # nested
            for q in Path(root).rglob(n) if Path(root).exists() else []:
                return ImageFont.truetype(str(q), size)
    return ImageFont.load_default()


def _tw(draw, s, fnt) -> int:
    b = draw.textbbox((0, 0), s, font=fnt)
    return b[2] - b[0]


def _wrap(draw, s, fnt, max_w, limit=3):
    words = str(s or "").split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if _tw(draw, trial, fnt) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines[:limit] or [""]


def _cover(path: Path, dark: float = 0.55):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    scale = max(W / im.width, H / im.height)
    im = im.resize((int(im.width * scale) + 1, int(im.height * scale) + 1), Image.Resampling.LANCZOS)
    x = (im.width - W) // 2
    y = (im.height - H) // 2
    im = im.crop((x, y, x + W, y + H))
    overlay = Image.new("RGB", im.size, NAVY)
    return Image.blend(im, overlay, dark)


def _circle_badge(path: Path, d: int):
    from PIL import Image, ImageDraw
    im = Image.open(path).convert("RGBA").resize((d, d), Image.Resampling.LANCZOS)
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse((1, 1, d - 2, d - 2), fill=255)
    out = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    ring = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse((1, 1, d - 2, d - 2), outline=(255, 255, 255, 230), width=4)
    return Image.alpha_composite(out, ring)


def _wordmark(d, y=64):
    fnt = _font(42, True)
    lab = "PLAYREPORT"
    d.text(((W - _tw(d, lab, fnt)) // 2, y), lab, fill=WHITE, font=fnt)
    d.rectangle(((W - 120) // 2, y + 52, (W + 120) // 2, y + 56), fill=GREEN)


def render_intro(logo: Path, bg: Path, dest: Path) -> None:
    from PIL import Image, ImageDraw, ImageFilter
    im = _cover(bg, 0.55)
    L = Image.open(logo).convert("RGBA").resize((520, 520), Image.Resampling.LANCZOS)
    glow = L.filter(ImageFilter.GaussianBlur(24))
    xy = ((W - 520) // 2, 420)
    im.paste(glow, xy, glow)
    im.paste(L, xy, L)
    d = ImageDraw.Draw(im)
    _wordmark(d, 180)
    sub = _font(28, True)
    s = "TONIGHT'S SHORTLIST"
    d.text(((W - _tw(d, s, sub)) // 2, 1120), s, fill=GREEN, font=sub)
    tiny = _font(22, False)
    t = "Football intelligence  ·  SAST"
    d.text(((W - _tw(d, t, tiny)) // 2, 1170), t, fill=MUTED, font=tiny)
    im.convert("RGB").save(dest, quality=92)


def render_pick(pick: dict, i: int, n: int, bg: Path, home_b: Path, away_b: Path, dest: Path) -> None:
    from PIL import ImageDraw
    im = _cover(bg, 0.58)
    d = ImageDraw.Draw(im)
    _wordmark(d, 64)
    k = f"PICK {i} OF {n}"
    d.text(((W - _tw(d, k, _font(22, True))) // 2, 150), k, fill=GREEN, font=_font(22, True))
    size, gap = 200, 90
    hb = _circle_badge(home_b, size)
    ab = _circle_badge(away_b, size)
    total = size * 2 + gap
    x0, y0 = (W - total) // 2, 220
    im.paste(hb, (x0, y0), hb)
    im.paste(ab, (x0 + size + gap, y0), ab)
    d = ImageDraw.Draw(im)
    d.text((x0 + size + (gap - _tw(d, "VS", _font(24, True))) // 2, y0 + size // 2 - 14), "VS", fill=WHITE, font=_font(24, True))
    nf = _font(26, True)
    for team, cx in ((pick.get("home") or "", x0 + size // 2), (pick.get("away") or "", x0 + size + gap + size // 2)):
        yy = y0 + size + 14
        for ln in _wrap(d, team, nf, size + 40, 2):
            d.text((cx - _tw(d, ln, nf) // 2, yy), ln, fill=WHITE, font=nf)
            yy += 32
    d.rounded_rectangle((80, 700, W - 80, 1500), 36, fill=(8, 22, 38), outline=GREEN, width=3)
    lf = _font(32, True)
    y = 750
    for ln in _wrap(d, pick.get("label") or "", lf, W - 220, 3):
        d.text(((W - _tw(d, ln, lf)) // 2, y), ln, fill=WHITE, font=lf)
        y += 46
    odds = pick.get("odds")
    od = f"{odds:.2f}" if isinstance(odds, (int, float)) else "N/A"
    of = _font(96, True)
    d.text(((W - _tw(d, od, of)) // 2, y + 8), od, fill=GREEN, font=of)
    cap = "SPORTYBET PRICE"
    d.text(((W - _tw(d, cap, _font(18, True))) // 2, y + 118), cap, fill=MUTED, font=_font(18, True))
    p = pick.get("p")
    pct = f"{round(p * 100)}%" if p is not None else "N/A"
    row = f"MODEL  {pct}"
    d.text(((W - _tw(d, row, _font(48, True))) // 2, 1270), row, fill=GOLD, font=_font(48, True))
    ko = str(pick.get("kickoff") or "")[11:16]
    kt = f"KICK-OFF  {ko} SAST" if ko else ""
    d.text(((W - _tw(d, kt, _font(26, True))) // 2, 1350), kt, fill=MUTED, font=_font(26, True))
    d.rectangle((80, 1780, W - 80, 1790), fill=(20, 48, 74))
    d.rectangle((80, 1780, 80 + int(i / max(n, 1) * (W - 160)), 1790), fill=GREEN)
    foot = "PlayReport  ·  not betting advice  ·  18+"
    d.text(((W - _tw(d, foot, _font(20, False))) // 2, 1820), foot, fill=MUTED, font=_font(20, False))
    im.convert("RGB").save(dest, quality=92)


def render_closer(logo: Path, bg: Path, dest: Path) -> None:
    from PIL import Image, ImageDraw
    im = _cover(bg, 0.6)
    L = Image.open(logo).convert("RGBA").resize((280, 280), Image.Resampling.LANCZOS)
    im.paste(L, ((W - 280) // 2, 520), L)
    d = ImageDraw.Draw(im)
    _wordmark(d, 180)
    t = "THAT'S THE LIST"
    d.text(((W - _tw(d, t, _font(48, True))) // 2, 860), t, fill=WHITE, font=_font(48, True))
    s = "Open the app for the full analysis"
    d.text(((W - _tw(d, s, _font(28, False))) // 2, 940), s, fill=MUTED, font=_font(28, False))
    n = "Statistical information, not betting advice. 18+."
    d.text(((W - _tw(d, n, _font(22, False))) // 2, 1180), n, fill=MUTED, font=_font(22, False))
    im.convert("RGB").save(dest, quality=92)


def fetch_badge(rel: str, dest: Path, fallback: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 100:
        return dest
    if rel:
        try:
            req = urllib.request.Request(BADGE_BASE + rel, headers={"User-Agent": "Mozilla/5.0 PlayReport"})
            with urllib.request.urlopen(req, timeout=15) as r:
                dest.write_bytes(r.read())
            if dest.stat().st_size > 100:
                return dest
        except Exception as exc:  # noqa: BLE001
            log.warning("badge fetch failed %s: %s", rel, exc)
    shutil.copy(fallback, dest)
    return dest


def speak_espeak(text: str, wav: Path) -> None:
    """Male English narrator for the daily CI reel (not the Arena session voice)."""
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise RuntimeError("espeak-ng is not installed")
    wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [exe, "-v", "en-gb", "-s", "150", "-p", "35", "-a", "140", "-w", str(wav), text]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0 or not wav.exists():
        raise RuntimeError(f"espeak failed: {r.stdout[-400:]}")


def pad_audio(src: Path, dest: Path, duration: float, ff: str) -> None:
    """Force a clip to `duration` seconds (pad with silence, never trim speech)."""
    _run([
        ff, "-y", "-i", str(src), "-af", f"apad=whole_dur={duration:.3f}",
        "-t", f"{duration:.3f}", str(dest),
    ], "pad")


def still_clip(img: Path, dest: Path, duration: float, ff: str) -> None:
    _run([
        ff, "-y", "-loop", "1", "-framerate", str(FPS), "-t", f"{duration:.3f}", "-i", str(img),
        "-vf", f"scale={W}:{H},format=yuv420p", "-r", str(FPS),
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-an", str(dest),
    ], "still")


def pick_script(p: dict) -> str:
    home, away = p.get("home") or "", p.get("away") or ""
    label = p.get("label") or "the selection"
    odds = p.get("odds")
    od = f"{odds:.2f}" if isinstance(odds, (int, float)) else "N/A"
    pct = f"{round(p['p'] * 100)} percent" if p.get("p") is not None else "N/A"
    ko = str(p.get("kickoff") or "")[11:16]
    spoken_ko = ko
    if ko.endswith(":00"):
        h = int(ko[:2])
        spoken_ko = f"{h if h <= 12 else h - 12} PM" if h >= 12 else f"{h} AM"
    return f"{home} versus {away}. {label}, at {od}. Model, {pct}. Kick-off, {spoken_ko}."


def overs_only(picks: list) -> list:
    out = []
    for p in picks or []:
        if "under" in str(p.get("label") or "").lower() or "under" in str(p.get("sel") or "").lower():
            continue
        out.append(p)
        if len(out) >= MAX_PICKS:
            break
    return out


def build(picks: list, outfile: Path, *, assets: Path, work: Path | None = None,
          voice_clips: list[Path] | None = None, fixtures: list | None = None) -> Path:
    """Build a 9:16 reel. `voice_clips` if set must be [intro, *picks, closer] audio files.
    Slide length = that clip's duration + TAIL (intro at least INTRO_MIN). No music.
    """
    from PIL import Image  # noqa: F401  — imported for a clear error if missing

    ff = _ffmpeg()
    picks = overs_only(picks)
    if not picks:
        raise ValueError("no shortlist picks for the reel")
    assets = Path(assets)
    logo = assets / "logo.png"
    bgs = [assets / "bg_stadium.jpg", assets / "bg_pitch.jpg", assets / "bg_lights.jpg"]
    fx_by_id = {str(f.get("id")): f for f in (fixtures or [])}

    work = Path(work) if work else Path(tempfile.mkdtemp(prefix="pr-reel-"))
    work.mkdir(parents=True, exist_ok=True)
    slides_dir = work / "slides"
    slides_dir.mkdir(exist_ok=True)
    audio_dir = work / "audio"
    audio_dir.mkdir(exist_ok=True)
    crests = work / "crests"
    crests.mkdir(exist_ok=True)

    n = len(picks)
    render_intro(logo, bgs[0], slides_dir / "intro.jpg")
    for i, p in enumerate(picks, 1):
        fx = fx_by_id.get(str(p.get("fixture") or "")) or {}
        badges = fx.get("badges") or {}
        hb = fetch_badge(badges.get("home"), crests / f"h{i}.png", logo)
        ab = fetch_badge(badges.get("away"), crests / f"a{i}.png", logo)
        render_pick(p, i, n, bgs[i % 3], hb, ab, slides_dir / f"p{i:02d}.jpg")
    render_closer(logo, bgs[2], slides_dir / "closer.jpg")

    texts = ["PlayReport. Tonight's shortlist."] + [pick_script(p) for p in picks] + [
        "That's PlayReport. Open the app for the full analysis. Not betting advice. Eighteen plus."
    ]
    images = [slides_dir / "intro.jpg"] + [slides_dir / f"p{i:02d}.jpg" for i in range(1, n + 1)] + [slides_dir / "closer.jpg"]

    if voice_clips is not None and len(voice_clips) != len(images):
        raise ValueError(f"voice_clips ({len(voice_clips)}) must match slides ({len(images)})")

    durations = []
    wavs = []
    for i, (img, text) in enumerate(zip(images, texts)):
        raw = audio_dir / f"raw{i:02d}.wav"
        if voice_clips is not None:
            # convert whatever we were given (mp3/wav) to wav
            _run([ff, "-y", "-i", str(voice_clips[i]), str(raw)], f"decode {i}")
        else:
            speak_espeak(text, raw)
        d = _probe(raw, ff)
        hold = hold_seconds(i, d)
        padded = audio_dir / f"a{i:02d}.wav"
        pad_audio(raw, padded, hold, ff)
        wavs.append(padded)
        durations.append(hold)

    total = sum(durations)
    # keep 1–2 min: drop trailing picks if over, never go under 60 by shortening speech
    if total > MAX_TOTAL and len(picks) > 3:
        log.info("reel %.1fs > 2 min — dropping last pick", total)
        vc = None if voice_clips is None else list(voice_clips[:-2]) + [voice_clips[-1]]
        return build(picks[:-1], outfile, assets=assets, work=work, voice_clips=vc, fixtures=fixtures)
    if total < MIN_TOTAL:
        extra = MIN_TOTAL - total
        durations[-1] += extra
        pad_audio(wavs[-1], wavs[-1], durations[-1], ff)
        total = sum(durations)

    clips = []
    for i, (img, dur) in enumerate(zip(images, durations)):
        clip = work / f"v{i:02d}.mp4"
        still_clip(img, clip, dur, ff)
        clips.append(clip)

    lst_v = work / "v.txt"
    lst_v.write_text("".join(f"file '{c}'\n" for c in clips))
    silent = work / "silent.mp4"
    _run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(lst_v), "-c", "copy", str(silent)], "concat v")

    lst_a = work / "a.txt"
    lst_a.write_text("".join(f"file '{w}'\n" for w in wavs))
    voice = work / "voice.wav"
    _run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(lst_a), "-c", "copy", str(voice)], "concat a")

    outfile = Path(outfile)
    outfile.parent.mkdir(parents=True, exist_ok=True)
    # voice only — no music bed
    _run([
        ff, "-y", "-i", str(silent), "-i", str(voice),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(outfile),
    ], "mux")
    log.info("reel built %s (%.1fs, %d KB)", outfile.name, total, outfile.stat().st_size // 1024)
    return outfile


def from_shortlist(sl_pub: dict, fixtures: list, outfile: Path, assets: Path, work: Path | None = None) -> Path:
    return build((sl_pub or {}).get("primary") or [], outfile, assets=assets, work=work, fixtures=fixtures)
