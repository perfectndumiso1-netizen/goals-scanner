"""Is this match fit for a video? Recent form, a recent head to head, and an internet cross-check.

The videos are the part of PlayReport a stranger sees. A slide that says "3rd of 16, 21 points" and "1W · 1D · 1L
in the last three meetings" has to be true and current, so a match only reaches a video when the app's own fixture
detail can back every line on the slide:

  * **both teams have recent results** — `MIN_TEAM_RESULTS` completed matches each with a score, the newest one
    inside `MAX_RECENT_DAYS`, so "last five" is really the last five and not the last five of a year;
  * **a recent head to head exists** — at least `MIN_H2H` meetings with scores, the latest inside `H2H_MAX_DAYS`.
    No meetings, or nothing in years, and the match is out: a "record" slide built on a 2019 friendly is worse than
    no slide;
  * **the numbers are internally sound** — the detail belongs to this fixture, the dates are in the past, every
    published rate is a real probability.

Then the internet check (`web_check`). The detail file already carries the scan's news lookups, but those are a
snapshot; before a video is finalised each match is queried again (`news.fixture_headlines`, cached per match) and
three things can happen:

  * **confirmed** — a reputable headline names both clubs near this fixture. The strongest case, used first when a
    video has more matches than it can carry;
  * **unverified** — nothing found. Not a failure (lower leagues get no coverage), but it is ranked after the
    confirmed matches and reported, so a video is always built from checked matches when enough exist;
  * **contradicted** — a headline says the game is postponed, cancelled, abandoned or awarded. The match is dropped:
    a video must never sell a bet on a game that is not being played.

Nothing here invents or rewrites a number, and a network failure never blocks a video — it degrades to "unverified".
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("scanner")

MIN_TEAM_RESULTS = 5        # completed matches with a score, per team
MAX_RECENT_DAYS = 200       # the newest of those results has to be this fresh
MIN_H2H = 2                 # meetings with a score
H2H_MAX_DAYS = 1100         # …and the latest of them inside three years
MIN_ACCEPTED = 3            # a video needs at least this many matches, or it is not built
VERIFIED_FIRST_MIN = 3      # with this many confirmed matches, unverified ones are left out

CONTRADICTION = re.compile(
    r"\b(postponed|called off|abandoned|cancel{1,2}ed|awarded the (?:win|tie|match)|"
    r"match (?:is )?off|will not be played|replay ordered|expelled from)\b", re.IGNORECASE)

_SEARCH_CACHE: dict[tuple[str, str], list[dict]] = {}


def _f(v) -> float | None:
    try:
        out = float(v)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def _date(raw) -> datetime | None:
    text = str(raw or "")[:19]
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:len(datetime.now().strftime(fmt))], fmt)
        except ValueError:
            continue
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _norm(name) -> str:
    from reel_insights import norm       # one spelling of "the same club" across the pipeline
    return norm(name)


def _results(team: dict, kickoff: datetime | None) -> list[dict]:
    """Completed matches with a score, newest first, that actually happened before this kick-off.

    A club cannot play twice on one date with the same score, so that pair is a duplicate (the same match delivered by
    two feeds, sometimes under two spellings of the opponent). Counting it twice would let a "last five" slide show
    three matches — the fault found on 2026-10-28 — so duplicates are removed here as well as at the source.
    """
    out = []
    seen = set()
    for m in (team or {}).get("last5") or []:
        gf, ga, when = _f(m.get("gf")), _f(m.get("ga")), _date(m.get("date"))
        if gf is None or ga is None or when is None:
            continue
        if kickoff and when > kickoff + timedelta(days=1):
            continue                     # a "result" after the match we are previewing is a data fault
        key = (when.date(), int(gf), int(ga))
        if key in seen:
            continue
        seen.add(key)
        out.append({"date": when, "gf": int(gf), "ga": int(ga), "opp": m.get("opp")})
    out.sort(key=lambda r: r["date"], reverse=True)
    return out


def stats_problems(pick: dict, detail: dict | None, *, now: datetime | None = None) -> list[str]:
    """Why this match cannot be explained on a video, in the order a reader would check it. [] = it can."""
    if not detail:
        return ["no fixture detail — the stats cannot be checked"]
    problems: list[str] = []
    # the detail must be THIS fixture's (the bug the app had: another match's numbers on the page)
    for side in ("home", "away"):
        want, got = _norm(pick.get(side)), _norm(detail.get(side))
        if want and got and want != got:
            problems.append(f"detail belongs to {detail.get('home')} v {detail.get('away')}")
            return problems
    kickoff = _date(pick.get("kickoff")) or _date(detail.get("kickoff"))
    reference = now or kickoff or datetime.now()
    if kickoff and now and kickoff < now - timedelta(hours=3):
        problems.append("kick-off has passed")
    teams = detail.get("teams") or {}
    for side, label in (("home", pick.get("home")), ("away", pick.get("away"))):
        rows = _results(teams.get(side) or {}, kickoff)
        if len(rows) < MIN_TEAM_RESULTS:
            problems.append(f"{label}: only {len(rows)} recent result(s) with a score")
            continue
        age = (reference - rows[0]["date"]).days
        if age > MAX_RECENT_DAYS:
            problems.append(f"{label}: newest result is {age} days old")
        prof = teams.get(side) or {}
        for key in ("o15", "o25", "o35", "btts", "cs", "fts"):
            rate = prof.get(key)
            if rate is None:
                continue
            value = _f(rate)
            if value is None or not (0.0 <= value <= 1.0):
                problems.append(f"{label}: {key} rate {rate!r} is not a probability")
    meetings = []
    seen = set()
    for m in detail.get("h2h") or []:
        when = _date(m.get("date"))
        hg, ag = _f(m.get("hg")), _f(m.get("ag"))
        if when is None or hg is None or ag is None:
            continue
        if (when.date(), hg, ag) in seen:
            continue
        seen.add((when.date(), hg, ag))
        meetings.append(when)
    meetings.sort(reverse=True)
    if len(meetings) < MIN_H2H:
        problems.append(f"only {len(meetings)} head-to-head meeting(s) with a score")
    elif (reference - meetings[0]).days > H2H_MAX_DAYS:
        problems.append(f"no head-to-head for {(reference - meetings[0]).days} days")
    return problems


def _search(pick: dict, search=None) -> list[dict]:
    """Headlines about this fixture. Cached per match; a failure is an empty list, never an exception."""
    key = (_norm(pick.get("home")), _norm(pick.get("away")))
    if key in _SEARCH_CACHE:
        return _SEARCH_CACHE[key]
    if search is None:
        try:
            import news
            search = news.fixture_headlines
        except Exception:                     # noqa: BLE001 - news is optional context
            search = None
    items: list[dict] = []
    if search is not None:
        try:
            items = list(search(pick.get("home") or "", pick.get("away") or "",
                                pick.get("country") or "", days=14, limit=6) or [])
        except Exception as exc:              # noqa: BLE001 - the video must survive a dead feed
            log.info("video check: search failed for %s v %s: %s", pick.get("home"), pick.get("away"), exc)
            items = []
    _SEARCH_CACHE[key] = items
    return items


def reset_cache() -> None:
    _SEARCH_CACHE.clear()


def web_check(pick: dict, *, search=None) -> dict:
    """What the internet says about this fixture: confirmed / unverified / contradicted, with the headlines."""
    items = _search(pick, search)
    home, away = _norm(pick.get("home")), _norm(pick.get("away"))
    titles = [str(it.get("title") or "") for it in items]
    for title in titles:
        if CONTRADICTION.search(title):
            return {"verdict": "contradicted", "note": title, "headlines": titles[:4]}
    both = [t for t in titles if home and away and home.split()[0] in _norm(t) and away.split()[0] in _norm(t)]
    if both:
        return {"verdict": "confirmed", "note": both[0], "headlines": titles[:4]}
    return {"verdict": "unverified", "note": "", "headlines": titles[:4]}


def check(pick: dict, detail: dict | None, *, now: datetime | None = None, search=None,
          require_confirmation: bool = False) -> dict:
    """The whole gate for one match: `{"ok": bool, "reasons": [...], "verdict": ..., "headlines": [...]}`."""
    problems = stats_problems(pick, detail, now=now)
    web = web_check(pick, search=search)
    if web["verdict"] == "contradicted":
        problems.append(f"the internet says this match is off: {web['note']}")
    elif require_confirmation and web["verdict"] != "confirmed":
        problems.append("no online confirmation of this fixture")
    return {"ok": not problems, "reasons": problems, "verdict": web["verdict"],
            "headlines": web["headlines"], "checked": True}


def select(picks: list, details: dict | None = None, *, load_detail=None, now: datetime | None = None,
           search=None, require_confirmation: bool = False) -> tuple[list, list[dict]]:
    """Split candidates into (kept, skipped) with a reason for every match left out.

    Kept matches are ordered confirmed-first, then by their original order, so a video uses the matches the internet
    could back when it has to choose. `details` maps a pick to its detail file (or pass `load_detail(pick)`).
    """
    kept: list[tuple[int, dict, dict]] = []
    skipped: list[dict] = []
    for idx, p in enumerate(picks or []):
        detail = (details or {}).get(_key(p)) if details else None
        if detail is None and load_detail is not None:
            detail = load_detail(p)
        verdict = check(p, detail, now=now, search=search, require_confirmation=require_confirmation)
        if not verdict["ok"]:
            skipped.append({"home": p.get("home"), "away": p.get("away"), "sel": p.get("sel"),
                            "verdict": verdict["verdict"], "reasons": verdict["reasons"]})
            continue
        kept.append((idx, p, verdict))
    confirmed = [x for x in kept if x[2]["verdict"] == "confirmed"]
    unverified = [x for x in kept if x[2]["verdict"] != "confirmed"]
    order = confirmed + unverified if len(confirmed) >= VERIFIED_FIRST_MIN else kept
    out = []
    for _idx, p, verdict in order:
        out.append({**p, "checked": verdict["verdict"], "check_note": verdict.get("headlines", [])[:1]})
    return out, skipped


def _key(p: dict) -> str:
    return f"{p.get('home')}|{p.get('away')}|{p.get('kickoff')}"


def detail_path(pick: dict, fx_dir: Path | None) -> Path | None:
    """Where the app keeps this fixture's detail file (the same key `shortlist_reel.load_detail` uses)."""
    if not fx_dir:
        return None
    from shortlist_reel import _fx_key
    return Path(fx_dir) / f"{_fx_key(pick)}.json"
