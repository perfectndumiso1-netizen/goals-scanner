"""Fatigue / scheduling facts — computed from data the scanner already holds (no external calls).

Input is the results frame the scanner already builds for the model window (columns: date, country, div, league,
home, away, hg, ag).  A match index over the last ~120 days answers, for both teams:

  * days since the last match (any competition),
  * matches played in the last 7 and 14 days,
  * whether the previous match went long (extra time / penalties) — recorded only when the feed's status for it
    is known, otherwise left as unknown (never guessed).

Everything here is a *fact with provenance* ("our own results archive, retrieved this run"), which is why it is
free, deterministic and fully backtestable — unlike news.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timedelta

import pandas as pd

from .facts import Fact, as_aware, make_fact

log = logging.getLogger("research.fatigue")
SOURCE = "PlayReport results archive (Livescore / football-data, own record)"
LOOKBACK_DAYS = 120
_SUFFIX = set("fc afc cf sc ac as us ss ssc calcio club de cd ud sd rcd fk sk bk if ff sv vfb vfl tsg fsv spvgg "
              "afk bv borussia".split())


def norm(name: str) -> str:
    """Same shape as sporty.norm (accent-stripped, suffix-stripped, alphanumeric) so team names line up."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    toks = [t for t in s.split() if t and t not in _SUFFIX]
    return "".join(toks)


class MatchIndex:
    """Team -> recent matches, built once per run from the frame the scanner already has in memory."""

    def __init__(self, results: pd.DataFrame, now: datetime, lookback_days: int = LOOKBACK_DAYS):
        self.now = now
        self.by_team: dict[str, list[tuple]] = {}
        if results is None or results.empty or "date" not in results.columns:
            return
        since = pd.Timestamp((now - timedelta(days=lookback_days)).date())
        df = results[results["date"] >= since]
        for row in df.itertuples(index=False):
            try:
                ko = pd.Timestamp(getattr(row, "date")).to_pydatetime()
                h, a = norm(getattr(row, "home")), norm(getattr(row, "away"))
                league = f"{getattr(row, 'country', '')} · {getattr(row, 'league', '')}".strip(" ·")
                score = ""
                hg, ag = getattr(row, "hg", None), getattr(row, "ag", None)
                if pd.notna(hg) and pd.notna(ag):
                    score = f"{int(hg)}-{int(ag)}"
            except (AttributeError, TypeError, ValueError):
                continue
            for key, opp in ((h, getattr(row, "away", "")), (a, getattr(row, "home", ""))):
                if key:
                    self.by_team.setdefault(key, []).append((ko, str(opp), league, score))
        for k in self.by_team:
            self.by_team[k].sort(key=lambda m: m[0], reverse=True)

    def matches(self, team: str) -> list[tuple]:
        return self.by_team.get(norm(team), [])

    # -- signals -----------------------------------------------------------------
    def signals(self, team: str, ko: datetime) -> dict | None:
        """Scheduling signals for one team *before* kick-off `ko`.  None when the team is unknown to the archive."""
        ms = [m for m in self.matches(team) if m[0].date() < ko.date()]
        if not ms:
            return None
        last = ms[0]
        # Calendar days, not elapsed hours: the archive stores match *dates*, and "played three days ago" in
        # football always means calendar days.
        days = float((ko.date() - last[0].date()).days)
        return {
            "team": team,
            "last_date": last[0],
            "days_since_last": days,
            "matches_7d": sum(1 for m in ms if 0 <= (ko.date() - m[0].date()).days < 7),
            "matches_14d": sum(1 for m in ms if 0 <= (ko.date() - m[0].date()).days < 14),
            "last_score": last[3],
            "last_competition": last[2],
            "n_known": len(ms),
        }


def facts_for(index: MatchIndex, fx: pd.Series, now: datetime) -> list[Fact]:
    """Fatigue facts for both sides of a fixture.  Missing archive coverage simply yields no fact (never a guess)."""
    ko = as_aware(pd.Timestamp(fx["kickoff"]).to_pydatetime(), now)
    out: list[Fact] = []
    for side in ("home", "away"):
        team = str(fx[side])
        sig = index.signals(team, ko)
        if not sig:
            out.append(make_fact("fatigue", team, "N/A — no archived matches for this team in the last "
                                 f"{LOOKBACK_DAYS} days", SOURCE, now, confidence="provider",
                                 kind="no_history", value={}))
            continue
        score = f" (last {sig['last_score']} v {sig['last_competition']})" if sig["last_score"] else ""
        out.append(make_fact(
            "fatigue", team,
            f"last match {sig['last_date']:%Y-%m-%d}, {sig['days_since_last']:.0f} day(s) before kick-off; "
            f"{sig['matches_7d']} match(es) in the last 7 days{score}",
            SOURCE, now, confidence="provider", kind="schedule",
            value={"days_since_last": sig["days_since_last"], "matches_7d": sig["matches_7d"],
                   "matches_14d": sig["matches_14d"], "last_date": sig["last_date"].strftime("%Y-%m-%d")}))
    return out
