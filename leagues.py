"""Worldwide league browser data for the app's Leagues tab.

Builds two artifacts from the Livescore stage archive (data/ls/stages/*.json, maintained by
worldfeed.py) plus a short upcoming-fixture window:

* data/app/leagues/index.json          - one compact entry per competition stage (all countries, cups,
                                         women's, youth — every stage the public feed publishes)
* data/app/leagues/<stage-slug>.json   - on-demand detail: league table (where the format allows it),
                                         the 40 most recent results, and the next fixtures

This module is strictly additive: it reads the archive and writes new app-data files. It never feeds
the model — the stage archive stays the model's world history, and nothing in here changes a probability.

Data-first rules honoured:
* a table is only published for league-format stages (teams that play several opponents); knockout
  rounds and two-legged ties show results/fixtures only — a bracket is not a table;
* half-time scores are N/A where the feed has none; postponed/cancelled matches simply never appear
  as results (they only surface as fixtures until they are played);
* "fetched" is stamped on every file so the app can show how fresh the data is.
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("leagues")

RESULTS_KEEP = 40       # most recent finished matches published per stage
FIXTURES_KEEP = 12      # upcoming fixtures published per stage
FIXTURE_HOURS = 48      # look-ahead for the fixtures list (2 extra day-feeds, 36 h apart)
_MIN_TEAMS = 4          # a table needs at least this many teams


def slug(key: str) -> str:
    """Stage key 'country/league' -> filename (same convention as worldfeed.Archive._path)."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", key.replace("/", "__")) + ".json"


def _evt(rec) -> dict | None:
    """One archived event [esd, home_id, home, away_id, away, hg, ag, (hth, hta)] -> dict, or None."""
    if not isinstance(rec, (list, tuple)) or len(rec) < 7:
        return None
    esd, _hid, home, _aid, away, hg, ag = rec[:7]
    hth = rec[7] if len(rec) > 7 else None
    hta = rec[8] if len(rec) > 8 else None
    try:
        ko = datetime.strptime(str(esd), "%Y%m%d%H%M%S")
    except ValueError:
        try:
            ko = datetime.strptime(str(esd), "%Y%m%d%H%M")
        except ValueError:
            return None
    if not home or not away:
        return None
    finished = hg is not None and ag is not None
    return {"ko": ko, "home": str(home), "away": str(away), "hg": hg, "ag": ag,
            "hth": hth, "hta": hta, "finished": finished}


def _ko(rec) -> str:
    return rec["ko"].strftime("%Y-%m-%d %H:%M")


def compute_table(evts: list[dict]) -> list[dict]:
    """Standings from finished events: P W D L GF GA GD Pts + last-5 form (oldest first)."""
    teams: dict[str, dict] = {}
    for e in sorted(evts, key=lambda x: x["ko"]):
        for side, other in (("home", "away"), ("away", "home")):
            t = teams.setdefault(e[side], {"p": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "res": []})
            sc, op = (e["hg"], e["ag"]) if side == "home" else (e["ag"], e["hg"])
            t["p"] += 1
            t["gf"] += sc
            t["ga"] += op
            r = "W" if sc > op else ("D" if sc == op else "L")
            t[r.lower()] += 1
            t["res"].append(r)
    rows = []
    for name, t in teams.items():
        rows.append({"team": name, "p": t["p"], "w": t["w"], "d": t["d"], "l": t["l"],
                     "gf": t["gf"], "ga": t["ga"], "gd": t["gf"] - t["ga"],
                     "pts": 3 * t["w"] + t["d"], "form": "".join(t["res"][-5:][::-1])})
    rows.sort(key=lambda r: (-r["pts"], -r["gd"], -r["gf"], r["team"].lower()))
    for i, r in enumerate(rows, 1):
        r["pos"] = i
    return rows


def league_like(evts: list[dict]) -> bool:
    """True when the stage looks like a league/group format: enough teams, and most of them have
    played several different opponents. Knockout rounds (1 opponent per team) fail this test."""
    opp: dict[str, set[str]] = defaultdict(set)
    for e in evts:
        if e["finished"]:
            opp[e["home"]].add(e["away"])
            opp[e["away"]].add(e["home"])
    if len(opp) < _MIN_TEAMS:
        return False
    return sum(1 for o in opp.values() if len(o) >= 3) / len(opp) >= 0.5


def _season(backfill: dict | None) -> str | None:
    """The season label of the stage: the season with the most archived matches (the main season)."""
    if not backfill:
        return None
    best = None
    for season, n in backfill.items():
        if not isinstance(n, int) or n <= 0:
            continue  # -1 sentinel = fetch failed for that season
        if best is None or (n, str(season)) > (best[1], str(best[0])):
            best = (season, n)
    return best[0] if best else None


def _stage_data(path: Path) -> dict | None:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not d.get("key"):
        return None
    return d


def _upcoming(now: datetime, tz_hours: int = 2) -> list[dict]:
    """Not-started matches of the next FIXTURE_HOURS from the public day feed (best effort)."""
    import worldfeed  # local import: keeps this module importable without the feed's deps

    out: dict[str, dict] = {}
    for off in range(12, FIXTURE_HOURS, 24):
        day = now + timedelta(hours=off)
        try:
            for e in worldfeed.fetch_day(day, tz_hours):
                if e["status"] == "NS" and e["eid"] not in out:
                    out[e["eid"]] = e
        except Exception as exc:  # noqa: BLE001
            log.warning("leagues: fixture day %s failed: %s", day.date(), exc)
    return list(out.values())


def build(stages_dir: Path, now: datetime, out_dir: Path, tz_hours: int = 2) -> int:
    """Publish index.json + one detail file per stage. Returns the number of league files written."""
    if now.tzinfo is not None:
        now = now.replace(tzinfo=None)   # feed kick-offs are naive display-time (SAST), like worldfeed.upcoming
    stages_dir = Path(stages_dir)
    if not list(stages_dir.glob("*.json")) and list((stages_dir / "stages").glob("*.json")):
        stages_dir = stages_dir / "stages"  # tolerate being handed the data/ls dir
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    up_by_stage: dict[str, list[dict]] = defaultdict(list)
    for e in _upcoming(now, tz_hours):
        up_by_stage[f"{e['ccd']}/{e['scd']}"].append(e)

    index: list[dict] = []
    slugs: set[str] = set()
    n = 0
    for path in sorted(stages_dir.glob("*.json")):
        d = _stage_data(path)
        if not d:
            continue
        evts = [ev for ev in (_evt(v) for v in (d.get("events") or {}).values()) if ev]
        if not evts:
            continue
        finished = sorted((e for e in evts if e["finished"]), key=lambda e: e["ko"], reverse=True)
        teams = {e["home"] for e in evts} | {e["away"] for e in evts}
        key = d["key"]
        up = sorted((e for e in up_by_stage.get(key, []) if e["kickoff"] >= now - timedelta(minutes=5)),
                    key=lambda e: e["kickoff"])
        table = compute_table(finished) if (finished and league_like(evts) and len(teams) >= _MIN_TEAMS) else []
        entry = {"slug": path.name, "country": d.get("country") or "", "league": d.get("league") or "",
                 "teams": len(teams), "played": len(finished), "season": _season(d.get("backfill")),
                 "table": bool(table), "next": up[0]["kickoff"].strftime("%Y-%m-%d %H:%M") if up else None,
                 "fetched": d.get("fetched") or None}
        index.append(entry)
        detail = {"key": key, "country": entry["country"], "league": entry["league"], "season": entry["season"],
                  "fetched": entry["fetched"], "teams": entry["teams"], "played": entry["played"],
                  "generated": now.strftime("%Y-%m-%d %H:%M"),
                  "table": table,
                  "results": [{"ko": _ko(e), "home": e["home"], "away": e["away"], "hg": e["hg"], "ag": e["ag"],
                               "hth": e["hth"], "hta": e["hta"]} for e in finished[:RESULTS_KEEP]],
                  "fixtures": [{"ko": e["kickoff"].strftime("%Y-%m-%d %H:%M"), "home": e["home"], "away": e["away"]}
                                for e in up[:FIXTURES_KEEP]]}
        (out_dir / path.name).write_text(json.dumps(detail, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        slugs.add(path.name)
        n += 1

    index.sort(key=lambda x: (x["country"].lower(), x["league"].lower()))
    (out_dir / "index.json").write_text(json.dumps(
        {"generated": now.strftime("%Y-%m-%d %H:%M"), "count": len(index), "leagues": index},
        ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # drop detail files of stages that no longer exist (renamed competitions)
    for old in out_dir.glob("*.json"):
        if old.name != "index.json" and old.name not in slugs:
            try:
                old.unlink()
            except OSError:
                pass
    log.info("leagues: %d stages published (index + detail)", n)
    return n


if __name__ == "__main__":  # manual run: python3 leagues.py <state_dir>
    import sys
    state = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    build(state / "data" / "ls" / "stages", datetime.now(), state / "data" / "app" / "leagues")
