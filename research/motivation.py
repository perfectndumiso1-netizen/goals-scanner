"""Motivation / match-context facts.

Phase A records only what is *factual and checkable* from our own archives and the coverage registry:

  * the competition's format (league / cup / qualifier / friendly) as published by the feed;
  * how deep into the season the fixture sits (matchday number for the two teams, from archived results);
  * whether the competition is one whose statistics/line-ups the feed actually publishes.

The *stakes* reading — title race, relegation, promotion, qualification, rotation risk, "must-win" — is a model
interpretation and is deliberately NOT produced here yet.  It needs points-based standings reconstructed as of a
given date so it can be backtested (Phase B: `rules.py::motivation_factor`).  Until then the layer must never
print a bare "motivated" label, exactly as specified.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

import pandas as pd

from .facts import Fact, make_fact
from .fatigue import norm

log = logging.getLogger("research.motivation")
SOURCE = "PlayReport competition record (feed + own archive)"

CUP_HINTS = re.compile(r"\bcup\b|\btrophy\b|copa|coupe|pokal|beker|taca|taça|copa|super ?cup|shield", re.I)
QUAL_HINTS = re.compile(r"qualif|play-?off|playoff|promotion|relegation|barrage", re.I)
FRIENDLY_HINTS = re.compile(r"friendl|club friendl", re.I)


def format_of(fx: pd.Series) -> tuple[str, str]:
    """(kind, evidence) — league | cup | qualifier | friendly | unknown, with the string that decided it."""
    text = f"{fx.get('league', '')} {fx.get('div', '')}"
    if FRIENDLY_HINTS.search(text):
        return "friendly", text.strip()
    if CUP_HINTS.search(text):
        return "cup", CUP_HINTS.search(text).group(0)
    if QUAL_HINTS.search(text):
        return "qualifier/play-off", QUAL_HINTS.search(text).group(0)
    if not text.strip():
        return "unknown", ""
    return "league", text.strip()


def season_progress(results: pd.DataFrame, fx: pd.Series, team: str) -> dict | None:
    """Matches this team has already played in this competition-season, from the archived results frame."""
    if results is None or results.empty:
        return None
    div = fx.get("div")
    if div is None or (isinstance(div, float) and pd.isna(div)):
        return None
    d = results[results["div"] == div]
    if d.empty:
        return None
    key = norm(team)
    mine = d[(d["home"].map(norm) == key) | (d["away"].map(norm) == key)]
    if mine.empty:
        return None
    ko = pd.Timestamp(fx["kickoff"])
    if ko.tzinfo is not None:
        ko = ko.tz_localize(None)      # the archive stores naive local dates
    mine = mine[mine["date"] < ko.normalize()]
    if mine.empty:
        return None
    start = d["date"].min()
    return {"played": int(len(mine)), "season_start": start.strftime("%Y-%m-%d"),
            "competition_matches_archived": int(len(d)),
            "since": start.strftime("%Y-%m-%d")}


def facts_for(results: pd.DataFrame, fx: pd.Series, now: datetime, support: str = "full") -> list[Fact]:
    out: list[Fact] = []
    kind, evidence = format_of(fx)
    out.append(make_fact("motivation", "competition",
                         f"{str(fx.get('league') or 'competition')} — format: {kind}"
                         + (f" (detected from “{evidence}”)" if evidence and kind != "league" else ""),
                         SOURCE, now, confidence="provider", kind="format", value={"format": kind}))
    for side in ("home", "away"):
        team = str(fx[side])
        sp = season_progress(results, fx, team)
        if sp:
            out.append(make_fact("motivation", team,
                                 f"{sp['played']} match(es) already archived for {team} in this competition "
                                 f"(season from {sp['since']})",
                                 SOURCE, now, confidence="provider", kind="season_progress", value=sp))
    out.append(make_fact("motivation", "stakes",
                         "N/A — stakes (title / relegation / qualification / rotation) are not asserted in Phase A; "
                         "they require the backtested points model",
                         SOURCE, now, confidence="provider", kind="stakes_unavailable", value={}))
    if support == "none":
        out.append(make_fact("motivation", "coverage",
                             "this competition publishes no statistics in the fixture feed — external facts are "
                             "unlikely to be found", SOURCE, now, confidence="provider", kind="coverage_none", value={}))
    return out
