"""Recent headlines per team from Google News RSS (no sign-up). Context only — never used by the model."""
from __future__ import annotations

import email.utils
import html
import json
import logging
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

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


def fixture_headlines(home: str, away: str, country: str = "", days: int = 7, limit: int = 4) -> list[dict]:
    """Headlines about the fixture itself (previews, line-ups, match news): both team names in the query."""
    hl, gl = _country_edition(country)
    q = urllib.parse.quote(f'"{core_name(home)}" "{core_name(away)}"')
    url = f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{hl.split('-')[0]}"
    try:
        r = SESSION.get(url, timeout=12)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
    except (requests.RequestException, ET.ParseError) as exc:
        log.info("fixture news failed for %s v %s: %s", home, away, exc)
        return []
    items = _parse_items(root, days, limit, (home, away))
    return items


def _parse_items(root, days: int, limit: int, names: tuple[str, ...]) -> list[dict]:
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
        mentions = any(n.lower() in title.lower() for n in names if n)
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


def _ser(item: dict) -> dict:
    """JSON-safe item with a freshness bucket (24h / 3d / 7d) for the app's News tab."""
    when = item.get("when")
    hours = (datetime.now(timezone.utc) - when).total_seconds() / 3600 if when is not None else None
    bucket = "24h" if hours is not None and hours <= 24 else ("3d" if hours is not None and hours <= 72 else "7d")
    return {"title": item.get("title"), "source": item.get("source"),
            "when": when.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M") if when is not None else None,
            "bucket": bucket, "link": item.get("link")}


class Cache:
    """On-disk TTL cache for headline queries (news is context only — never a model input).

    Keeps request volume flat across the half-hourly runs: each distinct query is fetched at most
    once per TTL; over the per-run budget the cache is served even when stale (with a flag)."""

    def __init__(self, path: Path, ttl_hours: float = 6.0):
        self.path = Path(path)
        self.ttl = ttl_hours * 3600
        self.data: dict = {}
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}
        self.requests = 0

    def items(self, key: str, fetch_fn, budget: list[int]) -> tuple[list[dict], str]:
        rec = self.data.get(key)
        fresh = rec and (time.time() - rec.get("ts", 0)) < self.ttl
        if fresh:
            return rec["items"], "cached"
        if budget and budget[0] <= 0:
            return (rec["items"] if rec else []), "stale"
        if budget:
            budget[0] -= 1
        self.requests += 1
        try:
            raw = fetch_fn() or []
        except Exception as exc:  # noqa: BLE001 — one failed query must never kill the scan
            log.info("news fetch failed for %s: %s", key, exc)
            # keep whatever was cached before (stale) so the next run can retry
            return (rec["items"] if rec else []), "stale"
        items = [_ser(x) for x in raw]
        self.data[key] = {"ts": time.time(), "items": items}
        return items, "fetched"

    def save(self) -> None:
        try:
            cut = time.time() - 3 * self.ttl
            self.data = {k: v for k, v in self.data.items() if v.get("ts", 0) > cut}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            log.info("news cache: %d request(s) this run, %d quer(ies) cached", self.requests, len(self.data))
        except OSError as exc:
            log.warning("news cache save failed: %s", exc)
