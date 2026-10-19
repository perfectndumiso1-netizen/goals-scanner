"""PlayReport daily match breakdown: YouTube 16:9 + TikTok 9:16 from ONE shared voice track.

Per match the viewer gets three beats, and the pick is only revealed at the very end of each match:
  A  recent form + home/away venue split
  B  head to head + team news + context (table, rest, weather) with a real stadium photo
  V  the pick (revealed last)

Rules baked in (user + standing rules):
  - Never advertises how it was made: no "AI", no "TV style", no studio/broadcast wording anywhere.
  - Never reveals picks in the opening. They appear only at the end of each match, then in the recap.
  - 5-7 matches when the data is strong enough, always under 8 minutes (<= 475 s), natural voice pace.
  - Real photography: free-licence stadium photos (Wikimedia Commons) with the photographer credited.
  - Never invents data: unknown is N/A; predicted line-ups are never called official; no model
    probabilities are ever shown or spoken; Sportybet odds are display-only.
  - 18+ disclaimer is read aloud in every video; copyright notice and a soft like/share/subscribe close.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import breakdown_script as bs
import shortlist_reel as reel
import spoken as sp
import venue_photos as vphotos

log = logging.getLogger("scanner")

MIN_MATCHES, DEFAULT_MATCHES, MAX_MATCHES = 5, 6, 7
MAX_SECONDS = 475.0            # hard ceiling, strictly under 8 minutes
MAX_TEMPO = 1.05               # never speed the voice up more than this (keeps it natural)
CHARS_PER_SEC = 14.0           # measured house-voice pace is ~14.7 chars/s; budget slightly under it
INTRO_CHARS, CLOSER_CHARS = 560, 430

GREEN, RED, WHITE, MUTED, GOLD = reel.GREEN, reel.RED, reel.WHITE, reel.MUTED, reel.GOLD
NAVY, CARD_BG = reel.NAVY, reel.CARD_BG
PANEL_BG = (11, 29, 49)
BORDER_DIM = (26, 58, 90)
CYAN = (56, 189, 248)

# Words that must never appear in anything the viewer sees or hears.
FORBIDDEN_PUBLIC = re.compile(r"\bAI\b|A\.I\.|artificial|generated|tv[- ]style|\bTV\b|broadcast|studio|deep dive", re.I)

BIG_LEAGUE_PRIORITY = (
    ("England", "Premier League"), ("Spain", "LaLiga"), ("Italy", "Serie A"), ("Germany", "Bundesliga"),
    ("France", "Ligue 1"), ("Champions League", ""), ("Europa League", ""), ("Conference League", ""),
    ("Netherlands", "Eredivisie"), ("Portugal", "Primeira Liga"), ("England", "Championship"),
    ("Turkiye", "Süper Lig"), ("Germany", "2. Bundesliga"), ("Italy", "Serie B"),
    ("Spain", "LaLiga 2"), ("France", "Ligue 2"),
)

_SAY_MAP = {
    "Deportivo A Coruna": "Deportivo La Coruna", "Borussia M'gladbach": "Gladbach",
    "Borussia Monchengladbach": "Gladbach", "Paris Saint-Germain": "Paris Saint-Germain",
    "Wolverhampton Wanderers": "Wolves", "Turkiye": "Turkey",
}

_REPUTABLE = (
    "bbc", "sky sports", "guardian", "espn", "reuters", "associated press", "the athletic", "goal", "fox sports",
    "independent", "telegraph", "marca", "as.com", "mundo deportivo", "gazzetta", "corriere", "kicker", "l'equipe",
    "l’équipe", "nos", "sports mole", "whoscored", "flashscore", "talksport", "cbs sports", "nbc sports", "the times",
)
_JUNK_TITLE = re.compile(
    r"predict|tips?\b|odds|betting|\bbet\b|spread|live ?stream|where to watch|tv channel|line-?ups?|"
    r"how to watch|live text|stats & head|head-to-head|preview:|tickets|prediction|live score|live blog|"
    r"highlights|box score|full match|replay|what time|channel|stream|matchday #|watch live|kick-?off time", re.I)
_NEWS_KEYWORDS = re.compile(
    r"injur|ruled out|rules? out|\bmiss|doubt|suspen|return|back from|fitness|\bfit\b|squad|sidelin|absen|boost|"
    r"blow|knock|setback|hamstring|knee|ankle|illness|concussion|sacked|appoint|press conference|pick of the stats",
    re.I)


# ============================================================================ text helpers

def say(name: str) -> str:
    """How a presenter would say a club name."""
    return sp.team(name)


def sentences(text: str) -> list[str]:
    """Sentence split that never breaks on decimals such as 1.24 (no whitespace after the dot)."""
    return [s for s in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if s]


def count_sentences(text: str) -> int:
    return len(sentences(text))


def _ord(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


_NUMW = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


def _w(n) -> str:
    """Small counts spoken as words, the way a presenter says them."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)
    return _NUMW[n] if 0 <= n <= 10 else str(n)


def _poss(name: str) -> str:
    n = str(name or "")
    return f"{n}'" if n.endswith("s") else f"{n}'s"


def _pct(v) -> str:
    return f"{round(100 * float(v))}%" if isinstance(v, (int, float)) else "N/A"


def _num(v, digits: int = 2) -> str:
    return f"{float(v):.{digits}f}" if isinstance(v, (int, float)) else "N/A"


_ORD_WORDS = {1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth", 9: "ninth",
              10: "tenth", 11: "eleventh", 12: "twelfth", 13: "thirteenth", 14: "fourteenth", 15: "fifteenth", 16: "sixteenth",
              17: "seventeenth", 18: "eighteenth", 19: "nineteenth", 20: "twentieth", 21: "twenty-first", 22: "twenty-second",
              23: "twenty-third", 24: "twenty-fourth", 25: "twenty-fifth", 26: "twenty-sixth", 27: "twenty-seventh",
              28: "twenty-eighth", 29: "twenty-ninth", 30: "thirtieth", 31: "thirty-first"}


def _day_label(day: str | None, now: datetime | None = None, *, spoken: bool = False) -> str:
    try:
        d = datetime.strptime(day, "%Y-%m-%d") if day else (now or datetime.now())
    except ValueError:
        d = now or datetime.now()
    if spoken:
        return d.strftime("%A the ") + _ORD_WORDS.get(d.day, str(d.day)) + d.strftime(" of %B")
    return d.strftime("%a %d %b").replace(" 0", " ")


# ============================================================================ dossier facts

def _l5(dos: dict, side: str) -> list[dict]:
    """Newest-first results with the same match never counted twice (see breakdown_script.last_results)."""
    return bs.last_results(dos, side)


def _letters(l5: list[dict]) -> str:
    return "".join("W" if m["gf"] > m["ga"] else "D" if m["gf"] == m["ga"] else "L" for m in l5[:5])


def _lead(letters: str, pred) -> int:
    k = 0
    for c in letters:
        if not pred(c):
            break
        k += 1
    return k


def _rest_days(dos: dict) -> tuple[str | None, str | None]:
    rh = ra = None
    for f in ((dos.get("context") or {}).get("facts") or []):
        if isinstance(f, dict) and f.get("category") == "fatigue" and not f.get("stale"):
            m = re.search(r"(\d+)\s*day\(s\)\s*before kick-off", str(f.get("text") or ""))
            if m and f.get("subject") == dos.get("home"):
                rh = m.group(1)
            elif m and f.get("subject") == dos.get("away"):
                ra = m.group(1)
    return rh, ra


def _weather(dos: dict) -> tuple[str, str] | None:
    """(slide text, spoken text) or None. Never guesses."""
    for f in ((dos.get("context") or {}).get("facts") or []):
        if isinstance(f, dict) and f.get("category") == "weather" and not f.get("stale"):
            t = str(f.get("text") or "")
            m = re.search(r"(-?\d+)\s*°C,\s*rain\s*([\d.]+)\s*mm/h,\s*wind\s*(\d+)\s*km/h", t)
            if not m:
                continue
            temp, rain, wind = int(m.group(1)), float(m.group(2)), int(m.group(3))
            wet = "rain around" if rain >= 0.3 else "dry"
            return (f"{temp}°C · {'rain around' if rain >= 0.3 else 'dry'} · wind {wind} km/h",
                    f"It's {temp} degrees at kick-off and {'there is some rain around' if rain >= 0.3 else 'it should stay dry'}.")
    return None


def _h2h(dos: dict) -> tuple[list[dict], dict]:
    return bs.meetings(dos), (dos.get("h2h_meta") or {})


def _first_word(name) -> str:
    return re.sub(r"^(1\.\s*)?(fc|sc)\s+", "", str(name or "").strip().lower()).split(" ")[0]


def _clean_title(title: str, source: str) -> str:
    """Drop a trailing ' - <source>' tag only when it really is the outlet's name."""
    t, src = str(title or "").strip(), re.sub(r"\s+", " ", str(source or "").strip())
    return re.sub(r"\s+[-|–—]\s+" + re.escape(src) + r"\s*$", "", t, flags=re.I).strip() if src else t


def _bare_fixture(title: str, dos: dict) -> bool:
    """True when the headline is little more than 'Team A v Team B'."""
    t = str(title or "").lower()
    for nm in (dos.get("home"), dos.get("away")):
        n = str(nm or "").lower()
        t = t.replace(n, " ").replace(_first_word(nm), " ")
    t = re.sub(r"\b(vs?\.?|versus|fc|sc)\b", " ", t)
    return len(re.findall(r"[a-z]{3,}", t)) < 3


def reputable_headlines(dos: dict, limit: int = 2) -> list[dict]:
    """Fresh headlines from reputable outlets (no tipster/odds pieces). Items: team, text, source."""
    out, seen = [], set()
    news = dos.get("news") or {}
    for side, label in (("match", ""), ("home", dos.get("home")), ("away", dos.get("away"))):
        for it in (news.get(side) or []):
            if not isinstance(it, dict):
                continue
            src = str(it.get("source") or "").strip()
            title = _clean_title(it.get("title"), src)
            if not title or not any(k in src.lower() for k in _REPUTABLE) or _JUNK_TITLE.search(title) or _bare_fixture(title, dos):
                continue
            if it.get("bucket") not in ("24h", "3d"):
                continue
            both = all(_first_word(x) in title.lower() for x in (dos.get("home"), dos.get("away")) if x)
            if not (_NEWS_KEYWORDS.search(title) or (both and len(title.split()) >= 7)):
                continue  # not team news for THIS match (old results, clickbait, bare fixture names)
            key = re.sub(r"\W+", "", title.lower())[:60]
            if key in seen:
                continue
            seen.add(key)
            when = str(it.get("when") or "")[5:10]
            out.append({"team": label or "", "text": title, "source": f"{src} · {when}" if when else src, "_src": src,
                        "_when": str(it.get("when") or "")})
    out.sort(key=lambda x: x["_when"], reverse=True)
    return out[:limit]


# ============================================================================ pick wording

# ============================================================================ selection

def _league_key(x) -> str:
    return re.sub(r"[^a-z0-9]", "", sp.ascii_fold(str(x or "")).lower())


def _league_rank(country: str, league: str) -> int:
    """Prestige order; spelling-proof ("La Liga" and "LaLiga" are the same league)."""
    c, l = _league_key(country), _league_key(league)
    for i, (bc, bl) in enumerate(BIG_LEAGUE_PRIORITY):
        if c == _league_key(bc) and (not bl or l == _league_key(bl)):
            return i
    return len(BIG_LEAGUE_PRIORITY) + 10


def select_featured_matches(dossiers: list[dict], shortlist_primary: list[dict] | None = None, *,
                            limit: int = DEFAULT_MATCHES, day: str | None = None) -> list[dict]:
    """Up to `limit` (5-7) matches from the biggest leagues with rich data and a qualifying Overs market.

    `day` (YYYY-MM-DD) keeps today's fixtures only. Best (most prestigious) leagues first; one match
    per league first, then a second from the same league if more are needed.
    """
    limit = max(1, min(MAX_MATCHES, int(limit)))
    sl = {(str(p.get("home") or ""), str(p.get("away") or "")): p for p in (shortlist_primary or []) if isinstance(p, dict)}
    cands = []
    for dos in dossiers or []:
        if not isinstance(dos, dict):
            continue
        ko = str(dos.get("kickoff") or "")
        if day and not ko.startswith(day):
            continue
        th, ta = ((dos.get("teams") or {}).get("home")) or {}, ((dos.get("teams") or {}).get("away")) or {}
        if min(int(th.get("n") or 0), int(ta.get("n") or 0)) < 15:
            continue
        h, a = str(dos.get("home") or ""), str(dos.get("away") or "")
        p = sl.get((h, a))
        best = None
        if p and reel.is_breakdown_market(p):
            best = {"sel": p.get("sel"), "label": p.get("label"), "odds": p.get("odds"), "market": p.get("market") or "goals"}
        else:
            for s in (dos.get("sels") or []):
                if isinstance(s, dict) and reel.is_breakdown_market(s) and isinstance(s.get("odds"), (int, float)) \
                        and 1.15 <= float(s["odds"]) <= 1.90:
                    best = {"sel": s.get("sel"), "label": s.get("label") or s.get("sel"), "odds": float(s["odds"]),
                            "market": s.get("market") or "goals"}
                    break
        if not best or not best.get("label"):
            continue
        cands.append(((0 if (p and reel.is_breakdown_market(p)) else 1), _league_rank(dos.get("country"), dos.get("league")), ko,
                      {**dos, "_best_market": best, "_shortlist_pick": p}))
    cands.sort(key=lambda x: (x[0], x[1], x[2]))
    chosen, leagues = [], set()
    for _, _, _, it in cands:
        k = (it.get("country"), it.get("league"))
        if k not in leagues and len(chosen) < limit:
            chosen.append(it)
            leagues.add(k)
    for _, _, _, it in cands:
        if len(chosen) >= limit:
            break
        if it not in chosen:
            chosen.append(it)
    chosen.sort(key=lambda it: (_league_rank(it.get("country"), it.get("league")), str(it.get("kickoff"))))
    return chosen[:limit]


# ============================================================================ script pack

def part_budgets(n_matches: int, cps: float = CHARS_PER_SEC) -> tuple[int, int, int]:
    """Character budgets for narration parts A, B, V so the whole video stays under MAX_SECONDS."""
    slides = 2 + 3 * max(1, n_matches)
    speech_s = MAX_SECONDS - slides * reel.TAIL - 4.0
    per_match = (speech_s * cps - INTRO_CHARS - CLOSER_CHARS) / max(1, n_matches)
    return int(per_match * 0.35), int(per_match * 0.36), int(per_match * 0.29)


def spoken_market(best: dict, dos: dict) -> str:
    return bs.spoken_market(best, dos)


def _chooser(day: str | None, key: str) -> sp.Chooser:
    return sp.Chooser(sp.seed_for(day or "", key))


def _a_text(dos: dict, idx: int, total: int, budget: int, ch: sp.Chooser | None = None, table: dict | None = None,
            rot: int = 0) -> str:
    ch = ch or _chooser(None, f"{dos.get('home')}|{dos.get('away')}")
    return bs.assemble(bs.a_units(dos, idx, total, ch, table, rot), budget)


def _b_text(dos: dict, cards: list[dict] | None, table: dict | None, budget: int, ch: sp.Chooser | None = None,
            facts: list[dict] | None = None) -> str:
    ch = ch or _chooser(None, f"{dos.get('home')}|{dos.get('away')}")
    structured = [c for c in (cards or []) if any(c.get(k) for k in ("out", "doubt", "susp", "back", "clear", "spoken"))]
    heads = [] if structured else reputable_headlines(dos, limit=2)
    return bs.assemble(bs.b_units(dos, structured, ch, headlines=heads, rest=_rest_days(dos), facts=facts), budget)


def _v_text(dos: dict, budget: int, ch: sp.Chooser | None = None, idx: int = 1, reasons: list | None = None,
            rot: int = 0) -> tuple[str, list[str]]:
    ch = ch or _chooser(None, f"{dos.get('home')}|{dos.get('away')}")
    items, bullets = bs.v_units(dos, ch, reasons, idx=idx, rot=rot)
    return bs.assemble(items, budget), bullets


def intro_text(matches: list[dict], day: str | None = None) -> str:
    return bs.intro_text(matches, _day_label(day, spoken=True), _chooser(day, "intro"))


def closer_text(matches: list[dict], day: str | None = None) -> str:
    return bs.closer_text(matches, _chooser(day, "closer"))


def _card_screen_text(c: dict) -> str:
    """On-screen line for a structured team-news card (it says what the narration says)."""
    parts = []
    if not any(c.get(k) for k in ("out", "susp", "doubt")):
        parts.append("No fresh injury concerns.")
    for key, label in (("out", "Out"), ("susp", "Suspended"), ("doubt", "Doubtful"), ("back", "Back")):
        if c.get(key):
            parts.append(f"{label}: {', '.join(str(x) for x in c[key])}.")
    return " ".join(parts) or str(c.get("note") or "No fresh injury concerns.")


def _cards_from_headlines(dos: dict) -> list[dict]:
    """On-screen cards for fresh headlines from reputable outlets (what is said comes from breakdown_script)."""
    return [{"team": h["team"] or "Match", "text": h["text"], "source": h["source"]} for h in reputable_headlines(dos, limit=2)]


def auto_pack(matches: list[dict], *, day: str | None = None, cps: float = CHARS_PER_SEC, extras: dict | None = None) -> dict:
    """Narration + on-screen text for every slide, written from the data alone.

    `extras` (optional, keyed "Home|Away") carries sourced material found by hand: structured team-news `cards`
    ({team, out[], doubt[], susp[], back[], source}), `table` ({home: "8th · 10 pts", away, source}), `facts`
    ([{text, source, spoken}]), `reasons`, `stadium`, `photos`. Everything is still spoken in the same natural voice.
    """
    n = len(matches)
    ba, bb, bv = part_budgets(n, cps)
    pack = {"intro": intro_text(matches, day), "closer": closer_text(matches, day), "matches": []}
    rot = sp.seed_for(day or "", "rot") % 60
    for i, m in enumerate(matches, 1):
        key = f"{m.get('home')}|{m.get('away')}"
        ex = (extras or {}).get(key) or {}
        ch = _chooser(day, key)
        cards = [dict(c) for c in (ex.get("cards") or [])]
        for c in cards:
            c.setdefault("text", _card_screen_text(c))
        screen_cards = cards or _cards_from_headlines(m)
        table = ex.get("table")
        v, why = _v_text(m, bv, ch, i, ex.get("reasons"), rot)
        w = _weather(m)
        pack["matches"].append({
            "key": key,
            "a": _a_text(m, i, n, ba, ch, table, rot),
            "b": _b_text(m, cards, table, bb, ch, ex.get("facts")),
            "v": v, "why": ex.get("why") or why, "cards": screen_cards, "table": table,
            "facts": [{k: f[k] for k in ("text", "source") if k in f} for f in (ex.get("facts") or [])],
            "weather": w[0] if w else None, "photos": ex.get("photos") or [], "stadium": ex.get("stadium"),
        })
    return pack


def apply_overrides(pack: dict, overrides: dict | None, matches: list[dict] | None = None) -> dict:
    """Overlay hand-researched content (sourced facts, polished lines) on an auto pack.

    String fields may use {odds} and {pick}: they are filled from the live data snapshot so what is
    said and shown always matches the price on screen.
    """
    if not overrides:
        return pack
    for k in ("intro", "closer"):
        if overrides.get(k):
            pack[k] = overrides[k]
    by_key = {o.get("key"): o for o in (overrides.get("matches") or []) if isinstance(o, dict)}
    by_match = {f"{m.get('home')}|{m.get('away')}": m for m in (matches or [])}
    for pm in pack["matches"]:
        o = by_key.get(pm["key"])
        if not o:
            continue
        m = by_match.get(pm["key"]) or {}
        best = m.get("_best_market") or {}
        odds = best.get("odds")
        fill = {"odds": f"{float(odds):.2f}" if isinstance(odds, (int, float)) else "N/A", "pick": spoken_market(best, m) if best else ""}
        for k, v in o.items():
            if k == "key" or v is None:
                continue
            pm[k] = v.format_map(fill) if isinstance(v, str) else v
    return pack


# ============================================================================ drawing helpers

def _font(size: int, bold: bool = True):
    return reel._font(int(size), bold)


def _tw(d, s, f) -> int:
    return reel._tw(d, s, f)


def _ellipsize(d, s: str, f, max_w: int) -> str:
    s = str(s or "")
    if _tw(d, s, f) <= max_w:
        return s
    while len(s) > 1 and _tw(d, s + "…", f) > max_w:
        s = s[:-1]
    return s.rstrip() + "…"


def _fit(d, s: str, size: int, max_w: int, bold: bool = True, min_size: int = 13):
    sz = size
    while sz > min_size:
        f = _font(sz, bold)
        if _tw(d, s, f) <= max_w:
            return f
        sz -= 2
    return _font(min_size, bold)


def _ctext(d, cx: int, y: int, s: str, f, fill, max_w: int | None = None) -> None:
    s = _ellipsize(d, s, f, max_w) if max_w else str(s)
    d.text((cx - _tw(d, s, f) // 2, y), s, fill=fill, font=f)


def _chip(d, cx: int, y: int, text: str, f, fg, *, fill=PANEL_BG, outline=GOLD, padx: int = 20, h: int = 42, r: int = 14,
          max_w: int | None = None) -> None:
    text = _ellipsize(d, text, f, max_w - 2 * padx) if max_w else text
    tw = _tw(d, text, f)
    d.rounded_rectangle((cx - tw // 2 - padx, y, cx + tw // 2 + padx, y + h), r, fill=fill, outline=outline, width=2)
    d.text((cx - tw // 2, y + (h - getattr(f, "size", 18)) // 2 - 3), text, fill=fg, font=f)


def _panel(d, box, outline=BORDER_DIM, fill=CARD_BG, r: int = 22, width: int = 2) -> None:
    d.rounded_rectangle(box, r, fill=fill, outline=outline, width=width)


def _wrap_all(d, s: str, f, max_w: int) -> list[str]:
    lines, cur = [], ""
    for w in str(s or "").split():
        t = (cur + " " + w).strip()
        if _tw(d, t, f) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _para_h(d, s: str, size: int, max_w: int, max_h: int, *, bold: bool = False, min_size: int = 14) -> int:
    """Height _para would use (no drawing)."""
    sz = size
    while True:
        f, lh = _font(sz, bold), int(sz * 1.3)
        n = len(_wrap_all(d, s, f, max_w))
        if n * lh <= max_h or sz <= min_size:
            return min(n, max(1, max_h // lh)) * lh
        sz -= 1


def _para(d, x: int, y: int, s: str, size: int, fill, max_w: int, max_h: int, *, bold: bool = False, min_size: int = 14) -> int:
    """Draw wrapped text that is guaranteed to fit max_h (shrinks the font, never cuts mid-sentence). Returns end y."""
    sz = size
    while True:
        f = _font(sz, bold)
        lh = int(sz * 1.3)
        lines = _wrap_all(d, s, f, max_w)
        if len(lines) * lh <= max_h or sz <= min_size:
            break
        sz -= 1
    f, lh = _font(sz, bold), int(sz * 1.3)
    lines = _wrap_all(d, s, f, max_w)
    maxl = max(1, max_h // lh)
    if len(lines) > maxl:
        lines = lines[:maxl]
        lines[-1] = _ellipsize(d, lines[-1] + " …", f, max_w)
    for ln in lines:
        d.text((x, y), ln, fill=fill, font=f)
        y += lh
    return y


def _bg(path: Path, size: tuple[int, int], dark: float = 0.70, blur: int = 5):
    from PIL import ImageFilter
    im = reel._cover(path, dark, size=size)
    return im.filter(ImageFilter.GaussianBlur(blur)) if blur else im


def _crest(im, path: Path, dpx: int, x: int, y: int) -> None:
    b = reel._circle_badge(path, dpx)
    im.paste(b, (x, y), b)


def _photo(im, path: Path | None, box, *, caption: str = "", credit: str = "", r: int = 20, outline=CYAN) -> None:
    """Framed, rounded photo (cropped around the pitch when the centre would be mostly sky) with a caption + credit strip."""
    from PIL import Image, ImageDraw, ImageOps
    x0, y0, x1, y1 = box
    pw, ph = x1 - x0, y1 - y0
    try:
        src = Image.open(path).convert("RGB")
        crop = ImageOps.fit(src, (pw, ph), Image.Resampling.LANCZOS, centering=vphotos.pitch_centering(src, pw, ph))
    except Exception:  # noqa: BLE001
        crop = Image.new("RGB", (pw, ph), PANEL_BG)
    if caption or credit:
        strip = 64 if (caption and credit) else 42
        ov = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        ImageDraw.Draw(ov).rectangle((0, ph - strip, pw, ph), fill=(4, 12, 22, 210))
        crop = Image.alpha_composite(crop.convert("RGBA"), ov).convert("RGB")
        dd = ImageDraw.Draw(crop)
        y = ph - strip + 8
        if caption:
            dd.text((14, y), caption, fill=GOLD, font=_fit(dd, caption, 21, pw - 28))
            y += 27
        if credit:
            dd.text((14, y), credit, fill=MUTED, font=_fit(dd, credit, 14, pw - 28, bold=False, min_size=10))
    mask = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw - 1, ph - 1), r, fill=255)
    im.paste(crop, (x0, y0), mask)
    ImageDraw.Draw(im).rounded_rectangle(box, r, outline=outline, width=2)


def _footer(d, cw: int, ch: int, text: str, y_off: int = 50) -> None:
    f = _fit(d, text, 19, cw - 120, bold=False)
    _ctext(d, cw // 2, ch - y_off, text, f, MUTED)


FOOT = "PlayReport  ·  Statistical information, not betting advice  ·  18+  ·  Bet responsibly"


def _venue_name(m: dict, photo: dict | None) -> str:
    return (photo or {}).get("stadium") or ""


def _comp(m: dict) -> str:
    return "  ·  ".join(x for x in (str(m.get("country") or "").upper(), str(m.get("league") or "").upper()) if x)


def _ko(m: dict) -> str:
    return str(m.get("kickoff") or "")[11:16]


# ============================================================================ slides

def _today_word(matches: list[dict]) -> str:
    """"TONIGHT'S" only when every kick-off is in the evening, otherwise "TODAY'S" (the narration says the same)."""
    return "TONIGHT'S" if sp.all_evening(str(m.get("kickoff") or "")[11:16] for m in matches) else "TODAY'S"


def render_intro(matches, pk_matches, logo: Path, bg: Path, dest: Path, *, crests, photos, day_text: str, aspect="16:9") -> None:
    from PIL import Image, ImageDraw, ImageFilter
    cw, ch = reel._resolve_size(aspect)
    im = _bg(bg, (cw, ch), 0.74, 6)
    d = ImageDraw.Draw(im)
    n = len(matches)
    L = Image.open(logo).convert("RGBA")
    if cw < ch:
        reel._wordmark(d, 52, width=cw)
        Lz = L.resize((150, 150), Image.Resampling.LANCZOS)
        im.paste(Lz.filter(ImageFilter.GaussianBlur(12)), ((cw - 150) // 2, 128), Lz.filter(ImageFilter.GaussianBlur(12)))
        im.paste(Lz, ((cw - 150) // 2, 128), Lz)
        d = ImageDraw.Draw(im)
        _ctext(d, cw // 2, 300, f"{_today_word(matches)} MATCHES", _font(54), GREEN)
        _ctext(d, cw // 2, 372, f"{day_text}  ·  {n} matches  ·  kick-offs in SAST", _font(24), GOLD, cw - 100)
        _ctext(d, cw // 2, 414, "Form  ·  Home & away  ·  Head to head  ·  Team news", _font(21, False), MUTED, cw - 100)
        card_h, gap, y = 192, 12, 470
        for i, m in enumerate(matches, 1):
            _panel(d, (50, y, cw - 50, y + card_h), outline=GREEN, r=22)
            hb, ab = crests[i - 1]
            _crest(im, hb, 96, 80, y + (card_h - 96) // 2)
            _crest(im, ab, 96, cw - 80 - 96, y + (card_h - 96) // 2)
            d = ImageDraw.Draw(im)
            _ctext(d, cw // 2, y + 20, f"MATCH {i}  ·  {_comp(m)}", _font(19), GREEN, cw - 340)
            _ctext(d, cw // 2, y + 60, f"{m.get('home')}  v  {m.get('away')}", _fit(d, f"{m.get('home')}  v  {m.get('away')}", 30, cw - 340), WHITE)
            v = (photos[i - 1] or [{}])[0].get("stadium") if photos[i - 1] else ""
            _ctext(d, cw // 2, y + 112, v or "", _font(19, False), CYAN, cw - 340)
            _chip(d, cw // 2, y + 144, f"KICK-OFF {_ko(m)}", _font(18), GOLD, h=36, padx=18)
            y += card_h + gap
        _footer(d, cw, ch, "18+  ·  Statistical information, not betting advice  ·  Bet responsibly", 96)
    else:
        reel._wordmark(d, 26, width=cw)
        Lz = L.resize((140, 140), Image.Resampling.LANCZOS)
        im.paste(Lz.filter(ImageFilter.GaussianBlur(12)), (90, 86), Lz.filter(ImageFilter.GaussianBlur(12)))
        im.paste(Lz, (90, 86), Lz)
        d = ImageDraw.Draw(im)
        d.text((258, 92), f"{_today_word(matches)} MATCHES", fill=GREEN, font=_font(54))
        d.text((258, 160), f"{day_text}  ·  {n} matches  ·  kick-offs in SAST", fill=GOLD, font=_font(25))
        d.text((258, 198), "Form  ·  Home & away numbers  ·  Head to head  ·  Team news  ·  my pick at the end of every match", fill=MUTED, font=_font(20, False))
        cols = 3 if n <= 6 else 4
        rows = (n + cols - 1) // cols
        mx, gx, gy, top = 80, 26, 26, 252
        card_w = (cw - 2 * mx - (cols - 1) * gx) // cols
        card_h = (ch - top - 70 - (rows - 1) * gy) // rows
        for i, m in enumerate(matches, 1):
            r_i, c_i = divmod(i - 1, cols)
            x0, y0 = mx + c_i * (card_w + gx), top + r_i * (card_h + gy)
            x1, y1 = x0 + card_w, y0 + card_h
            cx = (x0 + x1) // 2
            ph = (photos[i - 1] or [None])[0] if photos[i - 1] else None
            ban_h = int(card_h * 0.40)
            _panel(d, (x0, y0, x1, y1), outline=GREEN, r=24)
            if ph:
                _photo(im, ph["path"], (x0 + 8, y0 + 8, x1 - 8, y0 + 8 + ban_h), r=18, outline=BORDER_DIM)
            d = ImageDraw.Draw(im)
            yy = y0 + 8 + ban_h + 12
            _ctext(d, cx, yy, f"MATCH {i}  ·  {_comp(m)}", _font(18), GREEN, card_w - 30)
            hb, ab = crests[i - 1]
            _crest(im, hb, 70, x0 + 30, yy + 34)
            _crest(im, ab, 70, x1 - 30 - 70, yy + 34)
            d = ImageDraw.Draw(im)
            _ctext(d, cx, yy + 44, "v", _font(26), GOLD)
            nm = f"{m.get('home')}  v  {m.get('away')}"
            _ctext(d, cx, yy + 116, nm, _fit(d, nm, 23, card_w - 24), WHITE)
            _chip(d, cx, y1 - 52, f"KICK-OFF {_ko(m)} SAST", _font(17), GOLD, h=36, padx=16)
        _footer(d, cw, ch, "18+  ·  Statistical information, not betting advice  ·  Bet responsibly  ·  Never bet more than you can afford to lose", 50)
    im.convert("RGB").save(dest, quality=92)


def _table_str(pm: dict, side: str) -> str:
    t = (pm or {}).get("table") or {}
    return str(t.get(side) or "")


def _form_title(lh: list[dict], la: list[dict]) -> str:
    """"RECENT FORM · LAST FIVE", or the real number when the de-duplicated form lists are shorter."""
    n = min(len(lh[:5]), len(la[:5]))
    if len(lh[:5]) == len(la[:5]) and n:
        return f"RECENT FORM  ·  LAST {sp.words(n).upper()}"
    return "RECENT FORM"


def render_board_a(m: dict, pm: dict, idx: int, total: int, bgp: Path, hb: Path, ab: Path, dest: Path, *,
                   stadium: str = "", aspect="16:9") -> None:
    from PIL import ImageDraw
    cw, ch = reel._resolve_size(aspect)
    im = _bg(bgp, (cw, ch), 0.72, 6)
    d = ImageDraw.Draw(im)
    h, a = str(m.get("home")), str(m.get("away"))
    th, ta = ((m.get("teams") or {}).get("home")) or {}, ((m.get("teams") or {}).get("away")) or {}
    lh, la = _l5(m, "home"), _l5(m, "away")
    fh, fa = _letters(lh), _letters(la)
    head = f"MATCH {idx} OF {total}  ·  {_comp(m)}  ·  {_ko(m)} SAST"
    split = [
        (str(th.get("venue_n", "N/A")), "Venue sample (games)", str(ta.get("venue_n", "N/A"))),
        (_num(th.get("venue_gf")), "Goals scored per game", _num(ta.get("venue_gf"))),
        (_num(th.get("venue_ga")), "Goals conceded per game", _num(ta.get("venue_ga"))),
        (_pct(th.get("venue_o15")), "Over 1.5 goals", _pct(ta.get("venue_o15"))),
        (_pct(th.get("venue_o25")), "Over 2.5 goals", _pct(ta.get("venue_o25"))),
        (_pct(th.get("venue_btts")), "Both teams to score", _pct(ta.get("venue_btts"))),
        (_pct(1 - th["fts"]) if isinstance(th.get("fts"), (int, float)) else "N/A", "Scores in a match (season)",
         _pct(1 - ta["fts"]) if isinstance(ta.get("fts"), (int, float)) else "N/A"),
    ]

    def last5_rows(lst):
        rows = []
        for mm in lst[:5]:
            res = "W" if mm["gf"] > mm["ga"] else "D" if mm["gf"] == mm["ga"] else "L"
            rows.append((res, f"{int(mm['gf'])}-{int(mm['ga'])}", f"{'H' if mm.get('venue') == 'H' else 'A'}  {mm.get('opp') or ''}"))
        return rows or [("", "N/A", "no recent matches")]

    col = {"W": GREEN, "D": MUTED, "L": RED, "": MUTED}
    if cw < ch:
        reel._wordmark(d, 52, width=cw)
        _ctext(d, cw // 2, 118, head, _font(20), GREEN, cw - 80)
        _panel(d, (50, 160, cw - 50, 440), outline=BORDER_DIM, r=24)
        _crest(im, hb, 128, 110, 184)
        _crest(im, ab, 128, cw - 110 - 128, 184)
        d = ImageDraw.Draw(im)
        _ctext(d, cw // 2, 218, "v", _font(36), GOLD)
        _chip(d, cw // 2, 270, "FORM & VENUE", _font(19), CYAN, outline=CYAN, h=38, padx=16)
        for cx, nm, fm, side in ((174, h, fh, "home"), (cw - 174, a, fa, "away")):
            _ctext(d, cx, 322, nm, _fit(d, nm, 25, 320), WHITE)
            reel._draw_form_pills(d, fm, cx, 362)
            tb = _table_str(pm, side)
            if tb:
                _ctext(d, cx, 398, tb, _font(18), GOLD, 320)
        _panel(d, (50, 462, cw - 50, 1010), outline=GREEN)
        _ctext(d, cw // 2, 482, _form_title(lh, la), _font(23), GREEN)
        d.rectangle((cw // 2 - 1, 530, cw // 2 + 1, 980), fill=BORDER_DIM)
        for x0, nm, lst, tt in ((82, h, lh, th), (cw // 2 + 28, a, la, ta)):
            d.text((x0, 526), _ellipsize(d, nm, _font(21), 400), fill=GOLD, font=_font(21))
            d.text((x0, 556), f"{_num(tt.get('gf'))} for · {_num(tt.get('ga'))} against per game", fill=MUTED, font=_font(17, False))
            for r_i, (res, sc, who) in enumerate(last5_rows(lst)):
                yy = 600 + r_i * 74
                d.rounded_rectangle((x0 - 8, yy, x0 + 424, yy + 62), 12, fill=PANEL_BG)
                d.text((x0 + 8, yy + 16), res, fill=col[res], font=_font(24))
                d.text((x0 + 52, yy + 16), sc, fill=WHITE, font=_font(24))
                d.text((x0 + 128, yy + 20), _ellipsize(d, who, _font(18, False), 290), fill=MUTED, font=_font(18, False))
        _panel(d, (50, 1034, cw - 50, 1800), outline=CYAN)
        _ctext(d, cw // 2, 1054, "HOME v AWAY  ·  VENUE SPLIT", _font(23), CYAN)
        _ctext(d, 224, 1086, "HOME", _font(16), GREEN)
        _ctext(d, cw - 224, 1086, "AWAY", _font(16), GOLD)
        _ctext(d, 224, 1108, say(h), _fit(d, say(h), 24, 340), WHITE)
        _ctext(d, cw - 224, 1108, say(a), _fit(d, say(a), 24, 340), WHITE)
        yy = 1146
        for hv, lab, av in split:
            d.rounded_rectangle((78, yy, cw - 78, yy + 84), 14, fill=PANEL_BG)
            _ctext(d, 224, yy + 24, hv, _font(30), GREEN)
            _ctext(d, cw // 2, yy + 28, lab, _font(21, False), WHITE, 420)
            _ctext(d, cw - 224, yy + 24, av, _font(30), GOLD)
            yy += 94
        _footer(d, cw, ch, FOOT, 78)
    else:
        reel._wordmark(d, 26, width=cw)
        _ctext(d, cw // 2, 86, head, _font(22), GREEN)
        _panel(d, (80, 128, cw - 80, 300), outline=BORDER_DIM, r=24)
        _crest(im, hb, 124, 118, 152)
        _crest(im, ab, 124, cw - 118 - 124, 152)
        d = ImageDraw.Draw(im)
        _ctext(d, cw // 2, 160, "v", _font(40), GOLD)
        _chip(d, cw // 2, 218, "PART 1  ·  FORM & VENUE", _font(20), CYAN, outline=CYAN, h=40, padx=18)
        for x0, nm, fm, side, tt, right in ((262, h, fh, "home", th, False), (cw - 262, a, fa, "away", ta, True)):
            f = _fit(d, nm, 38, 560)
            tx = x0 if not right else x0 - _tw(d, nm, f)
            d.text((tx if not right else min(tx, x0 - _tw(d, _ellipsize(d, nm, f, 560), f)), 154), _ellipsize(d, nm, f, 560), fill=WHITE, font=f)
            pill_cx = x0 + 90 if not right else x0 - 90
            reel._draw_form_pills(d, fm, pill_cx, 212)
            sub = f"{_num(tt.get('gf'))} for · {_num(tt.get('ga'))} against per game"
            tb = _table_str(pm, side)
            sub = (tb + "   ·   " + sub) if tb else sub
            sf = _font(18, False)
            d.text((x0 if not right else x0 - _tw(d, sub, sf), 254), sub, fill=GOLD if tb else MUTED, font=sf)
        _panel(d, (80, 322, 935, 1000), outline=GREEN)
        d.text((112, 344), _form_title(lh, la), fill=GREEN, font=_font(24))
        d.rectangle((507, 392, 509, 972), fill=BORDER_DIM)
        for x0, nm, lst in ((112, h, lh), (534, a, la)):
            d.text((x0, 392), _ellipsize(d, nm, _font(22), 360), fill=GOLD, font=_font(22))
            for r_i, (res, sc, who) in enumerate(last5_rows(lst)):
                yy = 436 + r_i * 112
                d.rounded_rectangle((x0 - 6, yy, x0 + 370, yy + 96), 12, fill=PANEL_BG)
                d.text((x0 + 12, yy + 12), res, fill=col[res], font=_font(28))
                d.text((x0 + 62, yy + 12), sc, fill=WHITE, font=_font(28))
                d.text((x0 + 12, yy + 56), _ellipsize(d, who, _font(20, False), 340), fill=MUTED, font=_font(20, False))
        _panel(d, (985, 322, cw - 80, 1000), outline=CYAN)
        d.text((1020, 344), "HOME v AWAY  ·  VENUE SPLIT", fill=CYAN, font=_font(24))
        _ctext(d, 1110, 380, "HOME", _font(16), GREEN)
        _ctext(d, 1722, 380, "AWAY", _font(16), GOLD)
        _ctext(d, 1110, 402, say(h), _fit(d, say(h), 22, 250), WHITE)
        _ctext(d, 1722, 402, say(a), _fit(d, say(a), 22, 250), WHITE)
        yy = 438
        for hv, lab, av in split:
            d.rounded_rectangle((1015, yy, cw - 110, yy + 68), 12, fill=PANEL_BG)
            _ctext(d, 1110, yy + 18, hv, _font(27), GREEN)
            _ctext(d, 1416, yy + 22, lab, _font(20, False), WHITE, 300)
            _ctext(d, 1722, yy + 18, av, _font(27), GOLD)
            yy += 78
        _footer(d, cw, ch, FOOT, 52)
    im.convert("RGB").save(dest, quality=92)


def render_board_b(m: dict, pm: dict, idx: int, total: int, bgp: Path, hb: Path, ab: Path, dest: Path, *,
                   photo: dict | None, aspect="16:9") -> None:
    from PIL import ImageDraw
    cw, ch = reel._resolve_size(aspect)
    im = _bg(bgp, (cw, ch), 0.74, 7)
    d = ImageDraw.Draw(im)
    h, a = str(m.get("home")), str(m.get("away"))
    head = f"MATCH {idx} OF {total}  ·  {_comp(m)}  ·  {_ko(m)} SAST"
    rows, meta = _h2h(m)
    facts = [f for f in (pm.get("facts") or []) if isinstance(f, dict) and f.get("text")]
    cards = [c for c in (pm.get("cards") or []) if isinstance(c, dict) and c.get("text")]
    rh, ra = _rest_days(m)
    ctx = []
    if _table_str(pm, "home") or _table_str(pm, "away"):
        ctx.append(("TABLE", _table_str(pm, "home") or "N/A", _table_str(pm, "away") or "N/A"))
    if rh or ra:
        ctx.append(("DAYS SINCE LAST GAME", rh or "N/A", ra or "N/A"))
    wtxt = pm.get("weather")
    p_img = (photo or {}).get("path")
    p_cap = (photo or {}).get("stadium") or ""
    p_cr = (photo or {}).get("credit") or ""
    p_use = p_img if p_img else bgp

    def h2h_block(x, y, w, max_h):
        y_top = y
        f_s, f_m = _font(20), _font(21)
        if rows:
            goals = [int(r["hg"]) + int(r["ag"]) for r in rows]
            btts = sum(1 for r in rows if int(r["hg"]) > 0 and int(r["ag"]) > 0)
            o15 = sum(1 for g in goals if g >= 2)
            summ = (f"{len(rows)} meeting{'s' if len(rows) != 1 else ''}  ·  avg {sum(goals) / len(goals):.1f} goals  ·  "
                    f"BTTS {btts}/{len(rows)}  ·  Over 1.5 {o15}/{len(rows)}")
            d.text((x, y), _ellipsize(d, summ, f_s, w), fill=GOLD, font=f_s)
            y += 38
            fact_h = 34 if facts else 0
            n_rows = 3 if not facts else max(1, (max_h - 38 - fact_h) // 58)
            for r in rows[:n_rows]:
                line = f"{str(r.get('date'))[:10]}   {r.get('home')} {r.get('hg')}-{r.get('ag')} {r.get('away')}"
                d.rounded_rectangle((x, y, x + w, y + 50), 11, fill=PANEL_BG)
                d.text((x + 16, y + 12), _ellipsize(d, line, f_m, w - 32), fill=WHITE, font=f_m)
                y += 58
        else:
            d.text((x, y), "No meetings in the last 400 days  (N/A)", fill=WHITE, font=f_m)
            y += 40
        y_end = y_top + max_h
        for fct in facts[:2]:
            if y + 34 > y_end:                          # never let a line spill over the panel border
                break
            y = _para(d, x, y + 6, f"{fct['text']}  ({fct.get('source', '')})".replace("  ()", ""), 18, MUTED, w, min(56, y_end - y - 6), bold=False)
        return y

    def news_block(x, y, w, max_h, size=24):
        if not cards:
            _para(d, x, y + 8, "N/A: no confirmed team news yet. Line-ups usually arrive about an hour before kick-off.", 24, MUTED, w, max_h - 16)
            return
        n_c = min(3, len(cards))
        ch_ = (max_h - (n_c - 1) * 10) // n_c
        for c in cards[:n_c]:
            tcol = GREEN if c.get("team") == h else CYAN if c.get("team") == a else GOLD
            d.rounded_rectangle((x, y, x + w, y + ch_), 12, fill=PANEL_BG)
            d.rectangle((x, y + 8, x + 6, y + ch_ - 8), fill=tcol)
            tag = (c.get("team") or "MATCH").upper()
            d.text((x + 20, y + 8), _ellipsize(d, tag, _font(16), w - 260), fill=tcol, font=_font(16))
            src = str(c.get("source") or "")
            if src:
                sf = _font(15, False)
                d.text((x + w - 14 - _tw(d, _ellipsize(d, src, sf, 250), sf), y + 9), _ellipsize(d, src, sf, 250), fill=MUTED, font=sf)
            _para(d, x + 20, y + 34, c["text"], size, WHITE, w - 38, ch_ - 42)
            y += ch_ + 10

    if cw < ch:
        reel._wordmark(d, 48, width=cw)
        _ctext(d, cw // 2, 112, head, _font(20), GREEN, cw - 80)
        _photo(im, p_use, (50, 152, cw - 50, 520), caption=p_cap, credit=p_cr)
        d = ImageDraw.Draw(im)
        _crest(im, hb, 84, 74, 436 - 60)
        _crest(im, ab, 84, cw - 74 - 84, 436 - 60)
        d = ImageDraw.Draw(im)
        _panel(d, (50, 540, cw - 50, 905), outline=CYAN)
        d.text((84, 560), "HEAD TO HEAD  (CONTEXT ONLY)", fill=CYAN, font=_font(22))
        h2h_block(84, 604, cw - 168, 290)
        _panel(d, (50, 925, cw - 50, 1395), outline=GREEN)
        d.text((84, 945), "TEAM NEWS  ·  REPORTED BY", fill=GREEN, font=_font(22))
        news_block(78, 990, cw - 156, 380, size=27)
        _panel(d, (50, 1415, cw - 50, 1700), outline=BORDER_DIM)
        d.text((84, 1433), "MATCH CONTEXT", fill=GOLD, font=_font(22))
        yy = 1484
        _ctext(d, 690, yy - 4, say(h), _fit(d, say(h), 18, 250), GREEN)
        _ctext(d, 905, yy - 4, say(a), _fit(d, say(a), 18, 200), CYAN)
        yy += 26
        for lab, hv, av in ctx:
            d.text((84, yy + 10), lab, fill=MUTED, font=_font(17))
            _ctext(d, 690, yy, hv, _fit(d, hv, 25, 215), GREEN)
            _ctext(d, 905, yy, av, _fit(d, av, 25, 200), CYAN)
            yy += 52
        if wtxt:
            d.text((84, yy + 10), "WEATHER", fill=MUTED, font=_font(17))
            d.text((300, yy + 6), _ellipsize(d, wtxt, _font(22), cw - 400), fill=WHITE, font=_font(22))
        _footer(d, cw, ch, FOOT, 90)
    else:
        reel._wordmark(d, 26, width=cw)
        _ctext(d, cw // 2, 86, head, _font(22), GREEN)
        _panel(d, (80, 128, cw - 80, 262), outline=BORDER_DIM, r=22)
        _crest(im, hb, 96, 116, 147)
        _crest(im, ab, 96, cw - 116 - 96, 147)
        d = ImageDraw.Draw(im)
        title = f"{h}  v  {a}"
        _ctext(d, cw // 2, 154, title, _fit(d, title, 40, 1300), WHITE)
        _chip(d, cw // 2, 210, "PART 2  ·  HEAD TO HEAD, TEAM NEWS & CONTEXT", _font(19), GOLD, h=38, padx=18)
        _panel(d, (80, 282, 1120, 560), outline=CYAN)
        d.text((112, 300), "HEAD TO HEAD  (CONTEXT ONLY)", fill=CYAN, font=_font(23))
        h2h_block(112, 344, 976, 205)
        _panel(d, (80, 580, 1120, 1000), outline=GREEN)
        d.text((112, 598), "TEAM NEWS  ·  REPORTED BY", fill=GREEN, font=_font(23))
        news_block(104, 640, 992, 346, size=25)
        rx0, rx1 = 1155, cw - 80
        _photo(im, p_use, (rx0, 282, rx1, 600), caption=p_cap, credit=p_cr)
        d = ImageDraw.Draw(im)
        _panel(d, (rx0, 620, rx1, 1000), outline=BORDER_DIM)
        d.text((rx0 + 28, 636), "MATCH CONTEXT", fill=GOLD, font=_font(23))
        cxh, cxa = rx0 + 350, rx0 + 556
        _ctext(d, cxh, 678, say(h), _fit(d, say(h), 17, 196), GREEN)
        _ctext(d, cxa, 678, say(a), _fit(d, say(a), 17, 196), CYAN)
        yy = 712
        for lab, hv, av in ctx:
            d.rounded_rectangle((rx0 + 20, yy, rx1 - 20, yy + 62), 11, fill=PANEL_BG)
            d.text((rx0 + 36, yy + 22), lab, fill=MUTED, font=_fit(d, lab, 16, 190))
            _ctext(d, cxh, yy + 15, hv, _fit(d, hv, 23, 196), GREEN)
            _ctext(d, cxa, yy + 15, av, _fit(d, av, 23, 196), CYAN)
            yy += 72
        if wtxt:
            d.rounded_rectangle((rx0 + 20, yy, rx1 - 20, yy + 62), 11, fill=PANEL_BG)
            d.text((rx0 + 36, yy + 20), "WEATHER", fill=MUTED, font=_font(17))
            d.text((rx0 + 190, yy + 17), _ellipsize(d, wtxt, _font(21), rx1 - rx0 - 230), fill=WHITE, font=_font(21))
        _footer(d, cw, ch, FOOT, 50)
    im.convert("RGB").save(dest, quality=92)


def render_verdict(m: dict, pm: dict, idx: int, total: int, bgp: Path, hb: Path, ab: Path, dest: Path, *, aspect="16:9") -> None:
    from PIL import ImageDraw
    cw, ch = reel._resolve_size(aspect)
    im = _bg(bgp, (cw, ch), 0.66, 4)
    d = ImageDraw.Draw(im)
    h, a = str(m.get("home")), str(m.get("away"))
    best = m.get("_best_market") or {}
    odds = best.get("odds")
    od = f"{float(odds):.2f}" if isinstance(odds, (int, float)) else "N/A"
    label = str(best.get("label") or "Selection")
    why = [str(x) for x in (pm.get("why") or [])][:2]
    head = f"MATCH {idx} OF {total}  ·  {_comp(m)}"
    tall = cw < ch
    reel._wordmark(d, 52 if tall else 26, width=cw)
    _ctext(d, cw // 2, 120 if tall else 86, head, _font(21 if tall else 22), GREEN, cw - 80)

    # --- measure the card first so it hugs its content and sits in the visual middle
    card_w = (cw - 100) if tall else (cw - 940)
    inner_w = card_w - 120
    f_lab = _font(46 if tall else 44)
    lines = _wrap_all(d, label, f_lab, inner_w)[:2]
    lab_lh = 60 if tall else 56
    odds_sz = 190 if tall else 170
    bul_sz = 28 if tall else 25
    bul_h = sum(_para_h(d, f"•  {w}", bul_sz, inner_w, 84, bold=True) + 8 for w in why)
    content_h = 56 + lab_lh * len(lines) + (odds_sz + 90) + 50 + bul_h + 30 + 50 + 38
    top = (ch - content_h) // 2 + (30 if tall else 24)
    left = (cw - card_w) // 2
    bottom = top + content_h

    # crests flank the card (wide) or sit above it (tall)
    if tall:
        cy = max(150, top - 330)
        _crest(im, hb, 150, 120, cy)
        _crest(im, ab, 150, cw - 120 - 150, cy)
        d = ImageDraw.Draw(im)
        _ctext(d, cw // 2, cy + 50, "v", _font(46), GOLD)
        _ctext(d, 195, cy + 168, say(h), _fit(d, say(h), 27, 330), WHITE)
        _ctext(d, cw - 195, cy + 168, say(a), _fit(d, say(a), 27, 330), WHITE)
    else:
        mid = (top + bottom) // 2
        _crest(im, hb, 170, 150, mid - 105)
        _crest(im, ab, 170, cw - 150 - 170, mid - 105)
        d = ImageDraw.Draw(im)
        _ctext(d, 235, mid + 85, say(h), _fit(d, say(h), 30, 330), WHITE)
        _ctext(d, cw - 235, mid + 85, say(a), _fit(d, say(a), 30, 330), WHITE)

    _panel(d, (left, top, left + card_w, bottom), outline=GREEN, r=34, width=4)
    _ctext(d, cw // 2, top + 30, "MY PICK", _font(30), GREEN)
    y = top + 88
    for ln in lines:
        _ctext(d, cw // 2, y, ln, f_lab, WHITE)
        y += lab_lh
    _ctext(d, cw // 2, y + 12, od, _font(odds_sz), GREEN)
    y += odds_sz + 66
    _ctext(d, cw // 2, y, "SPORTYBET PRICE", _font(22 if tall else 21), MUTED)
    y += 50
    for w in why:
        y = _para(d, left + 60, y, f"•  {w}", bul_sz, WHITE, inner_w, 84, bold=True) + 8
    _chip(d, cw // 2, bottom - 38 - 50, f"KICK-OFF  {_ko(m)} SAST", _font(24 if tall else 23), GOLD, h=50, padx=26)
    _footer(d, cw, ch, "18+  ·  Statistical information, not betting advice" + ("" if tall else "  ·  Bet responsibly"), 150 if tall else 50)
    im.convert("RGB").save(dest, quality=92)


def render_closer(matches, pack_matches, logo: Path, bg: Path, dest: Path, *, credits_line: str = "", aspect="16:9") -> None:
    from PIL import ImageDraw
    cw, ch = reel._resolve_size(aspect)
    im = _bg(bg, (cw, ch), 0.74, 6)
    d = ImageDraw.Draw(im)
    n = len(matches)
    if cw < ch:
        reel._wordmark(d, 52, width=cw)
        _ctext(d, cw // 2, 130, f"{_today_word(matches)} {n} PICKS", _font(46), GREEN)
        y, card_h, gap = 210, 200, 12
        for i, m in enumerate(matches, 1):
            best = m.get("_best_market") or {}
            od = f" @ {float(best['odds']):.2f}" if isinstance(best.get("odds"), (int, float)) else ""
            _panel(d, (50, y, cw - 50, y + card_h), outline=GREEN, r=20)
            d.text((84, y + 16), _ellipsize(d, f"{_comp(m)}  ·  {_ko(m)}", _font(18), cw - 170), fill=MUTED, font=_font(18))
            nm = f"{i}.  {m.get('home')}  v  {m.get('away')}"
            d.text((84, y + 52), _ellipsize(d, nm, _font(28), cw - 170), fill=WHITE, font=_font(28))
            pk = f"{best.get('label') or ''}{od}"
            d.text((84, y + 106), _ellipsize(d, pk, _font(30), cw - 170), fill=GOLD, font=_font(30))
            y += card_h + gap
        _ctext(d, cw // 2, y + 8, "Like  ·  Share  ·  Subscribe  —  new matches every day", _font(25), WHITE, cw - 100)
        if credits_line:
            _ctext(d, cw // 2, y + 56, credits_line, _font(16, False), MUTED, cw - 100)
        _footer(d, cw, ch, "18+  ·  Statistical information, not betting advice  ·  Never bet more than you can afford to lose", 150)
        _footer(d, cw, ch, "© PlayReport. All rights reserved. Unauthorised copying or re-upload is prohibited.", 112)
    else:
        reel._wordmark(d, 26, width=cw)
        _ctext(d, cw // 2, 92, f"{_today_word(matches)} {n} PICKS", _font(42), GREEN)
        y = 160
        row_h = 112 if n <= 6 else 98
        gap = 12
        for i, m in enumerate(matches, 1):
            best = m.get("_best_market") or {}
            od = f"@ {float(best['odds']):.2f}" if isinstance(best.get("odds"), (int, float)) else ""
            _panel(d, (110, y, cw - 110, y + row_h), outline=GREEN, r=18)
            d.text((146, y + 14), _ellipsize(d, f"MATCH {i}  ·  {_comp(m)}  ·  {_ko(m)} SAST", _font(18), 900), fill=GREEN, font=_font(18))
            d.text((146, y + 50), _ellipsize(d, f"{m.get('home')}  v  {m.get('away')}", _font(30), 760), fill=WHITE, font=_font(30))
            pk = str(best.get("label") or "")
            pf = _font(27)
            right = cw - 146
            odw = _tw(d, od, _font(34))
            d.text((right - odw, y + 38), od, fill=GREEN, font=_font(34))
            d.text((right - odw - 28 - _tw(d, _ellipsize(d, pk, pf, 620), pf), y + 44), _ellipsize(d, pk, pf, 620), fill=GOLD, font=pf)
            y += row_h + gap
        _ctext(d, cw // 2, y + 6, "If this helped: like, share and subscribe. New matches every day.", _font(25), WHITE)
        if credits_line:
            _ctext(d, cw // 2, y + 50, credits_line, _font(16, False), MUTED, cw - 200)
        _footer(d, cw, ch, "18+  ·  Statistical information, not betting advice  ·  Never bet more than you can afford to lose", 84)
        _footer(d, cw, ch, "© PlayReport. All rights reserved. Unauthorised copying or re-upload is prohibited.", 46)
    im.convert("RGB").save(dest, quality=92)


# ============================================================================ audio

def _silences(src: Path, ff: str) -> list[tuple[float, float]]:
    p = subprocess.run([ff, "-i", str(src), "-af", "silencedetect=noise=-34dB:d=0.12", "-f", "null", "-"],
                       capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?[0-9.]+)", p.stderr or "")]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", p.stderr or "")]
    return [(s, e) for s, e in zip(starts, ends)]


def _tok(text: str) -> list[str]:
    return [t for t in re.sub(r"[^a-z0-9' ]+", " ", str(text or "").lower().replace("-", " ")).split() if t]


def asr_words(src: Path, ff: str) -> list[tuple[str, float, float]] | None:
    """Word-level timestamps via faster-whisper (tiny.en) when installed; None if unavailable.

    Only used to place slide changes inside ONE pre-recorded narration clip (e.g. when the voice API
    limits how many separate clips can be made). The daily CI build synthesises one clip per slide and
    never needs this.
    """
    try:
        import numpy as np
        from faster_whisper import WhisperModel
    except Exception:  # noqa: BLE001
        return None
    try:
        raw = subprocess.run([ff, "-v", "quiet", "-i", str(src), "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                             capture_output=True).stdout
        audio = np.frombuffer(raw, dtype=np.float32)
        model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
        segs, _ = model.transcribe(audio, word_timestamps=True, language="en", beam_size=1, vad_filter=False)
        return [(w.word.strip(), float(w.start), float(w.end)) for sg in segs for w in (sg.words or [])]
    except Exception as exc:  # noqa: BLE001
        log.warning("ASR alignment unavailable: %s", exc)
        return None


def align_boundaries(words: list[tuple[str, float, float]], parts: list[str]) -> list[float] | None:
    """Cut times between consecutive `parts` of a narration, found by aligning the script to the ASR words."""
    import difflib
    s_tok: list[str] = []
    starts: list[int] = []
    for t in parts:
        starts.append(len(s_tok))
        s_tok += _tok(t)
    a_tok = [x for w in words for x in (_tok(w[0]) or [""])][: len(words)]
    a_tok = [(_tok(w[0]) or [""])[0] for w in words]
    sm = difflib.SequenceMatcher(None, s_tok, a_tok, autojunk=False)
    mp: dict[int, int] = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            mp[blk.a + k] = blk.b + k
    cuts: list[float] = []
    for b in starts[1:]:
        ai = None
        for d in range(0, 4):
            if b + d in mp:
                ai = mp[b + d] - d
                break
        if ai is None:
            for d in range(1, 4):
                if b - d in mp:
                    ai = mp[b - d] + d
                    break
        if ai is None or not (0 < ai < len(words)):
            return None
        cuts.append(0.5 * (words[ai - 1][2] + words[ai][1]))
    if any(b <= a for a, b in zip([0.0] + cuts, cuts)):
        return None
    return cuts


def split_clip(src: Path, parts: list[str], dests: list[Path], ff: str, *, min_part: float = 2.0) -> list[float]:
    """Cut one narration clip into len(parts) clips exactly where each part begins."""
    total = reel._probe(src, ff)
    cuts = None
    words = asr_words(src, ff)
    if words:
        cuts = align_boundaries(words, parts)
        if cuts and any(b - a < min_part for a, b in zip([0.0] + cuts, cuts + [total])):
            cuts = None
    if cuts is None:   # fallback: expected time by characters, snapped to the nearest pause
        sil = [(s, e) for s, e in _silences(src, ff) if 0.8 < s < total - 0.3]
        chars, run, cuts = [len(t) for t in parts], 0, []
        for c in chars[:-1]:
            run += c
            exp = total * run / max(1, sum(chars))
            cands = [0.5 * (s + e) for s, e in sil] or [exp]
            cuts.append(min(cands, key=lambda t: abs(t - exp)))
        log.warning("split %s by pause heuristic (no ASR): cuts %s", Path(src).name, [round(c, 1) for c in cuts])
    # never cut inside a word: snap each cut to the middle of the nearest real pause (within 1 s)
    pauses = [0.5 * (a + b) for a, b in _silences(src, ff)]
    snapped = []
    for c in cuts:
        near = [t for t in pauses if abs(t - c) <= 1.0]
        snapped.append(min(near, key=lambda t: abs(t - c)) if near else c)
    if all(b - a >= min_part for a, b in zip([0.0] + snapped, snapped + [total])):
        cuts = snapped
    edges = [0.0] + cuts + [total]
    for i, dest in enumerate(dests):
        reel._run([ff, "-y", "-i", str(src), "-ss", f"{edges[i]:.3f}", "-to", f"{edges[i + 1]:.3f}", "-ac", "1", "-ar", "44100", str(dest)], f"cut {i}")
    return cuts


def _slice_clip(src: Path, texts: list[str], dests: list[Path], ff: str, polish: bool, seed: int) -> bool:
    """One narration clip -> one 44.1 kHz wav per slide.

    With `polish` the pauses are re-timed from the punctuation that caused them, sentences drift a little in pace and
    level, and each slide is mastered to one loudness (see voice_polish). If that cannot be done safely the clip is cut
    at its real pauses instead. Returns True when the polished version was used.
    """
    if polish:
        try:
            import voice_polish as vp
            x = vp.read_audio(src, ff)
            arrays = vp.polish_clip(x, texts, ff, words_fn=lambda: vp.asr_words(src, ff), seed=seed)
            if arrays and len(arrays) == len(dests):
                for a, d in zip(arrays, dests):
                    vp.to_wav44(a, d, ff)
                return True
            log.warning("voice polish could not place the slides in %s; cutting at the real pauses instead", Path(src).name)
        except Exception as exc:  # noqa: BLE001
            log.warning("voice polish failed for %s (%s); cutting at the real pauses instead", Path(src).name, exc)
    if len(texts) == 1:
        reel._run([ff, "-y", "-i", str(src), "-ac", "1", "-ar", "44100", str(dests[0])], f"decode {Path(src).name}")
    else:
        split_clip(Path(src), texts, dests, ff)
    return False


# ============================================================================ build

@dataclass
class Prepared:
    matches: list[dict]
    pack: dict
    slides: list[dict]               # {kind: intro|a|b|v|closer, i: match index or None, text}
    wavs: list[Path]
    work: Path
    assets: Path
    crests: list[tuple[Path, Path]] = field(default_factory=list)
    photos: list[list[dict]] = field(default_factory=list)
    day_text: str = ""
    credits: list[str] = field(default_factory=list)
    ff: str = ""


def _slides_for(matches: list[dict], pack: dict) -> list[dict]:
    sl = [{"kind": "intro", "i": None, "text": pack["intro"]}]
    for i, pm in enumerate(pack["matches"][: len(matches)]):
        sl += [{"kind": "a", "i": i, "text": pm["a"]}, {"kind": "b", "i": i, "text": pm["b"]}, {"kind": "v", "i": i, "text": pm["v"]}]
    sl.append({"kind": "closer", "i": None, "text": pack["closer"]})
    return sl


def _gather_photos(matches: list[dict], pack: dict, work: Path, supplied: list | None) -> list[list[dict]]:
    out: list[list[dict]] = []
    for i, m in enumerate(matches):
        if supplied and i < len(supplied) and supplied[i]:
            out.append(list(supplied[i]))
            continue
        titles = (pack["matches"][i].get("photos") if i < len(pack["matches"]) else None) or []
        got: list[dict] = []
        try:
            if titles:
                got = vphotos.photos_by_title(titles, work / "venues" / f"m{i + 1}", str(m.get("home") or ""),
                                              stadium=(pack["matches"][i].get("stadium") if i < len(pack["matches"]) else None))
            if not got:
                got = vphotos.venue_photos(str(m.get("home") or ""), work / "venues" / f"m{i + 1}", n=2)
        except Exception as exc:  # noqa: BLE001
            log.info("venue photos unavailable for %s: %s", m.get("home"), exc)
        out.append(got)
    return out


def prepare(matches: list[dict], *, assets: Path, work: Path | None = None, voice_clips: list[Path] | None = None,
            pack: dict | None = None, photos: list | None = None, day: str | None = None,
            polish: bool | None = None, extras: dict | None = None) -> Prepared:
    """Do all the slow, shared work once: pack, photos, crests, narration audio (split per slide)."""
    matches = list(matches or [])[:MAX_MATCHES]
    if not matches:
        raise ValueError("no matches to present")
    ff = reel._ffmpeg()
    assets = Path(assets)
    work = Path(work) if work else Path(tempfile.mkdtemp(prefix="pr-breakdown-"))
    for sub in ("audio", "crests", "venues", "slides"):
        (work / sub).mkdir(parents=True, exist_ok=True)
    logo = assets / "logo.png"
    pack = pack or auto_pack(matches, day=day, extras=extras)
    pack["matches"] = pack["matches"][: len(matches)]
    if polish is None:
        import voice_polish as _vp
        polish = _vp.enabled()

    # narration -> one wav per slide
    n = len(matches)
    raw: list[Path] = []
    seed0 = sp.seed_for(day or "", "voice")
    if voice_clips is not None and len(voice_clips) == n + 2:
        r0 = work / "audio" / "raw000.wav"
        _slice_clip(Path(voice_clips[0]), [pack["intro"]], [r0], ff, polish, seed0)
        raw.append(r0)
        for i in range(n):
            pm = pack["matches"][i]
            dests = [work / "audio" / f"raw{1 + 3 * i + k:03d}.wav" for k in range(3)]
            _slice_clip(Path(voice_clips[1 + i]), [pm["a"], pm["b"], pm["v"]], dests, ff, polish, seed0 + 1 + i)
            raw += dests
        rl = work / "audio" / f"raw{len(raw):03d}.wav"
        _slice_clip(Path(voice_clips[-1]), [pack["closer"]], [rl], ff, polish, seed0 + 99)
        raw.append(rl)
    elif voice_clips is not None and len(voice_clips) == 3 * n + 2:
        slide_texts = [sl["text"] for sl in _slides_for(matches, pack)]
        for i, vc in enumerate(voice_clips):
            r = work / "audio" / f"raw{i:03d}.wav"
            _slice_clip(Path(vc), [slide_texts[i]], [r], ff, polish, seed0 + i)
            raw.append(r)
    elif voice_clips is None:
        for i, s in enumerate(_slides_for(matches, pack)):
            r = work / "audio" / f"raw{i:03d}.wav"
            reel.synthesize_speech(s["text"], r)
            raw.append(r)
    else:
        raise ValueError(f"voice_clips must hold {n + 2} (per match) or {3 * n + 2} (per slide) files, got {len(voice_clips)}")

    # fit under the cap: drop trailing matches first (never below MIN_MATCHES), then a tiny tempo-up
    def total_hold(wavs: list[Path]) -> float:
        return sum(reel.frame_hold(reel.hold_seconds(i, reel._probe(w, ff))) for i, w in enumerate(wavs))

    while total_hold(raw) > MAX_SECONDS and n > MIN_MATCHES and voice_clips is None:
        n -= 1
        matches = matches[:n]
        pack["matches"] = pack["matches"][:n]
        raw = raw[: 1 + 3 * n] + [raw[-1]]
    tot = total_hold(raw)
    if tot > MAX_SECONDS:
        tempo = min(MAX_TEMPO, tot / (MAX_SECONDS - 3.0))
        if tempo > MAX_TEMPO - 1e-6 and (tot / MAX_TEMPO) > MAX_SECONDS:
            raise ValueError(f"narration too long: {tot:.0f}s > {MAX_SECONDS:.0f}s even at x{MAX_TEMPO}")
        log.info("tempo x%.3f to fit %.0fs", tempo, MAX_SECONDS)
        for i, r in enumerate(raw):
            t = r.with_suffix(".paced.wav")
            reel._run([ff, "-y", "-i", str(r), "-filter:a", f"atempo={tempo:.4f}", "-ac", "1", "-ar", "44100", str(t)], f"pace {i}")
            t.replace(r)

    slides = _slides_for(matches, pack)
    assert len(slides) == len(raw), (len(slides), len(raw))

    crests = []
    for i, m in enumerate(matches, 1):
        b = m.get("badges") or {}
        crests.append((reel.fetch_badge(b.get("home"), work / "crests" / f"h{i}.png", logo),
                       reel.fetch_badge(b.get("away"), work / "crests" / f"a{i}.png", logo)))
    ph = _gather_photos(matches, pack, work, photos)
    credits = []
    for lst in ph:
        for p in lst[:3]:
            if p.get("credit") and p["credit"] not in credits:
                credits.append(p["credit"])
    return Prepared(matches, pack, slides, raw, work, assets, crests, ph, _day_label(day), credits, ff)


def _still(img: Path, dest: Path, dur: float, ff: str, aspect: str) -> None:
    cw, ch = reel._resolve_size(aspect)
    reel._run([ff, "-y", "-loop", "1", "-framerate", str(reel.FPS), "-t", f"{dur:.3f}", "-i", str(img),
               "-vf", f"scale={cw}:{ch},format=yuv420p", "-r", str(reel.FPS),
               "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "27", "-pix_fmt", "yuv420p",
               "-an", str(dest)], "still")


def render_slides(prep: Prepared, aspect: str = "16:9") -> list[Path]:
    """Draw every slide image for one aspect ratio (no encoding)."""
    work, assets = prep.work, prep.assets
    logo = assets / "logo.png"
    bgs = [assets / "bg_stadium.jpg", assets / "bg_pitch.jpg", assets / "bg_lights.jpg"]
    sd = work / "slides" / aspect.replace(":", "x")
    sd.mkdir(parents=True, exist_ok=True)
    matches, pm = prep.matches, prep.pack["matches"]
    n = len(matches)

    def ph(i: int, k: int) -> dict | None:
        lst = prep.photos[i] if i < len(prep.photos) else []
        return lst[k % len(lst)] if lst else None

    def bg_for(i: int, k: int) -> Path:
        p = ph(i, k)
        return Path(p["path"]) if p else bgs[(i + k) % 3]

    credits_line = ""
    if prep.credits:
        credits_line = "Stadium photos via Wikimedia Commons (CC BY / CC BY-SA / public domain). Photographer credits are in the description."

    prev = reel._ACTIVE_SIZE
    reel._ACTIVE_SIZE = reel._resolve_size(aspect)
    try:
        images: list[Path] = []
        for idx, s in enumerate(prep.slides):
            dest = sd / f"s{idx:03d}.jpg"
            kind, i = s["kind"], s["i"]
            if kind == "intro":
                render_intro(matches, pm, logo, bgs[0], dest, crests=prep.crests, photos=prep.photos, day_text=prep.day_text, aspect=aspect)
            elif kind == "a":
                render_board_a(matches[i], pm[i], i + 1, n, bg_for(i, 0), *prep.crests[i], dest,
                               stadium=(ph(i, 0) or {}).get("stadium", ""), aspect=aspect)
            elif kind == "b":
                render_board_b(matches[i], pm[i], i + 1, n, bg_for(i, 1), *prep.crests[i], dest, photo=ph(i, 1), aspect=aspect)
            elif kind == "v":
                render_verdict(matches[i], pm[i], i + 1, n, bg_for(i, 2), *prep.crests[i], dest, aspect=aspect)
            else:
                render_closer(matches, pm, logo, bgs[2], dest, credits_line=credits_line, aspect=aspect)
            images.append(dest)
        return images
    finally:
        reel._ACTIVE_SIZE = prev


def render(prep: Prepared, outfile: Path, aspect: str = "16:9") -> Path:
    ff, work = prep.ff, prep.work
    tag = aspect.replace(":", "x")
    images = render_slides(prep, aspect)
    wavs, holds = [], []
    for idx, raw in enumerate(prep.wavs):
        hold = reel.frame_hold(reel.hold_seconds(idx, reel._probe(raw, ff)))
        padded = work / "audio" / f"pad{tag}{idx:03d}.wav"
        reel.pad_audio(raw, padded, hold, ff)
        wavs.append(padded)
        holds.append(hold)
    clips = []
    for idx, (img, hold) in enumerate(zip(images, holds)):
        c = work / f"v{tag}{idx:03d}.mp4"
        _still(img, c, hold, ff, aspect)
        clips.append(c)
    lv, la = work / f"v{tag}.txt", work / f"a{tag}.txt"
    lv.write_text("".join(f"file '{c}'\n" for c in clips))
    la.write_text("".join(f"file '{w}'\n" for w in wavs))
    silent, voice = work / f"silent{tag}.mp4", work / f"voice{tag}.wav"
    reel._run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(lv), "-c", "copy", str(silent)], "concat v")
    reel._run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(la), "-c", "copy", str(voice)], "concat a")
    outfile = Path(outfile)
    outfile.parent.mkdir(parents=True, exist_ok=True)
    reel._run([ff, "-y", "-i", str(silent), "-i", str(voice), "-map", "0:v", "-map", "1:a",
               "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(outfile)], "mux")
    log.info("match breakdown built %s [%s] %.1fs %d KB", outfile.name, aspect, sum(holds), outfile.stat().st_size // 1024)
    return outfile


def build_show(matches: list[dict], outfile: Path, *, assets: Path, work: Path | None = None, aspect: str = "16:9",
               voice_clips: list[Path] | None = None, pack: dict | None = None, photos: list | None = None,
               day: str | None = None, polish: bool | None = None, extras: dict | None = None) -> Path:
    return render(prepare(matches, assets=assets, work=work, voice_clips=voice_clips, pack=pack, photos=photos, day=day,
                          polish=polish, extras=extras), outfile, aspect)


def build_show_both(matches: list[dict], out_16x9: Path, out_9x16: Path, *, assets: Path, work: Path | None = None,
                    voice_clips: list[Path] | None = None, pack: dict | None = None, photos: list | None = None,
                    day: str | None = None, polish: bool | None = None, extras: dict | None = None) -> tuple[Path, Path, Prepared]:
    """Both aspect ratios from the SAME narration audio, photos and slides content."""
    prep = prepare(matches, assets=assets, work=work, voice_clips=voice_clips, pack=pack, photos=photos, day=day,
                   polish=polish, extras=extras)
    return render(prep, out_16x9, "16:9"), render(prep, out_9x16, "9:16"), prep


def credits_text(prep: Prepared) -> str:
    """Photo credits for the video description (CC BY / BY-SA need the author named; the link gives the full record)."""
    import urllib.parse
    lines = []
    for m, lst in zip(prep.matches, prep.photos):
        for p in lst[:3]:
            title = str(p.get("title") or "")
            url = ("https://commons.wikimedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"), safe=":/()%,'-.")) if title else ""
            lines.append(f"{p.get('stadium') or m.get('home')}: {p['credit']}" + (f"\n  {url}" if url else ""))
    return ("Photo credits (Wikimedia Commons):\n" + "\n".join(dict.fromkeys(lines))) if lines else ""
