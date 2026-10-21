"""Market policy (user rules, 2026-10-17): which selections the model may recommend, and from what probability.

    * Team-goals Overs are on (HO05, AO05, HO15, AO15 …). Team unders stay out.
    * Double chance is dropped (1X, 12, X2).
    * No unders in any market: total-goals unders, "no BTTS", team unders, corner and card unders.
    * 2026-10-21: the home page's "strong markets for the day" section is defined here — model probability >= 75%,
      price >= 1.16, and only Over 1.5 total goals, team goals, corners and bookings (see is_strong_market).
    * 2026-10-21: accumulators are retired — no acca is built, shown or spoken anywhere (build/settle code stays so
      the historical ledger keeps grading).
    * Over 1.5, Over 2.5, BTTS, team goals and bookings are the focus. Over 2.5, BTTS and 1X2 START from a 55% model
      probability; every other market keeps the bar it already had.

One source of truth. `safe.selections()` asks `allowed(code)` before it yields a candidate, so every surface that
is built from it (shortlist, high-probability selections, bets of the day, accas, the match page, the app's
boards and the Telegram texts) inherits the policy without re-implementing it. Settlement and labelling still
understand every code, so a bet placed before the change keeps grading and displaying correctly.

Nothing here touches a probability: the policy only decides which selections are eligible and where the floor sits.

Switches (rollback without a code change):
    MODEL_MARKETS=all                      restore every market the model ever offered
    MODEL_MARKETS=unders,team,dc           allow just those families back (comma list; any of: unders, team, dc)
    MODEL_DROP=corners,result              OPTIONAL: also drop corners and/or 1X2 (not asked for — both stay on by default)
    POLICY_MIN_P_O25 / POLICY_MIN_P_BTTS   override the 0.55 starting floors (NOT MIN_P_O25 / MIN_P_BTTS: scan.yml already
                                           uses those names, at 0.60, for the older "Goals shortlists" star thresholds)
"""
from __future__ import annotations

import os
import re

# ---------------------------------------------------------------- selection-code families
# Codes: O25 / U25 total goals, BTTS / NBTTS, HO05 / AU15 team goals, CO85 / CU85 total corners,
# CHO35 / CAU55 team corners, KO35 / KU35 total cards, KHO25 / KAU25 team cards, 1X / 12 / X2, H / D / A.
UNDER_RE = re.compile(r"^(?:NBTTS|(?:[HA]|C[HA]?|K[HA]?)?U\d+)$")
TEAM_GOAL_RE = re.compile(r"^[HA][OU]\d+$")
DOUBLE_CHANCE = frozenset(("1X", "12", "X2"))


def is_under(sel: str) -> bool:
    """Any under-style selection, in any market (incl. 'no BTTS', team unders, corner and card unders)."""
    return bool(UNDER_RE.match(sel or ""))


def is_team_goal(sel: str) -> bool:
    """Home / away team total-goals selections (not team corners or cards, which carry a C or K prefix)."""
    return bool(TEAM_GOAL_RE.match(sel or ""))


def is_double_chance(sel: str) -> bool:
    return (sel or "") in DOUBLE_CHANCE


CORNER_RE = re.compile(r"^C[HA]?[OU]\d+$")


def is_corner(sel: str) -> bool:
    return bool(CORNER_RE.match(sel or ""))


# ---------------------------------------------------------------- "strong markets for the day" (user rule 2026-10-21)
# The home page carries one section of the day's strongest markets: model probability >= 75% AND a real price of
# 1.16 or more, and only in the four families the user named — Over 1.5 total goals, team goals, corners and
# bookings. Team and total lines of the corner / booking markets are both in; 1X2, BTTS, Over 2.5 and every under
# are out.
STRONG_P_MIN = 0.75
STRONG_ODDS_MIN = 1.16
STRONG_RE = re.compile(r"^(?:O15|[HA]O\d+|C[HA]?O\d+|K[HA]?O\d+)$")


def is_strong_market(sel: str) -> bool:
    """One of the four families the home page's strong-markets section may show (overs only)."""
    return bool(STRONG_RE.match(sel or ""))


# ---------------------------------------------------------------- which families are on
def _families_allowed() -> frozenset:
    raw = os.getenv("MODEL_MARKETS", "").strip().lower()
    if not raw or raw in ("focus", "default"):
        return frozenset()
    if raw == "all":
        return frozenset(("unders", "team", "dc"))
    return frozenset(x.strip() for x in raw.split(",") if x.strip() in ("unders", "team", "dc"))


ALLOW = _families_allowed()
# families the user did NOT ask to drop but may want to switch off later (default: both stay on)
DROP = frozenset(x.strip() for x in os.getenv("MODEL_DROP", "").lower().split(",") if x.strip() in ("corners", "result"))


def allowed(sel: str) -> bool:
    """May the model offer this selection at all?"""
    if is_under(sel):
        return "unders" in ALLOW
    if is_team_goal(sel):
        return True   # user 2026-10-20: team-goal Overs are back (unders already rejected above)
    if is_double_chance(sel):
        return "dc" in ALLOW
    if DROP:
        if "corners" in DROP and is_corner(sel):
            return False
        if "result" in DROP and (sel or "") in ("H", "D", "A"):
            return False
    return True


# ---------------------------------------------------------------- probability floors
def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# Over 2.5, BTTS and 1X2 start from 55% (user rules 2026-10-17 / 2026-10-19). Every other selection keeps
# the floor of the board that asks (70% for goals lines, 65% for corners and bookings in the shortlist).
# The env names carry a POLICY_ prefix on purpose: scan.yml already sets MIN_P_O25 / MIN_P_BTTS (0.60) for the older "Goals
# shortlists" star thresholds, and reusing those names silently moved this floor to 60% in production on 2026-10-17.
_x12_floor = _env_float("POLICY_MIN_P_1X2", 0.55)
SEL_MIN_P = {"O25": _env_float("POLICY_MIN_P_O25", 0.55), "BTTS": _env_float("POLICY_MIN_P_BTTS", 0.55),
             "H": _x12_floor, "D": _x12_floor, "A": _x12_floor}


def min_p(sel: str, default: float) -> float:
    """The probability floor for one selection: its own starting floor when the policy names one, else `default`."""
    return SEL_MIN_P.get(sel, default)


def describe() -> dict:
    """Machine-readable summary published with the shortlist rules (shown in the app)."""
    return {
        "focus": ["Over 1.5", "Over 2.5", "BTTS", "Team goals", "Bookings"],
        "dropped": [f for f, on in (("double chance", "dc" not in ALLOW),
                                    ("unders (every market)", "unders" not in ALLOW)) if on],
        "starting_floor": {"O25": SEL_MIN_P["O25"], "BTTS": SEL_MIN_P["BTTS"], "1X2": SEL_MIN_P["H"]},
        "kept_by_default": [name for name, key in (("corners (overs)", "corners"), ("1X2 (home / away)", "result"))
                            if key not in DROP],
    }
