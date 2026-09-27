"""Markdown-lite -> PDF (reportlab). Handles headings, paragraphs, bullet lists, pipe tables, block quotes,
<details>/<summary> blocks and **bold** / _italic_ inline marks — enough for the scanner reports.

Layout: A4 portrait, 12 pt Liberation Sans (the metric-identical open-source twin of Arial — same letter
widths, near-identical look; Arial itself is a Microsoft font that cannot be shipped or installed on the
GitHub runner). Tables are set at 12 pt too: a table that physically cannot fit the page width at 12 pt is
re-flowed as one 12 pt "record" per row (bold match name, then 'Label: value' pairs) instead of shrinking
the text."""
from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parent
FONT_DIR = ROOT / "assets" / "fonts"

PAGE = A4                       # portrait
MARGIN_LR = 15 * mm
MARGIN_TB = 14 * mm
FONT_SIZE = 12.0                # body and table text
LEADING = 15.0
CELL_PAD = 4.0                  # left + right padding inside a table cell (each side)

_FONTS: dict = {}

EMOJI_MAP = {"⭐": "★", "✅": "✓", "❌": "✗", "⚠️": "⚠", "⚠": "⚠", "⏳": "…", "·": "·", "→": "→", "–": "–", "—": "—",
             "≥": "≥", "≤": "≤", "ρ": "ρ", "★": "★"}
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]")
KEEP = set("★✓✗⚠")
TAG_RE = re.compile(r"(<[^>]+>)")


# ----------------------------------------------------------------------------- fonts
def _fonts() -> dict:
    """Register Liberation Sans (Arial metrics) with DejaVu Sans as symbol fallback. Cached."""
    if _FONTS:
        return _FONTS
    try:
        pdfmetrics.registerFont(TTFont("Arial", str(FONT_DIR / "LiberationSans-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("Arial-Bold", str(FONT_DIR / "LiberationSans-Bold.ttf")))
        pdfmetrics.registerFont(TTFont("Arial-Italic", str(FONT_DIR / "LiberationSans-Italic.ttf")))
        pdfmetrics.registerFont(TTFont("Arial-BoldItalic", str(FONT_DIR / "LiberationSans-BoldItalic.ttf")))
        pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic",
                                      boldItalic="Arial-BoldItalic")
        regular, bold = "Arial", "Arial-Bold"
        covered = set(pdfmetrics.getFont("Arial").face.charToGlyph)
    except Exception:  # noqa: BLE001 - fall back to the core Helvetica (Arial-metric as well)
        regular, bold, covered = "Helvetica", "Helvetica-Bold", set(range(32, 256))
    fallback, fb_covered = None, set()
    try:
        pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_DIR / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold", italic="DejaVu", boldItalic="DejaVu-Bold")
        fallback = "DejaVu"
        fb_covered = set(pdfmetrics.getFont("DejaVu").face.charToGlyph)
    except Exception:  # noqa: BLE001
        pass
    _FONTS.update({"regular": regular, "bold": bold, "covered": covered, "fallback": fallback, "fb_covered": fb_covered})
    return _FONTS


def clean(s: str) -> str:
    s = s.replace(" (click to expand)", "")          # GitHub-only hint
    for k, v in EMOJI_MAP.items():
        s = s.replace(k, v)
    return EMOJI_RE.sub(lambda m: m.group(0) if m.group(0) in KEEP else "", s)


def _with_fallback(markup: str) -> str:
    """Wrap characters the main font lacks (★ ✓ ✗ ⚠ …) in the fallback font, outside of tags."""
    f = _fonts()
    if not f["fallback"]:
        return markup
    covered, fb = f["covered"], f["fb_covered"]
    out = []
    for part in TAG_RE.split(markup):
        if part.startswith("<") and part.endswith(">"):
            out.append(part)
            continue
        buf, run = [], []

        def flush():
            if run:
                buf.append(f"<font face='{f['fallback']}'>{''.join(run)}</font>")
                run.clear()
        i = 0
        while i < len(part):
            ch = part[i]
            if ch == "&":                       # keep entities intact
                j = part.find(";", i)
                if 0 < j < i + 10:
                    flush(); buf.append(part[i:j + 1]); i = j + 1
                    continue
            cp = ord(ch)
            if cp > 127 and cp not in covered and cp in fb:
                run.append(ch)
            else:
                flush(); buf.append(ch)
            i += 1
        flush()
        out.append("".join(buf))
    return "".join(out)


def inline(s: str) -> str:
    """Markdown inline marks -> reportlab mini-HTML."""
    s = clean(s)
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w])_(.+?)_(?![\w])", r"<i>\1</i>", s)
    s = re.sub(r"`(.+?)`", r"<font color='#1a3d6d'>\1</font>", s)   # code spans stay in the body font
    s = re.sub(r"\[(.+?)\]\((.+?)\)", r"<u>\1</u>", s)
    s = s.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>").replace("&lt;br&gt;", "<br/>")
    return _with_fallback(s)


def plain(s: str) -> str:
    """Cell text without markup, for width measurement."""
    s = clean(s)
    s = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", s)
    s = re.sub(r"</?b>|<br>", " ", s)
    return re.sub(r"[*`]|(?<![\w])_|_(?![\w])", "", s).strip()


# ----------------------------------------------------------------------------- styles
def _styles() -> dict:
    f = _fonts()
    font, bold = f["regular"], f["bold"]
    base = ParagraphStyle("base", fontName=font, fontSize=FONT_SIZE, leading=LEADING, alignment=TA_LEFT)
    return {
        "h1": ParagraphStyle("h1", parent=base, fontName=bold, fontSize=18, leading=22, spaceAfter=6, spaceBefore=2),
        "h2": ParagraphStyle("h2", parent=base, fontName=bold, fontSize=15, leading=19, spaceAfter=5, spaceBefore=12,
                             textColor=colors.HexColor("#1a3d6d")),
        "h3": ParagraphStyle("h3", parent=base, fontName=bold, fontSize=13, leading=17, spaceAfter=4, spaceBefore=9),
        "h4": ParagraphStyle("h4", parent=base, fontName=bold, fontSize=FONT_SIZE, leading=LEADING, spaceAfter=3, spaceBefore=7),
        "p": ParagraphStyle("p", parent=base, spaceAfter=4),
        "sub": ParagraphStyle("sub", parent=base, textColor=colors.HexColor("#555555"), spaceAfter=6),
        "quote": ParagraphStyle("quote", parent=base, leftIndent=8, textColor=colors.HexColor("#444444"), spaceAfter=6,
                                backColor=colors.HexColor("#f4f6f8"), borderPadding=4),
        "li": ParagraphStyle("li", parent=base, leftIndent=14, bulletIndent=3, spaceAfter=2, bulletFontName=font,
                             bulletFontSize=FONT_SIZE),
        "cell": ParagraphStyle("cell", parent=base, fontSize=FONT_SIZE, leading=LEADING - 0.5),
        "cellh": ParagraphStyle("cellh", parent=base, fontName=bold, fontSize=FONT_SIZE, leading=LEADING - 0.5,
                                textColor=colors.white),
        "rec": ParagraphStyle("rec", parent=base, spaceAfter=3, borderPadding=(3, 4, 3, 4)),
        "rec_alt": ParagraphStyle("rec_alt", parent=base, spaceAfter=3, borderPadding=(3, 4, 3, 4),
                                  backColor=colors.HexColor("#f2f5f9")),
        "foot": ParagraphStyle("foot", parent=base, fontSize=9, leading=11, textColor=colors.HexColor("#777777")),
    }


# ----------------------------------------------------------------------------- tables
def _measure(rows: list[list[str]]) -> tuple[list[float], list[float]]:
    """Per column: minimum width (longest single word) and natural width (longest cell on one line)."""
    f = _fonts()
    ncol = len(rows[0])
    minw, natw = [0.0] * ncol, [0.0] * ncol
    for ri, r in enumerate(rows):
        font = f["bold"] if ri == 0 else f["regular"]
        for c in range(ncol):
            txt = plain(r[c])
            if not txt:
                continue
            # bold cells are a little wider than regular ones; measure them as such
            if ri and r[c].startswith("**") and r[c].endswith("**"):
                font = f["bold"]
            full = pdfmetrics.stringWidth(txt, font, FONT_SIZE)
            words = max(pdfmetrics.stringWidth(w, font, FONT_SIZE) for w in txt.split())
            natw[c] = max(natw[c], full)
            minw[c] = max(minw[c], words)
            font = f["bold"] if ri == 0 else f["regular"]
    pad = 2 * CELL_PAD + 1.5
    return [w + pad for w in minw], [w + pad for w in natw]


def _fit_widths(minw: list[float], natw: list[float], width: float) -> list[float]:
    """Natural widths if they fit; otherwise narrow columns keep their natural width and the wide ones
    share what is left in proportion to their natural width, never below the longest-word minimum."""
    n = len(minw)
    if sum(natw) <= width:
        return list(natw)
    widths = [None] * n
    remaining = width
    open_cols = list(range(n))
    while open_cols:
        fair = remaining / len(open_cols)
        fixed = [c for c in open_cols if natw[c] <= fair]
        if not fixed:
            break
        for c in fixed:
            widths[c] = natw[c]
            remaining -= natw[c]
        open_cols = [c for c in open_cols if c not in fixed]
    # the columns still open are all wider than the fair share: split the rest proportionally
    while open_cols:
        tot = sum(natw[c] for c in open_cols)
        prop = {c: remaining * natw[c] / tot for c in open_cols}
        short = [c for c in open_cols if prop[c] < minw[c]]
        if not short:
            for c in open_cols:
                widths[c] = prop[c]
            break
        for c in short:                      # give them their minimum and retry with the others
            widths[c] = minw[c]
            remaining -= minw[c]
        open_cols = [c for c in open_cols if c not in short]
    return [w if w is not None else m for w, m in zip(widths, minw)]


def _table(rows: list[list[str]], st: dict, width: float) -> list:
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    minw, natw = _measure(rows)
    if sum(minw) > width:
        return _records(rows, st)
    widths = _fit_widths(minw, natw, width)
    data = [[Paragraph(inline(c), st["cellh"]) for c in rows[0]]]
    for r in rows[1:]:
        data.append([Paragraph(inline(c), st["cell"]) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3d6d")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5f9")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d0da")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), CELL_PAD), ("RIGHTPADDING", (0, 0), (-1, -1), CELL_PAD),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return [t, Spacer(1, 6)]


def _records(rows: list[list[str]], st: dict) -> list:
    """A table too wide for the page at 12 pt -> one paragraph per row, all columns kept."""
    header = [plain(h) for h in rows[0]]
    low = [h.lower() for h in header]
    title_idx = low.index("match") if "match" in low else (1 if low and low[0] == "#" and len(low) > 1 else 0)
    rank_idx = low.index("#") if "#" in low else None
    out = []
    for i, r in enumerate(rows[1:]):
        title = re.sub(r"\*\*", "", r[title_idx]).strip() or "–"
        if rank_idx is not None and rank_idx != title_idx and plain(r[rank_idx]):
            title = f"{plain(r[rank_idx])}. {title}"
        parts = []
        for c, h in enumerate(header):
            if c in (title_idx, rank_idx) or not plain(r[c]):
                continue
            parts.append(f"<font color='#5a6673'>{html.escape(h)}:</font> {inline(r[c])}")
        body = " &nbsp;·&nbsp; ".join(parts)
        text = f"<b>{inline(title)}</b><br/>{body}" if body else f"<b>{inline(title)}</b>"
        out.append(Paragraph(text, st["rec_alt" if i % 2 else "rec"]))
    out.append(Spacer(1, 6))
    return out


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


# ----------------------------------------------------------------------------- document
def markdown_to_pdf(md: str, path: Path, title: str = "", subtitle: str = "") -> Path:
    st = _styles()
    doc = SimpleDocTemplate(str(path), pagesize=PAGE, leftMargin=MARGIN_LR, rightMargin=MARGIN_LR,
                            topMargin=MARGIN_TB, bottomMargin=MARGIN_TB + 4 * mm, title=title or "PlayReport",
                            author="PlayReport")
    width = PAGE[0] - 2 * MARGIN_LR
    foot_font = _fonts()["regular"]
    foot_left = clean(title or "PlayReport")

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont(foot_font, 9)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawString(MARGIN_LR, 9 * mm, foot_left[:90])
        canvas.drawRightString(PAGE[0] - MARGIN_LR, 9 * mm, f"Page {doc_.page}")
        canvas.restoreState()

    flow = []
    lines = md.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        s = line.strip()
        if not s:
            i += 1
            continue
        if s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                r = _split_row(lines[i])
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c):
                    rows.append(r)
                i += 1
            if rows:
                flow += _table(rows, st, width)
            continue
        i += 1
        if s.startswith("<details>") or s.startswith("</details>"):
            m = re.search(r"<summary>(.*?)</summary>", s)
            if m:
                flow.append(Paragraph(inline(re.sub(r"</?b>", "", m.group(1))), st["h4"]))
            continue
        if s.startswith("<summary>"):
            m = re.search(r"<summary>(.*?)</summary>", s)
            flow.append(Paragraph(inline(re.sub(r"</?b>", "", m.group(1) if m else s)), st["h4"]))
            continue
        if s.startswith("#### "):
            flow.append(Paragraph(inline(s[5:]), st["h4"]))
        elif s.startswith("### "):
            flow.append(Paragraph(inline(s[4:]), st["h3"]))
        elif s.startswith("## "):
            flow.append(Paragraph(inline(s[3:]), st["h2"]))
        elif s.startswith("# "):
            flow.append(Paragraph(inline(s[2:]), st["h1"]))
            if subtitle:
                flow.append(Paragraph(inline(subtitle), st["sub"]))
        elif s.startswith("> "):
            txt = s[2:]
            while i < len(lines) and lines[i].strip().startswith("> "):
                txt += " " + lines[i].strip()[2:]
                i += 1
            flow.append(Paragraph(inline(txt), st["quote"]))
        elif s.startswith(("* ", "- ")):
            flow.append(Paragraph(inline(s[2:]), st["li"], bulletText="•"))
        elif s == "---":
            flow.append(PageBreak())
        else:
            flow.append(Paragraph(inline(s), st["p"]))
    if not flow:
        flow.append(Paragraph("(empty)", st["p"]))
    doc.build(flow, onFirstPage=_footer, onLaterPages=_footer)
    return path
