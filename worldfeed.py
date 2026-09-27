"""Worldwide coverage without an API key, built on Livescore.com's public app feed.

* fixture spine: every football match on the days inside the scan window (all countries, cups, women's, youth)
* results archive: one compact JSON per competition stage under data/ls/stages/, filled from the stage feed
  (whole current season) and topped up from the day feeds, so history accumulates across seasons
* results frame: the archive as a football-data-shaped DataFrame, appended to the model's history pool so the
  same team-form model, settlement, trends and team pages work for any league in the world

Teams are keyed by Livescore team id (stable) where the model needs a team's history; display uses the names.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import livescore

log = logging.getLogger("worldfeed")

BASE = livescore.BASE
STAGE_MAX_AGE_H = 6          # refresh a stage's season feed at most every 6 hours
BUDGET_S = 150               # stop refreshing stages after this many seconds (rest is picked up next run)
FINISHED = {"FT"}            # only regulation-time results feed the model (AET/pens scores are not 90-minute scores)
DIV_PREFIX = "LS:"


def stage_key(ccd: str, scd: str) -> str:
    return f"{ccd}/{scd}"


def div_code(ccd: str, scd: str) -> str:
    return f"{DIV_PREFIX}{ccd}/{scd}"


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _event(e: dict, st: dict) -> dict | None:
    try:
        t1, t2 = e["T1"][0], e["T2"][0]
        if t1.get("tbd") or t2.get("tbd") or not t1.get("Nm") or not t2.get("Nm"):
            return None
        ko = datetime.strptime(str(e["Esd"]), "%Y%m%d%H%M%S")
    except (KeyError, IndexError, ValueError, TypeError):
        return None
    return {
        "eid": str(e.get("Eid")), "kickoff": ko, "status": str(e.get("Eps") or ""),
        "country": st.get("Cnm") or "", "league": st.get("Snm") or "", "ccd": st.get("Ccd") or "", "scd": st.get("Scd") or "",
        "home": t1["Nm"], "away": t2["Nm"], "home_id": str(t1.get("ID") or ""), "away_id": str(t2.get("ID") or ""),
        "home_img": t1.get("Img") or None, "away_img": t2.get("Img") or None,
        "home_co": t1.get("CoNm") or "", "away_co": t2.get("CoNm") or "",
        "hg": _int(e.get("Tr1")), "ag": _int(e.get("Tr2")), "hth": _int(e.get("Trh1")), "hta": _int(e.get("Trh2")),
    }


def fetch_day(day: datetime, tz_offset_hours: int = 2) -> list[dict]:
    """Every match on `day` with stage codes and team ids (kick-offs in the given UTC offset)."""
    d = livescore._get(f"{BASE}/date/soccer/{day:%Y%m%d}/{int(tz_offset_hours)}?MD=1")
    out = []
    for st in (d or {}).get("Stages", []):
        for e in st.get("Events", []):
            ev = _event(e, st)
            if ev:
                out.append(ev)
    return out


def fetch_stage(ccd: str, scd: str, tz_offset_hours: int = 2) -> tuple[dict | None, list[dict]]:
    """Whole season of one competition stage (fixtures + results + league table meta)."""
    d = livescore._get(f"{BASE}/stage/soccer/{ccd}/{scd}/{int(tz_offset_hours)}?MD=1")
    for st in (d or {}).get("Stages", []):
        meta = {"country": st.get("Cnm") or "", "league": st.get("Snm") or "", "ccd": ccd, "scd": scd,
                "badge": st.get("badgeUrl") or None}
        events = [ev for ev in (_event(e, st) for e in st.get("Events", [])) if ev]
        return meta, events
    return None, []


# ----------------------------------------------------------------------------- archive
class Archive:
    """data/ls/stages/<ccd>__<scd>.json  +  data/ls/teams.json (id -> [name, img, country])."""

    def __init__(self, root: Path):
        self.root = root
        self.stages_dir = root / "stages"
        self.stages_dir.mkdir(parents=True, exist_ok=True)
        self.teams_file = root / "teams.json"
        try:
            self.teams = json.loads(self.teams_file.read_text(encoding="utf-8")) if self.teams_file.exists() else {}
        except (OSError, ValueError):
            self.teams = {}
        self._cache: dict[str, dict] = {}
        self._dirty: set[str] = set()

    # -- files
    def _path(self, key: str) -> Path:
        return self.stages_dir / (re.sub(r"[^A-Za-z0-9_.-]+", "_", key.replace("/", "__")) + ".json")

    def load(self, key: str) -> dict:
        if key in self._cache:
            return self._cache[key]
        p = self._path(key)
        data = None
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = None
        if not data:
            data = {"key": key, "country": "", "league": "", "fetched": None, "events": {}}
        self._cache[key] = data
        return data

    def merge(self, key: str, meta: dict | None, events: list[dict], fetched: datetime | None = None) -> int:
        """Add finished events (regulation time) to a stage file; returns the number of new/changed results."""
        data = self.load(key)
        if meta:
            data["country"] = meta.get("country") or data["country"]
            data["league"] = meta.get("league") or data["league"]
        if fetched is not None:
            data["fetched"] = fetched.strftime("%Y-%m-%d %H:%M")
        changed = 0
        for ev in events:
            if ev["status"] not in FINISHED or ev["hg"] is None or ev["ag"] is None:
                continue
            rec = [ev["kickoff"].strftime("%Y%m%d%H%M"), ev["home_id"], ev["home"], ev["away_id"], ev["away"],
                   ev["hg"], ev["ag"], ev["hth"], ev["hta"]]
            if data["events"].get(ev["eid"]) != rec:
                data["events"][ev["eid"]] = rec
                changed += 1
            for side in ("home", "away"):
                tid = ev[f"{side}_id"]
                if tid:
                    cur = self.teams.get(tid)
                    new = [ev[side], ev[f"{side}_img"], ev[f"{side}_co"]]
                    if cur != new:
                        self.teams[tid] = new
        if changed or fetched is not None or meta:
            self._dirty.add(key)
        return changed

    def save(self) -> int:
        n = 0
        for key in self._dirty:
            data = self._cache[key]
            self._path(key).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            n += 1
        self._dirty.clear()
        self.teams_file.write_text(json.dumps(self.teams, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return n

    # -- refresh policy
    def refresh(self, wanted: dict[str, int], now: datetime, tz_offset_hours: int = 2,
                max_age_h: float = STAGE_MAX_AGE_H, budget_s: float = BUDGET_S) -> dict:
        """Fetch the season feed of the stages in `wanted` {key: priority} that are missing or stale."""
        t0 = time.time()
        order = sorted(wanted.items(), key=lambda kv: -kv[1])
        done = skipped = failed = 0
        for key, _prio in order:
            data = self.load(key)
            fetched = data.get("fetched")
            if fetched:
                try:
                    age = (now.replace(tzinfo=None) - datetime.strptime(fetched, "%Y-%m-%d %H:%M")).total_seconds() / 3600
                except ValueError:
                    age = 1e9
                if age < max_age_h:
                    continue
            if time.time() - t0 > budget_s:
                skipped += 1
                continue
            ccd, scd = key.split("/", 1)
            meta, events = fetch_stage(ccd, scd, tz_offset_hours)
            if meta is None:
                failed += 1
                # remember the attempt so a dead stage is not retried every run
                self.merge(key, None, [], fetched=now)
                continue
            self.merge(key, meta, events, fetched=now)
            done += 1
        log.info("Livescore stages: %d refreshed, %d skipped (budget), %d failed, %d wanted, %.0fs",
                 done, skipped, failed, len(wanted), time.time() - t0)
        return {"refreshed": done, "skipped": skipped, "failed": failed}

    def absorb_days(self, events: list[dict], now: datetime) -> int:
        """Merge finished matches of the day feeds (results appear here before the stage feed refresh)."""
        by_stage: dict[str, list[dict]] = {}
        for ev in events:
            if ev["status"] in FINISHED and ev["ccd"] and ev["scd"]:
                by_stage.setdefault(stage_key(ev["ccd"], ev["scd"]), []).append(ev)
        n = 0
        for key, evs in by_stage.items():
            n += self.merge(key, {"country": evs[0]["country"], "league": evs[0]["league"]}, evs)
        return n

    # -- model input
    def results_frame(self, since: datetime) -> pd.DataFrame:
        rows = []
        cutoff = int(since.strftime("%Y%m%d%H%M"))
        for p in self.stages_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            key = data.get("key") or p.stem.replace("__", "/")
            ccd, _, scd = key.partition("/")
            div = div_code(ccd, scd)
            for eid, rec in (data.get("events") or {}).items():
                try:
                    esd, hid, home, aid, away, hg, ag, hth, hta = rec
                except (TypeError, ValueError):
                    continue
                if int(esd) < cutoff:
                    continue
                rows.append((data.get("country") or "", div, data.get("league") or "", esd[:8], home, away, hid, aid,
                             hg, ag, hth, hta, eid))
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["country", "div", "league", "d", "home", "away", "home_id", "away_id",
                                         "hg", "ag", "hth", "hta", "eid"])
        df["date"] = pd.to_datetime(df["d"], format="%Y%m%d")
        df = df.drop(columns=["d"])
        for c in ("hg", "ag"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        for c in ("hth", "hta"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        for c in ("hxg", "axg", "hst", "ast", "hc", "ac", "hy", "ay", "hr", "ar"):
            df[c] = np.nan
        df["referee"] = ""
        return df

    def badge_map(self) -> dict[str, str]:
        return {v[0]: v[1] for v in self.teams.values() if v and v[0] and v[1]}


# ----------------------------------------------------------------------------- spine
def window_days(start: datetime, end: datetime) -> list[datetime]:
    days = []
    d = start.date()
    while d <= end.date():
        days.append(datetime(d.year, d.month, d.day))
        d += timedelta(days=1)
    return days


def fetch_window(start: datetime, end: datetime, tz_offset_hours: int = 2, back_days: int = 1) -> list[dict]:
    """Day feeds covering [start - back_days, end] (yesterday is included so late finals reach the archive)."""
    events: dict[str, dict] = {}
    for day in window_days(start - timedelta(days=back_days), end):
        try:
            for ev in fetch_day(day, tz_offset_hours):
                events[ev["eid"]] = ev
        except Exception as exc:  # noqa: BLE001
            log.warning("Livescore day %s failed: %s", day.date(), exc)
    return list(events.values())


def upcoming(events: list[dict], start: datetime, end: datetime) -> list[dict]:
    s, e = start.replace(tzinfo=None), end.replace(tzinfo=None)
    return [ev for ev in events if ev["status"] == "NS" and s <= ev["kickoff"] <= e]


def fixtures_frame(events: list[dict], tz) -> pd.DataFrame:
    """Livescore events as scanner fixtures (same columns as load_fixtures, source='world', no feed odds)."""
    rows = []
    for ev in events:
        ko = ev["kickoff"].replace(tzinfo=tz)
        rows.append({
            "source": "world", "code": "LS", "country": ev["country"], "div": div_code(ev["ccd"], ev["scd"]),
            "league": ev["league"], "date": pd.Timestamp(ko.date()), "time": ko.strftime("%H:%M"),
            "home": ev["home"], "away": ev["away"], "home_id": ev["home_id"], "away_id": ev["away_id"],
            "odds_over": np.nan, "odds_under": np.nan, "b365_over": np.nan, "b365_under": np.nan,
            "odds_h": np.nan, "odds_d": np.nan, "odds_a": np.nan, "bfe_h": np.nan, "bfe_d": np.nan, "bfe_a": np.nan,
            "bfe_over": np.nan, "bfe_under": np.nan, "max_over": np.nan, "max_under": np.nan, "referee": "",
            "kickoff": ko, "time_known": True, "eid": ev["eid"],
        })
    return pd.DataFrame(rows)


def ls_entry(ev: dict) -> dict:
    """Shape used by history.Days / appdata (same keys as livescore.fetch_day events)."""
    return {"eid": ev["eid"], "country": ev["country"], "league": ev["league"], "home": ev["home"], "away": ev["away"],
            "kickoff": ev["kickoff"], "status": ev["status"], "hg": ev["hg"], "ag": ev["ag"], "ht": (ev["hth"], ev["hta"]),
            "home_img": ev["home_img"], "away_img": ev["away_img"], "ccd": ev["ccd"]}


def stage_priorities(fixtures: pd.DataFrame) -> dict[str, int]:
    """Stages with matches in the window, most matches first."""
    out: dict[str, int] = {}
    if fixtures is None or fixtures.empty:
        return out
    for div in fixtures["div"]:
        if str(div).startswith(DIV_PREFIX):
            key = str(div)[len(DIV_PREFIX):]
            out[key] = out.get(key, 0) + 1
    return out
