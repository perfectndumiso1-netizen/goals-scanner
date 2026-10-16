"""PlayReport shortlist video — 16:9 widescreen (1920x1080), narrated slides, no bed music or trailing silence.

Starts with the settled results of yesterday's shortlist selections (when available), then proceeds
to today's shortlist selections. Each slide lasts exactly as long as its own voice clip (plus a short tail),
so the next match never appears while the previous one is still being read.
"""
from __future__ import annotations

import logging
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

log = logging.getLogger("scanner")

W, H, FPS = 1920, 1080, 30
GREEN = (0, 200, 111)
RED = (239, 68, 68)
WHITE = (242, 248, 255)
MUTED = (170, 190, 210)
GOLD = (251, 191, 36)
NAVY = (7, 17, 29)
CARD_BG = (8, 22, 38)
BADGE_BASE = "https://lsm-static-prod.livescore.com/medium/"
TAIL = 0.70          # extra hold after speech so the next match never appears mid-sentence
INTRO_MIN = 5.0      # logo sting, seconds
MAX_PICKS = 7
MAX_TOTAL = 120.0
# Ultra-realistic neural British male voices (CI/local), with male eSpeak-NG as emergency fallback.
EDGE_TTS_VOICE = "en-GB-RyanNeural"
EDGE_TTS_RATE = "-4%"
EDGE_TTS_PITCH = "-2Hz"
PIPER_VOICE_MODEL = "en_GB-alan-medium.onnx"
ESPEAK_VOICE = "en-gb"
ESPEAK_SPEED = 150
ESPEAK_PITCH = 40

INTRO_SCRIPT = "PlayReport. Today's shortlist."
DISCLAIMER_SCRIPT = (
    "Statistical information, not betting advice. Bet responsibly. "
    "Not for persons under the age of 18. Do not bet with money you cannot afford to lose. "
    "There is no such thing as a sure bet."
)
CLOSER_SCRIPT = (
    "If this helped, like, share, or subscribe for tomorrow's list. "
    "PlayReport. All rights reserved."
)


def hold_seconds(index: int, speech: float) -> float:
    """Slide length = this clip's speech. Intro never shorter than 5s. Never trim speech."""
    speech = max(0.0, float(speech or 0.0))
    if index == 0:
        return max(INTRO_MIN, speech + TAIL)
    return speech + TAIL


def frame_hold(seconds: float) -> float:
    """Round duration up to a whole video frame so the picture outlasts the voice."""
    return math.ceil(max(0.0, float(seconds)) * FPS) / FPS


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


def _wordmark(d, y=44):
    fnt = _font(38, True)
    lab = "PLAYREPORT"
    d.text(((W - _tw(d, lab, fnt)) // 2, y), lab, fill=WHITE, font=fnt)
    d.rectangle(((W - 120) // 2, y + 48, (W + 120) // 2, y + 52), fill=GREEN)


def _draw_form_pills(d, form_str: str, cx: int, y: int) -> None:
    """Draw up to 5 W/D/L form pills centered at cx."""
    chars = [c for c in str(form_str or "").upper() if c in ("W", "D", "L")][:5]
    if not chars:
        return
    pw, ph, gap = 30, 26, 6
    total_w = len(chars) * pw + (len(chars) - 1) * gap
    x = cx - total_w // 2
    fnt = _font(15, True)
    colors = {"W": (34, 197, 94), "D": (100, 116, 139), "L": (239, 68, 68)}
    for ch in chars:
        d.rounded_rectangle((x, y, x + pw, y + ph), 6, fill=colors[ch])
        d.text((x + (pw - _tw(d, ch, fnt)) // 2, y + 4), ch, fill=NAVY if ch == "W" else WHITE, font=fnt)
        x += pw + gap


def render_intro(logo: Path, bg: Path, dest: Path) -> None:
    from PIL import Image, ImageDraw, ImageFilter
    im = _cover(bg, 0.55)
    L = Image.open(logo).convert("RGBA").resize((360, 360), Image.Resampling.LANCZOS)
    glow = L.filter(ImageFilter.GaussianBlur(24))
    xy = ((W - 360) // 2, 180)
    im.paste(glow, xy, glow)
    im.paste(L, xy, L)
    d = ImageDraw.Draw(im)
    _wordmark(d, 64)
    sub = _font(44, True)
    s = "TODAY'S SHORTLIST"
    d.text(((W - _tw(d, s, sub)) // 2, 600), s, fill=GREEN, font=sub)
    tiny = _font(26, False)
    t = "Football intelligence  ·  Results recap & today's selections  ·  SAST"
    d.text(((W - _tw(d, t, tiny)) // 2, 668), t, fill=MUTED, font=tiny)
    foot = "PlayReport  ·  18+"
    d.text(((W - _tw(d, foot, _font(20, True))) // 2, H - 64), foot, fill=MUTED, font=_font(20, True))
    im.convert("RGB").save(dest, quality=92)


def render_disclaimer(logo: Path, bg: Path, dest: Path) -> None:
    from PIL import Image, ImageDraw
    im = _cover(bg, 0.64)
    L = Image.open(logo).convert("RGBA").resize((130, 130), Image.Resampling.LANCZOS)
    im.paste(L, ((W - 130) // 2, 48), L)
    d = ImageDraw.Draw(im)
    _wordmark(d, 195)
    d.rounded_rectangle((220, 285, W - 220, H - 110), 32, fill=CARD_BG, outline=GREEN, width=3)
    title = "PLEASE BET RESPONSIBLY"
    d.text(((W - _tw(d, title, _font(38, True))) // 2, 330), title, fill=GREEN, font=_font(38, True))
    lines = [
        "Statistical information, not betting advice.",
        "Not for persons under the age of 18.",
        "Do not bet with money you cannot afford to lose.",
        "There is no such thing as a sure bet.",
    ]
    y = 430
    fnt = _font(30, False)
    for ln in lines:
        for wrapped in _wrap(d, ln, fnt, W - 520, 2):
            d.text(((W - _tw(d, wrapped, fnt)) // 2, y), wrapped, fill=WHITE, font=fnt)
            y += 46
        y += 18
    foot = "PlayReport  ·  18+"
    d.text(((W - _tw(d, foot, _font(20, True))) // 2, H - 64), foot, fill=MUTED, font=_font(20, True))
    im.convert("RGB").save(dest, quality=92)


def render_results(results: list[dict], logo: Path, bg: Path, dest: Path, *, day_label: str = "") -> None:
    """16:9 widescreen slide recapping yesterday's settled shortlist selections before today's picks."""
    from PIL import ImageDraw
    im = _cover(bg, 0.62)
    d = ImageDraw.Draw(im)
    _wordmark(d, 36)
    head = "YESTERDAY'S SHORTLIST RESULTS" + (f"  ·  {day_label}" if day_label else "")
    d.text(((W - _tw(d, head, _font(26, True))) // 2, 104), head, fill=GREEN, font=_font(26, True))

    settled = [r for r in results if r.get("result") in ("hit", "miss")]
    hits = sum(1 for r in settled if r.get("result") == "hit")
    rate_str = f"  ({round(100 * hits / len(settled))}%)" if settled else ""
    summary = f"{hits} OF {len(settled)} SELECTIONS WON{rate_str}" if settled else f"{len(results)} SELECTIONS RECAP"
    d.text(((W - _tw(d, summary, _font(34, True))) // 2, 144), summary, fill=GOLD, font=_font(34, True))

    d.rounded_rectangle((110, 205, W - 110, H - 95), 28, fill=CARD_BG, outline=GREEN, width=3)
    rows = results[:MAX_PICKS]
    if rows:
        row_h = min(102, (H - 330) // max(len(rows), 1))
        y = 225
        for idx, r in enumerate(rows, 1):
            if idx > 1:
                d.rectangle((145, y - 6, W - 145, y - 5), fill=(20, 48, 74))
            match_txt = f"{r.get('home') or ''} v {r.get('away') or ''}"
            comp_txt = competition_line(r)
            d.text((150, y + 6), match_txt[:42], fill=WHITE, font=_font(25, True))
            if comp_txt:
                d.text((150, y + 40), comp_txt[:52], fill=MUTED, font=_font(18, False))

            odds = r.get("odds")
            od = f" @ {odds:.2f}" if isinstance(odds, (int, float)) else ""
            sel_txt = f"{r.get('label') or r.get('sel') or ''}{od}"
            d.text((820, y + 18), sel_txt[:38], fill=WHITE, font=_font(24, True))

            sc = str(r.get("score") or "").strip()
            if sc:
                ft_txt = f"FT {sc}"
                d.text((1430, y + 20), ft_txt, fill=GOLD, font=_font(24, True))

            res = str(r.get("result") or "").lower()
            badge_lbl = "WON" if res == "hit" else "LOST" if res == "miss" else "VOID"
            badge_col = GREEN if res == "hit" else RED if res == "miss" else MUTED
            bx0, by0, bx1, by1 = 1600, y + 10, 1765, y + 60
            d.rounded_rectangle((bx0, by0, bx1, by1), 12, fill=badge_col)
            bf = _font(22, True)
            d.text(
                (bx0 + (bx1 - bx0 - _tw(d, badge_lbl, bf)) // 2, by0 + 12),
                badge_lbl,
                fill=NAVY if res == "hit" else WHITE,
                font=bf,
            )
            y += row_h

    foot = "PlayReport  ·  verified pre-match shortlist ledger  ·  18+"
    d.text(((W - _tw(d, foot, _font(20, False))) // 2, H - 56), foot, fill=MUTED, font=_font(20, False))
    im.convert("RGB").save(dest, quality=92)


def render_pick(pick: dict, i: int, n: int, bg: Path, home_b: Path, away_b: Path, dest: Path) -> None:
    from PIL import ImageDraw
    im = _cover(bg, 0.58)
    d = ImageDraw.Draw(im)
    _wordmark(d, 36)
    k = f"TODAY'S SHORTLIST  ·  PICK {i} OF {n}"
    d.text(((W - _tw(d, k, _font(24, True))) // 2, 102), k, fill=GREEN, font=_font(24, True))
    comp = competition_line(pick)
    if comp:
        d.text(((W - _tw(d, comp, _font(22, False))) // 2, 138), comp, fill=MUTED, font=_font(22, False))

    # Left panel: Home & Away crests, team names, and recent form pills when available
    size, gap = 180, 110
    hb = _circle_badge(home_b, size)
    ab = _circle_badge(away_b, size)
    left_cx = 500
    total = size * 2 + gap
    x0, y0 = left_cx - total // 2, 260
    im.paste(hb, (x0, y0), hb)
    im.paste(ab, (x0 + size + gap, y0), ab)
    d = ImageDraw.Draw(im)
    d.text((x0 + size + (gap - _tw(d, "VS", _font(28, True))) // 2, y0 + size // 2 - 16), "VS", fill=WHITE, font=_font(28, True))
    nf = _font(26, True)
    for team, form_key, cx in (
        (pick.get("home") or "", "form_h", x0 + size // 2),
        (pick.get("away") or "", "form_a", x0 + size + gap + size // 2),
    ):
        yy = y0 + size + 22
        for ln in _wrap(d, team, nf, size + 70, 2):
            d.text((cx - _tw(d, ln, nf) // 2, yy), ln, fill=WHITE, font=nf)
            yy += 34
        if pick.get(form_key):
            _draw_form_pills(d, str(pick.get(form_key)), cx, yy + 10)

    # Right panel: Selection card, Sportybet price, and SAST kick-off badge
    rx0, ry0, rx1, ry1 = 940, 210, W - 110, 885
    rcx = (rx0 + rx1) // 2
    d.rounded_rectangle((rx0, ry0, rx1, ry1), 34, fill=CARD_BG, outline=GREEN, width=3)
    eyebrow = "QUALIFIED SELECTION"
    d.text((rcx - _tw(d, eyebrow, _font(20, True)) // 2, ry0 + 42), eyebrow, fill=GREEN, font=_font(20, True))

    lf = _font(38, True)
    y = ry0 + 95
    for ln in _wrap(d, pick.get("label") or "", lf, (rx1 - rx0) - 90, 3):
        d.text((rcx - _tw(d, ln, lf) // 2, y), ln, fill=WHITE, font=lf)
        y += 50

    odds = pick.get("odds")
    od = f"{odds:.2f}" if isinstance(odds, (int, float)) else "N/A"
    of = _font(112, True)
    d.text((rcx - _tw(d, od, of) // 2, y + 18), od, fill=GREEN, font=of)
    cap = "SPORTYBET PRICE"
    d.text((rcx - _tw(d, cap, _font(20, True)) // 2, y + 148), cap, fill=MUTED, font=_font(20, True))

    ko = str(pick.get("kickoff") or "")[11:16]
    kt = f"KICK-OFF  {ko} SAST" if ko else "TODAY  ·  SAST"
    kf = _font(30, True)
    kw = _tw(d, kt, kf) + 56
    d.rounded_rectangle((rcx - kw // 2, ry1 - 115, rcx + kw // 2, ry1 - 52), 18, fill=(16, 40, 66), outline=GOLD, width=2)
    d.text((rcx - _tw(d, kt, kf) // 2, ry1 - 101), kt, fill=GOLD, font=kf)

    # Progress bar & footer
    d.rectangle((110, H - 115, W - 110, H - 103), fill=(20, 48, 74))
    d.rectangle((110, H - 115, 110 + int(i / max(n, 1) * (W - 220)), H - 103), fill=GREEN)
    foot = "PlayReport  ·  not betting advice  ·  18+"
    d.text(((W - _tw(d, foot, _font(20, False))) // 2, H - 64), foot, fill=MUTED, font=_font(20, False))
    im.convert("RGB").save(dest, quality=92)


def render_closer(logo: Path, bg: Path, dest: Path) -> None:
    from PIL import Image, ImageDraw
    im = _cover(bg, 0.6)
    L = Image.open(logo).convert("RGBA").resize((240, 240), Image.Resampling.LANCZOS)
    im.paste(L, ((W - 240) // 2, 165), L)
    d = ImageDraw.Draw(im)
    _wordmark(d, 64)
    t = "THAT'S THE LIST"
    d.text(((W - _tw(d, t, _font(50, True))) // 2, 445), t, fill=WHITE, font=_font(50, True))
    s = "Like, share or subscribe if this helped — no pressure."
    d.text(((W - _tw(d, s, _font(28, False))) // 2, 525), s, fill=MUTED, font=_font(28, False))
    n = "Statistical information, not betting advice. 18+."
    d.text(((W - _tw(d, n, _font(24, False))) // 2, 625), n, fill=MUTED, font=_font(24, False))
    c = "© PlayReport. All rights reserved."
    d.text(((W - _tw(d, c, _font(24, True))) // 2, 725), c, fill=WHITE, font=_font(24, True))
    p = "Unauthorised copying or re-upload is prohibited."
    d.text(((W - _tw(d, p, _font(20, False))) // 2, 770), p, fill=MUTED, font=_font(20, False))
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


def _fixture_key(values) -> tuple[str, str, str, str] | None:
    if not isinstance(values, (list, tuple)) or len(values) < 4:
        return None
    return (str(values[0] or "")[:10], str(values[1] or ""), str(values[2] or ""), str(values[3] or ""))


def fixture_for_pick(pick: dict, fixtures: list | None) -> dict | None:
    """Resolve either the published fixture ID or shortlist's raw (date, country, home, away) key."""
    by_id, by_key, by_teams = {}, {}, {}
    for fixture in fixtures or []:
        fid = str(fixture.get("id") or "")
        if fid:
            by_id[fid] = fixture
        key = _fixture_key((fixture.get("date"), fixture.get("country"), fixture.get("home"), fixture.get("away")))
        if key:
            by_key[key] = fixture
            by_teams[(key[0], key[2], key[3])] = fixture
    fid = str(pick.get("fixture") or "")
    if fid and fid in by_id:
        return by_id[fid]
    key = _fixture_key(pick.get("key"))
    if key and key in by_key:
        return by_key[key]
    if not key:
        key = _fixture_key((pick.get("date"), pick.get("country"), pick.get("home"), pick.get("away")))
    if key:
        return by_teams.get((key[0], key[2], key[3]))
    return None


def badges_for_pick(pick: dict, fixtures: list | None) -> dict:
    fixture = fixture_for_pick(pick, fixtures) or {}
    return pick.get("badges") or fixture.get("badges") or {}


def spoken_text(text: str) -> str:
    """Normalise football abbreviations and telegraphic punctuation for natural broadcast speech."""
    out = str(text or "")
    out = re.sub(r"\bUtd\b\.?", "United", out)
    out = re.sub(r"\bSt\.\s*(?=[A-Z])", "Saint ", out)
    out = re.sub(r"\bTurkiye\b", "Turkey", out)
    out = out.replace("Süper Lig", "Super Lig")
    out = re.sub(r"\bDjurgaarden\b", "Djurgarden", out)
    out = re.sub(r"\bMjaellby\b", "Mjallby", out)
    out = re.sub(r"\bLillestroem\b", "Lillestrom", out)
    out = re.sub(r"\bDeportivo A Coruna\b", "Deportivo La Coruna", out)
    out = re.sub(r"\bPFC CSKA\b", "CSKA", out)
    out = re.sub(r"\b1\.\s*FC\b", "FC", out)
    out = re.sub(r",\s*won,\s*(\d+)\s+to\s+(\d+)\.", r" landed, finishing \1 to \2.", out)
    out = re.sub(r",\s*lost,\s*(\d+)\s+to\s+(\d+)\.", r" missed, finishing \1 to \2.", out)
    out = re.sub(r",\s*at\s+(\d+\.\d+)\.", r" at \1.", out)
    out = out.replace("Kick-off, ", "Kick-off at ")
    return out


def synthesize_speech(text: str, wav: Path) -> None:
    """Use ultra-realistic male neural TTS (Edge-TTS RyanNeural or Piper Alan medium), with male eSpeak-NG fallback."""
    wav.parent.mkdir(parents=True, exist_ok=True)
    clean = spoken_text(text)

    edge_py = os.environ.get("EDGE_TTS_PYTHON")
    if edge_py and Path(edge_py).is_file():
        voice = os.environ.get("EDGE_TTS_VOICE") or EDGE_TTS_VOICE
        rate = os.environ.get("EDGE_TTS_RATE") or EDGE_TTS_RATE
        pitch = os.environ.get("EDGE_TTS_PITCH") or EDGE_TTS_PITCH
        mp3 = wav.with_suffix(".edge.mp3")
        try:
            cmd = [
                edge_py, "-m", "edge_tts",
                "--voice", voice,
                f"--rate={rate}",
                f"--pitch={pitch}",
                "--text", clean,
                "--write-media", str(mp3),
            ]
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30)
            if r.returncode == 0 and mp3.exists() and mp3.stat().st_size > 200:
                ff = _ffmpeg()
                _run([ff, "-y", "-i", str(mp3), "-ac", "1", "-ar", "44100", str(wav)], "edge_tts decode")
                mp3.unlink(missing_ok=True)
                if wav.exists():
                    return
        except Exception as exc:  # noqa: BLE001
            log.warning("Edge-TTS neural voice fallback to Piper/eSpeak: %s", exc)
        finally:
            mp3.unlink(missing_ok=True)

    model = os.environ.get("PIPER_MODEL_PATH")
    config = os.environ.get("PIPER_CONFIG_PATH")
    if model or config:
        if not model or not config or not Path(model).is_file() or not Path(config).is_file():
            raise RuntimeError("Piper voice is configured but its model or config file is missing")
        python = os.environ.get("PIPER_PYTHON") or sys.executable
        cmd = [python, "-m", "piper", "-m", model, "-c", config, "-f", str(wav), "--", clean]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if r.returncode != 0 or not wav.exists():
            raise RuntimeError(f"Piper TTS failed: {r.stdout[-400:]}")
        return

    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise RuntimeError("Piper is not configured and espeak-ng is not installed")
    cmd = [exe, "-v", ESPEAK_VOICE, "-s", str(ESPEAK_SPEED), "-p", str(ESPEAK_PITCH), "-a", "150", "-w", str(wav), clean]
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


def competition_line(p: dict) -> str:
    country = str(p.get("country") or "").strip()
    league = str(p.get("league") or "").strip()
    if country and league and country.lower() != league.lower():
        return f"{country}  ·  {league}"
    return country or league


def spoken_kickoff(p: dict) -> str:
    ko = str(p.get("kickoff") or "")[11:16]
    m = re.match(r"^(\d{1,2}):(\d{2})$", ko)
    if m:
        h, mins = int(m.group(1)), m.group(2)
        ampm = "PM" if h >= 12 else "AM"
        h12 = 12 if h % 12 == 0 else h % 12
        if mins == "00":
            return f"{h12} {ampm}"
        return f"{h12}:{mins} {ampm}"
    return ko


def pick_script(p: dict) -> str:
    home, away = p.get("home") or "", p.get("away") or ""
    label = p.get("label") or "the selection"
    odds = p.get("odds")
    od = f"{odds:.2f}" if isinstance(odds, (int, float)) else "N/A"
    comp = ", ".join(x for x in (str(p.get("country") or "").strip(), str(p.get("league") or "").strip()) if x)
    head = f"{comp}. " if comp else ""
    return f"{head}{home} versus {away}. {label}, at {od}. Kick-off, {spoken_kickoff(p)}."


def reel_results(yesterday: dict | list | None) -> list[dict]:
    """Extract settled yesterday shortlist rows for the video recap (Overs goals/corners/bookings, max MAX_PICKS)."""
    if not yesterday:
        return []
    items = yesterday.get("items") if isinstance(yesterday, dict) else yesterday
    if not isinstance(items, list):
        return []
    settled = [x for x in items if isinstance(x, dict) and str(x.get("result") or "").lower() in ("hit", "miss", "void")]
    filtered = [x for x in settled if is_reel_market(x)]
    chosen = filtered if filtered else settled
    return chosen[:MAX_PICKS]


def results_script(results: list[dict]) -> str:
    """Spoken narration for yesterday's shortlist results slide — factual, no model probabilities."""
    rows = reel_results(results)
    if not rows:
        return ""
    settled = [r for r in rows if r.get("result") in ("hit", "miss")]
    hits = sum(1 for r in settled if r.get("result") == "hit")
    lead = (
        f"Yesterday's shortlist results. {hits} of {len(settled)} selections won. "
        if settled
        else "Yesterday's shortlist results. "
    )
    parts = []
    for r in rows:
        home, away = r.get("home") or "", r.get("away") or ""
        label = r.get("label") or r.get("sel") or "selection"
        res = str(r.get("result") or "").lower()
        verdict = "won" if res == "hit" else "lost" if res == "miss" else "void"
        sc = str(r.get("score") or "").strip().replace("-", " to ")
        score_bit = f", {sc}" if sc else ""
        parts.append(f"{home} versus {away}, {label}, {verdict}{score_bit}.")
    return lead + " ".join(parts) + " Now, today's shortlist."


def is_reel_market(p: dict) -> bool:
    """Goals, corners and bookings only. Unders stay out of the video."""
    blob = " ".join(str(p.get(k) or "") for k in ("label", "sel", "market", "group")).lower()
    if "under" in blob:
        return False
    if any(w in blob for w in ("corner", "card", "booking", "yellow")):
        return True
    if any(w in blob for w in ("over", "btts", "both teams", "to score", "team goal", "goals")):
        return True
    return False


def reel_picks(picks: list) -> list:
    out = []
    for p in picks or []:
        if not is_reel_market(p):
            continue
        out.append(p)
        if len(out) >= MAX_PICKS:
            break
    return out


def overs_only(picks: list) -> list:
    """Kept name for scanner.py: video markets are goals / corners / bookings, Overs-side only."""
    return reel_picks(picks)


def build(picks: list, outfile: Path, *, assets: Path, work: Path | None = None,
          voice_clips: list[Path] | None = None, fixtures: list | None = None,
          yesterday_results: dict | list | None = None) -> Path:
    """Build a 16:9 widescreen video. Starts with yesterday's settled results when provided, then today's picks.
    Slide length = that clip's duration + TAIL (intro at least INTRO_MIN). No music.
    """
    from PIL import Image  # noqa: F401  — imported for a clear error if missing

    ff = _ffmpeg()
    picks = reel_picks(picks)
    if not picks:
        raise ValueError("no shortlist picks for the reel")
    recap = reel_results(yesterday_results)
    recap_day = yesterday_results.get("day", "") if isinstance(yesterday_results, dict) else ""

    assets = Path(assets)
    logo = assets / "logo.png"
    bgs = [assets / "bg_stadium.jpg", assets / "bg_pitch.jpg", assets / "bg_lights.jpg"]
    fixtures = fixtures or []

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
    render_disclaimer(logo, bgs[1], slides_dir / "disclaimer.jpg")

    texts = [INTRO_SCRIPT, DISCLAIMER_SCRIPT]
    images = [slides_dir / "intro.jpg", slides_dir / "disclaimer.jpg"]

    if recap:
        res_img = slides_dir / "results.jpg"
        render_results(recap, logo, bgs[2], res_img, day_label=recap_day)
        images.append(res_img)
        texts.append(results_script(recap))

    for i, p in enumerate(picks, 1):
        fx = fixture_for_pick(p, fixtures) or {}
        badges = p.get("badges") or fx.get("badges") or {}
        if not fx:
            log.warning("no fixture match for shortlist badges: %s v %s", p.get("home"), p.get("away"))
        if not badges.get("home") or not badges.get("away"):
            log.warning("club badge metadata missing for %s v %s", p.get("home"), p.get("away"))
        hb = fetch_badge(badges.get("home"), crests / f"h{i}.png", logo)
        ab = fetch_badge(badges.get("away"), crests / f"a{i}.png", logo)
        p_img = slides_dir / f"p{i:02d}.jpg"
        render_pick(p, i, n, bgs[i % 3], hb, ab, p_img)
        images.append(p_img)
        texts.append(pick_script(p))

    render_closer(logo, bgs[2], slides_dir / "closer.jpg")
    images.append(slides_dir / "closer.jpg")
    texts.append(CLOSER_SCRIPT)

    if voice_clips is not None and len(voice_clips) != len(images):
        raise ValueError(f"voice_clips ({len(voice_clips)}) must match slides ({len(images)})")

    durations = []
    wavs = []
    for i, (img, text) in enumerate(zip(images, texts)):
        raw = audio_dir / f"raw{i:02d}.wav"
        if voice_clips is not None:
            _run([ff, "-y", "-i", str(voice_clips[i]), "-ac", "1", "-ar", "44100", str(raw)], f"decode {i}")
        else:
            synthesize_speech(text, raw)
        d = _probe(raw, ff)
        hold = frame_hold(hold_seconds(i, d))
        padded = audio_dir / f"a{i:02d}.wav"
        pad_audio(raw, padded, hold, ff)
        wavs.append(padded)
        durations.append(hold)

    total = sum(durations)
    max_allowed = MAX_TOTAL + (60.0 if recap else 0.0)
    if total > max_allowed and len(picks) > 3:
        log.info("reel %.1fs > %.0fs — dropping last pick", total, max_allowed)
        vc = None if voice_clips is None else list(voice_clips[:-2]) + [voice_clips[-1]]
        return build(
            picks[:-1], outfile, assets=assets, work=work, voice_clips=vc,
            fixtures=fixtures, yesterday_results=yesterday_results,
        )
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
    _run([
        ff, "-y", "-i", str(silent), "-i", str(voice),
        "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(outfile),
    ], "mux")
    log.info("reel built %s (%.1fs, %d KB)", outfile.name, total, outfile.stat().st_size // 1024)
    return outfile


def from_shortlist(sl_pub: dict, fixtures: list, outfile: Path, assets: Path, work: Path | None = None,
                   yesterday_results: dict | list | None = None) -> Path:
    sl = sl_pub or {}
    prim = [dict(p) for p in (sl.get("primary") or [])]
    art_by_id = {
        str(a.get("id") or ""): a
        for a in ((sl.get("article") or {}).get("items") or [])
        if isinstance(a, dict)
    }
    for p in prim:
        aid = f"{p.get('home')}|{p.get('away')}|{p.get('kickoff')}"
        form = (art_by_id.get(aid) or {}).get("form") or {}
        if form.get("h") and not p.get("form_h"):
            p["form_h"] = form["h"]
        if form.get("a") and not p.get("form_a"):
            p["form_a"] = form["a"]
    yres = yesterday_results if yesterday_results is not None else sl.get("yesterday_results")
    return build(prim, outfile, assets=assets, work=work, fixtures=fixtures, yesterday_results=yres)
