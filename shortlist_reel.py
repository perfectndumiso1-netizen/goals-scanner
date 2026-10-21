"""PlayReport shortlist video — 16:9 widescreen (1920x1080) or 9:16 vertical, one music bed, no narration.

2026-10-21 (user rule): there is no voice any more — no neural TTS, no Piper, no eSpeak, nothing to speak. Every
video carries the user's track `assets/reel/under_the_stadium_lights.mp3` for its whole length (looped, faded and
normalised by `music.bed`). Slide lengths come from how long each slide's words take to read, at the pace the
narration used to speak them, so the length and the format of the videos are unchanged.

The morning video opens with the settled results of *every* video from yesterday (morning, noon and evening),
then walks today's matches one at a time — the match, the selection, the price and the reason it made the list.
Videos carry Over 1.5 total goals, team goals, corners and bookings only, and no accumulator is built, shown or
shown anywhere (user rules 2026-10-21). Each slide lasts as long as its own words take to read (plus TAIL), so the
next match never appears while the previous one is still being read.
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

import music

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
TAIL = 0.70          # extra hold after a slide's words so the next one never lands on top of the last line
INTRO_MIN = 5.0      # logo sting, seconds
MAX_PICKS = 12
MAX_TOTAL = 240.0
RECAP_ROWS = 9       # results per recap slide (readable in both 16:9 and 9:16)
MAX_RECAP = 60       # every selection from yesterday's three videos, with a hard ceiling

INTRO_SCRIPT = "PlayReport. These are the matches worth your attention today."
DISCLAIMER_SCRIPT = (
    "Quick note before we start. This is statistical information, not betting advice. "
    "It's eighteen plus only, so please bet responsibly. "
    "Never use money you can't afford to lose, and remember, there's no such thing as a sure bet."
)
CLOSER_SCRIPT = (
    "That's the list. Take them as singles, take fewer, or skip the ones you don't like. "
    "If this helped, give it a like, share it with a mate, and subscribe for tomorrow's list. "
    "PlayReport. All rights reserved."
)
def spoken_text(text: str) -> str:
    """Normalise football abbreviations and telegraphic punctuation for plain, broadcast-style wording.

    Kept after the voice was retired: `spoken.market_phrase` and the script writers use it so the on-screen text
    reads like a person wrote it rather than like a feed.
    """
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


def hold_seconds(index: int, speech: float) -> float:
    """Slide length = the seconds given (reading time since 2026-10-21). Intro never shorter than INTRO_MIN."""
    speech = max(0.0, float(speech or 0.0))
    if index == 0:
        return max(INTRO_MIN, speech + TAIL)
    return speech + TAIL


def frame_hold(seconds: float) -> float:
    """Round duration up to a whole video frame so the picture outlasts the slide's words."""
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


def _clean_score(raw) -> str:
    """A final score for the slide, or "" when there is not a real one (a void pick carries "-")."""
    sc = str(raw or "").strip()
    return sc if re.match(r"^\d+\s*[-:]\s*\d+$", sc) else ""


def render_results(results: list[dict], logo: Path, bg: Path, dest: Path, *, day_label: str = "",
                   aspect: str | None = None, size: tuple[int, int] | None = None,
                   page: int = 1, pages: int = 1, all_rows: list[dict] | None = None) -> None:
    """Slide recapping yesterday's settled selections — every video from the day, paged when the card is long."""
    from PIL import ImageDraw
    cw, ch = _resolve_size(aspect, size)
    im = _cover(bg, 0.62, size=(cw, ch))
    d = ImageDraw.Draw(im)

    every = list(all_rows) if all_rows is not None else list(results)
    settled = [r for r in every if r.get("result") in ("hit", "miss")]
    hits = sum(1 for r in settled if r.get("result") == "hit")
    rate_str = f"  ({round(100 * hits / len(settled))}%)" if settled else ""
    summary = f"{hits} OF {len(settled)} SELECTIONS WON{rate_str}" if settled else f"{len(every)} SELECTIONS RECAP"
    head = "YESTERDAY'S CARD  ·  EVERY VIDEO" + (f"  ·  {day_label}" if day_label else "")
    if pages > 1:
        head += f"  ·  PART {page} OF {pages}"
    rows = results[:RECAP_ROWS]

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

                sc = _clean_score(r.get("score"))
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

                sc = _clean_score(r.get("score"))
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


def _draw_reason_panel(d, bits: list[str], x0: int, y_top: int, x1: int, y_bottom: int) -> None:
    """The 'why it's here' lines under the price, from the pick's own evidence. Never overflows the card."""
    if not bits or y_bottom - y_top < 40:
        return
    y = y_top
    if y_bottom - y_top >= 92:
        d.text((x0, y), "WHY IT'S HERE", fill=GREEN, font=_font(16, True))
        y += 28
    fnt = _font(22, False)
    for bit in bits:
        for line in _wrap(d, bit, fnt, x1 - x0, 2):
            if y + 27 > y_bottom:
                return
            d.text((x0, y), line, fill=WHITE, font=fnt)
            y += 27
    d.rectangle((x0 - 16, y_top, x0 - 10, min(y, y_bottom)), fill=GREEN)


def render_pick(pick: dict, i: int, n: int, bg: Path, home_b: Path, away_b: Path, dest: Path,
                *, aspect: str | None = None, size: tuple[int, int] | None = None) -> None:
    from PIL import ImageDraw
    cw, ch = _resolve_size(aspect, size)
    im = _cover(bg, 0.58, size=(cw, ch))
    d = ImageDraw.Draw(im)
    k = f"TODAY'S SHORTLIST  ·  MATCH {i} OF {n}"
    reasons = pick_reason_bits(pick)
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

        _draw_reason_panel(d, reasons, rx0 + 60, y + 205, rx1 - 60, ry1 - 150)

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

        _draw_reason_panel(d, reasons, rx0 + 55, y + 178, rx1 - 55, ry1 - 130)

        d.rectangle((110, ch - 115, cw - 110, ch - 103), fill=(20, 48, 74))
        d.rectangle((110, ch - 115, 110 + int(i / max(n, 1) * (cw - 220)), ch - 103), fill=GREEN)
        foot = "PlayReport  ·  not betting advice  ·  18+"
        d.text(((cw - _tw(d, foot, _font(20, False))) // 2, ch - 64), foot, fill=MUTED, font=_font(20, False))
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


def _as_odds(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 1.0 else None


def _chance_phrase(p) -> str:
    """A probability as a presenter says it, and never the word \"percent\"."""
    try:
        v = float(p)
    except (TypeError, ValueError):
        return ""
    if v >= 0.95:
        return "better than nine in ten"
    if v >= 0.85:
        return "around nine in ten"
    if v >= 0.75:
        return "about three in four"
    if v >= 0.65:
        return "about two in three"
    if v >= 0.55:
        return "better than half"
    if v >= 0.45:
        return "around half"
    return "roughly a third"


def _form_string(p: dict, key: str) -> str:
    return "".join(ch for ch in str(p.get(key) or "").upper() if ch in "WDL")[:5]


def _won_phrase(form: str) -> str:
    """\"have won three of their last five\" / \"have not won any of their last five\"."""
    import spoken as sp

    f = "".join(ch for ch in str(form or "").upper() if ch in "WDL")
    if len(f) < 3:
        return ""
    wins = f.count("W")
    n = len(f)
    if wins == 0:
        return f"have not won any of their last {sp.words(n)}"
    return f"have won {sp.of_last(wins, n)}"


def _pick_xg(p: dict) -> tuple[float, float] | None:
    """The model's own projected goals, when the pick carries them (support string or direct fields)."""
    for a, b in (("mod_h", "mod_a"), ("xg_h", "xg_a")):
        try:
            return float(p[a]), float(p[b])
        except (KeyError, TypeError, ValueError):
            continue
    for s in (p.get("support") or []):
        m = re.search(r"(?:model\s+)?xG\s*([\d.]+)\s*[–\-]\s*([\d.]+)", str(s), re.I)
        if m:
            try:
                return float(m.group(1)), float(m.group(2))
            except ValueError:
                continue
    return None


def _pick_hist(p: dict) -> tuple[str, float] | None:
    """The historical base rate the pick cites (market code, probability)."""
    for s in (p.get("support") or []):
        m = re.search(r"historical\s+(O15|O25|BTTS)\s+rate\s+([\d.]+)\s*%", str(s), re.I)
        if m:
            try:
                return m.group(1).upper(), float(m.group(2)) / 100.0
            except ValueError:
                continue
    return None


def _pick_edge(p: dict) -> float | None:
    try:
        return float(p.get("edge_pp"))
    except (TypeError, ValueError):
        pass
    for s in (p.get("support") or []):
        m = re.search(r"model\s+([\d.]+)\s*pp\s+above", str(s), re.I)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                break
    return None


def pick_reason_bits(p: dict) -> list[str]:
    """Short, human phrases for the slide: why this match is on the list. Only the pick's own evidence."""
    import spoken as sp

    out: list[str] = []
    pv = _reel_p(p)
    if pv:
        out.append(f"Model {round(100 * pv)}% ({_chance_phrase(pv)})")
    xg = _pick_xg(p)
    if xg and str(p.get("market") or "").lower() in ("goals", "btts", "team", ""):
        out.append(f"Projected goals {xg[0]:.2f} – {xg[1]:.2f}")
    hist = _pick_hist(p)
    if hist:
        out.append(f"{hist[0]} landed in {round(100 * hist[1])}% of their matches")
    fh, fa = _form_string(p, "form_h"), _form_string(p, "form_a")
    if fh and fa:
        out.append(f"Last {len(fh)}: {sp.team(p.get('home'))} {fh}  ·  {sp.team(p.get('away'))} {fa}")
    edge = _pick_edge(p)
    if edge is not None and edge >= 1.0:
        out.append(f"Sits {edge:.1f} points above the market price")
    return out[:3]


def pick_reason_script(p: dict) -> str:
    """Why the pick is there, said aloud in one or two short sentences. No percentages, no table reading."""
    import spoken as sp

    home, away = str(p.get("home") or ""), str(p.get("away") or "")
    h, a = sp.team(home), sp.team(away)
    bits: list[str] = []
    pv = _reel_p(p)
    if pv:
        bits.append(f"The model has that at {_chance_phrase(pv)}")
    xg = _pick_xg(p)
    market = str(p.get("market") or "").lower()
    if xg and market in ("goals", "btts", "team", ""):
        bits.append(f"it projects {sp.per_game(xg[0])} goals for {h} and {sp.per_game(xg[1])} for {a}")
    for form_key, name in (("form_h", h), ("form_a", a)):
        phrase = _won_phrase(_form_string(p, form_key))
        if phrase:
            bits.append(f"{name} {phrase}")
            break
    tail = ""
    hist = _pick_hist(p)
    if hist:
        label = {"O15": "Over one and a half", "O25": "Over two and a half", "BTTS": "Both teams to score"}[hist[0]]
        tail = f"{label} has landed in {sp.rate(hist[1])} of their matches."
    if not bits and not tail:
        return ""
    head = ", ".join(bits[:-1]) + (" and " + bits[-1] if len(bits) > 1 else bits[0]) if bits else ""
    reason = f"{sp.cap(head)}." if head else ""
    edge = _pick_edge(p)
    if not tail and edge is not None and edge >= 2.0:
        tail = "It also sits above what the market implies."
    return " ".join(x for x in (reason, tail) if x)


def pick_script(p: dict, idx: int = 1, total: int = 1) -> str:
    """One pick, said once: competition, match, kick-off, the selection and price, then the reason it is here."""
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
    return " ".join(x for x in (f"{head} {match}.", f"{_PICK_LEAD[idx % len(_PICK_LEAD)]} {market}, at {od}.",
                                pick_reason_script(p)) if x)


def reel_results(yesterday: dict | list | None, limit: int | None = None) -> list[dict]:
    """Every settled selection from *all* of yesterday's videos, for the morning recap.

    The history is merged per day (morning + noon + evening) before it reaches here, so this is the full day's
    card, not just the last video. `limit` is only for a deliberate cap; the morning recap passes None.
    """
    if not yesterday:
        return []
    items = yesterday.get("items") if isinstance(yesterday, dict) else yesterday
    if not isinstance(items, list):
        return []
    settled = [x for x in items if isinstance(x, dict) and str(x.get("result") or "").lower() in ("hit", "miss", "void")]
    filtered = [x for x in settled if is_reel_market(x)]
    chosen = filtered if filtered else settled
    chosen = chosen[:MAX_RECAP]
    return chosen if limit is None else chosen[:limit]


def _score_words(raw) -> str:
    import spoken as sp

    m = re.match(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$", str(raw or ""))
    return sp.score(int(m.group(1)), int(m.group(2))) if m else ""


def _record_phrase(settled: list[dict]) -> str:
    import spoken as sp

    n = len(settled)
    if not n:
        return ""
    hits = sum(1 for r in settled if r.get("result") == "hit")
    if hits == n:
        return "It landed." if n == 1 else f"A clean sweep: all {sp.words(n)} landed."
    if hits == 0:
        return "A tough one, with none landing." if n == 1 else f"A tough one: none of the {sp.words(n)} landed."
    return f"We went {sp.words(hits)} from {sp.words(n)}."


def _notable(rows: list[dict]) -> str:
    """The one win and the one loss worth naming — the rest of the card is on screen, not read out."""
    import spoken as sp

    settled = [r for r in rows if r.get("result") in ("hit", "miss")]
    wins = sorted((r for r in settled if r.get("result") == "hit"), key=lambda r: -(_as_odds(r.get("odds")) or 0))
    losses = sorted((r for r in settled if r.get("result") == "miss"), key=lambda r: -(_as_odds(r.get("odds")) or 0))
    out = []
    for row, kind in ((wins[0] if wins else None, "hit"), (losses[0] if losses else None, "miss")):
        if row is None:
            continue
        home, away = row.get("home") or "", row.get("away") or ""
        mk = sp.market_phrase(row.get("label") or row.get("sel") or "the selection", home, away)
        sc = _score_words(row.get("score"))
        tail = f", {sc}" if sc else ""
        if kind == "hit":
            out.append(f"The standout: {sp.team(home)} against {sp.team(away)}, {mk}, landed{tail}.")
        else:
            out.append(f"The one that got away: {sp.team(home)} against {sp.team(away)}, {mk}, finished{tail}.")
    return " ".join(out)


def results_script(results: list[dict] | list, *, page: int = 1, pages: int = 1, rows: list[dict] | None = None) -> str:
    """Yesterday's card as a short, spoken look back: the record and the notable ones. Factual, no probabilities.

    Page one carries the day's record across every video plus the standout win and the one that got away; later pages
    are a single line for the rows on that slide. Nothing is read match by match — that is what the slide is for.
    """
    import spoken as sp

    all_rows = reel_results(results) if rows is None else list(rows)
    if not all_rows:
        return ""
    if page > 1:
        settled = [r for r in all_rows if r.get("result") in ("hit", "miss")]
        if not settled:
            return "The rest of yesterday's card is on screen."
        hits = sum(1 for r in settled if r.get("result") == "hit")
        if hits == len(settled):
            return f"The rest of the card: all {sp.words(len(settled))} of these landed."
        if hits == 0:
            return f"The rest of the card: none of these {sp.words(len(settled))} landed."
        return f"The rest of the card: {sp.words(hits)} of these {sp.words(len(settled))} landed."
    settled = [r for r in all_rows if r.get("result") in ("hit", "miss")]
    voids = sum(1 for r in all_rows if str(r.get("result") or "").lower() == "void")
    record = _record_phrase(settled)
    if record and voids:
        record += f" {sp.words(voids)} void."
    elif voids:
        record = f"{sp.words(voids)} void."
    notable = _notable(all_rows)
    rest = "Everything else is on screen." if len(all_rows) > 2 else ""
    return " ".join(x for x in ("First, a quick look back at yesterday, across all of yesterday's videos.",
                                record, notable, rest, "Now, today's shortlist.") if x)


def is_breakdown_market(p: dict) -> bool:
    """Match-breakdown videos: goals, corners and bookings (Overs). Independent of the morning reel pool."""
    blob = " ".join(str(p.get(k) or "") for k in ("label", "sel", "market", "group")).lower()
    if "under" in blob:
        return False
    if any(w in blob for w in ("corner", "card", "booking", "yellow")):
        return True
    if any(w in blob for w in ("over", "btts", "both teams", "to score", "team goal", "goals")):
        return True
    return False


REEL_MIN_P = 0.65   # user 2026-10-20: videos only carry selections at 65%+


def _reel_p(p: dict) -> float | None:
    for k in ("p", "p_cal", "prob"):
        try:
            v = float(p.get(k))
        except (TypeError, ValueError):
            continue
        if v == v:
            return v
    return None


REEL_MARKET_RE = re.compile(r"^(?:O15|[HA]O\d+|C[HA]?O\d+|K[HA]?O\d+)$")


def is_reel_market(p: dict) -> bool:
    """Videos carry Over 1.5 total goals, team goals, corners and bookings — nothing else (user rule 2026-10-21).

    BTTS, Over 2.5, 1X2 and every under are out, and no accumulator is built from the picks any more.
    """
    sel = str(p.get("sel") or "").upper()
    blob = " ".join(str(p.get(k) or "") for k in ("label", "market", "group")).lower()
    if "under" in blob or "no btts" in blob:
        return False
    return bool(REEL_MARKET_RE.match(sel))


def _match_key(p: dict) -> tuple:
    return (str(p.get("kickoff") or ""), str(p.get("home") or ""), str(p.get("away") or ""))


def reel_picks(picks: list, *, used: set | None = None) -> list:
    """At least twelve when the pool allows: one selection per match, 65%+, never a match already shown today."""
    rank = {"O15": 0, "HO05": 1, "AO05": 1, "HO15": 1, "AO15": 1}
    skip = used or set()
    best = {}
    order = []
    for p in picks or []:
        if not is_reel_market(p):
            continue
        pr = _reel_p(p)
        if pr is None or pr < REEL_MIN_P:
            continue
        k = _match_key(p)
        if k in skip or (k[1], k[2]) in skip:
            continue
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


def build(picks: list, outfile: Path, *, assets: Path, work: Path | None = None,
          fixtures: list | None = None, yesterday_results: dict | list | None = None,
          aspect: str = "16:9", recap: bool = True) -> Path:
    """Build a 16:9 widescreen (1920x1080) or 9:16 vertical reel (1080x1920) video.

    Order: intro, disclaimer, yesterday's full card (first video of the day only), today's matches one at a time with
    the reason for each. Each pick appears once. Slide length = its words' reading time + TAIL (intro at least
    INTRO_MIN), muxed over one looped music bed. No voice, no accumulator slide.
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
        recap_rows = reel_results(yesterday_results) if recap else []
        recap_day = yesterday_results.get("day", "") if isinstance(yesterday_results, dict) else ""

        assets = Path(assets)
        logo = assets / "logo.png"
        bgs = [assets / "bg_stadium.jpg", assets / "bg_pitch.jpg", assets / "bg_lights.jpg"]
        fixtures = fixtures or []

        work = Path(work) if work else Path(tempfile.mkdtemp(prefix="pr-reel-"))
        work.mkdir(parents=True, exist_ok=True)
        slides_dir = work / "slides"
        slides_dir.mkdir(exist_ok=True)
        crests = work / "crests"
        crests.mkdir(exist_ok=True)

        n = len(picks)
        render_intro(logo, bgs[0], slides_dir / "intro.jpg")
        render_disclaimer(logo, bgs[1], slides_dir / "disclaimer.jpg")

        texts = [INTRO_SCRIPT, DISCLAIMER_SCRIPT]
        images = [slides_dir / "intro.jpg", slides_dir / "disclaimer.jpg"]

        pages: list[list[dict]] = []
        if recap_rows:
            pages = [recap_rows[i:i + RECAP_ROWS] for i in range(0, len(recap_rows), RECAP_ROWS)]
            for pageno, page_rows in enumerate(pages, 1):
                res_img = slides_dir / f"results{pageno:02d}.jpg"
                render_results(page_rows, logo, bgs[2], res_img, day_label=recap_day,
                               page=pageno, pages=len(pages), all_rows=recap_rows)
                images.append(res_img)
                texts.append(results_script(recap_rows, page=pageno, pages=len(pages), rows=page_rows))

        # Every match is introduced once — match, selection, price and the reason it is on the list.
        pi = 0
        for p in picks:
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

        durations = [frame_hold(hold_seconds(i, music.reading_seconds(text)))
                     for i, text in enumerate(texts)]

        total = sum(durations)
        max_allowed = MAX_TOTAL + (180.0 if recap_rows else 0.0)
        if total > max_allowed and len(picks) > 6:
            log.info("reel %.1fs > %.0fs — dropping the last three picks", total, max_allowed)
            return build(
                picks[:-3], outfile, assets=assets, work=work,
                fixtures=fixtures, yesterday_results=yesterday_results, aspect=aspect, recap=recap,
            )

        # build_both reads this to give the 9:16 cut the same picks the 16:9 cut kept.
        (work / "build_meta.json").write_text(json.dumps({"picks_count": len(picks)}), encoding="utf-8")

        clips = []
        for i, (img, dur) in enumerate(zip(images, durations)):
            clip = work / f"v{i:02d}.mp4"
            still_clip(img, clip, dur, ff)
            clips.append(clip)

        lst_v = work / "v.txt"
        lst_v.write_text("".join(f"file '{c}'\n" for c in clips))
        silent = work / "silent.mp4"
        _run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(lst_v), "-c", "copy", str(silent)], "concat v")

        # One track for the whole video: the user's file, looped to the picture's length, faded and normalised.
        bed = music.bed(total, work / "bed.m4a", ff, assets=assets)

        outfile = Path(outfile)
        outfile.parent.mkdir(parents=True, exist_ok=True)
        music.mux(silent, bed, outfile, ff, bitrate="192k")
        log.info("reel built %s [%s] (%.1fs, %d KB) music=%s", outfile.name, aspect, total,
                 outfile.stat().st_size // 1024, music.MUSIC_FILE)
        return outfile
    finally:
        _ACTIVE_SIZE = prev_size


def build_both(picks: list, out_16x9: Path, out_9x16: Path, *, assets: Path, work: Path | None = None,
               fixtures: list | None = None, yesterday_results: dict | list | None = None,
               recap: bool = True) -> tuple[Path, Path]:
    """Build both 16:9 widescreen (1920x1080) and 9:16 vertical reel (1080x1920) with the same slides and music.

    The 9:16 cut uses the picks the 16:9 cut actually kept (the length cap can drop the last three), and its
    slides are timed from the same words, so both cuts tell the same story in the same order.
    """
    base_work = Path(work) if work else Path(tempfile.mkdtemp(prefix="pr-dual-"))
    w16 = base_work / "w16x9"
    w9 = base_work / "w9x16"
    p16 = build(
        picks, out_16x9, assets=assets, work=w16,
        fixtures=fixtures, yesterday_results=yesterday_results, aspect="16:9", recap=recap,
    )
    used_picks = reel_picks(picks)
    meta_file = w16 / "build_meta.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            used_picks = used_picks[: int(meta.get("picks_count", len(used_picks)))]
        except (OSError, ValueError):
            pass
    p9 = build(
        used_picks, out_9x16, assets=assets, work=w9,
        fixtures=fixtures, yesterday_results=yesterday_results, aspect="9:16", recap=recap,
    )
    return p16, p9


def from_shortlist(sl_pub: dict, fixtures: list, outfile: Path, assets: Path, work: Path | None = None,
                   yesterday_results: dict | list | None = None, *, aspect: str = "16:9", recap: bool = True) -> Path:
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
    return build(prim, outfile, assets=assets, work=work, fixtures=fixtures, yesterday_results=yres,
                 aspect=aspect, recap=recap)

