"""PlayReport shortlist video — 16:9 widescreen (1920x1080), narrated slides, no bed music or trailing silence.

Starts with the settled results of yesterday's shortlist selections (when available), then proceeds
to today's shortlist selections. Each slide lasts exactly as long as its own voice clip (plus a short tail),
so the next match never appears while the previous one is still being read.
"""
from __future__ import annotations

import json
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
REEL_W, REEL_H = 1080, 1920
_ACTIVE_SIZE: tuple[int, int] = (W, H)


def _resolve_size(aspect: str | None = None, size: tuple[int, int] | None = None) -> tuple[int, int]:
    if size is not None:
        return int(size[0]), int(size[1])
    if aspect:
        a = str(aspect).strip().lower()
        if a in ("9:16", "9x16", "vertical", "reel", "portrait"):
            return REEL_W, REEL_H
        if a in ("16:9", "16x9", "widescreen", "landscape", "horizontal"):
            return W, H
    return _ACTIVE_SIZE
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
MAX_PICKS = 12
MAX_TOTAL = 240.0
# Ultra-realistic neural British male voices (CI/local), with male eSpeak-NG as emergency fallback.
EDGE_TTS_VOICE = "en-GB-RyanNeural"
EDGE_TTS_RATE = "-4%"
EDGE_TTS_PITCH = "-2Hz"
PIPER_VOICE_MODEL = "en_GB-alan-medium.onnx"
ESPEAK_VOICE = "en-gb"
ESPEAK_SPEED = 150
ESPEAK_PITCH = 40

INTRO_SCRIPT = "PlayReport. Here's today's shortlist."
DISCLAIMER_SCRIPT = (
    "Quick note before we start. This is statistical information, not betting advice. "
    "It's eighteen plus only, so please bet responsibly. "
    "Never use money you can't afford to lose, and remember, there's no such thing as a sure bet."
)
CLOSER_SCRIPT = (
    "If this helped, give it a like, share it with a mate, and subscribe for tomorrow's list. "
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


def _cover(path: Path, dark: float = 0.55, *, size: tuple[int, int] | None = None):
    from PIL import Image
    cw, ch = _resolve_size(size=size)
    im = Image.open(path).convert("RGB")
    scale = max(cw / im.width, ch / im.height)
    im = im.resize((int(im.width * scale) + 1, int(im.height * scale) + 1), Image.Resampling.LANCZOS)
    x = (im.width - cw) // 2
    y = (im.height - ch) // 2
    im = im.crop((x, y, x + cw, y + ch))
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


def _wordmark(d, y=44, *, width: int | None = None):
    cw = width if width is not None else _resolve_size()[0]
    fnt = _font(38, True)
    lab = "PLAYREPORT"
    d.text(((cw - _tw(d, lab, fnt)) // 2, y), lab, fill=WHITE, font=fnt)
    d.rectangle(((cw - 120) // 2, y + 48, (cw + 120) // 2, y + 52), fill=GREEN)


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


def render_intro(logo: Path, bg: Path, dest: Path, *, aspect: str | None = None, size: tuple[int, int] | None = None) -> None:
    from PIL import Image, ImageDraw, ImageFilter
    cw, ch = _resolve_size(aspect, size)
    im = _cover(bg, 0.55, size=(cw, ch))
    d = ImageDraw.Draw(im)
    if cw < ch:
        # 9:16 vertical reel layout (1080x1920)
        _wordmark(d, 150, width=cw)
        L = Image.open(logo).convert("RGBA").resize((460, 460), Image.Resampling.LANCZOS)
        glow = L.filter(ImageFilter.GaussianBlur(24))
        xy = ((cw - 460) // 2, 420)
        im.paste(glow, xy, glow)
        im.paste(L, xy, L)
        d = ImageDraw.Draw(im)
        sub = _font(50, True)
        s = "TODAY'S SHORTLIST"
        d.text(((cw - _tw(d, s, sub)) // 2, 1020), s, fill=GREEN, font=sub)
        tiny = _font(26, False)
        for idx, ln in enumerate(_wrap(d, "Football intelligence  ·  Results recap & today's selections  ·  SAST", tiny, cw - 140, 2)):
            d.text(((cw - _tw(d, ln, tiny)) // 2, 1105 + idx * 38), ln, fill=MUTED, font=tiny)
        foot = "PlayReport  ·  18+"
        d.text(((cw - _tw(d, foot, _font(22, True))) // 2, ch - 110), foot, fill=MUTED, font=_font(22, True))
    else:
        # 16:9 widescreen layout (1920x1080)
        L = Image.open(logo).convert("RGBA").resize((360, 360), Image.Resampling.LANCZOS)
        glow = L.filter(ImageFilter.GaussianBlur(24))
        xy = ((cw - 360) // 2, 180)
        im.paste(glow, xy, glow)
        im.paste(L, xy, L)
        d = ImageDraw.Draw(im)
        _wordmark(d, 64, width=cw)
        sub = _font(44, True)
        s = "TODAY'S SHORTLIST"
        d.text(((cw - _tw(d, s, sub)) // 2, 600), s, fill=GREEN, font=sub)
        tiny = _font(26, False)
        t = "Football intelligence  ·  Results recap & today's selections  ·  SAST"
        d.text(((cw - _tw(d, t, tiny)) // 2, 668), t, fill=MUTED, font=tiny)
        foot = "PlayReport  ·  18+"
        d.text(((cw - _tw(d, foot, _font(20, True))) // 2, ch - 64), foot, fill=MUTED, font=_font(20, True))
    im.convert("RGB").save(dest, quality=92)


def render_disclaimer(logo: Path, bg: Path, dest: Path, *, aspect: str | None = None, size: tuple[int, int] | None = None) -> None:
    from PIL import Image, ImageDraw
    cw, ch = _resolve_size(aspect, size)
    im = _cover(bg, 0.64, size=(cw, ch))
    lines = [
        "Statistical information, not betting advice.",
        "Not for persons under the age of 18.",
        "Do not bet with money you cannot afford to lose.",
        "There is no such thing as a sure bet.",
    ]
    if cw < ch:
        # 9:16 vertical reel layout (1080x1920)
        L = Image.open(logo).convert("RGBA").resize((180, 180), Image.Resampling.LANCZOS)
        im.paste(L, ((cw - 180) // 2, 120), L)
        d = ImageDraw.Draw(im)
        _wordmark(d, 330, width=cw)
        d.rounded_rectangle((70, 450, cw - 70, 1460), 34, fill=CARD_BG, outline=GREEN, width=3)
        title = "PLEASE BET RESPONSIBLY"
        d.text(((cw - _tw(d, title, _font(40, True))) // 2, 520), title, fill=GREEN, font=_font(40, True))
        y = 635
        fnt = _font(32, False)
        for ln in lines:
            for wrapped in _wrap(d, ln, fnt, cw - 220, 2):
                d.text(((cw - _tw(d, wrapped, fnt)) // 2, y), wrapped, fill=WHITE, font=fnt)
                y += 50
            y += 28
        foot = "PlayReport  ·  18+"
        d.text(((cw - _tw(d, foot, _font(22, True))) // 2, ch - 110), foot, fill=MUTED, font=_font(22, True))
    else:
        # 16:9 widescreen layout (1920x1080)
        L = Image.open(logo).convert("RGBA").resize((130, 130), Image.Resampling.LANCZOS)
        im.paste(L, ((cw - 130) // 2, 48), L)
        d = ImageDraw.Draw(im)
        _wordmark(d, 195, width=cw)
        d.rounded_rectangle((220, 285, cw - 220, ch - 110), 32, fill=CARD_BG, outline=GREEN, width=3)
        title = "PLEASE BET RESPONSIBLY"
        d.text(((cw - _tw(d, title, _font(38, True))) // 2, 330), title, fill=GREEN, font=_font(38, True))
        y = 430
        fnt = _font(30, False)
        for ln in lines:
            for wrapped in _wrap(d, ln, fnt, cw - 520, 2):
                d.text(((cw - _tw(d, wrapped, fnt)) // 2, y), wrapped, fill=WHITE, font=fnt)
                y += 46
            y += 18
        foot = "PlayReport  ·  18+"
        d.text(((cw - _tw(d, foot, _font(20, True))) // 2, ch - 64), foot, fill=MUTED, font=_font(20, True))
    im.convert("RGB").save(dest, quality=92)


def render_results(results: list[dict], logo: Path, bg: Path, dest: Path, *, day_label: str = "",
                   aspect: str | None = None, size: tuple[int, int] | None = None) -> None:
    """Slide recapping yesterday's settled video shortlist selections before today's picks (16:9 or 9:16)."""
    from PIL import ImageDraw
    cw, ch = _resolve_size(aspect, size)
    im = _cover(bg, 0.62, size=(cw, ch))
    d = ImageDraw.Draw(im)

    settled = [r for r in results if r.get("result") in ("hit", "miss")]
    hits = sum(1 for r in settled if r.get("result") == "hit")
    rate_str = f"  ({round(100 * hits / len(settled))}%)" if settled else ""
    summary = f"{hits} OF {len(settled)} SELECTIONS WON{rate_str}" if settled else f"{len(results)} SELECTIONS RECAP"
    head = "YESTERDAY'S SHORTLIST RESULTS" + (f"  ·  {day_label}" if day_label else "")
    rows = results[:MAX_PICKS]

    if cw < ch:
        # 9:16 vertical reel layout (1080x1920)
        _wordmark(d, 90, width=cw)
        d.text(((cw - _tw(d, head, _font(24, True))) // 2, 168), head, fill=GREEN, font=_font(24, True))
        d.text(((cw - _tw(d, summary, _font(34, True))) // 2, 212), summary, fill=GOLD, font=_font(34, True))
        d.rounded_rectangle((56, 280, cw - 56, ch - 150), 28, fill=CARD_BG, outline=GREEN, width=3)
        if rows:
            row_h = min(205, (ch - 460) // max(len(rows), 1))
            y = 304
            for idx, r in enumerate(rows, 1):
                if idx > 1:
                    d.rectangle((86, y - 10, cw - 86, y - 9), fill=(20, 48, 74))
                match_txt = f"{r.get('home') or ''} v {r.get('away') or ''}"
                comp_txt = competition_line(r)
                odds = r.get("odds")
                od = f" @ {odds:.2f}" if isinstance(odds, (int, float)) else ""
                sel_txt = f"{r.get('label') or r.get('sel') or ''}{od}"

                d.text((88, y + 6), match_txt[:34], fill=WHITE, font=_font(26, True))
                if comp_txt:
                    d.text((88, y + 44), comp_txt[:46], fill=MUTED, font=_font(19, False))
                d.text((88, y + 80), sel_txt[:38], fill=GREEN, font=_font(23, True))

                sc = str(r.get("score") or "").strip()
                res = str(r.get("result") or "").lower()
                badge_lbl = "WON" if res == "hit" else "LOST" if res == "miss" else "VOID"
                badge_col = GREEN if res == "hit" else RED if res == "miss" else MUTED
                bx0, by0, bx1, by1 = cw - 240, y + 58, cw - 88, y + 110
                if sc:
                    ft_txt = f"FT {sc}"
                    ffnt = _font(24, True)
                    d.text((bx0 + (bx1 - bx0 - _tw(d, ft_txt, ffnt)) // 2, y + 14), ft_txt, fill=GOLD, font=ffnt)
                d.rounded_rectangle((bx0, by0, bx1, by1), 12, fill=badge_col)
                bf = _font(22, True)
                d.text(
                    (bx0 + (bx1 - bx0 - _tw(d, badge_lbl, bf)) // 2, by0 + 13),
                    badge_lbl,
                    fill=NAVY if res == "hit" else WHITE,
                    font=bf,
                )
                y += row_h
        foot = "PlayReport  ·  verified pre-match shortlist ledger  ·  18+"
        d.text(((cw - _tw(d, foot, _font(20, False))) // 2, ch - 100), foot, fill=MUTED, font=_font(20, False))
    else:
        # 16:9 widescreen layout (1920x1080)
        _wordmark(d, 36, width=cw)
        d.text(((cw - _tw(d, head, _font(26, True))) // 2, 104), head, fill=GREEN, font=_font(26, True))
        d.text(((cw - _tw(d, summary, _font(34, True))) // 2, 144), summary, fill=GOLD, font=_font(34, True))
        d.rounded_rectangle((110, 205, cw - 110, ch - 95), 28, fill=CARD_BG, outline=GREEN, width=3)
        if rows:
            row_h = min(102, (ch - 330) // max(len(rows), 1))
            y = 225
            for idx, r in enumerate(rows, 1):
                if idx > 1:
                    d.rectangle((145, y - 6, cw - 145, y - 5), fill=(20, 48, 74))
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
        d.text(((cw - _tw(d, foot, _font(20, False))) // 2, ch - 56), foot, fill=MUTED, font=_font(20, False))
    im.convert("RGB").save(dest, quality=92)


def render_pick(pick: dict, i: int, n: int, bg: Path, home_b: Path, away_b: Path, dest: Path,
                *, aspect: str | None = None, size: tuple[int, int] | None = None) -> None:
    from PIL import ImageDraw
    cw, ch = _resolve_size(aspect, size)
    im = _cover(bg, 0.58, size=(cw, ch))
    d = ImageDraw.Draw(im)
    k = f"TODAY'S SHORTLIST  ·  PICK {i} OF {n}"
    comp = competition_line(pick)

    if cw < ch:
        # 9:16 vertical reel layout (1080x1920)
        _wordmark(d, 90, width=cw)
        d.text(((cw - _tw(d, k, _font(26, True))) // 2, 172), k, fill=GREEN, font=_font(26, True))
        if comp:
            d.text(((cw - _tw(d, comp, _font(24, False))) // 2, 212), comp, fill=MUTED, font=_font(24, False))

        bsize, gap = 210, 150
        hb = _circle_badge(home_b, bsize)
        ab = _circle_badge(away_b, bsize)
        total = bsize * 2 + gap
        x0, y0 = (cw - total) // 2, 295
        im.paste(hb, (x0, y0), hb)
        im.paste(ab, (x0 + bsize + gap, y0), ab)
        d = ImageDraw.Draw(im)
        d.text((x0 + bsize + (gap - _tw(d, "VS", _font(36, True))) // 2, y0 + bsize // 2 - 20), "VS", fill=WHITE, font=_font(36, True))
        nf = _font(30, True)
        for team, form_key, cx in (
            (pick.get("home") or "", "form_h", x0 + bsize // 2),
            (pick.get("away") or "", "form_a", x0 + bsize + gap + bsize // 2),
        ):
            yy = y0 + bsize + 24
            for ln in _wrap(d, team, nf, bsize + 110, 2):
                d.text((cx - _tw(d, ln, nf) // 2, yy), ln, fill=WHITE, font=nf)
                yy += 38
            if pick.get(form_key):
                _draw_form_pills(d, str(pick.get(form_key)), cx, yy + 10)

        rx0, ry0, rx1, ry1 = 76, 760, cw - 76, 1545
        rcx = (rx0 + rx1) // 2
        d.rounded_rectangle((rx0, ry0, rx1, ry1), 36, fill=CARD_BG, outline=GREEN, width=3)
        eyebrow = "QUALIFIED SELECTION"
        d.text((rcx - _tw(d, eyebrow, _font(22, True)) // 2, ry0 + 48), eyebrow, fill=GREEN, font=_font(22, True))

        lf = _font(44, True)
        y = ry0 + 115
        for ln in _wrap(d, pick.get("label") or "", lf, (rx1 - rx0) - 90, 3):
            d.text((rcx - _tw(d, ln, lf) // 2, y), ln, fill=WHITE, font=lf)
            y += 56

        odds = pick.get("odds")
        od = f"{odds:.2f}" if isinstance(odds, (int, float)) else "N/A"
        of = _font(132, True)
        d.text((rcx - _tw(d, od, of) // 2, y + 25), od, fill=GREEN, font=of)
        cap = "SPORTYBET PRICE"
        d.text((rcx - _tw(d, cap, _font(22, True)) // 2, y + 175), cap, fill=MUTED, font=_font(22, True))

        ko = str(pick.get("kickoff") or "")[11:16]
        kt = f"KICK-OFF  {ko} SAST" if ko else "TODAY  ·  SAST"
        kf = _font(32, True)
        kw = _tw(d, kt, kf) + 64
        d.rounded_rectangle((rcx - kw // 2, ry1 - 130, rcx + kw // 2, ry1 - 60), 20, fill=(16, 40, 66), outline=GOLD, width=2)
        d.text((rcx - _tw(d, kt, kf) // 2, ry1 - 114), kt, fill=GOLD, font=kf)

        d.rectangle((76, ch - 190, cw - 76, ch - 176), fill=(20, 48, 74))
        d.rectangle((76, ch - 190, 76 + int(i / max(n, 1) * (cw - 152)), ch - 176), fill=GREEN)
        foot = "PlayReport  ·  not betting advice  ·  18+"
        d.text(((cw - _tw(d, foot, _font(22, False))) // 2, ch - 110), foot, fill=MUTED, font=_font(22, False))
    else:
        # 16:9 widescreen layout (1920x1080)
        _wordmark(d, 36, width=cw)
        d.text(((cw - _tw(d, k, _font(24, True))) // 2, 102), k, fill=GREEN, font=_font(24, True))
        if comp:
            d.text(((cw - _tw(d, comp, _font(22, False))) // 2, 138), comp, fill=MUTED, font=_font(22, False))

        bsize, gap = 180, 110
        hb = _circle_badge(home_b, bsize)
        ab = _circle_badge(away_b, bsize)
        left_cx = 500
        total = bsize * 2 + gap
        x0, y0 = left_cx - total // 2, 260
        im.paste(hb, (x0, y0), hb)
        im.paste(ab, (x0 + bsize + gap, y0), ab)
        d = ImageDraw.Draw(im)
        d.text((x0 + bsize + (gap - _tw(d, "VS", _font(28, True))) // 2, y0 + bsize // 2 - 16), "VS", fill=WHITE, font=_font(28, True))
        nf = _font(26, True)
        for team, form_key, cx in (
            (pick.get("home") or "", "form_h", x0 + bsize // 2),
            (pick.get("away") or "", "form_a", x0 + bsize + gap + bsize // 2),
        ):
            yy = y0 + bsize + 22
            for ln in _wrap(d, team, nf, bsize + 70, 2):
                d.text((cx - _tw(d, ln, nf) // 2, yy), ln, fill=WHITE, font=nf)
                yy += 34
            if pick.get(form_key):
                _draw_form_pills(d, str(pick.get(form_key)), cx, yy + 10)

        rx0, ry0, rx1, ry1 = 940, 210, cw - 110, 885
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

        d.rectangle((110, ch - 115, cw - 110, ch - 103), fill=(20, 48, 74))
        d.rectangle((110, ch - 115, 110 + int(i / max(n, 1) * (cw - 220)), ch - 103), fill=GREEN)
        foot = "PlayReport  ·  not betting advice  ·  18+"
        d.text(((cw - _tw(d, foot, _font(20, False))) // 2, ch - 64), foot, fill=MUTED, font=_font(20, False))
    im.convert("RGB").save(dest, quality=92)


def render_acca(group: dict, idx: int, total: int, bg: Path, dest: Path, logo: Path) -> None:
    """One treble: three legs and the combined Sportybet price."""
    from PIL import Image, ImageDraw
    cw, ch = _ACTIVE_SIZE
    im = _cover(bg, 0.58, size=(cw, ch))
    d = ImageDraw.Draw(im)
    _wordmark(d, 50 if cw > ch else 90, width=cw)
    title = f"TREBLE  {idx} OF {total}"
    d.text(((cw - _tw(d, title, _font(28, True))) // 2, 140 if cw > ch else 180), title, fill=GREEN, font=_font(28, True))
    legs = group.get("legs") or []
    comb = group.get("combined")
    od = f"{comb:.2f}" if isinstance(comb, (int, float)) else "N/A"
    box_top = 210 if cw > ch else 280
    y = box_top
    for i, p in enumerate(legs, 1):
        line1 = f"{i}. {p.get('home') or ''}  v  {p.get('away') or ''}"
        line2 = f"{p.get('label') or ''}   @   {p.get('odds') if p.get('odds') is not None else 'N/A'}"
        d.text((80, y), line1, fill=WHITE, font=_font(32 if cw < ch else 28, True))
        d.text((80, y + 40), line2, fill=GOLD, font=_font(26 if cw < ch else 24, True))
        y += 110 if cw < ch else 90
    cap = "COMBINED PRICE"
    d.text(((cw - _tw(d, cap, _font(20, True))) // 2, y + 10), cap, fill=MUTED, font=_font(20, True))
    d.text(((cw - _tw(d, od, _font(96, True))) // 2, y + 40), od, fill=GREEN, font=_font(96, True))
    foot = "PlayReport  ·  three selections  ·  not betting advice  ·  18+"
    d.text(((cw - _tw(d, foot, _font(20, False))) // 2, ch - 80), foot, fill=MUTED, font=_font(20, False))
    im.convert("RGB").save(dest, quality=92)



def render_closer(logo: Path, bg: Path, dest: Path, *, aspect: str | None = None, size: tuple[int, int] | None = None) -> None:
    from PIL import Image, ImageDraw
    cw, ch = _resolve_size(aspect, size)
    im = _cover(bg, 0.6, size=(cw, ch))
    if cw < ch:
        # 9:16 vertical reel layout (1080x1920)
        L = Image.open(logo).convert("RGBA").resize((300, 300), Image.Resampling.LANCZOS)
        im.paste(L, ((cw - 300) // 2, 330), L)
        d = ImageDraw.Draw(im)
        _wordmark(d, 150, width=cw)
        t = "THAT'S THE LIST"
        d.text(((cw - _tw(d, t, _font(54, True))) // 2, 710), t, fill=WHITE, font=_font(54, True))
        s = "Like, share or subscribe if this helped — no pressure."
        for idx, ln in enumerate(_wrap(d, s, _font(30, False), cw - 140, 2)):
            d.text(((cw - _tw(d, ln, _font(30, False))) // 2, 805 + idx * 42), ln, fill=MUTED, font=_font(30, False))
        n = "Statistical information, not betting advice. 18+."
        d.text(((cw - _tw(d, n, _font(26, False))) // 2, 950), n, fill=MUTED, font=_font(26, False))
        c = "© PlayReport. All rights reserved."
        d.text(((cw - _tw(d, c, _font(26, True))) // 2, 1110), c, fill=WHITE, font=_font(26, True))
        p = "Unauthorised copying or re-upload is prohibited."
        d.text(((cw - _tw(d, p, _font(22, False))) // 2, 1160), p, fill=MUTED, font=_font(22, False))
    else:
        # 16:9 widescreen layout (1920x1080)
        L = Image.open(logo).convert("RGBA").resize((240, 240), Image.Resampling.LANCZOS)
        im.paste(L, ((cw - 240) // 2, 165), L)
        d = ImageDraw.Draw(im)
        _wordmark(d, 64, width=cw)
        t = "THAT'S THE LIST"
        d.text(((cw - _tw(d, t, _font(50, True))) // 2, 445), t, fill=WHITE, font=_font(50, True))
        s = "Like, share or subscribe if this helped — no pressure."
        d.text(((cw - _tw(d, s, _font(28, False))) // 2, 525), s, fill=MUTED, font=_font(28, False))
        n = "Statistical information, not betting advice. 18+."
        d.text(((cw - _tw(d, n, _font(24, False))) // 2, 625), n, fill=MUTED, font=_font(24, False))
        c = "© PlayReport. All rights reserved."
        d.text(((cw - _tw(d, c, _font(24, True))) // 2, 725), c, fill=WHITE, font=_font(24, True))
        p = "Unauthorised copying or re-upload is prohibited."
        d.text(((cw - _tw(d, p, _font(20, False))) // 2, 770), p, fill=MUTED, font=_font(20, False))
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


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _edge_sentence(sentence: str, edge_py: str, dest: Path) -> bool:
    """One sentence through the Edge neural voice into `dest` (an mp3). False on any failure."""
    voice = os.environ.get("EDGE_TTS_VOICE") or EDGE_TTS_VOICE
    rate = os.environ.get("EDGE_TTS_RATE") or EDGE_TTS_RATE
    pitch = os.environ.get("EDGE_TTS_PITCH") or EDGE_TTS_PITCH
    cmd = [edge_py, "-m", "edge_tts", "--voice", voice, f"--rate={rate}", f"--pitch={pitch}", "--text", sentence, "--write-media", str(dest)]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=45)
    return r.returncode == 0 and dest.exists() and dest.stat().st_size > 200


def _polished_edge(clean: str, wav: Path, edge_py: str) -> bool:
    """Speak a script sentence by sentence and join it the way a person paces it (see voice_polish). False -> use the plain voice."""
    try:
        import voice_polish as vp
        from concurrent.futures import ThreadPoolExecutor

        if not vp.enabled():
            return False
        sents = [s for s in _SENT_SPLIT.split(clean.strip()) if s]
        if not sents:
            return False
        ff = _ffmpeg()
        tmp = wav.parent / (wav.stem + ".sent")
        tmp.mkdir(parents=True, exist_ok=True)
        try:
            paths = [tmp / f"s{i:02d}.mp3" for i in range(len(sents))]
            with ThreadPoolExecutor(max_workers=4) as pool:
                ok = list(pool.map(lambda a: _edge_sentence(a[0], edge_py, a[1]), zip(sents, paths)))
            if not all(ok):
                return False
            clips = [vp.read_audio(p, ff) for p in paths]
            if any(len(c) < 2400 for c in clips):
                return False
            kinds = ["colon" if s.rstrip().endswith(":") else "sentence" for s in sents]
            track = vp.polish_sentences(clips, kinds, ff, seed=hash_seed(clean))
            vp.to_wav44(track, wav, ff)
            return wav.exists()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001
        log.warning("voice polish skipped, using the plain voice: %s", exc)
        return False


def hash_seed(text: str) -> int:
    import hashlib
    return int(hashlib.sha1(text.encode("utf-8")).hexdigest()[:10], 16)


def synthesize_speech(text: str, wav: Path) -> None:
    """Use ultra-realistic male neural TTS (Edge-TTS RyanNeural or Piper Alan medium), with male eSpeak-NG fallback.

    The neural voice is spoken sentence by sentence and re-paced like a person (varied pauses, a little tempo and level
    drift, warmth, room) by `voice_polish`; if that cannot run, the plain single-call voice is used.
    """
    wav.parent.mkdir(parents=True, exist_ok=True)
    clean = spoken_text(text)

    edge_py = os.environ.get("EDGE_TTS_PYTHON")
    if edge_py and Path(edge_py).is_file() and _polished_edge(clean, wav, edge_py):
        return
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


ROOM_TONE_DB = -41.0     # level trim of the brown-noise bed (comes out near -62 dBFS, far below any speech)


def pad_audio(src: Path, dest: Path, duration: float, ff: str) -> None:
    """Force a clip to `duration` seconds without ever trimming speech.

    The hold after the speech is filled with a very quiet room tone rather than perfect digital silence: dead air is one
    of the things that makes a synthetic narration sound synthetic. Falls back to plain silence if ffmpeg lacks the filters.
    """
    graph = (f"[0:a]apad=whole_dur={duration:.3f}[v];[1:a]lowpass=f=3200,highpass=f=50,volume={ROOM_TONE_DB}dB[n];"
             f"[v][n]amix=inputs=2:duration=first:normalize=0:dropout_transition=0[o]")
    try:
        _run([ff, "-y", "-i", str(src), "-f", "lavfi", "-i", "anoisesrc=color=brown:amplitude=0.5:sample_rate=44100",
              "-filter_complex", graph, "-map", "[o]", "-t", f"{duration:.3f}", "-ac", "1", "-ar", "44100", str(dest)], "pad+tone")
        return
    except Exception as exc:  # noqa: BLE001
        log.info("room tone unavailable, padding with silence: %s", exc)
    _run([
        ff, "-y", "-i", str(src), "-af", f"apad=whole_dur={duration:.3f}",
        "-t", f"{duration:.3f}", str(dest),
    ], "pad")


def still_clip(img: Path, dest: Path, duration: float, ff: str, *, aspect: str | None = None,
               size: tuple[int, int] | None = None) -> None:
    cw, ch = _resolve_size(aspect, size)
    _run([
        ff, "-y", "-loop", "1", "-framerate", str(FPS), "-t", f"{duration:.3f}", "-i", str(img),
        "-vf", f"scale={cw}:{ch},format=yuv420p", "-r", str(FPS),
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


_PICK_OPEN_FIRST = ("First up,", "To start,", "Let's begin with")
_PICK_OPEN_MID = ("Next,", "Then,", "Now,", "After that,", "Moving on to")
_PICK_OPEN_LAST = ("And finally,", "Last one:", "And to finish,")
_PICK_LEAD = ("I like", "My pick is", "I'm going with", "The pick here is")
_HOSTS = ("host", "welcome", "are at home to")


def pick_script(p: dict, idx: int = 1, total: int = 1) -> str:
    """One pick as it is said: country and league, the match, kick-off, then the selection and price."""
    import spoken as sp

    home, away = str(p.get("home") or ""), str(p.get("away") or "")
    odds = p.get("odds")
    od = f"{float(odds):.2f}" if isinstance(odds, (int, float)) else "N/A"
    opens = _PICK_OPEN_FIRST if idx <= 1 else _PICK_OPEN_LAST if idx >= total > 1 else _PICK_OPEN_MID
    place = sp.competition(p.get("country"), p.get("league"))
    ko = sp.kickoff(str(p.get("kickoff") or "")[11:16])
    match = f"{sp.team(home)} {_HOSTS[idx % len(_HOSTS)]} {sp.team(away)}" + (f" {ko}" if ko else "")
    market = sp.market_phrase(p.get("label"), home, away)
    head = f"{opens[idx % len(opens)]} {place}." if place else f"{opens[idx % len(opens)]}"
    return f"{head} {match}. {_PICK_LEAD[idx % len(_PICK_LEAD)]} {market}, at {od}."


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


def _score_words(raw) -> str:
    import spoken as sp

    m = re.match(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$", str(raw or ""))
    return sp.score(int(m.group(1)), int(m.group(2))) if m else ""


def results_script(results: list[dict]) -> str:
    """Yesterday's settled picks as a short, spoken look back. Factual, no model probabilities."""
    import spoken as sp

    rows = reel_results(results)
    if not rows:
        return ""
    settled = [r for r in rows if r.get("result") in ("hit", "miss")]
    hits = sum(1 for r in settled if r.get("result") == "hit")
    n = len(settled)
    if not n:
        count = ""
    elif hits == n:
        count = "It landed." if n == 1 else f"A clean sweep, {sp.words(hits)} from {sp.words(n)}."
    elif hits == 0:
        count = "A tough one, with none landing." if n == 1 else f"A tough one, none of the {sp.words(n)} landed."
    else:
        count = f"We went {sp.words(hits)} from {sp.words(n)}."
    parts = []
    for i, r in enumerate(rows):
        home, away = r.get("home") or "", r.get("away") or ""
        h, a = sp.team(home), sp.team(away)
        mk = sp.market_phrase(r.get("label") or r.get("sel") or "the selection", home, away)
        sc = _score_words(r.get("score"))
        res = str(r.get("result") or "").lower()
        tail = f", {sc}" if sc else ""
        if res == "hit":
            parts.append((f"{h} against {a}: {mk} came in{tail}.", f"{h} against {a}, {mk}, landed{tail}.")[i % 2])
        elif res == "miss":
            parts.append((f"{h} against {a}: {mk} missed{tail}.", f"{sp.cap(mk)} didn't come in for {h} against {a}{tail}.")[i % 2])
        else:
            parts.append(f"{h} against {a} was void.")
    return " ".join(x for x in ("First, a quick look back at yesterday.", count, " ".join(parts), "Now, today's shortlist.") if x)


def is_reel_market(p: dict) -> bool:
    """Videos: 1X2, BTTS and Over 2.5. Unders stay out."""
    sel = str(p.get("sel") or "").upper()
    blob = " ".join(str(p.get(k) or "") for k in ("label", "sel", "market", "group")).lower()
    if "under" in blob or sel in ("U15", "U25", "U35", "NBTTS", "1X", "12", "X2"):
        return False
    if sel in ("H", "D", "A"):
        return True
    if sel == "BTTS" or "btts" in blob or "both teams" in blob:
        return True
    if sel == "O25" or "over 2.5" in blob:
        return True
    return False


def _match_key(p: dict) -> tuple:
    return (str(p.get("kickoff") or ""), str(p.get("home") or ""), str(p.get("away") or ""))


def reel_picks(picks: list) -> list:
    """At least twelve when the pool allows: 1X2 / BTTS / Over 2.5, one per match."""
    rank = {"O25": 0, "BTTS": 1, "H": 2, "A": 2, "D": 3}
    best = {}
    order = []
    for p in picks or []:
        if not is_reel_market(p):
            continue
        k = _match_key(p)
        prev = best.get(k)
        if prev is None:
            best[k] = p
            order.append(k)
        else:
            if rank.get(str(p.get("sel") or "").upper(), 9) < rank.get(str(prev.get("sel") or "").upper(), 9):
                best[k] = p
    out = [best[k] for k in order]
    return out[:MAX_PICKS]


def overs_only(picks: list) -> list:
    """Kept name for scanner.py."""
    return reel_picks(picks)


def pack_accas(picks: list, size: int = 3) -> list:
    """Group picks into 3-fold accas. Same match never appears twice in one treble. Combined odds = product of prices."""
    remaining = list(picks or [])
    groups = []
    while remaining:
        g, matches, rest = [], set(), []
        for p in remaining:
            mk = _match_key(p)
            if mk in matches or len(g) >= size:
                rest.append(p)
                continue
            g.append(p)
            matches.add(mk)
        if len(g) < size:
            break
        combined = 1.0
        ok = True
        for p in g:
            od = p.get("odds")
            if not isinstance(od, (int, float)) or od <= 1:
                ok = False
                break
            combined *= float(od)
        groups.append({"legs": g, "combined": round(combined, 2) if ok else None})
        remaining = rest
    return groups


def acca_script(group: dict, idx: int, total: int) -> str:
    import spoken as sp
    legs = group.get("legs") or []
    n = len(legs)
    comb = group.get("combined")
    od = f"{comb:.2f}" if isinstance(comb, (int, float)) else "N/A"
    bits = []
    for p in legs:
        home, away = p.get("home") or "", p.get("away") or ""
        mk = sp.market_phrase(p.get("label"), home, away)
        price = p.get("odds")
        ps = f"{float(price):.2f}" if isinstance(price, (int, float)) else "N/A"
        bits.append(f"{sp.team(home)} against {sp.team(away)}, {mk} at {ps}")
    body = "; ".join(bits[:-1]) + (", and " + bits[-1] if len(bits) > 1 else (bits[0] if bits else ""))
    head = "First treble" if idx == 1 else ("Last treble" if idx == total else f"Treble number {sp.words(idx)}")
    return (f"{head}. Three selections: {body}. "
            f"Together that's about {od}. Statistical information, not a sure thing.")


def build(picks: list, outfile: Path, *, assets: Path, work: Path | None = None,
          voice_clips: list[Path] | None = None, fixtures: list | None = None,
          yesterday_results: dict | list | None = None, aspect: str = "16:9") -> Path:
    """Build a 16:9 widescreen (1920x1080) or 9:16 vertical reel (1080x1920) video.
    Starts with yesterday's settled video results when provided, then today's picks.
    Slide length = that clip's duration + TAIL (intro at least INTRO_MIN). No music.
    """
    from PIL import Image  # noqa: F401  — imported for a clear error if missing

    global _ACTIVE_SIZE
    prev_size = _ACTIVE_SIZE
    _ACTIVE_SIZE = _resolve_size(aspect)
    try:
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

        accas = pack_accas(picks, 3)
        covered = {id(p) for g in accas for p in g["legs"]}
        pi = 0
        for gi, g in enumerate(accas, 1):
            a_img = slides_dir / f"acca{gi:02d}.jpg"
            render_acca(g, gi, len(accas), bgs[gi % 3], a_img, logo)
            images.append(a_img)
            texts.append(acca_script(g, gi, len(accas)))
            for p in g["legs"]:
                pi += 1
                fx = fixture_for_pick(p, fixtures) or {}
                badges = p.get("badges") or fx.get("badges") or {}
                hb = fetch_badge(badges.get("home"), crests / f"h{pi}.png", logo)
                ab = fetch_badge(badges.get("away"), crests / f"a{pi}.png", logo)
                p_img = slides_dir / f"p{pi:02d}.jpg"
                render_pick(p, pi, n, bgs[pi % 3], hb, ab, p_img)
                images.append(p_img)
                texts.append(pick_script(p, pi, n))
        for p in picks:
            if id(p) in covered:
                continue
            pi += 1
            fx = fixture_for_pick(p, fixtures) or {}
            badges = p.get("badges") or fx.get("badges") or {}
            hb = fetch_badge(badges.get("home"), crests / f"h{pi}.png", logo)
            ab = fetch_badge(badges.get("away"), crests / f"a{pi}.png", logo)
            p_img = slides_dir / f"p{pi:02d}.jpg"
            render_pick(p, pi, n, bgs[pi % 3], hb, ab, p_img)
            images.append(p_img)
            texts.append(pick_script(p, pi, n))

        render_closer(logo, bgs[2], slides_dir / "closer.jpg")
        images.append(slides_dir / "closer.jpg")
        texts.append(CLOSER_SCRIPT)

        if voice_clips is not None and len(voice_clips) != len(images):
            raise ValueError(f"voice_clips ({len(voice_clips)}) must match slides ({len(images)})")

        durations = []
        wavs = []
        raw_wavs = []
        for i, (img, text) in enumerate(zip(images, texts)):
            raw = audio_dir / f"raw{i:02d}.wav"
            if voice_clips is not None:
                _run([ff, "-y", "-i", str(voice_clips[i]), "-ac", "1", "-ar", "44100", str(raw)], f"decode {i}")
            else:
                synthesize_speech(text, raw)
            raw_wavs.append(raw)
            d = _probe(raw, ff)
            hold = frame_hold(hold_seconds(i, d))
            padded = audio_dir / f"a{i:02d}.wav"
            pad_audio(raw, padded, hold, ff)
            wavs.append(padded)
            durations.append(hold)

        total = sum(durations)
        max_allowed = MAX_TOTAL + (60.0 if recap else 0.0)
        if total > max_allowed and len(picks) > 6:
            log.info("reel %.1fs > %.0fs — dropping last treble", total, max_allowed)
            return build(
                picks[:-3], outfile, assets=assets, work=work, voice_clips=None,
                fixtures=fixtures, yesterday_results=yesterday_results, aspect=aspect,
            )

        # Persist metadata of the final slides & raw audio so build_both can reuse the exact same voice clips
        (work / "build_meta.json").write_text(
            json.dumps({"picks_count": len(picks), "raw_wavs": [str(p) for p in raw_wavs]}),
            encoding="utf-8",
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
        log.info("reel built %s [%s] (%.1fs, %d KB)", outfile.name, aspect, total, outfile.stat().st_size // 1024)
        return outfile
    finally:
        _ACTIVE_SIZE = prev_size


def build_both(picks: list, out_16x9: Path, out_9x16: Path, *, assets: Path, work: Path | None = None,
               voice_clips: list[Path] | None = None, fixtures: list | None = None,
               yesterday_results: dict | list | None = None) -> tuple[Path, Path]:
    """Build both 16:9 widescreen (1920x1080) and 9:16 vertical reel (1080x1920) videos using the EXACT same voice audio."""
    base_work = Path(work) if work else Path(tempfile.mkdtemp(prefix="pr-dual-"))
    w16 = base_work / "w16x9"
    w9 = base_work / "w9x16"
    p16 = build(
        picks, out_16x9, assets=assets, work=w16, voice_clips=voice_clips,
        fixtures=fixtures, yesterday_results=yesterday_results, aspect="16:9",
    )
    shared_vc = voice_clips
    used_picks = reel_picks(picks)
    meta_file = w16 / "build_meta.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            used_picks = used_picks[: int(meta.get("picks_count", len(used_picks)))]
            raw_list = [Path(p) for p in (meta.get("raw_wavs") or [])]
            if raw_list and all(p.exists() for p in raw_list):
                shared_vc = raw_list
        except (OSError, ValueError):
            pass
    p9 = build(
        used_picks, out_9x16, assets=assets, work=w9, voice_clips=shared_vc,
        fixtures=fixtures, yesterday_results=yesterday_results, aspect="9:16",
    )
    return p16, p9


def from_shortlist(sl_pub: dict, fixtures: list, outfile: Path, assets: Path, work: Path | None = None,
                   yesterday_results: dict | list | None = None, *, aspect: str = "16:9") -> Path:
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
    return build(prim, outfile, assets=assets, work=work, fixtures=fixtures, yesterday_results=yres, aspect=aspect)

