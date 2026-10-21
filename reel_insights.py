"""Evidence for the shortlist video slides — taken straight from the app's own fixture detail.

The voice is gone (2026-10-21), so a slide can no longer rely on someone saying the reasoning. Everything the
viewer needs to judge a pick has to be on the screen, and it has to change often enough that nothing sits still:
each match is now three short slides instead of one long one.

  THE PICK      the selection, its price, and a bar chart of every market this match offers that the video covers —
                the picked market is always the tallest bar
  WHY IT'S HERE the reasons, this fixture's trends, both teams' league standing and their home/away splits
  THE RECORD    head to head, and both teams' last five results with scores

Nothing here invents a number. Every value comes from `data/app/fx/<key>.json` (the same file the match page reads)
or `data/app/leagues/<slug>.json` (the same table the league page shows). Anything missing is simply left off the
slide, and a slide with nothing to show is skipped rather than padded.

The video only carries Over 1.5 total goals, team goals, corners and bookings (`shortlist_reel.is_reel_market`), so
the chart is built from that same family: the pick is the highest model probability **among the markets the video
covers**, which is what makes it the top bar on the chart rather than a claim we have to dress up.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path

log = logging.getLogger("scanner")

CHART_ROWS = 6                 # bars on THE PICK slide
TREND_LINES = 3                # trends on the evidence slide
RECENT_ROWS = 5                # results per team on the record slide
H2H_ROWS = 5                   # meetings on the record slide


# ----------------------------------------------------------------------------- helpers

def norm(name) -> str:
    """Casefold + strip accents, so Livescore and app spellings still match."""
    s = unicodedata.normalize("NFKD", str(name or ""))
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if not unicodedata.combining(c)).lower()).strip()


def _f(v) -> float | None:
    try:
        out = float(v)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def _pct(p: float | None, digits: int = 0) -> str:
    return "N/A" if p is None else f"{100 * p:.{digits}f}%"


def chance_phrase(p: float | None) -> str:
    """Plain words for a probability — the same ladder the app and the old narration used."""
    if p is None:
        return "unknown"
    if p >= 0.95:
        return "better than nine in ten"
    if p >= 0.85:
        return "around nine in ten"
    if p >= 0.75:
        return "about three in four"
    if p >= 0.65:
        return "about two in three"
    if p >= 0.55:
        return "better than half"
    return "around half"


def _line(code: str) -> float:
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    return int(digits) / 10.0 if digits else 0.0


def short_market(sel: str, home: str = "Home", away: str = "Away") -> str:
    """A market name that fits in a chart label: 'Over 1.5 goals', 'Chiefs to score', 'Over 9.5 corners'."""
    sel = str(sel or "").upper()
    m = re.match(r"^O(\d+)$", sel)
    if m:
        return f"Over {_line(sel):.1f} goals"
    m = re.match(r"^([HA])O(\d+)$", sel)
    if m:
        team = home if m.group(1) == "H" else away
        n = _line(sel)
        if n <= 0.5:
            return f"{team} to score"
        return f"{team} {int(n) + 1}+ goals"
    m = re.match(r"^C([HA])?O(\d+)$", sel)
    if m:
        who = "" if not m.group(1) else (f"{home} " if m.group(1) == "H" else f"{away} ")
        n = _line(sel)
        return f"{who}{int(n) + 1}+ corners" if who else f"Over {n:.1f} corners"
    m = re.match(r"^K([HA])?O(\d+)$", sel)
    if m:
        who = "" if not m.group(1) else (f"{home} " if m.group(1) == "H" else f"{away} ")
        n = _line(sel)
        return f"{who}{int(n) + 1}+ cards" if who else f"Over {n:.1f} cards"
    return str(sel or "Selection")


# ----------------------------------------------------------------------------- markets

def _eligible(pick: dict) -> bool:
    from shortlist_reel import is_reel_market       # local import: shortlist_reel imports this module
    return bool(is_reel_market(pick))


def market_rows(detail: dict | None, pick: dict) -> list[dict]:
    """Every market the video covers for this match, highest model probability first.

    `detail["sels"]` is [[sel, p, p_model, p_sb, odds, diff, diff_pp, ev], …] from appdata. A row is kept when the
    video is allowed to show that market and the model has a probability for it. If the fixture detail is missing,
    the pick itself is the only row — the chart still draws, it is just short.
    """
    home, away = str(pick.get("home") or "Home"), str(pick.get("away") or "Away")
    rows: dict[str, dict] = {}
    for s in ((detail or {}).get("sels") or []):
        if not isinstance(s, (list, tuple)) or not s:
            continue
        cand = {"sel": str(s[0]), "home": home, "away": away}
        if not _eligible(cand):
            continue
        pv = _f(s[1] if len(s) > 1 else None)
        if pv is None or not (0.0 < pv < 1.0):
            continue
        odds = _f(s[4]) if len(s) > 4 else None
        p_sb = _f(s[3]) if len(s) > 3 else None
        rows[cand["sel"]] = {"sel": cand["sel"], "label": short_market(cand["sel"], home, away),
                             "p": pv, "odds": odds, "p_sb": p_sb,
                             "picked": cand["sel"] == str(pick.get("sel") or "")}
    own = str(pick.get("sel") or "")
    if own and own not in rows:                      # the pick must always be on its own chart
        pv = _f(pick.get("p"))
        if pv is not None:
            rows[own] = {"sel": own, "label": short_market(own, home, away), "p": pv,
                         "odds": _f(pick.get("odds")), "p_sb": _f(pick.get("p_sb")),
                         "picked": True}
    out = sorted(rows.values(), key=lambda r: (-r["p"], not r["picked"]))
    return out


def chosen_market(detail: dict | None, pick: dict) -> dict | None:
    """The market the video should feature: the highest model probability of the ones the video covers.

    The user rule is that the highlighted bar must be the highest on the chart. Rather than draw a chart that
    quietly disagrees with the pick, the video takes the strongest market the fixture actually offers — which is
    what the shortlist board is trying to do anyway. Returns only the fields that identify the market, so the
    caller can overlay them on the pick without disturbing anything else.
    """
    rows = market_rows(detail, pick)
    if not rows:
        return None
    best = rows[0]
    return {"sel": best["sel"], "label": best["label"], "p": best["p"],
            "odds": best["odds"] if best["odds"] is not None else pick.get("odds"),
            "p_sb": best["p_sb"]}


def chart_rows(detail: dict | None, pick: dict, limit: int = CHART_ROWS) -> list[dict]:
    """The bars, top-first, with the picked market marked. Always includes the pick."""
    rows = market_rows(detail, pick)
    if not rows:
        return []
    top = rows[:limit]
    if not any(r["picked"] for r in top):
        mine = next((r for r in rows if r["picked"]), None)
        if mine:
            top = (top[: limit - 1] + [mine])
    return sorted(top, key=lambda r: (-r["p"], not r["picked"]))


# ----------------------------------------------------------------------------- standings

def league_tables(leagues_dir: Path | None) -> dict:
    """{(normalised country, normalised league): table rows}, read from the app's league files.

    The league page already publishes the current-season table (`leagues.compute_table`), so the video shows the
    same numbers the app shows. Only the leagues the app actually has a table for are loaded — everything else is
    simply absent and the slide does without a standing.
    """
    out: dict = {}
    if not leagues_dir:
        return out
    d = Path(leagues_dir)
    try:
        index = json.loads((d / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    rows = index.get("leagues") if isinstance(index, dict) else index   # index.json = {count, leagues: [...]}
    for entry in rows if isinstance(rows, list) else []:
        if not entry.get("table") or not entry.get("slug"):
            continue
        try:
            detail = json.loads((d / entry["slug"]).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        table = detail.get("table") or []
        if table:
            out[(norm(entry.get("country")), norm(entry.get("league")))] = table
    return out


def _lookup_table(tables: dict, pick: dict) -> list[dict] | None:
    if not tables:
        return None
    country, league = norm(pick.get("country")), norm(pick.get("league"))
    if (country, league) in tables:
        return tables[(country, league)]
    for (c, lg), table in tables.items():
        if lg == league and (not c or not country or c == country):
            return table
    if league:
        for (c, lg), table in tables.items():
            if lg and (lg in league or league in lg):
                return table
    return None


def standing(tables: dict, pick: dict) -> dict | None:
    """{'league':…, 'teams':[…], 'size':n} for both clubs, or None when the table does not list them."""
    table = _lookup_table(tables or {}, pick)
    if not table:
        return None
    want = {norm(pick.get("home")): "home", norm(pick.get("away")): "away"}
    found = {}
    for row in table:
        side = want.get(norm(row.get("team")))
        if side:
            found[side] = row
    if len(found) < 2:
        return None
    return {"league": str(pick.get("league") or ""), "size": len(table), "teams": found}


def standing_line(row: dict | None, size: int) -> str:
    if not row:
        return ""
    pos = row.get("pos")
    suffix = "th" if 10 <= int(pos or 0) % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(int(pos or 0) % 10, "th")
    return (f"{pos}{suffix} of {size} · {row.get('pts', 0)} pts · "
            f"{row.get('p', 0)} played · {str(row.get('form') or '').upper()}")


# ----------------------------------------------------------------------------- trends / records

def trend_lines(detail: dict | None, limit: int = TREND_LINES) -> list[str]:
    """This fixture's own trend statements, strongest first, deduplicated and short enough for the slide."""
    tr = (detail or {}).get("trends") or {}
    groups = [tr.get("match") or [], (tr.get("home") or {}).get("all") or [],
              (tr.get("away") or {}).get("all") or [], tr.get("h2h") or []]
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for item in group:
            text = str((item or {}).get("t") or "").strip()
            if not text or len(text) > 110:
                continue
            key = norm(text)
            if key in seen:
                continue
            seen.add(key)
            out.append(text[0].upper() + text[1:])
            if len(out) >= limit:
                return out
    return out


def recent_rows(detail: dict | None, side: str, limit: int = RECENT_ROWS) -> list[dict]:
    """A team's last matches with the score and W/D/L, newest first (appdata `teams.<side>.last5`)."""
    team = ((detail or {}).get("teams") or {}).get(side) or {}
    out = []
    for m in (team.get("last5") or [])[:limit]:
        gf, ga = m.get("gf"), m.get("ga")
        if gf is None or ga is None:
            continue
        res = "W" if gf > ga else ("L" if gf < ga else "D")
        out.append({"date": str(m.get("date") or "")[:10], "opp": str(m.get("opp") or ""),
                    "venue": str(m.get("venue") or ""), "gf": int(gf), "ga": int(ga), "res": res})
    return out


def h2h_summary(detail: dict | None, pick: dict, limit: int = H2H_ROWS) -> dict | None:
    """Head-to-head meetings plus the W–D–L record from the home team's point of view."""
    rows = []
    for m in ((detail or {}).get("h2h") or [])[:limit]:
        hg, ag = m.get("hg"), m.get("ag")
        if hg is None or ag is None:
            continue
        home_is_us = norm(m.get("home")) == norm(pick.get("home"))
        gf, ga = (hg, ag) if home_is_us else (ag, hg)
        rows.append({"date": str(m.get("date") or "")[:10], "home": str(m.get("home") or ""),
                     "away": str(m.get("away") or ""), "hg": int(hg), "ag": int(ag),
                     "res": "W" if gf > ga else ("L" if gf < ga else "D")})
    if not rows:
        return None
    w = sum(1 for r in rows if r["res"] == "W")
    d = sum(1 for r in rows if r["res"] == "D")
    goals = sum(r["hg"] + r["ag"] for r in rows) / len(rows)
    return {"rows": rows, "w": w, "d": d, "l": len(rows) - w - d, "avg_goals": goals,
            "line": f"{w}W · {d}D · {len(rows) - w - d}L in the last {len(rows)} meetings · {goals:.1f} goals a game"}


# ----------------------------------------------------------------------------- reasons

def reasons(pick: dict, detail: dict | None, table: dict | None) -> list[str]:
    """Three or four short lines on why this selection is on the list — each one traceable to a number."""
    out: list[str] = []
    pv = _f(pick.get("p"))
    if pv:
        out.append(f"Model gives it {_pct(pv)} — {chance_phrase(pv)}")
    xg = None
    d_xg = ((detail or {}).get("xg") or {})
    if isinstance(d_xg, dict):                      # detail shape {"home":..,"away":..,"total":..}
        xg = (_f(d_xg.get("home")), _f(d_xg.get("away")))
    elif isinstance(d_xg, list) and len(d_xg) == 2:  # older shape [home, away]
        xg = (_f(d_xg[0]), _f(d_xg[1]))
    if xg and None not in xg:
        out.append(f"Projected goals {xg[0]:.2f} – {xg[1]:.2f}")
    market = str(pick.get("market") or "").lower()
    teams = (detail or {}).get("teams") or {}
    prof = (teams.get("home") or {}) if market in ("goals", "team", "") else {}
    rate = _f((prof or {}).get("o15")) if isinstance(prof, dict) else None
    if rate is not None:
        out.append(f"Over 1.5 has landed in {_pct(rate)} of {pick.get('home')}’s matches")
    if table:
        row = (table.get("teams") or {}).get("home")
        line = standing_line(row, table.get("size") or 0)
        if line:
            out.append(f"{pick.get('home')}: {line.split(' · ')[0]} in {table.get('league') or 'the league'}")
    psb = _f(pick.get("p_sb")) or _f(pick.get("p_market"))
    if pv and psb:
        gap = 100 * (pv - psb)
        if abs(gap) >= 1.0:
            out.append(f"Model sits {gap:+.1f} points {'above' if gap > 0 else 'below'} the market price")
    return out[:4]


def evidence_lines(detail: dict | None, pick: dict, table: dict | None) -> dict:
    """Everything the evidence and record slides need, gathered once."""
    return {
        "reasons": reasons(pick, detail, table),
        "trends": trend_lines(detail),
        "table": table,
        "home_recent": recent_rows(detail, "home"),
        "away_recent": recent_rows(detail, "away"),
        "h2h": h2h_summary(detail, pick),
    }


def slide_plan(pick: dict, detail: dict | None, table: dict | None) -> list[str]:
    """Which slides this match earns. A slide with nothing to show is skipped, never left empty."""
    ev = evidence_lines(detail, pick, table)
    plan = ["pick"]
    if ev["reasons"] or ev["trends"] or table:
        plan.append("evidence")
    if ev["h2h"] or ev["home_recent"] or ev["away_recent"]:
        plan.append("record")
    return plan
