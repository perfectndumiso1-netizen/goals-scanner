"""Markdown-lite -> PDF (reportlab). Handles headings, paragraphs, bullet lists, pipe tables, block quotes,
<details>/<summary> blocks and **bold** / _italic_ inline marks — enough for the scanner reports."""
from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parent
FONT_DIR = ROOT / "assets" / "fonts"
_FONTS_READY = False

EMOJI_MAP = {"⭐": "★", "✅": "✓", "❌": "✗", "⚠️": "⚠", "⚠": "⚠", "⏳": "…", "·": "·", "→": "→", "–": "–", "—": "—",
             "≥": "≥", "≤": "≤", "ρ": "ρ", "★": "★"}
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]")
KEEP = set("★✓✗⚠")


def _fonts() -> tuple[str, str]:
    global _FONTS_READY
    if not _FONTS_READY:
        try:
            pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_DIR / "DejaVuSans.ttf")))
            pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))
            pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold", italic="DejaVu", boldItalic="DejaVu-Bold")
            _FONTS_READY = True
        except Exception:  # noqa: BLE001 - fall back to core fonts (no unicode symbols)
            return "Helvetica", "Helvetica-Bold"
    return "DejaVu", "DejaVu-Bold"


def clean(s: str) -> str:
    for k, v in EMOJI_MAP.items():
        s = s.replace(k, v)
    return EMOJI_RE.sub(lambda m: m.group(0) if m.group(0) in KEEP else "", s)


def inline(s: str) -> str:
    """Markdown inline marks -> reportlab mini-HTML."""
    s = clean(s)
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w])_(.+?)_(?![\w])", r"<i>\1</i>", s)
    s = re.sub(r"`(.+?)`", r"<font face='Courier'>\1</font>", s)
    s = re.sub(r"\[(.+?)\]\((.+?)\)", r"<u>\1</u>", s)
    s = s.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>").replace("&lt;br&gt;", "<br/>")
    return s


def _styles(font: str, bold: str) -> dict:
    base = ParagraphStyle("base", fontName=font, fontSize=8, leading=10.5, alignment=TA_LEFT)
    return {
        "h1": ParagraphStyle("h1", parent=base, fontName=bold, fontSize=16, leading=20, spaceAfter=6, spaceBefore=4),
        "h2": ParagraphStyle("h2", parent=base, fontName=bold, fontSize=12.5, leading=16, spaceAfter=4, spaceBefore=10,
                             textColor=colors.HexColor("#1a3d6d")),
        "h3": ParagraphStyle("h3", parent=base, fontName=bold, fontSize=10, leading=13, spaceAfter=3, spaceBefore=7),
        "h4": ParagraphStyle("h4", parent=base, fontName=bold, fontSize=8.5, leading=11, spaceAfter=2, spaceBefore=5),
        "p": ParagraphStyle("p", parent=base, spaceAfter=3),
        "quote": ParagraphStyle("quote", parent=base, leftIndent=8, textColor=colors.HexColor("#555555"), spaceAfter=3,
                                backColor=colors.HexColor("#f4f6f8"), borderPadding=3),
        "li": ParagraphStyle("li", parent=base, leftIndent=10, bulletIndent=2, spaceAfter=1.5),
        "cell": ParagraphStyle("cell", parent=base, fontSize=6.8, leading=8.4),
        "cellh": ParagraphStyle("cellh", parent=base, fontName=bold, fontSize=6.8, leading=8.4, textColor=colors.white),
    }


def _table(rows: list[list[str]], st: dict, width: float) -> Table:
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    # column widths proportional to content length (bounded)
    lens = [max(min(len(clean(r[c])), 40) for r in rows) for c in range(ncol)]
    lens = [max(l, 4) for l in lens]
    tot = sum(lens)
    if ncol <= 2:
        width *= 0.62
    widths = [width * l / tot for l in lens]
    data = [[Paragraph(inline(c), st["cellh"]) for c in rows[0]]]
    for r in rows[1:]:
        data.append([Paragraph(inline(c), st["cell"]) for c in r])
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3d6d")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f5f9")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c8d0da")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.5), ("RIGHTPADDING", (0, 0), (-1, -1), 2.5),
        ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
    ]))
    return t


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def markdown_to_pdf(md: str, path: Path, title: str = "", subtitle: str = "") -> Path:
    font, bold = _fonts()
    st = _styles(font, bold)
    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm, title=title or "Goals Scanner")
    width = landscape(A4)[0] - 24 * mm
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
                flow.append(_table(rows, st, width))
                flow.append(Spacer(1, 4))
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
                flow.append(Paragraph(inline(subtitle), st["quote"]))
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
    doc.build(flow)
    return path
