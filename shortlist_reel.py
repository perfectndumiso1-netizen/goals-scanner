"""Mr 2 Odds shortlist video — 16:9 widescreen (1920x1080) or 9:16 vertical, one music bed, no narration.

2026-10-21 (user rule): there is no voice any more — no neural TTS, no Piper, no eSpeak, nothing to speak. Every
video carries the user's track `assets/reel/under_the_stadium_lights.mp3` for its whole length (looped, faded and
normalised by `music.bed`). Slide lengths come from how long each slide's words take to read, at the pace the
narration used to speak them, so the length and the format of the videos are unchanged.

The morning video opens with the settled results of *every* video from yesterday (morning, noon and evening),
then walks today's matches one at a time. Without a voice, each match is up to three short slides — THE PICK (the
selection, its price and a chart of every market the video covers, with the featured one as the tallest bar), WHY
IT'S HERE (reasons, trends, league standing and venue splits) and THE RECORD (head to head and both teams' last
five); see `reel_insights` for where every number comes from. Videos carry Over 1.5 total goals, team goals, corners
and bookings only, and no accumulator is built, shown or mentioned anywhere (user rules 2026-10-21).
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
from datetime import datetime
from pathlib import Path

import music
import reel_insights

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
GREEN = (44, 225, 204)
RED = (239, 68, 68)
WHITE = (242, 248, 255)
MUTED = (170, 190, 210)
GOLD = (251, 191, 36)
NAVY = (9, 12, 31)
CARD_BG = (17, 23, 48)
BADGE_BASE = "https://lsm-static-prod.livescore.com/medium/"
TAIL = 0.70          # extra hold after a slide's words so the next one never lands on top of the last line
INTRO_MIN = 5.0      # logo sting, seconds
# 2026-10-27 (user): the videos carry Over 1.5 only, and they were too fast to read. Fewer matches, each on screen
# long enough to take in: eight matches at three slides is a full video without racing the reader.
MAX_PICKS = 8
MAX_TOTAL = 600.0
RECAP_ROWS = 9       # results per recap slide (readable in both 16:9 and 9:16)
MAX_RECAP = 60       # every selection from yesterday's three videos, with a hard ceiling

INTRO_SCRIPT = "Mr 2 Odds. These are the matches worth your attention today."
DISCLAIMER_SCRIPT = (
    "Quick note before we start. This is statistical information, not betting advice. "
    "It's eighteen plus only, so please bet responsibly. "
    "Never use money you can't afford to lose, and remember, there's no such thing as a sure bet."
)
CLOSER_SCRIPT = (
    "That's the list. Take them as singles, take fewer, or skip the ones you don't like. "
    "If this helped, give it a like, share it with a mate, and subscribe for tomorrow's list. "
    "Mr 2 Odds. All rights reserved."
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
    im = Image.blend(im, overlay, dark)
    from PIL import ImageDraw
    ink = ImageDraw.Draw(im)
    w, h = im.size
    ink.line((0, h-12, w, h-12), fill=GREEN, width=4)
    ink.line((0, 12, w//3, 12), fill=GOLD, width=4)
    for x in range(w//2, w+200, 140):
        ink.line((x, 0, x-240, h), fill=(28, 37, 61), width=1)
    return im


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
    lab = "MR 2 ODDS"
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
        foot = "Mr 2 Odds  ·  18+"
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
        foot = "Mr 2 Odds  ·  18+"
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
        foot = "Mr 2 Odds  ·  18+"
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
        foot = "Mr 2 Odds  ·  18+"
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
        foot = "Mr 2 Odds  ·  verified pre-match shortlist ledger  ·  18+"
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
        foot = "Mr 2 Odds  ·  verified pre-match shortlist ledger  ·  18+"
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
        foot = "Mr 2 Odds  ·  not betting advice  ·  18+"
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
        foot = "Mr 2 Odds  ·  not betting advice  ·  18+"
        d.text(((cw - _tw(d, foot, _font(20, False))) // 2, ch - 64), foot, fill=MUTED, font=_font(20, False))
    im.convert("RGB").save(dest, quality=92)


# ============================================================================ deeper pick slides
# Since the voice was retired (2026-10-21) a pick is shown as three short slides instead of one long one: the pick
# and the market chart it tops, the evidence behind it (reasons, trends, league standing, venue splits) and the
# record (head to head plus both teams' recent results). The screen changes every few seconds, and every number on
# it comes from the app's own fixture detail — see reel_insights.

# The minimum time a slide of each kind is on screen (2026-10-27: raised from 5.0 / 5.6 / 6.0 — the viewer could not
# read the numbers before the next slide arrived).
STAGE_FLOOR = {"pick": 6.5, "evidence": 7.5, "record": 8.5}


def _ellip(d, s: str, fnt, max_w: int) -> str:
    """One line, cut with an ellipsis if it will not fit — never a clipped or overflowing row."""
    s = str(s or "")
    if _tw(d, s, fnt) <= max_w:
        return s
    while s and _tw(d, s + "…", fnt) > max_w:
        s = s[:-1]
    return (s.rstrip() + "…") if s else ""


def _fit(rows: int, avail: int, lo: int, hi: int) -> int:
    """Row height that spreads `rows` over `avail` pixels — few rows get bigger, many rows get tighter."""
    if rows <= 0:
        return hi
    return max(lo, min(hi, int(avail / rows)))


def _heading(d, x: int, y: int, text: str, *, size: int = 20, colour=GREEN) -> int:
    d.text((x, y), str(text).upper(), fill=colour, font=_font(size, True))
    return y + int(size * 1.75)


def _stage_header(d, cw: int, ch: int, stage: str, i: int, n: int, comp: str, *, wide: bool) -> int:
    """Wordmark, the match counter, the competition and the stage name — the same furniture on every slide."""
    _wordmark(d, 26 if wide else 56, width=cw)
    kicker = f"MATCH {i} OF {n}  ·  {stage.upper()}"
    kf = _font(24 if wide else 26, True)
    d.text(((cw - _tw(d, kicker, kf)) // 2, 92 if wide else 132), kicker, fill=GREEN, font=kf)
    y = 126 if wide else 176
    if comp:
        cf = _font(21 if wide else 24, False)
        for line in _wrap(d, comp, cf, cw - 160, 1):
            d.text(((cw - _tw(d, line, cf)) // 2, y), line, fill=MUTED, font=cf)
        y += 30 if wide else 34
    return y


def _stage_footer(d, cw: int, ch: int, *, wide: bool) -> None:
    foot = "Mr 2 Odds  ·  not betting advice  ·  18+"
    f = _font(20 if wide else 22, False)
    d.text(((cw - _tw(d, foot, f)) // 2, ch - (58 if wide else 92)), foot, fill=MUTED, font=f)


def _progress_bar(d, cw: int, ch: int, i: int, n: int, *, wide: bool) -> None:
    x0, x1 = (110, cw - 110) if wide else (76, cw - 76)
    y = ch - (112 if wide else 148)
    d.rectangle((x0, y, x1, y + 12), fill=(20, 48, 74))
    d.rectangle((x0, y, x0 + int(i / max(n, 1) * (x1 - x0)), y + 12), fill=GREEN)


def _chart(d, rows: list[dict], box: tuple[int, int, int, int], *, wide: bool) -> None:
    """Horizontal probability bars: the model's Over 1.5 against the de-vigged market's.

    The scale runs from 50% to 100% rather than from zero: every pick is 65%+ by rule, so a zero-based axis would
    draw two identical-looking bars and hide the gap the reader is here to see. The axis is labelled, so the
    truncation is never hidden. In portrait each bar gets its own label line above it — a 9:16 frame cannot fit a
    market name beside a bar without cutting the name in half.
    """
    x0, y0, x1, y1 = box
    if not rows:
        return
    top_p = max(r.get("p", 0.0) for r in rows)
    picked_top = bool(rows[0].get("picked"))
    market = next((r for r in rows if r.get("market")), None)
    title = _heading(d, x0, y0, "Over 1.5 — model vs market" if market else "Over 1.5 probability",
                     size=19 if wide else 22)
    if market:
        mine = next((r for r in rows if r.get("picked")), rows[0])
        gap = 100 * (mine.get("p", 0.0) - market.get("p", 0.0))
        if abs(gap) < 0.5:
            # the published number is the model blended towards this price, so the two often land together. Say that
            # plainly instead of dressing a half-point difference up as an edge.
            note = f"model and market agree at {100 * mine.get('p', 0):.0f}% — no edge claimed"
        elif gap > 0:
            note = f"model {100 * mine.get('p', 0):.0f}% · market {100 * market.get('p', 0):.0f}% · {gap:.0f} pts above"
        else:
            note = f"model {100 * mine.get('p', 0):.0f}% · market {100 * market.get('p', 0):.0f}% · {-gap:.0f} pts below"
        picked_top = True                    # the slide is about the model's number, which is always the first bar
    else:
        note = "the model's own number — the book did not price this one"
        picked_top = True
    nf = _font(15 if wide else 19, False)
    if wide:
        d.text((x1 - _tw(d, note, nf), y0 + 4), note, fill=GREEN if picked_top else MUTED, font=nf)
    else:
        d.text((x0, y0 + 34), _ellip(d, note, nf, x1 - x0), fill=GREEN if picked_top else MUTED, font=nf)
        title += 14

    top = title + (4 if wide else 10)
    axis_h = 28 if wide else 34
    avail = max(60, (y1 - axis_h) - top)
    rowh = _fit(len(rows), avail, 34 if wide else 58, 74 if wide else 104)
    top += max(0, (avail - rowh * len(rows)) // 2)          # a short chart sits mid-panel, not at its top
    pct_w = 78
    label_w = int((x1 - x0) * 0.34)
    track_x0 = x0 if not wide else x0 + label_w
    track_x1 = x1 - (pct_w if wide else pct_w + 4)
    track_w = max(40, track_x1 - track_x0)
    bar_h = max(16, min(34, int(rowh * (0.46 if wide else 0.3))))
    fs = int(min(26, max(19, rowh * (0.42 if wide else 0.3))))
    lf, lfb = _font(fs, False), _font(fs, True)
    pf = _font(int(min(28, max(20, fs * 1.05))), True)

    def place(p: float) -> int:
        return track_x0 + int(track_w * max(0.0, min(1.0, (p - 0.5) / 0.5)))

    for idx, row in enumerate(rows):
        slot_y = top + idx * rowh
        picked = bool(row.get("picked"))
        label = row.get("label") or ""
        pct = f"{100 * row.get('p', 0):.0f}%"
        if wide:
            cy = slot_y + rowh // 2
            d.text((x0, cy - lf.size // 2 - 2), _ellip(d, label, lfb if picked else lf, label_w - 24),
                   fill=WHITE if picked else MUTED, font=lfb if picked else lf)
        else:
            cy = slot_y + int(rowh * 0.62)
            d.text((x0, slot_y), _ellip(d, label, lfb if picked else lf, x1 - x0 - 120),
                   fill=WHITE if picked else MUTED, font=lfb if picked else lf)
        d.rounded_rectangle((track_x0, cy - bar_h // 2, track_x1, cy + bar_h // 2), bar_h // 2,
                            fill=(16, 46, 38) if picked else (18, 38, 60))
        w = max(8, place(row.get("p", 0.0)) - track_x0)
        d.rounded_rectangle((track_x0, cy - bar_h // 2, track_x0 + w, cy + bar_h // 2), bar_h // 2,
                            fill=GREEN if picked else (66, 96, 132))
        d.text((track_x1 + 14, cy - pf.size // 2 - 2), pct, fill=WHITE if picked else MUTED, font=pf)
        if picked:
            if wide:
                d.text((track_x1 + 14, cy + pf.size // 2 - 2), "PICK", fill=GREEN, font=_font(13, True))
            else:
                d.text((x1 - _tw(d, "PICK", _font(15, True)), slot_y), "PICK", fill=GREEN, font=_font(15, True))

    axis_y = top + len(rows) * rowh + (4 if wide else 10)
    af = _font(14 if wide else 18, False)
    for frac, lab in ((0.0, "50%"), (0.5, "75%"), (1.0, "100%")):
        x = track_x0 + int(track_w * frac)
        d.line((x, axis_y, x, axis_y + 6), fill=(70, 100, 130), width=2)
        d.text((x - _tw(d, lab, af) // 2, axis_y + 8), lab, fill=(120, 148, 175), font=af)


def _team_form_block(d, pick: dict, x: int, y: int, w: int, *, wide: bool) -> int:
    """Team names with their last-five pills, side by side."""
    f = _font(22 if wide else 26, True)
    half = w // 2
    for idx, key in enumerate(("form_h", "form_a")):
        name = _ellip(d, str(pick.get("home") if idx == 0 else pick.get("away") or ""), f, half - 20)
        cx = x + idx * half + half // 2
        d.text((cx - _tw(d, name, f) // 2, y), name, fill=WHITE, font=f)
        form = str(pick.get(key) or "")
        if form:
            _draw_form_pills(d, form, cx, y + (34 if wide else 40))
    return y + (74 if wide else 86)


def _venue_lines(pick: dict, detail: dict | None) -> list[str]:
    teams = (detail or {}).get("teams") or {}
    home, away = teams.get("home") or {}, teams.get("away") or {}
    out = []
    hgf, hga = home.get("venue_gf"), home.get("venue_ga")
    if hgf is not None and hga is not None:
        out.append(f"At home: {hgf:.2f} scored · {hga:.2f} conceded")
    agf, aga = away.get("venue_gf"), away.get("venue_ga")
    if agf is not None and aga is not None:
        out.append(f"Away: {agf:.2f} scored · {aga:.2f} conceded")
    return out


def render_pick_overview(pick: dict, i: int, n: int, bg: Path, home_b: Path, away_b: Path, dest: Path,
                         *, aspect: str | None = None, size: tuple[int, int] | None = None,
                         chart: list[dict] | None = None) -> None:
    """Slide 1 of a match: the selection and its price up top, every market's probability filling the frame."""
    from PIL import ImageDraw
    cw, ch = _resolve_size(aspect, size)
    wide = cw >= ch
    im = _cover(bg, 0.62, size=(cw, ch))
    d = ImageDraw.Draw(im)
    _stage_header(d, cw, ch, "the pick", i, n, competition_line(pick), wide=wide)

    # ---- top left: the two clubs, their form and the kick-off
    bsize = 132 if wide else 150
    gap = 110 if wide else 140
    left_x0 = 80 if wide else 60
    left_w = 700 if wide else cw - 120
    total = bsize * 2 + gap
    x0 = left_x0 + (left_w - total) // 2
    y0 = 196 if wide else 250
    hb, ab = _circle_badge(home_b, bsize), _circle_badge(away_b, bsize)
    im.paste(hb, (x0, y0), hb)
    im.paste(ab, (x0 + bsize + gap, y0), ab)
    d = ImageDraw.Draw(im)
    vf = _font(28 if wide else 32, True)
    d.text((x0 + bsize + (gap - _tw(d, "VS", vf)) // 2, y0 + bsize // 2 - 16), "VS", fill=WHITE, font=vf)
    _team_form_block(d, pick, left_x0, y0 + bsize + (22 if wide else 30), left_w, wide=wide)

    ko = str(pick.get("kickoff") or "")[11:16]
    kt = f"KICK-OFF  {ko} SAST" if ko else "TODAY  ·  SAST"
    kf = _font(25 if wide else 30, True)
    kw = _tw(d, kt, kf) + (48 if wide else 60)
    kcx = left_x0 + left_w // 2
    kby = y0 + bsize + (92 if wide else 120)
    d.rounded_rectangle((kcx - kw // 2, kby, kcx + kw // 2, kby + (46 if wide else 56)), 16,
                        fill=(16, 40, 66), outline=GOLD, width=2)
    d.text((kcx - _tw(d, kt, kf) // 2, kby + (9 if wide else 12)), kt, fill=GOLD, font=kf)

    # ---- top right: the selection card
    pv, od = pick.get("p"), pick.get("odds")
    if wide:
        cx0, cy0, cx1, cy1 = 880, 190, cw - 54, 392
    else:
        cx0, cy0, cx1, cy1 = 60, 640, cw - 60, 900
    d.rounded_rectangle((cx0, cy0, cx1, cy1), 26 if wide else 30, fill=CARD_BG, outline=GREEN, width=3)
    d.text((cx0 + 32, cy0 + 20), "THE SELECTION", fill=GREEN, font=_font(18 if wide else 20, True))
    label_f = _font(40 if wide else 42, True)
    od_txt = f"{od:.2f}" if isinstance(od, (int, float)) else "N/A"
    label_w = (cx1 - cx0) - 260 if wide else (cx1 - cx0) - 70
    y = cy0 + (52 if wide else 55)
    for line in _wrap(d, pick.get("label") or "", label_f, label_w, 2):
        d.text((cx0 + 32, y), line, fill=WHITE, font=label_f)
        y += 46 if wide else 50
    odds_f = _font(84 if wide else 76, True)
    if wide:
        d.text((cx1 - 32 - _tw(d, od_txt, odds_f), cy0 + 38), od_txt, fill=GREEN, font=odds_f)
        d.text((cx1 - 32 - _tw(d, "SPORTYBET PRICE", _font(15, True)), cy0 + 132), "SPORTYBET PRICE",
               fill=MUTED, font=_font(15, True))
    else:
        d.text((cx0 + 32, y + 8), od_txt, fill=GREEN, font=odds_f)
        d.text((cx0 + 32 + _tw(d, od_txt, odds_f) + 18, y + 60), "SPORTYBET PRICE", fill=MUTED,
               font=_font(17, True))
    if isinstance(pv, (int, float)):
        chip = f"MODEL {100 * pv:.0f}%"
        cf = _font(19 if wide else 22, True)
        cwid = _tw(d, chip, cf) + 30
        bx = (cx1 - 32 - cwid) if wide else (cx0 + 32)
        by = (cy1 - 52) if wide else (cy1 - 52)
        d.rounded_rectangle((bx, by, bx + cwid, by + (36 if wide else 42)), 12, fill=(16, 52, 40),
                            outline=GREEN, width=2)
        d.text((bx + 15, by + (7 if wide else 9)), chip, fill=GREEN, font=cf)

    # ---- the chart across the whole width: this is the slide's point, so it gets the room
    chart_box = (80, 506, cw - 54, ch - 150) if wide else (60, 960, cw - 60, ch - 175)
    _chart(d, chart or [], chart_box, wide=wide)
    _progress_bar(d, cw, ch, i, n, wide=wide)
    _stage_footer(d, cw, ch, wide=wide)
    im.convert("RGB").save(dest, quality=92)


def _fill_slots(d, box: tuple[int, int, int, int], heading: str, slots: list, *, wide: bool,
                pad: int, cap: int = 96, lo: int = 17, hi: int = 32, rule: bool = False,
                center: bool = True) -> None:
    """Lay a card out under its heading, using the card instead of pooling in the top third.

    `slots` are callables taking (x, y, w, h). Each gets an equal share of the space under the heading, but never
    more than `cap` — a two-line card is centred rather than dragged apart — and the whole group is centred in the
    card vertically. Fonts are sized from the slot height so the two cards stay balanced with each other.
    """
    _heading(d, box[0] + pad, box[1] + pad, heading, size=19 if wide else 22)
    top = box[1] + pad + int((19 if wide else 22) * 1.75)
    avail = max(1, (box[3] - pad) - top)
    h = max(1, min(cap or avail, avail // max(1, len(slots))))
    size = max(lo, min(hi, int(h * 0.46)))
    y = top + (max(0, (avail - h * len(slots)) // 2) if center else 0)
    for idx, fn in enumerate(slots):
        if rule and idx:
            d.line((box[0] + pad, y + 1, box[2] - pad, y + 1), fill=(26, 52, 80), width=1)
        fn(box[0] + pad, y, (box[2] - box[0]) - pad * 2, h, size)
        y += h


def render_pick_evidence(pick: dict, i: int, n: int, bg: Path, dest: Path, *,
                         aspect: str | None = None, size: tuple[int, int] | None = None,
                         reasons: list[str] | None = None, trends: list[str] | None = None,
                         table: dict | None = None, detail: dict | None = None) -> None:
    """Slide 2 of a match: why it is on the list — reasons, trends, standing and the venue splits."""
    from PIL import ImageDraw
    cw, ch = _resolve_size(aspect, size)
    wide = cw >= ch
    im = _cover(bg, 0.66, size=(cw, ch))
    d = ImageDraw.Draw(im)
    _stage_header(d, cw, ch, "why it's here", i, n, competition_line(pick), wide=wide)
    reasons, trends = reasons or [], trends or []
    pad = 26 if wide else 30

    if wide:
        lx0, ly0, lx1, ly1 = 80, 186, 900, ch - 150
        rx0, ry0, rx1, ry1 = 930, 186, cw - 54, ch - 150
    else:
        lx0, ly0, lx1, ly1 = 50, 235, cw - 50, 905
        rx0, ry0, rx1, ry1 = 50, 935, cw - 50, ch - 185
    for box in ((lx0, ly0, lx1, ly1), (rx0, ry0, rx1, ry1)):
        d.rounded_rectangle(box, 24 if wide else 28, fill=CARD_BG, outline=(30, 62, 96), width=2)

    teams = (table or {}).get("teams") or {}
    size_n = (table or {}).get("size") or 0
    venue = _venue_lines(pick, detail)

    # ---- left: each club's standing, its form and its home/away numbers, as four rows per club
    left_slots = []
    for idx, key in enumerate(("home", "away")):
        row = teams.get(key)
        name = str(pick.get(key if key == "home" else "away") or "")
        stand = reel_insights.standing_line(row, size_n) if row else "No league table published for this competition"
        form = str((row or {}).get("form") or pick.get("form_h" if idx == 0 else "form_a") or "")
        venue_line = venue[idx] if idx < len(venue) else ""

        def name_slot(x, y, w, h, size, name=name):
            d.text((x, y + int(h * 0.04)), _ellip(d, name, _font(int(size * 1.18), True), w),
                   fill=WHITE, font=_font(int(size * 1.18), True))

        def stand_slot(x, y, w, h, size, stand=stand):
            f = _font(size, False)
            d.text((x, y + int(h * 0.1)), _ellip(d, stand, f, w), fill=MUTED, font=f)

        def form_slot(x, y, w, h, size, form=form):
            if form:
                _draw_form_pills(d, form, x + 90, y + int(h * 0.08))

        def venue_slot(x, y, w, h, size, venue_line=venue_line):
            if not venue_line:
                return
            f = _font(size, False)
            d.text((x, y + int(h * 0.1)), _ellip(d, venue_line, f, w), fill=WHITE, font=f)

        left_slots += [name_slot, stand_slot, form_slot, venue_slot]
    _fill_slots(d, (lx0, ly0, lx1, ly1), "League standing & venue", left_slots, wide=wide, pad=pad, cap=92)

    # ---- right: the reasons and the trends
    right_slots = []
    for bit in reasons[:4]:
        def reason_slot(x, y, w, h, size, bit=bit):
            f = _font(int(size * 1.02), False)
            lines = _wrap(d, bit, f, w - 24, 2)
            ly = y + max(0, (h - len(lines) * int(f.size * 1.25)) // 2)
            d.rectangle((x, ly + 4, x + 6, ly + 6 + int(f.size * 1.05)), fill=GREEN)
            for part in lines:
                d.text((x + 22, ly), part, fill=WHITE, font=f)
                ly += int(f.size * 1.25)
        right_slots.append(reason_slot)
    for t in trends[:3]:
        def trend_slot(x, y, w, h, size, t=t):
            f = _font(int(size * 0.92), False)
            lines = _wrap(d, f"•  {t}", f, w, 2)
            ly = y + max(0, (h - len(lines) * int(f.size * 1.25)) // 2)
            for part in lines:
                d.text((x, ly), part, fill=MUTED, font=f)
                ly += int(f.size * 1.25)
        right_slots.append(trend_slot)
    heading = "Why this pick" + ("  ·  trends" if trends else "")
    _fill_slots(d, (rx0, ry0, rx1, ry1), heading, right_slots, wide=wide, pad=pad, cap=100)

    _progress_bar(d, cw, ch, i, n, wide=wide)
    _stage_footer(d, cw, ch, wide=wide)
    im.convert("RGB").save(dest, quality=92)


def _result_pill(d, x: int, y: int, res: str, size: int) -> None:
    col = {"W": (34, 197, 94), "D": (100, 116, 139), "L": (239, 68, 68)}.get(res, (100, 116, 139))
    d.rounded_rectangle((x, y, x + size, y + size), 7, fill=col)
    f = _font(int(size * 0.62), True)
    d.text((x + (size - _tw(d, res, f)) // 2, y + int(size * 0.14)), res, fill=NAVY if res == "W" else WHITE, font=f)


def render_pick_record(pick: dict, i: int, n: int, bg: Path, dest: Path, *,
                       aspect: str | None = None, size: tuple[int, int] | None = None,
                       home_recent: list[dict] | None = None, away_recent: list[dict] | None = None,
                       h2h: dict | None = None) -> None:
    """Slide 3 of a match: head to head on the left, both teams' last results on the right."""
    from PIL import ImageDraw
    cw, ch = _resolve_size(aspect, size)
    wide = cw >= ch
    im = _cover(bg, 0.68, size=(cw, ch))
    d = ImageDraw.Draw(im)
    _stage_header(d, cw, ch, "the record", i, n, competition_line(pick), wide=wide)
    home_recent, away_recent = home_recent or [], away_recent or []
    pad = 26 if wide else 30

    if wide:
        lx0, ly0, lx1, ly1 = 80, 186, 900, ch - 150
        rx0, ry0, rx1, ry1 = 930, 186, cw - 54, ch - 150
    else:
        lx0, ly0, lx1, ly1 = 50, 235, cw - 50, 880
        rx0, ry0, rx1, ry1 = 50, 910, cw - 50, ch - 185
    for box in ((lx0, ly0, lx1, ly1), (rx0, ry0, rx1, ry1)):
        d.rounded_rectangle(box, 24 if wide else 28, fill=CARD_BG, outline=(30, 62, 96), width=2)

    h2h_rows = (h2h or {}).get("rows") or []
    left_slots = []
    if h2h:
        def summary_slot(x, y, w, h, size, line=h2h["line"]):
            f = _font(int(size * 0.9), False)
            d.text((x, y + int(h * 0.2)), _ellip(d, line, f, w), fill=GREEN, font=f)
        left_slots.append(summary_slot)
    for r in h2h_rows[:5]:
        def h2h_slot(x, y, w, h, size, r=r):
            pill = max(24, min(40, int(h * 0.52)))
            f = _font(int(size * 0.86), False)
            ty = y + (h - f.size) // 2 - 2
            df = _font(int(size * 0.72), False)
            d.text((x, ty + 2), r["date"], fill=MUTED, font=df)
            dx = x + _tw(d, r["date"], df) + 18
            fixture, room = f"{r['home']} v {r['away']}", w - (dx - x) - 150
            # shrink before cutting: a head-to-head line that names both clubs is the point of the row
            fs = f.size
            while fs > 14 and _tw(d, fixture, _font(fs, False)) > room:
                fs -= 1
            f = _font(fs, False)
            if fs < int(size * 0.86):
                ty = y + (h - f.size) // 2 - 2
            d.text((dx, ty), _ellip(d, fixture, f, room), fill=WHITE, font=f)
            score = f"{r['hg']}–{r['ag']}"
            d.text((x + w - 96 - _tw(d, score, f), ty), score, fill=WHITE, font=f)
            _result_pill(d, x + w - 74, ty - 2, r["res"], pill)
        left_slots.append(h2h_slot)
    if not left_slots:
        left_slots.append(lambda x, y, w, h, size: d.text((x, y), "No meetings on record",
                                                          fill=MUTED, font=_font(size, False)))
    _fill_slots(d, (lx0, ly0, lx1, ly1), "Head to head", left_slots, wide=wide, pad=pad, cap=150, hi=30, rule=True, center=False)

    # ---- right: two columns, one per club
    rows = max(len(home_recent), len(away_recent), 1)
    right_slots = []
    for idx in range(rows):
        def recent_slot(x, y, w, h, size, idx=idx):
            col_w = (w - 30) // 2
            for side, (name, team_rows) in enumerate(((pick.get("home"), home_recent),
                                                      (pick.get("away"), away_recent))):
                bx = x + side * (col_w + 30)
                nf = _font(int(size * 1.0), True)
                row_top = y
                if idx == 0:                     # the club's name sits above its first result
                    d.text((bx, y), _ellip(d, str(name or ""), nf, col_w), fill=WHITE, font=nf)
                    row_top = y + int(nf.size * 1.5)
                r = team_rows[idx] if idx < len(team_rows) else None
                if not r:
                    continue
                pill = max(24, min(38, int(h * 0.5)))
                f = _font(int(size * 0.86), False)
                ry = row_top + max(0, (h - int(nf.size * 1.5) - f.size) // 2) if idx == 0 \
                    else row_top + (h - f.size) // 2 - 2
                d.text((bx, ry + 2), _ellip(d, r["opp"], f, col_w - 112), fill=MUTED, font=f)
                sc = f"{r['gf']}–{r['ga']}"
                d.text((bx + col_w - 92 - _tw(d, sc, f), ry + 2), sc, fill=WHITE, font=f)
                _result_pill(d, bx + col_w - 70, ry, r["res"], pill)
        right_slots.append(recent_slot)
    _fill_slots(d, (rx0, ry0, rx1, ry1), "Recent matches", right_slots, wide=wide, pad=pad, cap=150, hi=30, rule=True, center=False)

    _progress_bar(d, cw, ch, i, n, wide=wide)
    _stage_footer(d, cw, ch, wide=wide)
    im.convert("RGB").save(dest, quality=92)


def stage_seconds(stage: str, *, bars: int = 0, lines: int = 0) -> float:
    """How long a slide stays up: scaled to how much is on it, floored so nothing flashes past.

    2026-10-27 (user): the videos moved on before the viewer could read the numbers. The old pace gave a dense
    evidence or record slide five to seven seconds — a line a second is a scan, not a read. Every slide now gets
    `STAGE_FLOOR[stage]` seconds before anything else is added, and each line on it buys about a second and a third
    on top, so a record slide with ten results is up for ~16 s. The cap keeps a pathological slide from stalling the
    video; the length guard (`MAX_TOTAL`) handles the rest by dropping picks, never by speeding slides up again.
    """
    floor = STAGE_FLOOR.get(stage, 7.0)
    if stage == "pick":
        secs = 6.5 + 0.9 * max(1, bars)
    else:
        secs = 4.5 + 1.3 * max(1, lines)
    return float(min(16.0, max(floor, secs)))


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
        c = "© Mr 2 Odds. All rights reserved."
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
        c = "© Mr 2 Odds. All rights reserved."
        d.text(((cw - _tw(d, c, _font(24, True))) // 2, 725), c, fill=WHITE, font=_font(24, True))
        p = "Unauthorised copying or re-upload is prohibited."
        d.text(((cw - _tw(d, p, _font(20, False))) // 2, 770), p, fill=MUTED, font=_font(20, False))
    im.convert("RGB").save(dest, quality=92)


def fetch_badge(rel: str, dest: Path, fallback: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 100:
        return dest
    if rel:
        try:
            req = urllib.request.Request(BADGE_BASE + rel, headers={"User-Agent": "Mozilla/5.0 Mr 2 Odds"})
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


def render_card_summary(picks, bg, dest):
    """Final screen: multiply every displayed decimal price, with no payout promises."""
    from PIL import ImageDraw
    from video_card import combined_odds
    cw, ch = _resolve_size()
    im = _cover(bg, .83, size=(cw, ch))
    d = ImageDraw.Draw(im)
    pad = 70
    d.rounded_rectangle((pad, 100, cw-pad, ch-100), 32, fill=(13, 27, 49), outline=GREEN, width=3)
    d.text((pad+35, 140), "BET ADVISOR | THE FULL CARD", font=_font(32, True), fill=GREEN)
    y = 215
    for i, p in enumerate(picks, 1):
        label = f"{i}. {p['home']} v {p['away']} · {p.get('label') or p['sel']} @ {float(p['odds']):.2f}"
        for line in _wrap(d, label, _font(24), cw-2*pad-70, 2):
            d.text((pad+35, y), line, font=_font(24), fill=WHITE)
            y += 30
        y += 6
    formula = " × ".join(f"{float(p['odds']):.2f}" for p in picks)
    d.text((pad+35, y+20), formula, font=_font(25), fill=MUTED)
    d.text((pad+35, y+75), f"COMBINED ODDS  {combined_odds(picks):.2f}", font=_font(42, True), fill=GREEN)
    d.text((pad+35, ch-160), "Prices can change. All legs must win. 18+ | No guaranteed return.", font=_font(20), fill=MUTED)
    im.convert("RGB").save(dest, quality=94)


def still_clip(img: Path, dest: Path, duration: float, ff: str, *, aspect: str | None = None,
               size: tuple[int, int] | None = None, logo: Path | None = None) -> None:
    cw, ch = _resolve_size(aspect, size)
    if logo is not None:
        _run([
            ff, "-y", "-loop", "1", "-framerate", str(FPS), "-t", f"{duration:.3f}", "-i", str(img),
            "-loop", "1", "-framerate", str(FPS), "-i", str(logo),
            "-filter_complex_threads", "1", "-filter_complex",
            f"[0:v]scale={cw}:{ch}[bg];[1:v]scale=88:88,format=rgba,rotate=2*PI*t/8:c=none:ow=124:oh=124[disc];"
            "[bg][disc]overlay=W-w-24:24:shortest=1,format=yuv420p[v]",
            "-map", "[v]", "-t", f"{duration:.3f}", "-r", str(FPS), "-c:v", "libx264",
            "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-an", str(dest),
        ], "rotating app logo")
        return
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


# 2026-10-27 (user rule, latest): the videos cover **Over 1.5 total goals and nothing else**. Corners came out with
# this change — the point of the videos is the one market the record actually supports, explained properly — and the
# families dropped by the model review (team goals, bookings, BTTS, Over 2.5, 1X2, unders) were never coming back.
# A payload published before any of these changes cannot put a dropped market on screen.
REEL_MARKET_RE = re.compile(r"^(O15|O25|C[HA]?O\d+)$")


def is_reel_market(p: dict) -> bool:
    """Advisor video markets: Over 1.5, corner overs, and Over 2.5 fallback. Never unders or cards."""
    sel = str(p.get("sel") or "").upper()
    blob = " ".join(str(p.get(k) or "") for k in ("label", "market", "group")).lower()
    if "under" in blob or "no btts" in blob:
        return False
    return bool(REEL_MARKET_RE.match(sel))


def _match_key(p: dict) -> tuple:
    """The clubs, not the kick-off: the same fixture is the same match however its time is written.

    The board, the primary list and yesterday's history can each carry the same fixture with a slightly different
    kick-off string (timezone, a corrected time), which used to let one match appear twice in a video. The user rule
    is that a match is never repeated, so identity here is the pair of clubs.
    """
    return (_club(p.get("home")), _club(p.get("away")))


def _club(name) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()
    for noise in (" fc", " cf", " sc", " ac", " afc", " club", " football club", " united fc"):
        text = text.replace(noise, "")
    return text.strip()


_REEL_RANK = {"O15": 0, "HO05": 1, "AO05": 1, "HO15": 1, "AO15": 1}


def _stronger(a: dict, b: dict) -> bool:
    """True when pick `a` is the better one to feature for the same match.

    Since 2026-10-21 the video draws a chart of every market for the match and the featured market has to be the
    tallest bar on it, so the strongest model probability wins. Within a percentage point the old preference order
    decides (Over 1.5 first, then team goals) so a video does not turn into twelve identical markets.
    """
    pa, pb = _reel_p(a), _reel_p(b)
    if pa is None:
        return False
    if pb is None:
        return True
    if abs(pa - pb) >= 0.01:
        return pa > pb
    ra = _REEL_RANK.get(str(a.get("sel") or "").upper(), 9)
    rb = _REEL_RANK.get(str(b.get("sel") or "").upper(), 9)
    if ra != rb:
        return ra < rb
    return pa > pb


def reel_picks(picks: list, *, used: set | None = None) -> list:
    """One selection per match, 65%+, Over 1.5 only, and never a match already shown today.

    `used` holds (home, away) pairs from earlier videos (and, for the first video of the day, yesterday's recap), in
    either order — a match introduced once is never introduced again. Per match the strongest Over 1.5 line wins, so
    a fixture offered by two lists does not appear twice.
    """
    skip = set()
    for item in used or set():
        pair = tuple(item) if isinstance(item, (tuple, list)) else ()
        if len(pair) == 3:                       # (kickoff, home, away) from an older history row
            pair = pair[1:]
        if len(pair) == 2:
            skip.add((_club(pair[0]), _club(pair[1])))
    best = {}
    order = []
    for p in picks or []:
        if not is_reel_market(p):
            continue
        pr = _reel_p(p)
        if pr is None or pr < (0.55 if p.get("sel") == "O25" else REEL_MIN_P):
            continue
        k = _match_key(p)
        if k in skip or k[::-1] in skip:
            continue
        prev = best.get(k)
        if prev is None:
            best[k] = p
            order.append(k)
        elif _stronger(p, prev):
            best[k] = p
    out = [best[k] for k in order]
    return out[:MAX_PICKS]


def overs_only(picks: list) -> list:
    """Kept name for scanner.py."""
    return reel_picks(picks)


def video_picks(picks: list, *, used: set | None = None, fx_dir: Path | None = None, now=None, search=None,
                require_confirmation: bool = False) -> tuple[list[dict], list[dict]]:
    """The matches a video may show: Over 1.5, one per match, and verified before they are finalised.

    Every candidate is checked against its own fixture detail — recent results for both clubs, a recent head to
    head, sane numbers (`reel_verify.stats_problems`) — and against the internet (`reel_verify.web_check`), which
    can confirm the fixture or knock it out. Returns (kept, skipped) with a reason for every match left out, so the
    scan log and the Telegram caption can say what was dropped and why instead of quietly showing fewer matches.
    """
    import reel_verify

    import video_card
    from datetime import timezone
    now = now or datetime.now(timezone.utc)
    excluded = set()
    for item in used or set():
        pair = tuple(item)[-2:]
        if len(pair) == 2:
            excluded.add(video_card.match_key({"home": pair[0], "away": pair[1]}))
    clean = []
    for p in picks or []:
        if not video_card.eligible(p) or video_card.match_key(p) in excluded:
            continue
        try:
            ko = datetime.fromisoformat(str(p.get("kickoff") or ""))
            reference = now.replace(tzinfo=ko.tzinfo) if ko.tzinfo is None or now.tzinfo is None else now
            if ko <= reference:
                continue
        except ValueError:
            continue  # unknown kick-off: cannot promise a future selection
        clean.append(p)
    root = Path(fx_dir) if fx_dir else _data_dir("fx")
    if root is None or not root.exists():
        log.warning("video check: missing fixture details — fail closed")
        return [], [{"reasons": ["missing fixture details"]}]
    kept, skipped = reel_verify.select(
        clean, load_detail=lambda p: load_detail(p, root),
        now=now, search=search, require_confirmation=require_confirmation,
    )
    card = video_card.choose(kept)
    if not card:
        log.warning("Video skipped: need 5+ verified Advisor matches at combined odds 2.00–3.30; %d eligible", len(kept))
    return card, skipped


def _fx_key(pick: dict) -> str:
    """The fixture id the app uses: date|country|home|away, hashed to the detail filename (`appdata.detail_key`)."""
    import hashlib
    date = str(pick.get("kickoff") or "")[:10] or str(pick.get("date") or "")[:10]
    fid = f"{date}|{pick.get('country') or ''}|{pick.get('home') or ''}|{pick.get('away') or ''}"
    return hashlib.sha1(fid.encode("utf-8")).hexdigest()[:12]


def load_detail(pick: dict, fx_dir: Path | None) -> dict | None:
    """The app's own fixture detail for this pick, or None when the file is not there.

    Every number on the deeper slides comes from here, so a missing file simply means fewer slides — never a made-up
    figure. The scanner writes these files in the same run, a few lines before the video is built.
    """
    if not fx_dir:
        return None
    path = Path(fx_dir) / f"{_fx_key(pick)}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _data_dir(*parts: str) -> Path | None:
    root = Path(os.getenv("MR 2 ODDS_DATA_DIR") or "data")
    path = root.joinpath("app", *parts)
    return path if path.exists() else None


def build(picks: list, outfile: Path, *, assets: Path, work: Path | None = None,
          fixtures: list | None = None, yesterday_results: dict | list | None = None,
          aspect: str = "16:9", recap: bool = True, fx_dir: Path | None = None,
          leagues_dir: Path | None = None) -> Path:
    """Build a 16:9 widescreen (1920x1080) or 9:16 vertical reel (1080x1920) video.

    Order: intro, disclaimer, yesterday's full card (first video of the day only), then each match as three short
    slides — THE PICK (Over 1.5, its price and the model-vs-market chart), WHY IT'S HERE (reasons, trends, standing,
    venue splits) and THE RECORD (head to head and both teams' last five, always fresh). Each match appears once.
    Since 2026-10-27 only **Over 1.5 total goals** is carried, and only for matches whose own stats and a recent
    head to head check out (`video_picks`). Talking slides are timed
    from their words' reading time + TAIL (intro at least INTRO_MIN); the new slides are timed by what is on them
    (`stage_seconds`). No voice, no accumulator slide.
    """
    from PIL import Image  # noqa: F401  — imported for a clear error if missing

    global _ACTIVE_SIZE
    prev_size = _ACTIVE_SIZE
    _ACTIVE_SIZE = _resolve_size(aspect)
    try:
        ff = _ffmpeg()
        picks = list(picks)
        if not picks:
            raise ValueError("no shortlist picks for the reel")
        # 2026-10-27 (user): a match only makes it into a video when its own stats are recent and complete, it has a
        # recent head to head, and the internet does not contradict the fixture. Checked here as well as in the
        # scanner so `build()` can never be handed an unverified match by any caller.
        fx_dir = Path(fx_dir) if fx_dir else _data_dir("fx")
        picks, _skipped = video_picks(picks, fx_dir=fx_dir, now=datetime.now(__import__("zoneinfo").ZoneInfo("Africa/Johannesburg")))
        if len(picks) < 5:
            raise ValueError("fewer than five verified matches for the reel — every candidate failed the stats / head-to-head check")
        recap_rows = reel_results(yesterday_results) if recap else []
        recap_day = yesterday_results.get("day", "") if isinstance(yesterday_results, dict) else ""

        assets = Path(assets)
        logo = assets / "logo.png"
        bgs = [assets / "bg_stadium.jpg", assets / "bg_pitch.jpg", assets / "bg_lights.jpg"]
        fixtures = fixtures or []
        leagues_dir = Path(leagues_dir) if leagues_dir else _data_dir("leagues")
        tables = reel_insights.league_tables(leagues_dir)

        work = Path(work) if work else Path(tempfile.mkdtemp(prefix="pr-reel-"))
        work.mkdir(parents=True, exist_ok=True)
        slides_dir = work / "slides"
        slides_dir.mkdir(exist_ok=True)
        crests = work / "crests"
        crests.mkdir(exist_ok=True)

        n = len(picks)
        if aspect == "9:16":
            # The Facebook cover/opening uses only the exact, already verified filmed matches.
            from facebook_cover import render_matches
            cover = render_matches(picks, Path(outfile).with_suffix(".cover.jpg"))
            __import__("shutil").copyfile(cover, slides_dir / "intro.jpg")
        else:
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

        # Every match is introduced once, as up to three slides. Nothing is spoken, so each slide carries its own
        # evidence and stays up only as long as there is something new to read (`stage_seconds`).
        pi = 0
        for p in picks:
            pi += 1
            fx = fixture_for_pick(p, fixtures) or {}
            badges = p.get("badges") or fx.get("badges") or {}
            hb = fetch_badge(badges.get("home"), crests / f"h{pi}.png", logo)
            ab = fetch_badge(badges.get("away"), crests / f"a{pi}.png", logo)
            detail = load_detail(p, fx_dir)
            # The chart has to show the featured market as its tallest bar (user rule 2026-10-21), and the board's
            # own pick is not always the strongest market in the fixture detail — so the video features the
            # strongest market the match actually offers, still 65%+ and still priced. Everything else is untouched.
            # Preserve the exact market and price selected by the bounded card planner.
            table = reel_insights.standing(tables, p) if tables else None
            ev = reel_insights.evidence_lines(detail, p, table)
            bars = reel_insights.market_rows(detail, p)
            for stage in reel_insights.slide_plan(p, detail, table):
                p_img = slides_dir / f"p{pi:02d}-{stage}.jpg"
                if stage == "pick":
                    render_pick_overview(p, pi, n, bgs[pi % 3], hb, ab, p_img,
                                         chart=reel_insights.chart_rows(detail, p))
                    texts.append(stage_seconds("pick", bars=len(bars)))
                elif stage == "evidence":
                    render_pick_evidence(p, pi, n, bgs[(pi + 1) % 3], p_img, reasons=ev["reasons"],
                                         trends=ev["trends"], table=table, detail=detail)
                    texts.append(stage_seconds("evidence", lines=len(ev["reasons"]) + len(ev["trends"])))
                else:
                    render_pick_record(p, pi, n, bgs[(pi + 2) % 3], p_img, home_recent=ev["home_recent"],
                                       away_recent=ev["away_recent"], h2h=ev["h2h"])
                    rows = max(len(ev["home_recent"]), len(ev["away_recent"]))
                    texts.append(stage_seconds("record", lines=rows + (len(ev["h2h"]["rows"]) if ev["h2h"] else 0)))
                images.append(p_img)

        render_closer(logo, bgs[2], slides_dir / "closer.jpg")
        images.append(slides_dir / "closer.jpg")
        texts.append(CLOSER_SCRIPT)
        render_card_summary(picks, bgs[2], slides_dir / "combined.jpg")
        images.append(slides_dir / "combined.jpg")
        texts.append(16.0)

        # A float in `texts` is a fixed hold (the chart/evidence slides, which nobody reads aloud); a string is timed
        # by how long its words take at the old narration pace.
        durations = [frame_hold(t if isinstance(t, float) else hold_seconds(i, music.reading_seconds(t)))
                     for i, t in enumerate(texts)]

        total = sum(durations)
        # Never trim a qualified five-match card to meet a length cap; preserve readable pacing.

        # build_both reads this to give the 9:16 cut the same picks the 16:9 cut kept.
        (work / "build_meta.json").write_text(json.dumps({"picks_count": len(picks), "picks": picks}), encoding="utf-8")

        disc = work / "app-logo-disc.png"
        _circle_badge(logo, 256).save(disc)
        clips = []
        for i, (img, dur) in enumerate(zip(images, durations)):
            clip = work / f"v{i:02d}.mp4"
            still_clip(img, clip, dur, ff, logo=disc)
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
               recap: bool = True, fx_dir: Path | None = None,
               leagues_dir: Path | None = None) -> tuple[Path, Path]:
    """Build both 16:9 widescreen (1920x1080) and 9:16 vertical reel (1080x1920) with the same slides and music.

    The 9:16 cut uses the picks the 16:9 cut actually kept (the length cap can drop the last three), and its
    slides are timed from the same words, so both cuts tell the same story in the same order.
    """
    base_work = Path(work) if work else Path(tempfile.mkdtemp(prefix="pr-dual-"))
    w16 = base_work / "w16x9"
    w9 = base_work / "w9x16"
    p16 = build(
        picks, out_16x9, assets=assets, work=w16, fx_dir=fx_dir, leagues_dir=leagues_dir,
        fixtures=fixtures, yesterday_results=yesterday_results, aspect="16:9", recap=recap,
    )
    used_picks = list(picks)
    meta_file = w16 / "build_meta.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            used_picks = meta.get("picks") or used_picks[: int(meta.get("picks_count", len(used_picks)))]
        except (OSError, ValueError):
            pass
    add = {"fx_dir": fx_dir, "leagues_dir": leagues_dir}
    p9 = build(
        used_picks, out_9x16, assets=assets, work=w9, fixtures=fixtures,
        yesterday_results=yesterday_results, aspect="9:16", recap=recap, **add,
    )
    return p16, p9


def from_shortlist(sl_pub: dict, fixtures: list, outfile: Path, assets: Path, work: Path | None = None,
                   yesterday_results: dict | list | None = None, *, aspect: str = "16:9", recap: bool = True,
                   fx_dir: Path | None = None, leagues_dir: Path | None = None) -> Path:
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
                 aspect=aspect, recap=recap, fx_dir=fx_dir, leagues_dir=leagues_dir)

