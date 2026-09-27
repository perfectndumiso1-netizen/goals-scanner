"""Squad market values (Transfermarkt public API, weekly refresh).

`tmapi-alpha.transfermarkt.technology` serves club market values without the bot wall of the website:
  competition/{code}/table  -> club ids of the competition
  clubs?ids[]=..            -> name, squad size, average age, current market value (EUR)
The values are matched to our team names per division and cached in STATE/data/squads.json.
Display / context only — they do not enter the model.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

import requests

import sporty

log = logging.getLogger("scanner")
BASE = "https://tmapi-alpha.transfermarkt.technology"
UA = sporty.UA if hasattr(sporty, "UA") else "Mozilla/5.0"
MAX_AGE_DAYS = 6

# football-data division codes -> Transfermarkt competition codes
TM_CODES = {
    "E0": "GB1", "E1": "GB2", "E2": "GB3", "E3": "GB4", "EC": "CNAT",
    "SC0": "SC1", "SC1": "SC2", "SC2": "SC3", "SC3": "SC4",
    "D1": "L1", "D2": "L2", "I1": "IT1", "I2": "IT2", "SP1": "ES1", "SP2": "ES2",
    "F1": "FR1", "F2": "FR2", "N1": "NL1", "B1": "BE1", "P1": "PO1", "T1": "TR1", "G1": "GR1",
    # extra leagues (div = "CODE:League")
    "ARG": "ARG1", "AUT": "A1", "BRA": "BRA1", "CHN": "CSL", "DNK": "DK1", "FIN": "FI1", "IRL": "IR1", "JPN": "JAP1",
    "MEX": "MEX1", "NOR": "NO1", "POL": "PL1", "ROU": "RO1", "RUS": "RU1", "SWE": "SE1", "SWZ": "C1", "USA": "MLS1",
}


def tm_code(div: str) -> str | None:
    if not div or div.startswith("LS:"):
        return None
    return TM_CODES.get(div) or TM_CODES.get(div.split(":", 1)[0])


def _get(url: str) -> dict | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=20)
        if r.status_code != 200:
            return None
        j = r.json()
        return j.get("data") if isinstance(j, dict) and j.get("success") else None
    except (requests.RequestException, ValueError):
        return None


def fetch_competition(code: str) -> list[dict]:
    """[{id, name, value, avg_age, size, crest}] for every club of a competition."""
    table = _get(f"{BASE}/competition/{code}/table")
    if not table:
        return []
    ids = []
    for t in table.get("tables") or []:
        for c in t.get("clubs") or []:
            if c.get("clubId"):
                ids.append(str(c["clubId"]))
    out = []
    for i in range(0, len(ids), 25):
        batch = ids[i:i + 25]
        data = _get(f"{BASE}/clubs?" + "&".join(f"ids[]={x}" for x in batch))
        for c in data or []:
            sd = c.get("squadDetails") or {}
            mv = (sd.get("currentMarketValue") or {}).get("value")
            out.append({"id": str(c.get("id")), "name": c.get("name") or "", "short": (c.get("baseDetails") or {}).get("shortName") or "",
                        "value": float(mv) if mv is not None else None, "avg_age": sd.get("averageAge"),
                        "size": sd.get("squadSize"), "crest": c.get("crestUrl")})
    return out


class Squads:
    def __init__(self, path: Path):
        self.path = path
        try:
            self.data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, ValueError):
            self.data = {}
        self.data.setdefault("leagues", {})
        self.data.setdefault("map", {})
        self._dirty = False

    def stale(self, now: datetime) -> bool:
        f = self.data.get("fetched")
        if not f:
            return True
        try:
            return (now.replace(tzinfo=None) - datetime.strptime(f, "%Y-%m-%d %H:%M")).days >= MAX_AGE_DAYS
        except ValueError:
            return True

    def refresh(self, divs: set[str], now: datetime, budget_s: float = 90.0, force: bool = False) -> int:
        """Re-fetch the competitions of `divs` when the cache is older than MAX_AGE_DAYS."""
        if not force and not self.stale(now):
            return 0
        t0 = time.time()
        codes = {}
        for d in divs:
            c = tm_code(d)
            if c:
                codes.setdefault(c, d)
        n = 0
        for code in sorted(codes):
            if time.time() - t0 > budget_s:
                break
            clubs = fetch_competition(code)
            if clubs:
                self.data["leagues"][code] = {"clubs": clubs, "fetched": now.strftime("%Y-%m-%d %H:%M")}
                n += 1
        if n:
            self.data["fetched"] = now.strftime("%Y-%m-%d %H:%M")
            self.data["map"] = {}          # names are re-matched against the fresh lists
            self._dirty = True
        log.info("Squad values: %d competition(s) refreshed in %.0fs", n, time.time() - t0)
        return n

    def lookup(self, div: str, team: str) -> dict | None:
        """{value, avg_age, size, name} of a team, matched by name inside its competition."""
        code = tm_code(div)
        if not code or code not in self.data["leagues"]:
            return None
        key = f"{code}|{team}"
        m = self.data["map"].get(key)
        clubs = self.data["leagues"][code]["clubs"]
        if m is None:
            best, best_s = None, 0.0
            for c in clubs:
                s = max(sporty.similarity(team, c["name"]), sporty.similarity(team, c.get("short") or c["name"]))
                if s > best_s:
                    best, best_s = c, s
            m = best["id"] if best is not None and best_s >= 0.72 else ""
            self.data["map"][key] = m
            self._dirty = True
        if not m:
            return None
        for c in clubs:
            if c["id"] == m:
                return {"value": c["value"], "avg_age": c["avg_age"], "size": c["size"], "name": c["name"], "tm_id": c["id"]}
        return None

    def save(self) -> None:
        if self._dirty:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            self._dirty = False


def fmt_value(v: float | None) -> str:
    if v is None:
        return "–"
    if v >= 1e9:
        return f"€{v / 1e9:.2f}bn"
    if v >= 1e6:
        return f"€{v / 1e6:.1f}M"
    return f"€{v / 1e3:.0f}K"
