"""Confirmed line-ups from the Livescore public feed — the only line-up source this system has.

Facts about this source, verified by probing it (2026-10-06):
  * `GET /lineups/soccer/<eid>` returns `{Eid, Lu:[{Tnb, Fo, Ps:[...]}]}` — team name, formation and the players.
  * It is published **close to kick-off** (roughly an hour before), and only for competitions the feed covers.
    Fixtures outside that window, and many lower-league / friendly / youth matches, return an empty list.
  * Because of that, an empty response is recorded as "not published" — never as "no changes" and never guessed.

There is deliberately **no predicted line-up** path: nothing in this system invents an XI.  Confirmed and
predicted line-ups therefore cannot be conflated (the code cannot produce a "predicted" one at all).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

from .facts import Fact, as_aware, make_fact

log = logging.getLogger("research.lineups")

BASE = "https://prod-public-api.livescore.com/v1/api/app"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0 Safari/537.36")
TIMEOUT = 20
TTL_MIN = 15          # never re-request the same event inside this window
SOURCE = "Livescore feed (confirmed XI)"


class Client:
    """Tiny TTL-cached client.  Requests are only ever made inside the lead window (see `facts_for`)."""

    def __init__(self, cache_path: Path, ttl_min: float = TTL_MIN, budget: int = 60):
        self.path = Path(cache_path)
        self.ttl = timedelta(minutes=float(ttl_min))
        self.budget = int(budget)
        self.used = 0
        self.cache: dict[str, dict] = {}
        self._dirty = False
        try:
            if self.path.exists():
                self.cache = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.cache = {}

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkstemp(dir=str(self.path.parent), prefix=".lineups-", suffix=".tmp")[1])
        try:
            tmp.write_text(json.dumps(self.cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, self.path)
        finally:
            tmp.unlink(missing_ok=True)
        self._dirty = False

    def _cached(self, eid: str, now: datetime) -> dict | None:
        """Cache hits are age-checked on the epoch clock (never on a parsed datetime: a naive cached timestamp
        minus an aware run clock is exactly the bug that once disabled this whole collector)."""
        rec = self.cache.get(str(eid))
        if not rec:
            return None
        try:
            age = time.time() - float(rec["ts"])
        except (KeyError, TypeError, ValueError):
            return None
        return rec if age <= self.ttl.total_seconds() else None

    def fetch(self, eid: str, now: datetime) -> dict | None:
        """{'home': {...}, 'away': {...}} when the feed publishes both XIs, else None.  Never raises."""
        hit = self._cached(str(eid), now)
        if hit is not None:
            return {"home": hit.get("home"), "away": hit.get("away")}
        if self.used >= self.budget:
            log.info("Line-up budget exhausted (%d requests)", self.used)
            return None
        url = f"{BASE}/lineups/soccer/{eid}"
        try:
            self.used += 1
            r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/json"}, timeout=TIMEOUT)
            data = r.json() if r.status_code == 200 else None
        except Exception as exc:  # noqa: BLE001 - a collector must fail soft on any transport error
            log.warning("Lineups request failed for %s: %s", eid, exc)
            return None
        parsed = _parse(data) if data else {"home": None, "away": None}
        self.cache[str(eid)] = {"ts": time.time(), "home": parsed["home"],
                                "away": parsed["away"], "status": r.status_code if data is not None else 0}
        self._dirty = True
        return parsed if (parsed["home"] or parsed["away"]) else None


def _parse(data: dict) -> dict:
    """Livescore payload -> {'home': {side, formation, players[]}, 'away': {...}} (None when unpublished).

    Field semantics are the ones the shipped Android app already relies on for its Line-ups tab
    (android/.../www/pages.js::lineupsBlock): `Tnb` is the side number (1 = home, 2 = away), `Fo` is the
    formation as a list, `Pos` 1-4 = starting XI, 5 = substitute, 10 = coach, and a player's display name is
    `Snm` or first name + last name.
    """
    out = {"home": None, "away": None}
    lines = data.get("Lu") or []
    for i, side in enumerate(lines[:2]):
        side_no = side.get("Tnb")
        side_key = {1: "home", 2: "away"}.get(side_no) or ("home" if i == 0 else "away")
        players = []
        for p in (side.get("Ps") or []):
            try:
                pos = p.get("Pos")
                name = str(p.get("Snm") or " ".join(x for x in (p.get("Fn"), p.get("Ln")) if x) or "").strip()
                if not name:
                    continue
                players.append({"name": name, "number": p.get("Snu"), "position": pos,
                                "order": p.get("Fp") or "",
                                "starter": isinstance(pos, int) and 1 <= pos <= 4,
                                "sub": pos == 5, "coach": pos == 10,
                                "id": p.get("Pid") or p.get("Aid")})
            except (AttributeError, TypeError):
                continue
        if players:
            fo = side.get("Fo")
            formation = "-".join(str(x) for x in fo) if isinstance(fo, (list, tuple)) else (fo or "")
            out[side_key] = {"side": side_no, "formation": formation,
                             "players": sorted(players, key=lambda x: (x["position"] if isinstance(x["position"], int) else 99,
                                                                       str(x["order"])))[:20]}
    return out


def facts_for(fx, now: datetime, client: Client | None, lead_min: float = 120.0, eid: str | None = None,
              match_started: bool = False) -> list[Fact]:
    """Line-up facts for a fixture, or an honest "not published" fact when the feed has none.

    Outside the lead window we do not even call the feed: the data does not exist yet and a request would be
    wasted (probed behaviour), so the fixture simply carries no line-up fact until the pre-match refresh.
    """
    if client is None or not eid:
        return [make_fact("lineup", "line-ups", "N/A — no fixture id on the live feed, line-ups cannot be looked up",
                          SOURCE, now, confidence="provider", kind="lineup_unavailable", value={})]
    ko = as_aware(fx["kickoff"] if isinstance(fx["kickoff"], datetime) else datetime.fromisoformat(str(fx["kickoff"])),
                  now)
    now = as_aware(now, ko) or now      # both sides of every comparison below live in the same zone
    lead_h = (ko - now).total_seconds() / 3600.0
    if not match_started and lead_h * 60.0 > lead_min:
        return []          # too early: no call, no fact (the pre-match refresh will pick it up)
    got = client.fetch(str(eid), now)
    if not got:
        return [make_fact("lineup", "line-ups",
                          f"N/A — the feed has not published line-ups for this fixture (checked {now:%H:%M} UTC, "
                          f"{lead_h:.1f} h to kick-off)", SOURCE, now, confidence="provider",
                          kind="lineup_not_published", value={})]
    out: list[Fact] = []
    for side in ("home", "away"):
        lx = got.get(side)
        if not lx:
            out.append(make_fact("lineup", f"{side} XI", "N/A — the feed published only one team's line-up",
                                 SOURCE, now, confidence="provider", kind="lineup_partial", value={}))
            continue
        starters = [p["name"] for p in lx["players"] if p.get("starter")]
        subs = [p["name"] for p in lx["players"] if p.get("sub")]
        out.append(make_fact("lineup", f"{side} XI",
                             f"confirmed XI published by the feed: {len(starters)} starters"
                             + (f", {len(subs)} substitutes" if subs else "")
                             + (f", formation {lx['formation']}" if lx["formation"] else ""),
                             SOURCE, now, confidence="official", verified=True, kind="confirmed_xi",
                             value={"side": lx["side"], "formation": lx["formation"],
                                    "starters": starters[:11], "n_subs": len(subs),
                                    "n_players": len(lx["players"])}))
    return out
