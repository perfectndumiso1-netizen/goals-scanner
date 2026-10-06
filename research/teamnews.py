"""Team news -> facts, built from the news cache the scanner already maintains (no second request per team).

`news.py` already does the hard parts: Google-News per team and per fixture, a reputable-source gate, keyword
scoring, a TTL cache and a per-run request budget.  This module only *reads* that feed and turns headlines into
attributed facts:

  * an item is stored exactly as published (headline, outlet, link, publication time) — never paraphrased into a
    claim we cannot point at;
  * a headline that explicitly reports a player/team availability situation is tagged `team_out` / `team_in` so
    that conflicting reports can be detected, but the tag is a **report**, not a verified squad fact — the fact's
    confidence stays `press` and `verified` stays False;
  * availability reports therefore never adjust a probability on their own; they are shown, and they gate quality.

The injury/suspension signal here is text, and there is no historical archive of it, so per the audit it carries
zero weight until forward evidence exists.  Nothing in this module can move a probability.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from .facts import Fact, make_fact

log = logging.getLogger("research.teamnews")

MAX_PER_SIDE = 3

OUT_RE = re.compile(r"\b(out|injured|injury|injuries|sidelined|suspended|suspend(?:ed|ion)?|banned|ban|ruled ?out|"
                    r"miss(?:es|ing)?|doubt(?:ful|s)?|unavailable|withdraws?|withdrawn|fracture[ds]?|"
                    r"hamstring|ankle|knee|groin|calf|illness|surgery|operation|tear[s]?|tear|ruled out)\b", re.I)
IN_RE = re.compile(r"\b(returns?|returned|back in (?:the )?(?:squad|training|contention)|fit again|available|"
                   r"cleared to play|recalled|recovered|reinforcements|signs?|signing|joins?|debut|"
                   r"back from (?:injury|suspension|loan))\b", re.I)
NEGATION = re.compile(r"\b(no|not|denies|denied|ruled out the|dismisses|quashes|clears?)\b", re.I)
# Headlines that are not news about a team: live-score pages, fixture listings, betting/odds/prediction pieces.
# They carry no information we could attribute, and the specification forbids using another site's prediction —
# so they are dropped rather than stored as "facts".
JUNK = re.compile(r"\b(live ?score|live ?stream|how to watch|where to watch|tv channel|kick-?off time|"
                  r"prediction|predictions|betting|bet ?tips|odds|accumulator|acca tips|fantasy|"
                  r"player ratings|match preview live|line ?ups? (?:confirmed|predicted)|highlights|recap)\b", re.I)


def _when(item: dict) -> datetime | None:
    try:
        return datetime.strptime(str(item.get("when") or ""), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _flag(title: str) -> tuple[str, str]:
    """(kind, evidence) — 'team_out' | 'team_in' | '' for an availability report, with the matched words."""
    m_out, m_in = OUT_RE.search(title), IN_RE.search(title)
    if m_out and not m_in:
        return "team_out", m_out.group(0)
    if m_in and not m_out:
        return "team_in", m_in.group(0)
    if m_out and m_in:
        # e.g. "X out but Y returns" — a mixed report is not a conflict, it is simply not a binary flag
        return "", f"{m_out.group(0)}/{m_in.group(0)}"
    return "", ""


def facts_for(row, now: datetime, limit: int = MAX_PER_SIDE, fetched: dict | None = None,
              looked_up: bool = True) -> list[Fact]:
    """Facts for both teams.

    `fetched` (optional) is {'home': [...], 'away': [...]} straight from the shared news cache — the engine
    passes it so a team is looked up once per run and the same cache serves the app's News tab.  Without it the
    scanner's own per-fixture block (`row.news`) is used, which is what the app path and the tests use.
    `looked_up=False` means the fixture is outside the news window: no lookup happened, and the fact says so
    rather than implying the team has no news.
    """
    news = fetched if fetched is not None else (getattr(row, "news", None) or {})
    out: list[Fact] = []
    for side in ("home", "away"):
        team = str(row.fx[side])
        items = news.get(side) or []
        if not items:
            text = ("N/A — no reputable recent headline found for this team" if looked_up else
                    "N/A — not looked up this run (fixture outside the news window)")
            out.append(make_fact("team_news", team, text,
                                 "news cache (Google News, reputable outlets only)", now, confidence="provider",
                                 kind="news_unavailable", value={"looked_up": bool(looked_up)}))
            continue
        picked: list[tuple[dict, str, str]] = []
        for it in items:
            title = str(it.get("title") or "")
            if JUNK.search(title):
                continue                      # fixture listings / betting pages are not team news
            kind, ev = _flag(title)
            picked.append((it, kind, ev))
        # availability reports first, then the freshest items
        picked.sort(key=lambda t: (t[1] != "", str(t[0].get("when") or "")), reverse=True)
        for it, kind, ev in picked[:limit]:
            title = str(it.get("title") or "").strip()
            if not title:
                continue
            when = _when(it)
            text = f"reported: “{title}”"
            if kind:
                text += f" — availability signal ({ev}): unverified, shown only"
            out.append(make_fact(
                "team_news", team, text, str(it.get("source") or "news (unattributed)"), now,
                url=str(it.get("link") or ""), effective_at=when, confidence="press",
                verified=False,      # a headline is never a first-party confirmation
                kind=kind or "report",
                value={"outlet": it.get("source"), "bucket": it.get("bucket"), "flag": kind, "evidence": ev}))
        if not any(f.subject == team for f in out):
            out.append(make_fact("team_news", team, "N/A — no reputable recent headline found for this team",
                                 "news cache (Google News, reputable outlets only)", now, confidence="provider",
                                 kind="news_unavailable", value={}))
    return out


def availability_conflict(facts: list[Fact]) -> list[dict]:
    """Unresolved out/in reports about the same team — recorded as a conflict, never averaged away."""
    conflicts: list[dict] = []
    by_team: dict[str, list[Fact]] = {}
    for f in facts:
        if f.category == "team_news" and f.kind in ("team_out", "team_in"):
            by_team.setdefault(f.subject, []).append(f)
    for team, group in by_team.items():
        outs = [f for f in group if f.kind == "team_out"]
        ins = [f for f in group if f.kind == "team_in"]
        if outs and ins:
            a, b = outs[0], ins[0]
            conflicts.append({"subject": team, "source_a": a.source, "source_b": b.source, "conflict": True,
                              "resolution": "unresolved (both are press reports; no first-party confirmation)",
                              "impact": "no adjustment", "text_a": a.text, "text_b": b.text, "keep": ""})
    return conflicts
