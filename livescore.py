"""Live scores from Livescore.com's public JSON (the feed its own website uses). Unofficial, no key.
Used only to *follow* chosen matches (parlay legs, shortlist picks): scores, minute, scorers, cards.
Nothing here feeds the model. Fails soft: every function returns an empty result on any error."""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timedelta

import pandas as pd
import requests

import sporty  # name normalisation / similarity (same rules as the Sportybet matcher)

log = logging.getLogger("livescore")

BASE = "https://prod-public-api.livescore.com/v1/api/app"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0 Safari/537.36")
TIMEOUT = 20
INCIDENT_TYPES = {36: "goal", 37: "own_goal", 39: "penalty", 40: "missed_penalty", 43: "yellow",
                  44: "second_yellow", 45: "red", 63: "sub_off", 64: "sub_on"}
FINISHED = {"FT", "AET", "AP", "Postp.", "Canc.", "Aband.", "Awarded"}


def _get(url: str, quiet: bool = False) -> dict | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
        (log.debug if quiet else log.warning)("Livescore HTTP %s for %s", r.status_code, url[:100])
    except (requests.RequestException, ValueError) as exc:
        log.warning("Livescore request failed: %s", exc)
    return None


def fetch_day(day: datetime, tz_offset_hours: int = 2) -> list[dict]:
    """Every football match on `day` (dates and kick-offs in the given UTC offset)."""
    d = _get(f"{BASE}/date/soccer/{day:%Y%m%d}/{int(tz_offset_hours)}?MD=1")
    out = []
    for st in (d or {}).get("Stages", []):
        for e in st.get("Events", []):
            try:
                ko = datetime.strptime(str(e["Esd"]), "%Y%m%d%H%M%S")
                out.append({
                    "eid": str(e["Eid"]), "country": st.get("Cnm", ""), "league": st.get("Snm", ""),
                    "home": e["T1"][0]["Nm"], "away": e["T2"][0]["Nm"], "kickoff": ko,
                    "status": e.get("Eps", ""), "hg": _int(e.get("Tr1")), "ag": _int(e.get("Tr2")),
                    "ht": (_int(e.get("Trh1")), _int(e.get("Trh2"))),
                    "home_img": e["T1"][0].get("Img") or None, "away_img": e["T2"][0].get("Img") or None,
                    "ccd": st.get("Ccd") or None,
                })
            except (KeyError, IndexError, ValueError, TypeError):
                continue
    return out


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def match_fixtures(fixtures: pd.DataFrame, now: datetime, tz_offset_hours: int = 2,
                   min_sim: float = 0.72, tol_min: int = 20, events: list[dict] | None = None) -> dict:
    """{fixture index: livescore event dict} for fixtures in the scan window (today + tomorrow)."""
    if fixtures is None or fixtures.empty:
        return {}
    if events is None:
        days = sorted({d.date() for d in fixtures["kickoff"]})
        events = []
        for day in days[:3]:
            events += fetch_day(datetime(day.year, day.month, day.day), tz_offset_hours)
    if not events:
        return {}
    out = {}
    for idx, fx in fixtures.iterrows():
        ko = fx["kickoff"].replace(tzinfo=None)
        best, best_s = None, 0.0
        for e in events:
            if abs((e["kickoff"] - ko).total_seconds()) > tol_min * 60:
                continue
            s = min(sporty.similarity(fx["home"], e["home"]), sporty.similarity(fx["away"], e["away"]))
            if s > best_s:
                best, best_s = e, s
        if best is not None and best_s >= min_sim:
            out[idx] = best
    log.info("Livescore: matched %d of %d fixtures", len(out), len(fixtures))
    return out


def live_status(eids: set[str], now: datetime, tz_offset_hours: int = 2) -> dict:
    """Current status for the given event ids: {eid: {status, hg, ag, ht, minute_text}} (today ± 1 day)."""
    want = {str(e) for e in eids}
    out = {}
    for delta in (-1, 0, 1):
        day = now + timedelta(days=delta)
        for e in fetch_day(day, tz_offset_hours):
            if e["eid"] in want:
                out[e["eid"]] = e
    return out


def incidents(eid: str) -> list[dict]:
    """Goals / cards for one match: [{minute, team 'H'/'A', type, player, score:[h,a]}] in time order."""
    d = _get(f"{BASE}/incidents/soccer/{eid}")
    out = []
    for _period, lst in ((d or {}).get("Incs") or {}).items():
        for x in lst:
            items = [x] + list(x.get("Incs") or [])
            for y in items:
                t = INCIDENT_TYPES.get(y.get("IT"))
                if not t or t.startswith("sub"):
                    continue
                out.append({"minute": y.get("Min"), "team": "H" if y.get("Nm") == 1 else "A", "type": t,
                            "player": y.get("Pn") or " ".join(p for p in (y.get("Fn"), y.get("Ln")) if p),
                            "score": y.get("Sc")})
    out.sort(key=lambda z: (z["minute"] or 0))
    return out


def is_finished(status: str) -> bool:
    return status in FINISHED


def is_live(status: str) -> bool:
    return bool(status) and status != "NS" and not is_finished(status)
