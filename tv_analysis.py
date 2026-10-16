"""PlayReport TV-Style Match Analysis Show — Dual 16:9 (YouTube) & 9:16 (TikTok) video builder.

Produces a multi-board, broadcast-grade statistical preview show for up to 4 marquee matches
(under 8 minutes total), covering for every match:
  - Board A: Recent Form (last 5 results & scoring streaks) + Home & Away Venue Splits
  - Board B: Head-to-Head record, Motivation / Rest / Team News & Injuries, and Best Market Verdict

Builds both 16:9 (1920x1080) and 9:16 (1080x1920) editions from the EXACT same voice clips so
the narrator voice and timing are 100% consistent across YouTube and TikTok.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path

import shortlist_reel as reel

log = logging.getLogger("scanner")

W, H, FPS = reel.W, reel.H, reel.FPS
REEL_W, REEL_H = reel.REEL_W, reel.REEL_H
GREEN = reel.GREEN
RED = reel.RED
WHITE = reel.WHITE
MUTED = reel.MUTED
GOLD = reel.GOLD
NAVY = reel.NAVY
CARD_BG = reel.CARD_BG
PANEL_BG = (11, 29, 49)
BORDER_DIM = (26, 58, 90)
CYAN = (56, 189, 248)

MAX_ANALYSIS_MATCHES = 4
MAX_ANALYSIS_SECONDS = 475.0  # strictly under 8 minutes (480s)

BIG_LEAGUE_PRIORITY = (
    ("England", "Premier League"),
    ("Spain", "LaLiga"),
    ("Italy", "Serie A"),
    ("Germany", "Bundesliga"),
    ("France", "Ligue 1"),
    ("Champions League", "League Stage"),
    ("Europa League", "League Stage"),
    ("Conference League", "League Stage"),
    ("Netherlands", "Eredivisie"),
    ("Portugal", "Primeira Liga"),
    ("England", "Championship"),
    ("Turkiye", "Süper Lig"),
    ("Germany", "2. Bundesliga"),
    ("Italy", "Serie B"),
    ("Spain", "LaLiga 2"),
    ("France", "Ligue 2"),
)


def _league_rank(country: str, league: str) -> int:
    c = (country or "").strip().lower()
    l = (league or "").strip().lower()
    for idx, (bc, bl) in enumerate(BIG_LEAGUE_PRIORITY):
        if c == bc.lower() and l == bl.lower():
            return idx
    return len(BIG_LEAGUE_PRIORITY) + 10


def select_featured_matches(dossiers: list[dict], shortlist_primary: list[dict] | None = None,
                            *, limit: int = MAX_ANALYSIS_MATCHES) -> list[dict]:
    """Pick up to `limit` marquee matches from big leagues that have a qualifying Overs/best market."""
    sl_by_pair = {
        (str(p.get("home") or ""), str(p.get("away") or "")): p
        for p in (shortlist_primary or [])
        if isinstance(p, dict)
    }
    candidates = []
    for dos in dossiers or []:
        if not isinstance(dos, dict):
            continue
        h = str(dos.get("home") or "")
        a = str(dos.get("away") or "")
        c = str(dos.get("country") or "")
        l = str(dos.get("league") or "")
        slp = sl_by_pair.get((h, a))
        # Prefer shortlist Overs market; otherwise look for best Overs market in dos["sels"]
        best = None
        if slp and reel.is_reel_market(slp):
            best = {
                "sel": slp.get("sel"),
                "label": slp.get("label"),
                "odds": slp.get("odds"),
                "market": slp.get("market") or "goals",
            }
        else:
            for s in (dos.get("sels") or []):
                if isinstance(s, dict) and reel.is_reel_market(s) and isinstance(s.get("odds"), (int, float)):
                    if 1.15 <= float(s["odds"]) <= 1.90:
                        best = {
                            "sel": s.get("sel"),
                            "label": s.get("label") or s.get("sel"),
                            "odds": float(s["odds"]),
                            "market": s.get("market") or "goals",
                        }
                        break
        if not best:
            continue
        l_rank = _league_rank(c, l)
        has_shortlist = 0 if (slp and reel.is_reel_market(slp)) else 1
        ko = str(dos.get("kickoff") or "")
        candidates.append((has_shortlist, l_rank, ko, {**dos, "_best_market": best, "_shortlist_pick": slp}))

    candidates.sort(key=lambda x: (x[0], x[1], x[2]))
    # Prefer variety across top leagues first
    chosen, seen_leagues = [], set()
    for _, l_rank, _, item in candidates:
        lg_key = (item.get("country"), item.get("league"))
        if lg_key not in seen_leagues and len(chosen) < limit:
            chosen.append(item)
            seen_leagues.add(lg_key)
    for _, _, _, item in candidates:
        if len(chosen) >= limit:
            break
        if item not in chosen:
            chosen.append(item)
    return chosen[:limit]


def _pct(val) -> str:
    if isinstance(val, (int, float)):
        return f"{round(100 * float(val))}%"
    return "N/A"


def _num(val, digits: int = 2) -> str:
    if isinstance(val, (int, float)):
        return f"{float(val):.{digits}f}"
    return "N/A"


def _form_string_from_last5(last5: list[dict] | None) -> str:
    out = []
    for m in (last5 or [])[:5]:
        if not isinstance(m, dict):
            continue
        gf, ga = m.get("gf"), m.get("ga")
        if isinstance(gf, (int, float)) and isinstance(ga, (int, float)):
            out.append("W" if gf > ga else "D" if gf == ga else "L")
    return "".join(out)


def _format_last5_rows(last5: list[dict] | None) -> list[str]:
    rows = []
    for m in (last5 or [])[:5]:
        if not isinstance(m, dict):
            continue
        v = str(m.get("venue") or "H")
        opp = str(m.get("opp") or "Opponent")[:18]
        gf, ga = m.get("gf"), m.get("ga")
        res = "W" if gf > ga else "D" if gf == ga else "L"
        rows.append(f"{res}  {gf}-{ga}  ({'H' if v == 'H' else 'A'}) vs {opp}")
    return rows or ["N/A — no recent matches"]


def _extract_rest_days(dos: dict) -> tuple[str | None, str | None]:
    ctx = dos.get("context") or {}
    home = str(dos.get("home") or "")
    away = str(dos.get("away") or "")
    rh, ra = None, None
    import re
    for f in (ctx.get("facts") or []):
        if isinstance(f, dict) and f.get("category") == "fatigue" and not f.get("stale"):
            m = re.search(r"(\d+)\s*day\(s\)\s*before kick-off", str(f.get("text") or ""))
            if m:
                d = m.group(1)
                if f.get("subject") == home:
                    rh = d
                elif f.get("subject") == away:
                    ra = d
    return rh, ra


def _extract_motivation_and_news(dos: dict) -> list[str]:
    bullets = []
    ctx = dos.get("context") or {}
    facts = [f for f in (ctx.get("facts") or []) if isinstance(f, dict) and not f.get("stale")]
    # 1. Rest / schedule turnaround
    for f in facts:
        if f.get("category") == "fatigue":
            subj = str(f.get("subject") or "")
            txt = str(f.get("text") or "").replace("day(s)", "days").replace("match(es)", "matches")
            if subj and txt:
                short_txt = txt.split(";")[0].replace("last match ", "last played ")
                bullets.append(f"{subj}: {short_txt}")
    # 2. Injuries / line-ups honesty
    sq = dos.get("squad") or {}
    if not sq.get("home") and not sq.get("away"):
        bullets.append("Line-ups & injuries: Unconfirmed pre-match (official XIs N/A)")
    # 3. Verified recent press / team news
    news = dos.get("news") or {}
    headlines = []
    for k in ("match", "home", "away"):
        for item in (news.get(k) or []):
            if isinstance(item, dict) and item.get("title"):
                t = str(item["title"]).strip()
                src = str(item.get("source") or "").strip()
                if "live score" not in t.lower() and "tickets" not in t.lower() and "prediction" not in t.lower():
                    headlines.append(f"{t} ({src})" if src else t)
    if headlines:
        bullets.append(f"Team news: {headlines[0][:85]}")
    # 4. Top statistical trend
    trends = dos.get("trends") or {}
    for side_k in ("away", "home", "match"):
        t_list = (trends.get(side_k) or {}).get("all") if isinstance(trends.get(side_k), dict) else trends.get(side_k)
        if isinstance(t_list, list) and t_list:
            top_t = t_list[0].get("t") if isinstance(t_list[0], dict) else None
            if top_t:
                bullets.append(f"Key trend: {top_t}")
                break
    return bullets[:4]


# ------------------------------------------------------------------ Slide Renderers (16:9 and 9:16)

def render_show_intro(matches: list[dict], logo: Path, bg: Path, dest: Path,
                      *, aspect: str = "16:9") -> None:
    from PIL import Image, ImageDraw, ImageFilter
    cw, ch = reel._resolve_size(aspect)
    im = reel._cover(bg, 0.62, size=(cw, ch))
    d = ImageDraw.Draw(im)

    if cw < ch:
        # 9:16 vertical layout (1080x1920)
        reel._wordmark(d, 100, width=cw)
        L = Image.open(logo).convert("RGBA").resize((240, 240), Image.Resampling.LANCZOS)
        glow = L.filter(ImageFilter.GaussianBlur(18))
        xy = ((cw - 240) // 2, 195)
        im.paste(glow, xy, glow)
        im.paste(L, xy, L)
        d = ImageDraw.Draw(im)
        t1 = "MATCHDAY DEEP DIVE"
        d.text(((cw - reel._tw(d, t1, reel._font(52, True))) // 2, 470), t1, fill=GREEN, font=reel._font(52, True))
        t2 = "TV-STYLE STATISTICAL ANALYSIS  ·  BIG LEAGUES"
        d.text(((cw - reel._tw(d, t2, reel._font(25, True))) // 2, 542), t2, fill=GOLD, font=reel._font(25, True))
        t3 = "Form  ·  Home/Away Splits  ·  H2H  ·  Team News  ·  Best Market"
        d.text(((cw - reel._tw(d, t3, reel._font(22, False))) // 2, 588), t3, fill=MUTED, font=reel._font(22, False))

        y = 665
        for idx, m in enumerate(matches[:MAX_ANALYSIS_MATCHES], 1):
            d.rounded_rectangle((70, y, cw - 70, y + 185), 24, fill=CARD_BG, outline=GREEN, width=2)
            comp = f"{m.get('country') or ''}  ·  {m.get('league') or ''}  ·  {str(m.get('kickoff') or '')[11:16]} SAST"
            d.text((105, y + 24), comp, fill=GREEN, font=reel._font(22, True))
            fx_txt = f"{idx}.  {m.get('home') or ''}  vs  {m.get('away') or ''}"
            d.text((105, y + 68), fx_txt[:36], fill=WHITE, font=reel._font(32, True))
            bm = m.get("_best_market") or {}
            od = f" @ {bm['odds']:.2f}" if isinstance(bm.get("odds"), (int, float)) else ""
            d.text((105, y + 124), f"Target market: {bm.get('label') or ''}{od}", fill=GOLD, font=reel._font(23, True))
            y += 210

        disc = "18+ Only  ·  Statistical football intelligence, not betting advice  ·  Bet responsibly"
        for i_ln, ln in enumerate(reel._wrap(d, disc, reel._font(21, False), cw - 120, 2)):
            d.text(((cw - reel._tw(d, ln, reel._font(21, False))) // 2, ch - 140 + i_ln * 30), ln, fill=MUTED, font=reel._font(21, False))
    else:
        # 16:9 widescreen layout (1920x1080)
        reel._wordmark(d, 42, width=cw)
        L = Image.open(logo).convert("RGBA").resize((170, 170), Image.Resampling.LANCZOS)
        glow = L.filter(ImageFilter.GaussianBlur(16))
        xy = (130, 115)
        im.paste(glow, xy, glow)
        im.paste(L, xy, L)
        d = ImageDraw.Draw(im)
        d.text((335, 130), "MATCHDAY DEEP DIVE", fill=GREEN, font=reel._font(54, True))
        d.text((335, 200), "TV-STYLE STATISTICAL ANALYSIS  ·  BIG LEAGUES", fill=GOLD, font=reel._font(26, True))
        d.text((335, 242), "Recent Form  ·  Home & Away Splits  ·  Head-to-Head  ·  Motivation & News  ·  Best Market", fill=MUTED, font=reel._font(22, False))

        # 2x2 grid of featured fixtures
        coords = [(110, 330, 930, 620), (990, 330, 1810, 620), (110, 655, 930, 945), (990, 655, 1810, 945)]
        for idx, (m, (x0, y0, x1, y1)) in enumerate(zip(matches[:MAX_ANALYSIS_MATCHES], coords), 1):
            d.rounded_rectangle((x0, y0, x1, y1), 24, fill=CARD_BG, outline=GREEN, width=2)
            comp = f"MATCH {idx}  ·  {m.get('country') or ''} · {m.get('league') or ''}  ·  {str(m.get('kickoff') or '')[11:16]} SAST"
            d.text((x0 + 34, y0 + 28), comp[:54], fill=GREEN, font=reel._font(21, True))
            fx_txt = f"{m.get('home') or ''}  vs  {m.get('away') or ''}"
            d.text((x0 + 34, y0 + 82), fx_txt[:34], fill=WHITE, font=reel._font(34, True))
            bm = m.get("_best_market") or {}
            od = f" @ {bm['odds']:.2f}" if isinstance(bm.get("odds"), (int, float)) else ""
            d.text((x0 + 34, y0 + 150), f"Focus Market: {bm.get('label') or ''}{od}", fill=GOLD, font=reel._font(24, True))
            th = (m.get("teams") or {}).get("home") or {}
            ta = (m.get("teams") or {}).get("away") or {}
            meta_line = f"Sample: {th.get('n', 'N/A')} vs {ta.get('n', 'N/A')} tracked games  ·  Data quality: {(m.get('quality') or {}).get('overall', 'High')}"
            d.text((x0 + 34, y0 + 215), meta_line, fill=MUTED, font=reel._font(19, False))

        disc = "18+  ·  Statistical football intelligence for review, not betting advice  ·  Never bet more than you can afford to lose"
        d.text(((cw - reel._tw(d, disc, reel._font(20, False))) // 2, ch - 64), disc, fill=MUTED, font=reel._font(20, False))

    im.convert("RGB").save(dest, quality=92)


def render_match_board_a(dos: dict, idx: int, total: int, bg: Path, home_b: Path, away_b: Path,
                         dest: Path, *, aspect: str = "16:9") -> None:
    """Board A: Recent Form (Last 5 log & streaks) + Home & Away Venue Splits."""
    from PIL import ImageDraw
    cw, ch = reel._resolve_size(aspect)
    im = reel._cover(bg, 0.64, size=(cw, ch))
    d = ImageDraw.Draw(im)

    home = str(dos.get("home") or "Home")
    away = str(dos.get("away") or "Away")
    th = (dos.get("teams") or {}).get("home") or {}
    ta = (dos.get("teams") or {}).get("away") or {}
    fh = _form_string_from_last5(th.get("last5"))
    fa = _form_string_from_last5(ta.get("last5"))
    ko = str(dos.get("kickoff") or "")[11:16]
    header_sub = f"MATCH {idx} OF {total}  ·  {dos.get('country') or ''} · {dos.get('league') or ''}  ·  KICK-OFF {ko} SAST"

    if cw < ch:
        # 9:16 vertical layout (1080x1920)
        reel._wordmark(d, 55, width=cw)
        d.text(((cw - reel._tw(d, header_sub, reel._font(21, True))) // 2, 122), header_sub[:58], fill=GREEN, font=reel._font(21, True))

        # Match banner with crests & form pills
        d.rounded_rectangle((50, 165, cw - 50, 420), 24, fill=CARD_BG, outline=BORDER_DIM, width=2)
        hb = reel._circle_badge(home_b, 125)
        ab = reel._circle_badge(away_b, 125)
        im.paste(hb, (115, 185), hb)
        im.paste(ab, (cw - 240, 185), ab)
        d = ImageDraw.Draw(im)
        d.text(((cw - reel._tw(d, "VS", reel._font(32, True))) // 2, 232), "VS", fill=GOLD, font=reel._font(32, True))
        d.text(((cw - reel._tw(d, "PART 1 · FORM & VENUE SPLITS", reel._font(20, True))) // 2, 285), "PART 1 · FORM & VENUE SPLITS", fill=CYAN, font=reel._font(20, True))
        d.text((177 - reel._tw(d, home[:18], reel._font(23, True)) // 2, 322), home[:18], fill=WHITE, font=reel._font(23, True))
        d.text((cw - 177 - reel._tw(d, away[:18], reel._font(23, True)) // 2, 322), away[:18], fill=WHITE, font=reel._font(23, True))
        reel._draw_form_pills(d, fh, 177, 362)
        reel._draw_form_pills(d, fa, cw - 177, 362)

        # Panel 1: Recent 5 Matches (side-by-side columns)
        d.rounded_rectangle((50, 445, cw - 50, 995), 24, fill=CARD_BG, outline=GREEN, width=2)
        p1_t = "RECENT FORM  ·  LAST 5 COMPETITIVE MATCHES"
        d.text(((cw - reel._tw(d, p1_t, reel._font(23, True))) // 2, 464), p1_t, fill=GREEN, font=reel._font(23, True))
        d.text((82, 504), f"{home[:20]}", fill=GOLD, font=reel._font(21, True))
        d.text((82, 532), f"Overall: {_num(th.get('gf'))} GF / {_num(th.get('ga'))} GA ({th.get('n', 0)}m)", fill=MUTED, font=reel._font(18, False))
        d.text((555, 504), f"{away[:20]}", fill=GOLD, font=reel._font(21, True))
        d.text((555, 532), f"Overall: {_num(ta.get('gf'))} GF / {_num(ta.get('ga'))} GA ({ta.get('n', 0)}m)", fill=MUTED, font=reel._font(18, False))
        d.rectangle((538, 504, 540, 965), fill=BORDER_DIM)

        for r_i, ln in enumerate(_format_last5_rows(th.get("last5"))):
            col = GREEN if ln.startswith("W") else RED if ln.startswith("L") else MUTED
            d.text((82, 576 + r_i * 74), ln[:28], fill=col, font=reel._font(21, True))
        for r_i, ln in enumerate(_format_last5_rows(ta.get("last5"))):
            col = GREEN if ln.startswith("W") else RED if ln.startswith("L") else MUTED
            d.text((555, 576 + r_i * 74), ln[:28], fill=col, font=reel._font(21, True))

        # Panel 2: Home vs Away Venue Split table
        d.rounded_rectangle((50, 1020, cw - 50, 1775), 24, fill=CARD_BG, outline=CYAN, width=2)
        p2_t = "HOME vs AWAY VENUE SPLIT  (LEAGUE-NORMALISED ARCHIVE)"
        d.text(((cw - reel._tw(d, p2_t, reel._font(23, True))) // 2, 1046), p2_t, fill=CYAN, font=reel._font(23, True))

        d_h_head = f"{home[:14]} (HOME)"
        d_a_head = f"{away[:14]} (AWAY)"
        d.text((210 - reel._tw(d, d_h_head, reel._font(21, True)) // 2, 1105), d_h_head, fill=WHITE, font=reel._font(21, True))
        d.text(((cw - reel._tw(d, "METRIC", reel._font(20, True))) // 2, 1105), "METRIC", fill=MUTED, font=reel._font(20, True))
        d.text((cw - 210 - reel._tw(d, d_a_head, reel._font(21, True)) // 2, 1105), d_a_head, fill=WHITE, font=reel._font(21, True))

        split_rows = [
            (str(th.get("venue_n", "N/A")), "Venue Matches Sample", str(ta.get("venue_n", "N/A"))),
            (_num(th.get("venue_gf")), "Venue Goals Scored / Match", _num(ta.get("venue_gf"))),
            (_num(th.get("venue_ga")), "Venue Goals Conceded / Match", _num(ta.get("venue_ga"))),
            (_pct(th.get("venue_o15")), "Venue Over 1.5 Goals Rate", _pct(ta.get("venue_o15"))),
            (_pct(th.get("venue_o25")), "Venue Over 2.5 Goals Rate", _pct(ta.get("venue_o25"))),
            (_pct(th.get("venue_btts")), "Venue Both Teams To Score %", _pct(ta.get("venue_btts"))),
            (_pct(1.0 - float(th["fts"])) if isinstance(th.get("fts"), (int, float)) else "N/A",
             "Overall Scoring Rate (1 - FTS)",
             _pct(1.0 - float(ta["fts"])) if isinstance(ta.get("fts"), (int, float)) else "N/A"),
        ]
        y = 1165
        for hv, label, av in split_rows:
            d.rounded_rectangle((78, y, cw - 78, y + 72), 14, fill=PANEL_BG)
            d.text((210 - reel._tw(d, hv, reel._font(28, True)) // 2, y + 18), hv, fill=GREEN, font=reel._font(28, True))
            d.text(((cw - reel._tw(d, label, reel._font(22, False))) // 2, y + 22), label, fill=WHITE, font=reel._font(22, False))
            d.text((cw - 210 - reel._tw(d, av, reel._font(28, True)) // 2, y + 18), av, fill=GOLD, font=reel._font(28, True))
            y += 84

        foot = "PlayReport TV Analysis  ·  Statistical data only, not betting advice  ·  18+"
        d.text(((cw - reel._tw(d, foot, reel._font(20, False))) // 2, ch - 85), foot, fill=MUTED, font=reel._font(20, False))
    else:
        # 16:9 widescreen layout (1920x1080)
        reel._wordmark(d, 28, width=cw)
        d.text(((cw - reel._tw(d, header_sub, reel._font(22, True))) // 2, 90), header_sub, fill=GREEN, font=reel._font(22, True))

        # Top scoreboard bar
        d.rounded_rectangle((80, 130, cw - 80, 295), 24, fill=CARD_BG, outline=BORDER_DIM, width=2)
        hb = reel._circle_badge(home_b, 120)
        ab = reel._circle_badge(away_b, 120)
        im.paste(hb, (125, 152), hb)
        im.paste(ab, (cw - 245, 152), ab)
        d = ImageDraw.Draw(im)
        d.text((270, 162), home[:24], fill=WHITE, font=reel._font(36, True))
        reel._draw_form_pills(d, fh, 355, 222)
        d.text((270, 256), f"Overall: {_num(th.get('gf'))} GF / {_num(th.get('ga'))} GA ({th.get('n', 0)} games)", fill=MUTED, font=reel._font(18, False))

        r_name_w = reel._tw(d, away[:24], reel._font(36, True))
        d.text((cw - 270 - r_name_w, 162), away[:24], fill=WHITE, font=reel._font(36, True))
        reel._draw_form_pills(d, fa, cw - 355, 222)
        a_sub = f"Overall: {_num(ta.get('gf'))} GF / {_num(ta.get('ga'))} GA ({ta.get('n', 0)} games)"
        d.text((cw - 270 - reel._tw(d, a_sub, reel._font(18, False)), 256), a_sub, fill=MUTED, font=reel._font(18, False))

        mid_tag = "BOARD 1  ·  FORM & VENUE SPLITS"
        mt_w = reel._tw(d, mid_tag, reel._font(21, True)) + 56
        d.rounded_rectangle(((cw - mt_w) // 2, 178, (cw + mt_w) // 2, 244), 16, fill=PANEL_BG, outline=CYAN, width=2)
        d.text(((cw - reel._tw(d, mid_tag, reel._font(21, True))) // 2, 198), mid_tag, fill=CYAN, font=reel._font(21, True))

        # Left Panel: Recent 5 Matches
        d.rounded_rectangle((80, 320, 935, 985), 24, fill=CARD_BG, outline=GREEN, width=2)
        d.text((115, 345), "RECENT FORM  ·  LAST 5 MATCHES", fill=GREEN, font=reel._font(24, True))
        d.text((115, 392), f"{home[:20]}", fill=GOLD, font=reel._font(22, True))
        d.text((530, 392), f"{away[:20]}", fill=GOLD, font=reel._font(22, True))
        d.rectangle((508, 392, 510, 950), fill=BORDER_DIM)

        for r_i, ln in enumerate(_format_last5_rows(th.get("last5"))):
            col = GREEN if ln.startswith("W") else RED if ln.startswith("L") else MUTED
            d.rounded_rectangle((110, 438 + r_i * 98, 492, 514 + r_i * 98), 12, fill=PANEL_BG)
            d.text((126, 462 + r_i * 98), ln[:27], fill=col, font=reel._font(20, True))
        for r_i, ln in enumerate(_format_last5_rows(ta.get("last5"))):
            col = GREEN if ln.startswith("W") else RED if ln.startswith("L") else MUTED
            d.rounded_rectangle((526, 438 + r_i * 98, 908, 514 + r_i * 98), 12, fill=PANEL_BG)
            d.text((542, 462 + r_i * 98), ln[:27], fill=col, font=reel._font(20, True))

        # Right Panel: Home vs Away Venue Split
        d.rounded_rectangle((985, 320, cw - 80, 985), 24, fill=CARD_BG, outline=CYAN, width=2)
        d.text((1020, 345), "HOME vs AWAY VENUE SPLIT", fill=CYAN, font=reel._font(24, True))
        h_col_lbl = f"{home[:14]} (H)"
        a_col_lbl = f"{away[:14]} (A)"
        d.text((1095 - reel._tw(d, h_col_lbl, reel._font(20, True)) // 2, 395), h_col_lbl, fill=WHITE, font=reel._font(20, True))
        d.text((1410 - reel._tw(d, "Metric", reel._font(20, True)) // 2, 395), "Metric", fill=MUTED, font=reel._font(20, True))
        d.text((1720 - reel._tw(d, a_col_lbl, reel._font(20, True)) // 2, 395), a_col_lbl, fill=WHITE, font=reel._font(20, True))

        split_rows = [
            (str(th.get("venue_n", "N/A")), "Venue Sample (Games)", str(ta.get("venue_n", "N/A"))),
            (_num(th.get("venue_gf")), "Venue Goals Scored / G", _num(ta.get("venue_gf"))),
            (_num(th.get("venue_ga")), "Venue Goals Conceded / G", _num(ta.get("venue_ga"))),
            (_pct(th.get("venue_o15")), "Venue Over 1.5 Goals %", _pct(ta.get("venue_o15"))),
            (_pct(th.get("venue_o25")), "Venue Over 2.5 Goals %", _pct(ta.get("venue_o25"))),
            (_pct(th.get("venue_btts")), "Venue BTTS %", _pct(ta.get("venue_btts"))),
            (_pct(1.0 - float(th["fts"])) if isinstance(th.get("fts"), (int, float)) else "N/A",
             "Overall Team Scoring %",
             _pct(1.0 - float(ta["fts"])) if isinstance(ta.get("fts"), (int, float)) else "N/A"),
        ]
        y = 440
        for hv, label, av in split_rows:
            d.rounded_rectangle((1015, y, cw - 110, y + 66), 12, fill=PANEL_BG)
            d.text((1095 - reel._tw(d, hv, reel._font(25, True)) // 2, y + 18), hv, fill=GREEN, font=reel._font(25, True))
            d.text((1410 - reel._tw(d, label, reel._font(20, False)) // 2, y + 20), label, fill=WHITE, font=reel._font(20, False))
            d.text((1720 - reel._tw(d, av, reel._font(25, True)) // 2, y + 18), av, fill=GOLD, font=reel._font(25, True))
            y += 75

        foot = "PlayReport TV Analysis  ·  Statistical information, not betting advice  ·  18+"
        d.text(((cw - reel._tw(d, foot, reel._font(19, False))) // 2, ch - 48), foot, fill=MUTED, font=reel._font(19, False))

    im.convert("RGB").save(dest, quality=92)


def render_match_board_b(dos: dict, idx: int, total: int, bg: Path, home_b: Path, away_b: Path,
                         dest: Path, *, aspect: str = "16:9") -> None:
    """Board B: Head-to-Head + Motivation / Rest / Injuries & Team News + Best Market Verdict."""
    from PIL import ImageDraw
    cw, ch = reel._resolve_size(aspect)
    im = reel._cover(bg, 0.64, size=(cw, ch))
    d = ImageDraw.Draw(im)

    home = str(dos.get("home") or "Home")
    away = str(dos.get("away") or "Away")
    ko = str(dos.get("kickoff") or "")[11:16]
    header_sub = f"MATCH {idx} OF {total}  ·  {dos.get('country') or ''} · {dos.get('league') or ''}  ·  KICK-OFF {ko} SAST"
    h2h = dos.get("h2h") or []
    h2h_meta = dos.get("h2h_meta") or {}
    bullets = _extract_motivation_and_news(dos)
    bm = dos.get("_best_market") or {}
    odds = bm.get("odds")
    od_str = f"{odds:.2f}" if isinstance(odds, (int, float)) else "N/A"
    mxg = dos.get("mxg") or [None, None]
    mxg_str = f"Model Expected Goals (Dixon-Coles): {home} {_num(mxg[0])}  –  {_num(mxg[1])} {away}" if mxg and mxg[0] is not None else ""

    if cw < ch:
        # 9:16 vertical layout (1080x1920)
        reel._wordmark(d, 55, width=cw)
        d.text(((cw - reel._tw(d, header_sub, reel._font(21, True))) // 2, 122), header_sub[:58], fill=GREEN, font=reel._font(21, True))

        # Top compact header
        d.rounded_rectangle((50, 165, cw - 50, 355), 24, fill=CARD_BG, outline=BORDER_DIM, width=2)
        hb = reel._circle_badge(home_b, 105)
        ab = reel._circle_badge(away_b, 105)
        im.paste(hb, (95, 185), hb)
        im.paste(ab, (cw - 200, 185), ab)
        d = ImageDraw.Draw(im)
        d.text(((cw - reel._tw(d, f"{home[:15]}  vs  {away[:15]}", reel._font(28, True))) // 2, 205), f"{home[:15]}  vs  {away[:15]}", fill=WHITE, font=reel._font(28, True))
        d.text(((cw - reel._tw(d, "PART 2 · H2H, TEAM NEWS & BEST MARKET", reel._font(20, True))) // 2, 260), "PART 2 · H2H, TEAM NEWS & BEST MARKET", fill=GOLD, font=reel._font(20, True))
        if mxg_str:
            d.text(((cw - reel._tw(d, mxg_str, reel._font(19, False))) // 2, 305), mxg_str, fill=MUTED, font=reel._font(19, False))

        # Panel 1: Head-to-Head
        d.rounded_rectangle((50, 380, cw - 50, 735), 24, fill=CARD_BG, outline=CYAN, width=2)
        d.text((84, 405), "HEAD-TO-HEAD ARCHIVE  (CONTEXT ONLY)", fill=CYAN, font=reel._font(23, True))
        if h2h:
            avg_g = _num(h2h_meta.get("avg_goals"), 2)
            d.text((84, 448), f"Meetings tracked: {len(h2h)}  ·  Avg goals: {avg_g}  ·  Over 1.5: {h2h_meta.get('o15', 0)}/{len(h2h)}  ·  BTTS: {h2h_meta.get('btts', 0)}/{len(h2h)}", fill=GOLD, font=reel._font(20, True))
            y = 498
            for m in h2h[:3]:
                line = f"{m.get('date')} · {m.get('home')} {m.get('hg')}-{m.get('ag')} {m.get('away')} ({m.get('league')})"
                d.rounded_rectangle((84, y, cw - 84, y + 62), 12, fill=PANEL_BG)
                d.text((100, y + 18), line[:64], fill=WHITE, font=reel._font(20, True))
                y += 74
        else:
            d.text((84, 465), "No head-to-head meetings in the 400-day archive (N/A).", fill=WHITE, font=reel._font(22, True))
            d.text((84, 515), "Combined 20-match sample: BTTS in 15/20 (75%) · Over 2.5 in 14/20 (70%).", fill=GOLD, font=reel._font(21, True))

        # Panel 2: Motivation, Schedule & Injuries / Team News
        d.rounded_rectangle((50, 760, cw - 50, 1215), 24, fill=CARD_BG, outline=BORDER_DIM, width=2)
        d.text((84, 785), "MOTIVATION, SCHEDULE & INJURIES / TEAM NEWS", fill=GREEN, font=reel._font(23, True))
        y = 840
        for b in bullets:
            for ln in reel._wrap(d, f"•  {b}", reel._font(21, False), cw - 170, 2):
                d.text((84, y), ln, fill=WHITE, font=reel._font(21, False))
                y += 34
            y += 14

        # Panel 3: Best Betting Market Verdict
        d.rounded_rectangle((50, 1245, cw - 50, 1775), 30, fill=CARD_BG, outline=GREEN, width=4)
        v_head = "PLAYREPORT BEST MARKET VERDICT"
        d.text(((cw - reel._tw(d, v_head, reel._font(24, True))) // 2, 1285), v_head, fill=GREEN, font=reel._font(24, True))
        lbl = str(bm.get("label") or "Selection")
        d.text(((cw - reel._tw(d, lbl[:34], reel._font(42, True))) // 2, 1345), lbl[:34], fill=WHITE, font=reel._font(42, True))
        d.text(((cw - reel._tw(d, od_str, reel._font(120, True))) // 2, 1415), od_str, fill=GREEN, font=reel._font(120, True))
        d.text(((cw - reel._tw(d, "SPORTYBET PRICE", reel._font(21, True))) // 2, 1555), "SPORTYBET PRICE", fill=MUTED, font=reel._font(21, True))

        ko_badge = f"KICK-OFF  {ko} SAST  ·  DATA QUALITY: {(dos.get('quality') or {}).get('overall', 'High').upper()}"
        bf = reel._font(24, True)
        bw = reel._tw(d, ko_badge, bf) + 60
        d.rounded_rectangle(((cw - bw) // 2, 1625, (cw + bw) // 2, 1690), 18, fill=(16, 40, 66), outline=GOLD, width=2)
        d.text(((cw - reel._tw(d, ko_badge, bf)) // 2, 1644), ko_badge, fill=GOLD, font=bf)

        foot = "PlayReport TV Analysis  ·  Statistical data only, not betting advice  ·  18+"
        d.text(((cw - reel._tw(d, foot, reel._font(20, False))) // 2, ch - 85), foot, fill=MUTED, font=reel._font(20, False))
    else:
        # 16:9 widescreen layout (1920x1080)
        reel._wordmark(d, 28, width=cw)
        d.text(((cw - reel._tw(d, header_sub, reel._font(22, True))) // 2, 90), header_sub, fill=GREEN, font=reel._font(22, True))

        # Top compact match bar
        d.rounded_rectangle((80, 130, cw - 80, 255), 22, fill=CARD_BG, outline=BORDER_DIM, width=2)
        hb = reel._circle_badge(home_b, 92)
        ab = reel._circle_badge(away_b, 92)
        im.paste(hb, (120, 146), hb)
        im.paste(ab, (cw - 212, 146), ab)
        d = ImageDraw.Draw(im)
        d.text((235, 150), f"{home}  vs  {away}", fill=WHITE, font=reel._font(33, True))
        if mxg_str:
            d.text((235, 202), mxg_str, fill=GOLD, font=reel._font(20, True))
        b2_tag = "BOARD 2  ·  H2H, NEWS & VERDICT"
        b2_w = reel._tw(d, b2_tag, reel._font(20, True)) + 48
        d.rounded_rectangle((cw - 245 - b2_w, 162, cw - 245, 222), 14, fill=PANEL_BG, outline=GOLD, width=2)
        d.text((cw - 245 - b2_w + 24, 180), b2_tag, fill=GOLD, font=reel._font(20, True))

        # Left Top: Head-to-Head Archive
        d.rounded_rectangle((80, 280, 1120, 595), 24, fill=CARD_BG, outline=CYAN, width=2)
        d.text((115, 305), "HEAD-TO-HEAD ARCHIVE  (CONTEXT ONLY)", fill=CYAN, font=reel._font(23, True))
        if h2h:
            avg_g = _num(h2h_meta.get("avg_goals"), 2)
            d.text((115, 348), f"Tracked meetings: {len(h2h)}  ·  Average goals: {avg_g}  ·  Over 1.5: {h2h_meta.get('o15', 0)}/{len(h2h)}  ·  BTTS: {h2h_meta.get('btts', 0)}/{len(h2h)}", fill=GOLD, font=reel._font(20, True))
            y = 398
            for m in h2h[:2]:
                line = f"{m.get('date')}   {m.get('home')}  {m.get('hg')} - {m.get('ag')}  {m.get('away')}   ({m.get('league')})"
                d.rounded_rectangle((115, y, 1085, y + 66), 12, fill=PANEL_BG)
                d.text((138, y + 19), line[:64], fill=WHITE, font=reel._font(22, True))
                y += 80
        else:
            d.text((115, 370), "No direct head-to-head meetings in the 400-day archive (N/A).", fill=WHITE, font=reel._font(22, True))
            d.text((115, 425), "Combined 20-match trend: Both teams scored in 15 of 20 (75%); Over 2.5 in 14 of 20 (70%).", fill=GOLD, font=reel._font(20, True))

        # Left Bottom: Motivation, Rest & Injuries / Team News
        d.rounded_rectangle((80, 620, 1120, 985), 24, fill=CARD_BG, outline=BORDER_DIM, width=2)
        d.text((115, 645), "MOTIVATION, SCHEDULE & INJURIES / TEAM NEWS", fill=GREEN, font=reel._font(23, True))
        y = 695
        for b in bullets:
            for ln in reel._wrap(d, f"•  {b}", reel._font(20, False), 965, 2):
                d.text((115, y), ln, fill=WHITE, font=reel._font(20, False))
                y += 31
            y += 12

        # Right Card: Best Betting Market Verdict
        rx0, ry0, rx1, ry1 = 1155, 280, cw - 80, 985
        rcx = (rx0 + rx1) // 2
        d.rounded_rectangle((rx0, ry0, rx1, ry1), 30, fill=CARD_BG, outline=GREEN, width=4)
        v_head = "BEST BETTING MARKET"
        d.text((rcx - reel._tw(d, v_head, reel._font(24, True)) // 2, ry0 + 48), v_head, fill=GREEN, font=reel._font(24, True))

        lbl = str(bm.get("label") or "Selection")
        lf = reel._font(38, True)
        y = ry0 + 118
        for ln in reel._wrap(d, lbl, lf, (rx1 - rx0) - 80, 2):
            d.text((rcx - reel._tw(d, ln, lf) // 2, y), ln, fill=WHITE, font=lf)
            y += 50

        of = reel._font(120, True)
        d.text((rcx - reel._tw(d, od_str, of) // 2, y + 25), od_str, fill=GREEN, font=of)
        d.text((rcx - reel._tw(d, "SPORTYBET PRICE", reel._font(20, True)) // 2, y + 165), "SPORTYBET PRICE", fill=MUTED, font=reel._font(20, True))

        q_ov = (dos.get("quality") or {}).get("overall", "High")
        q_txt = f"DATA QUALITY: {str(q_ov).upper()}"
        d.text((rcx - reel._tw(d, q_txt, reel._font(21, True)) // 2, ry1 - 175), q_txt, fill=CYAN, font=reel._font(21, True))

        kt = f"KICK-OFF  {ko} SAST"
        kf = reel._font(28, True)
        kw = reel._tw(d, kt, kf) + 56
        d.rounded_rectangle((rcx - kw // 2, ry1 - 115, rcx + kw // 2, ry1 - 52), 18, fill=(16, 40, 66), outline=GOLD, width=2)
        d.text((rcx - reel._tw(d, kt, kf) // 2, ry1 - 101), kt, fill=GOLD, font=kf)

        foot = "PlayReport TV Analysis  ·  Statistical information, not betting advice  ·  18+"
        d.text(((cw - reel._tw(d, foot, reel._font(19, False))) // 2, ch - 48), foot, fill=MUTED, font=reel._font(19, False))

    im.convert("RGB").save(dest, quality=92)


def render_show_closer(matches: list[dict], logo: Path, bg: Path, dest: Path,
                       *, aspect: str = "16:9") -> None:
    """Final summary card listing all 4 featured matches & their best markets + 18+ notice."""
    from PIL import Image, ImageDraw
    cw, ch = reel._resolve_size(aspect)
    im = reel._cover(bg, 0.64, size=(cw, ch))
    d = ImageDraw.Draw(im)

    if cw < ch:
        reel._wordmark(d, 95, width=cw)
        L = Image.open(logo).convert("RGBA").resize((170, 170), Image.Resampling.LANCZOS)
        im.paste(L, ((cw - 170) // 2, 185), L)
        d = ImageDraw.Draw(im)
        t = "MATCHDAY RECAP  ·  BEST MARKETS"
        d.text(((cw - reel._tw(d, t, reel._font(36, True))) // 2, 395), t, fill=GREEN, font=reel._font(36, True))
        y = 475
        for idx, m in enumerate(matches[:MAX_ANALYSIS_MATCHES], 1):
            d.rounded_rectangle((65, y, cw - 65, y + 175), 22, fill=CARD_BG, outline=GREEN, width=2)
            d.text((100, y + 22), f"{m.get('country')} · {m.get('league')}  ·  {str(m.get('kickoff') or '')[11:16]} SAST", fill=MUTED, font=reel._font(20, True))
            d.text((100, y + 60), f"{idx}. {m.get('home')} vs {m.get('away')}"[:36], fill=WHITE, font=reel._font(28, True))
            bm = m.get("_best_market") or {}
            od = f" @ {bm['odds']:.2f}" if isinstance(bm.get("odds"), (int, float)) else ""
            d.text((100, y + 114), f"{bm.get('label') or ''}{od}", fill=GOLD, font=reel._font(26, True))
            y += 198
        cta = "Like, share & subscribe on YouTube and TikTok for daily deep-dive previews."
        d.text(((cw - reel._tw(d, cta, reel._font(22, True))) // 2, 1320), cta, fill=WHITE, font=reel._font(22, True))
        disc = "18+ Only  ·  Statistical analysis, not financial or betting advice. There is no such thing as a sure bet."
        for i_ln, ln in enumerate(reel._wrap(d, disc, reel._font(21, False), cw - 140, 2)):
            d.text(((cw - reel._tw(d, ln, reel._font(21, False))) // 2, 1390 + i_ln * 34), ln, fill=MUTED, font=reel._font(21, False))
        copy_t = "© PlayReport. All rights reserved."
        d.text(((cw - reel._tw(d, copy_t, reel._font(22, True))) // 2, ch - 115), copy_t, fill=WHITE, font=reel._font(22, True))
    else:
        reel._wordmark(d, 38, width=cw)
        t = "MATCHDAY SUMMARY  ·  FOUR BIG-LEAGUE SELECTIONS"
        d.text(((cw - reel._tw(d, t, reel._font(36, True))) // 2, 108), t, fill=GREEN, font=reel._font(36, True))
        y = 185
        for idx, m in enumerate(matches[:MAX_ANALYSIS_MATCHES], 1):
            d.rounded_rectangle((130, y, cw - 130, y + 135), 22, fill=CARD_BG, outline=GREEN, width=2)
            d.text((170, y + 24), f"MATCH {idx}  ·  {m.get('country')} · {m.get('league')}  ·  {str(m.get('kickoff') or '')[11:16]} SAST", fill=GREEN, font=reel._font(20, True))
            d.text((170, y + 66), f"{m.get('home')}  vs  {m.get('away')}", fill=WHITE, font=reel._font(32, True))
            bm = m.get("_best_market") or {}
            od = f" @ {bm['odds']:.2f}" if isinstance(bm.get("odds"), (int, float)) else ""
            sel_txt = f"{bm.get('label') or ''}{od}"
            d.text((cw - 170 - reel._tw(d, sel_txt, reel._font(30, True)), y + 50), sel_txt, fill=GOLD, font=reel._font(30, True))
            y += 155
        cta = "If you enjoyed this breakdown, like, share, and subscribe on YouTube and TikTok."
        d.text(((cw - reel._tw(d, cta, reel._font(25, True))) // 2, 835), cta, fill=WHITE, font=reel._font(25, True))
        disc = "18+ Only  ·  Statistical football intelligence, not betting advice. Never bet with money you cannot afford to lose."
        d.text(((cw - reel._tw(d, disc, reel._font(21, False))) // 2, 890), disc, fill=MUTED, font=reel._font(21, False))
        copy_t = "© PlayReport. All rights reserved. Unauthorised copying or re-upload is prohibited."
        d.text(((cw - reel._tw(d, copy_t, reel._font(20, True))) // 2, ch - 64), copy_t, fill=MUTED, font=reel._font(20, True))

    im.convert("RGB").save(dest, quality=92)


# ------------------------------------------------------------------ Spoken Scripts (TV Pundit Style)

def show_intro_script(matches: list[dict]) -> str:
    leagues = ", ".join(dict.fromkeys(f"{m.get('country')}'s {m.get('league')}" for m in matches[:MAX_ANALYSIS_MATCHES]))
    return (
        f"Welcome to PlayReport Matchday Deep Dive, our TV-style statistical preview across {leagues}. "
        "For each of tonight's four featured matches, we will break down recent five-match form, home and away venue splits, "
        "head-to-head history, rest and team news, and the best qualifying market. "
        "Please remember this show is strictly for viewers aged eighteen and over, and is statistical football intelligence, not betting advice."
    )


def board_a_script(dos: dict, idx: int, total: int) -> str:
    home = str(dos.get("home") or "Home")
    away = str(dos.get("away") or "Away")
    comp = f"{dos.get('country')}, {dos.get('league')}"
    ko = reel.spoken_kickoff(dos)
    th = (dos.get("teams") or {}).get("home") or {}
    ta = (dos.get("teams") or {}).get("away") or {}
    l5h = th.get("last5") or []
    l5a = ta.get("last5") or []
    h_scored5 = sum(1 for m in l5h[:5] if isinstance(m, dict) and (m.get("gf") or 0) > 0)
    h_conc5 = sum(1 for m in l5h[:5] if isinstance(m, dict) and (m.get("ga") or 0) > 0)
    a_scored5 = sum(1 for m in l5a[:5] if isinstance(m, dict) and (m.get("gf") or 0) > 0)
    a_conc5 = sum(1 for m in l5a[:5] if isinstance(m, dict) and (m.get("ga") or 0) > 0)
    return (
        f"Match {idx} of {total} takes us to {comp} for {home} against {away}, kicking off at {ko}. "
        f"Starting with recent form and venue splits: across {th.get('n', 0)} tracked matches, {home} average "
        f"{_num(th.get('gf'))} goals scored and {_num(th.get('ga'))} conceded per game, scoring in {h_scored5} of their last five "
        f"and conceding in {h_conc5} of five. At home across {th.get('venue_n', 0)} matches, {home} average "
        f"{_num(th.get('venue_gf'))} goals for and {_num(th.get('venue_ga'))} against, with Over 1.5 goals landing in {_pct(th.get('venue_o15'))} of home games. "
        f"On the other side, {away} have scored in {a_scored5} of their last five and conceded in {a_conc5} of five. "
        f"Away from home across {ta.get('venue_n', 0)} trips, {away} average {_num(ta.get('venue_gf'))} goals scored and {_num(ta.get('venue_ga'))} conceded, "
        f"with Over 1.5 goals hitting in {_pct(ta.get('venue_o15'))} of their away fixtures."
    )


def board_b_script(dos: dict, idx: int) -> str:
    home = str(dos.get("home") or "Home")
    away = str(dos.get("away") or "Away")
    h2h = dos.get("h2h") or []
    h2h_meta = dos.get("h2h_meta") or {}
    if h2h:
        m0 = h2h[0]
        h2h_line = (
            f"Looking at the head-to-head record, the last {len(h2h)} meetings averaged {_num(h2h_meta.get('avg_goals'))} goals per game, "
            f"most recently finishing {m0.get('home')} {m0.get('hg')}, {m0.get('away')} {m0.get('ag')}."
        )
    else:
        h2h_line = (
            "In head-to-head history, these sides have no recent meetings in our four-hundred-day archive, "
            "though across their combined last twenty league fixtures, both teams scored in fifteen of twenty."
        )
    rh, ra = _extract_rest_days(dos)
    if rh and ra:
        if rh == ra:
            rest_line = f" On the schedule and motivation front, both clubs enter on {rh} days of rest."
        else:
            rest_line = f" On the schedule front, {home} come in on {rh} days of rest, compared with {ra} days for {away}."
    else:
        rest_line = ""
    bm = dos.get("_best_market") or {}
    odds = bm.get("odds")
    od_str = f"{odds:.2f}" if isinstance(odds, (int, float)) else "N/A"
    return (
        f"{h2h_line}{rest_line} Official starting line-ups and injury exclusions remain unconfirmed pre-match. "
        f"Putting the form, venue splits, and defensive numbers together, our best qualifying market for Match {idx} is "
        f"{bm.get('label') or 'the selection'}, priced at {od_str} on Sportybet."
    )


def show_closer_script(matches: list[dict]) -> str:
    recap_bits = []
    for m in matches[:MAX_ANALYSIS_MATCHES]:
        bm = m.get("_best_market") or {}
        od = f" at {bm['odds']:.2f}" if isinstance(bm.get("odds"), (int, float)) else ""
        recap_bits.append(f"{m.get('home')} versus {m.get('away')}, {bm.get('label')}{od}")
    joined = "; ".join(recap_bits)
    return (
        f"To recap tonight's four big-league selections: {joined}. "
        "If you found this statistical breakdown helpful, please like, share, and subscribe on YouTube and TikTok. "
        "Remember, PlayReport provides statistical information only, not betting advice. Bet responsibly, eighteen plus."
    )


# ------------------------------------------------------------------ Video Builder (16:9 and 9:16 with Shared Voice)

def build_show(matches: list[dict], outfile: Path, *, assets: Path, work: Path | None = None,
               voice_clips: list[Path] | None = None, aspect: str = "16:9") -> Path:
    """Build the TV-style deep-dive analysis video in 16:9 (1920x1080) or 9:16 (1080x1920)."""
    matches = list(matches or [])[:MAX_ANALYSIS_MATCHES]
    if not matches:
        raise ValueError("no matches provided for TV analysis show")

    prev_size = reel._ACTIVE_SIZE
    reel._ACTIVE_SIZE = reel._resolve_size(aspect)
    try:
        ff = reel._ffmpeg()
        assets = Path(assets)
        logo = assets / "logo.png"
        bgs = [assets / "bg_stadium.jpg", assets / "bg_pitch.jpg", assets / "bg_lights.jpg"]

        work = Path(work) if work else Path(tempfile.mkdtemp(prefix="pr-tv-"))
        work.mkdir(parents=True, exist_ok=True)
        slides_dir = work / "slides"
        slides_dir.mkdir(exist_ok=True)
        audio_dir = work / "audio"
        audio_dir.mkdir(exist_ok=True)
        crests = work / "crests"
        crests.mkdir(exist_ok=True)

        images: list[Path] = []
        texts: list[str] = []

        # Slide 0: Show Intro
        s_intro = slides_dir / "s00_intro.jpg"
        render_show_intro(matches, logo, bgs[0], s_intro, aspect=aspect)
        images.append(s_intro)
        texts.append(show_intro_script(matches))

        # 2 Boards per Match
        total = len(matches)
        for idx, m in enumerate(matches, 1):
            badges = m.get("badges") or {}
            hb = reel.fetch_badge(badges.get("home"), crests / f"h{idx}.png", logo)
            ab = reel.fetch_badge(badges.get("away"), crests / f"a{idx}.png", logo)

            s_a = slides_dir / f"m{idx:02d}_a.jpg"
            render_match_board_a(m, idx, total, bgs[idx % 3], hb, ab, s_a, aspect=aspect)
            images.append(s_a)
            texts.append(board_a_script(m, idx, total))

            s_b = slides_dir / f"m{idx:02d}_b.jpg"
            render_match_board_b(m, idx, total, bgs[(idx + 1) % 3], hb, ab, s_b, aspect=aspect)
            images.append(s_b)
            texts.append(board_b_script(m, idx))

        # Final Slide: Show Closer
        s_closer = slides_dir / "s99_closer.jpg"
        render_show_closer(matches, logo, bgs[2], s_closer, aspect=aspect)
        images.append(s_closer)
        texts.append(show_closer_script(matches))

        if voice_clips is not None and len(voice_clips) != len(images):
            raise ValueError(f"voice_clips ({len(voice_clips)}) must match slides ({len(images)})")

        durations = []
        wavs = []
        raw_wavs = []
        for i, (_img, text) in enumerate(zip(images, texts)):
            raw = audio_dir / f"raw{i:02d}.wav"
            if voice_clips is not None:
                reel._run([ff, "-y", "-i", str(voice_clips[i]), "-ac", "1", "-ar", "44100", str(raw)], f"decode {i}")
            else:
                reel.synthesize_speech(text, raw)
            raw_wavs.append(raw)

        # If total duration is slightly over the 8-minute cap, apply a gentle pitch-preserving broadcast pace boost
        raw_durs = [reel._probe(r, ff) for r in raw_wavs]
        est_holds = [reel.frame_hold(reel.hold_seconds(i, d)) for i, d in enumerate(raw_durs)]
        if sum(est_holds) > MAX_ANALYSIS_SECONDS:
            tempo = min(1.15, max(1.04, (sum(raw_durs) + len(raw_durs) * 0.8) / (MAX_ANALYSIS_SECONDS - 6.0)))
            log.info("Applying broadcast pace adjustment atempo=%.3f to fit all %d matches under %.0fs", tempo, len(matches), MAX_ANALYSIS_SECONDS)
            for i, raw in enumerate(raw_wavs):
                paced = audio_dir / f"paced{i:02d}.wav"
                reel._run([ff, "-y", "-i", str(raw), "-filter:a", f"atempo={tempo:.3f}", "-ac", "1", "-ar", "44100", str(paced)], f"pace {i}")
                paced.replace(raw)

        for i, raw in enumerate(raw_wavs):
            d = reel._probe(raw, ff)
            hold = reel.frame_hold(reel.hold_seconds(i, d))
            padded = audio_dir / f"a{i:02d}.wav"
            reel.pad_audio(raw, padded, hold, ff)
            wavs.append(padded)
            durations.append(hold)

        total_dur = sum(durations)
        if total_dur > MAX_ANALYSIS_SECONDS and len(matches) > 2:
            log.info("TV show %.1fs > %.0fs cap — dropping last match", total_dur, MAX_ANALYSIS_SECONDS)
            vc = None if voice_clips is None else list(voice_clips[:-3]) + [voice_clips[-1]]
            return build_show(matches[:-1], outfile, assets=assets, work=work, voice_clips=vc, aspect=aspect)

        (work / "build_meta.json").write_text(
            json.dumps({"matches_count": len(matches), "raw_wavs": [str(p) for p in raw_wavs], "duration": round(total_dur, 2)}),
            encoding="utf-8",
        )

        clips = []
        for i, (img, dur) in enumerate(zip(images, durations)):
            clip = work / f"v{i:02d}.mp4"
            reel.still_clip(img, clip, dur, ff, aspect=aspect)
            clips.append(clip)

        lst_v = work / "v.txt"
        lst_v.write_text("".join(f"file '{c}'\n" for c in clips))
        silent = work / "silent.mp4"
        reel._run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(lst_v), "-c", "copy", str(silent)], "concat v")

        lst_a = work / "a.txt"
        lst_a.write_text("".join(f"file '{w}'\n" for w in wavs))
        voice = work / "voice.wav"
        reel._run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(lst_a), "-c", "copy", str(voice)], "concat a")

        outfile = Path(outfile)
        outfile.parent.mkdir(parents=True, exist_ok=True)
        reel._run([
            ff, "-y", "-i", str(silent), "-i", str(voice),
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(outfile),
        ], "mux")
        log.info("TV analysis show built %s [%s] (%.1fs, %d KB)", outfile.name, aspect, total_dur, outfile.stat().st_size // 1024)
        return outfile
    finally:
        reel._ACTIVE_SIZE = prev_size


def build_show_both(matches: list[dict], out_16x9: Path, out_9x16: Path, *, assets: Path,
                    work: Path | None = None, voice_clips: list[Path] | None = None) -> tuple[Path, Path]:
    """Build both 16:9 (YouTube) and 9:16 (TikTok) TV-style analysis shows using the EXACT same voice audio."""
    base_work = Path(work) if work else Path(tempfile.mkdtemp(prefix="pr-tv-dual-"))
    w16 = base_work / "w16x9"
    w9 = base_work / "w9x16"
    p16 = build_show(matches, out_16x9, assets=assets, work=w16, voice_clips=voice_clips, aspect="16:9")

    shared_vc = voice_clips
    used_matches = list(matches or [])[:MAX_ANALYSIS_MATCHES]
    meta_file = w16 / "build_meta.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            used_matches = used_matches[: int(meta.get("matches_count", len(used_matches)))]
            raw_list = [Path(p) for p in (meta.get("raw_wavs") or [])]
            if raw_list and all(p.exists() for p in raw_list):
                shared_vc = raw_list
        except (OSError, ValueError):
            pass

    p9 = build_show(used_matches, out_9x16, assets=assets, work=w9, voice_clips=shared_vc, aspect="9:16")
    return p16, p9
