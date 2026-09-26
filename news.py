"""Recent headlines per team from Google News RSS (no sign-up). Context only — never used by the model."""
from __future__ import annotations

import email.utils
import html
import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import requests

log = logging.getLogger("news")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (compatible; GoalsScanner/3.0)"})
KEYWORDS = re.compile(r"injur|out for|ruled out|doubt|suspend|ban|return|fitness|team news|line-?up|squad|"
                      r"sack|appoint|manager|boss|preview|predicted|absent|miss|blow|boost|sidelined|knock",
                      re.IGNORECASE)


def _country_edition(country: str) -> tuple[str, str]:
    c = (country or "").lower()
    if c in ("england", "scotland", "wales", "ireland"):
        return "en-GB", "GB"
    if c == "usa":
        return "en-US", "US"
    return "en-ZA", "ZA"


def core_name(name: str) -> str:
    """'York City FC' -> 'York City'; 'AFC Bournemouth' -> 'AFC Bournemouth' (single core word keeps its suffix)."""
    toks = name.replace(".", "").split()
    core = [t for t in toks if t.upper() not in ("FC", "AFC", "SC", "CF", "AC", "BK", "IF", "FK", "SK", "KV", "CD", "UD", "SD")]
    return " ".join(core) if len(core) >= 2 else name


def team_headlines(team: str, country: str = "", days: int = 7, limit: int = 4, query_hint: str = "football",
                   long_name: str | None = None) -> list[dict]:
    """Up to `limit` recent headlines mentioning the team. Prefers injury/team-news style items."""
    hl, gl = _country_edition(country)
    name = core_name(long_name) if long_name else team
    q = urllib.parse.quote(f'"{name}" {query_hint}' if len(name.split()) >= 2 else f'"{name}" {query_hint} club')
    url = f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{hl.split('-')[0]}"
    try:
        r = SESSION.get(url, timeout=12)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
    except (requests.RequestException, ET.ParseError) as exc:
        log.info("news failed for %s: %s", team, exc)
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    items = []
    for it in root.findall(".//item"):
        title = html.unescape(it.findtext("title") or "").strip()
        pub = it.findtext("pubDate") or ""
        try:
            when = email.utils.parsedate_to_datetime(pub)
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            when = None
        if when is not None and when < cutoff:
            continue
        src = it.find("source")
        source = (src.text if src is not None else "") or ""
        if source and title.endswith(" - " + source):
            title = title[: -len(source) - 3].strip()
        mentions = name.lower() in title.lower() or team.lower() in title.lower()
        items.append({"title": title, "source": source, "when": when, "link": it.findtext("link") or "",
                      "score": (2 if KEYWORDS.search(title) else 0) + (1 if when and when > cutoff + timedelta(days=4) else 0)
                      + (3 if mentions else 0)})
    items.sort(key=lambda x: (-x["score"], -(x["when"].timestamp() if x["when"] else 0)))
    seen, out = set(), []
    for x in items:
        key = x["title"].lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
        if len(out) >= limit:
            break
    return out


def headlines_for_matches(pairs: list[tuple], limit: int = 4) -> dict[str, list[dict]]:
    """pairs = (home, away, country[, home_long, away_long]). Returns team -> headlines (each team fetched once)."""
    out: dict[str, list[dict]] = {}
    for pair in pairs:
        home, away, country = pair[:3]
        longs = pair[3:5] if len(pair) >= 5 else (None, None)
        for team, long_name in zip((home, away), longs):
            if team not in out:
                out[team] = team_headlines(team, country, limit=limit, long_name=long_name)
    return out
