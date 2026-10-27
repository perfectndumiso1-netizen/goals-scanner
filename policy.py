"""Market policy — which selections the model may recommend, from what probability, and at what price.

2026-10-27 model review (docs/MODEL_REVIEW_2026-10-27.md) rewrote the rules. The measured record over 3,910 priced,
settled selections said:

    * the de-vigged market out-forecasts the model (Brier 0.1879 vs 0.1916), by about 4.6 pp of overconfidence;
    * the margin paid on the prices we take is ~5 pp, while the real edge over the market is ~2 pp — a guaranteed loss;
    * the damage is concentrated in the markets where our probability has no price to check it against:
      double chance (-16.7 %), team goals (-6.4 %, home team to score -10.1 %), cards (-9.4 %), BTTS (-7.0 %).

So from 2026-10-27:

    * DROPPED families: double chance (1X / 12 / X2), team goals (HO05 / AO05 / HO15 / AU15 …), cards (K…),
      BTTS / no-BTTS, Over 0.5 (O05). None of these may be offered, shown, spoken or fed to the videos.
    * KEPT: total goals Overs from Over 1.5 up, total and team corners, and the 1X2 result board (H / D / A).
    * No unders in any market (user rule, unchanged).
    * PRICE FLOOR 1.16: a selection priced below it is not offered at all (the 1.12–1.15 band loses even when the
      probability is right, because 1.12 needs ~89 % to break even).
    * PRICE CHECK: a pick whose price is below 95 % of its own fair price (1 / p) is not promoted to primary — it is
      still recorded, but as a watchlist row. 65 % of the old book failed this check.
    * PUBLISHED PROBABILITY is anchored to the market: p_pub = 0.25 x model + 0.75 x de-vigged market, capped at
      +3 pp above the market and at 90 % (80 % with no price to anchor it). This is what the app, the shortlist and
      the videos show; the raw model number survives as `p_model` in the ledger. Best Brier/log-loss weight.
    * The home page's "strong markets for the day" section is model probability >= 78 %, price >= 1.16, in Over 1.5
      total goals and corners only (total corners get their own room). Team goals and bookings left with their family.
    * Accumulators stay retired — no acca is built, shown or spoken anywhere.

One source of truth. `safe.selections()` asks `allowed(code)` before it yields a candidate and `safe.Sel.p` is the
published probability, so every surface built from it (shortlist, high-probability selections, bets of the day, the
match page, the app's boards, the videos and the Telegram texts) inherits the rules without re-implementing them.
Settlement and labelling still understand every code, so a bet placed before the change keeps grading and displaying.

Switches (rollback without a code change):
    MODEL_MARKETS=all                        restore every family the model ever offered
    MODEL_MARKETS=btts,cards,team,dc,o05     allow just those families back (comma list of any of those names)
    MODEL_DROP=corners,result                OPTIONAL: also drop corners and/or 1X2 (not asked for — both stay on)
    POLICY_MARKET_WEIGHT=0.75                weight of the de-vigged market in the published probability (1 = model only)
    POLICY_PRICE_FLOOR=1.16                  the price floor (below it, nothing is offered)
    POLICY_PRICE_VS_FAIR=0.95                price / fair-price needed to be promoted to primary
    POLICY_MIN_P_O25 / POLICY_MIN_P_BTTS     override the 0.55 starting floors (NOT MIN_P_O25 / MIN_P_BTTS: scan.yml
                                             already uses those names, at 0.60, for the older star thresholds)
    POLICY_STRONG_P_MIN=0.78                 the home page's strong-markets floor
"""
from __future__ import annotations

import os
import re


def _env_float(name: str, default: float) -> float:
    """A number from the environment, with the default when it is unset or unparseable."""
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


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
CARDS_RE = re.compile(r"^K[HA]?[OU]\d+$")
BTTS_SELS = frozenset(("BTTS", "NBTTS"))
NO_GOAL_SELS = frozenset(("O05",))          # 2026-10-27: Over 0.5 lost 5.9 % over 42 priced bets


def is_corner(sel: str) -> bool:
    return bool(CORNER_RE.match(sel or ""))


def is_cards(sel: str) -> bool:
    """Total and team bookings/cards (KO35, KU95, KHO25 …). Dropped 2026-10-27: -9.4 % over 37 priced bets."""
    return bool(CARDS_RE.match(sel or ""))


def is_btts(sel: str) -> bool:
    return (sel or "").upper() in BTTS_SELS


# ---------------------------------------------------------------- "strong markets for the day" (home page)
# One section on the home page: model probability >= 78 % AND a real price of 1.16 or more, and only the two families
# that survived the 2026-10-27 review — Over 1.5 total goals and corners. Team goals and bookings left with their
# families (they were the two worst markets on the board), and the floor moved 75 % -> 78 % because the 75-80 %
# band was 993 selections at -2.8 %. Total corner lines keep their own cap in appdata.STRONG_CAPS so the team lines
# cannot fill the section.
STRONG_P_MIN = _env_float("POLICY_STRONG_P_MIN", 0.78)
STRONG_ODDS_MIN = _env_float("POLICY_STRONG_ODDS_MIN", 1.16)
STRONG_RE = re.compile(r"^(?:O15|C[HA]?O\d+)$")
_LINE_05 = re.compile(r"O0?5$")       # "at least one corner" is not a market worth a home-page row


def is_strong_market(sel: str) -> bool:
    """One of the two families the home page's strong-markets section may show (overs only, no 0.5 lines)."""
    sel = (sel or "").upper()
    return bool(STRONG_RE.match(sel)) and not _LINE_05.search(sel)


# ---------------------------------------------------------------- the price rules (2026-10-27)
# At the odds this book lives on (1.2-1.4) the bookmaker's margin is 4-5 points of probability. The 1.12-1.15 band
# needs ~89 % to break even and lost even when the probability was right, so nothing below the floor is offered.
PRICE_FLOOR = _env_float("POLICY_PRICE_FLOOR", 1.16)
# A pick whose price is below this share of its own fair price (1 / p) is real but not good: 65 % of the old book was
# in that state. It is recorded as a watchlist row instead of being promoted to primary.
PRICE_VS_FAIR = _env_float("POLICY_PRICE_VS_FAIR", 0.95)


def price_check(p, odds) -> dict | None:
    """How the offer compares with the fair price of our own probability. None when either side is missing."""
    try:
        p, odds = float(p), float(odds)
    except (TypeError, ValueError):
        return None
    if not (0 < p < 1) or odds <= 1:
        return None
    fair = 1 / p
    ratio = odds / fair
    if ratio >= 1.0:
        verdict, text = "value", "priced above our fair price"
    elif ratio >= PRICE_VS_FAIR:
        verdict, text = "fair", "priced close to our fair price"
    else:
        verdict, text = "short", "priced below our fair price"
    return {"fair": round(fair, 2), "ratio": round(ratio, 3), "verdict": verdict, "text": text}


# ---------------------------------------------------------------- the published probability (2026-10-27)
# The market is a better forecaster than the model (Brier 0.1879 vs 0.1916 over 3,910 priced settled rows) and the
# best blend weight is a quarter on the model, so that is what every surface publishes. The raw model number is kept
# in the ledger as `p_model`; nothing is lost, but what we SHOW is anchored to a price.
MARKET_WEIGHT = min(max(_env_float("POLICY_MARKET_WEIGHT", 0.75), 0.0), 1.0)
EDGE_CAP = 0.03          # published p is never more than 3 pp above the de-vigged market
P_MAX_PRICED = 0.90      # and never above 90 % when a price exists to check it against
P_MAX_UNPRICED = 0.80    # 80 % when there is no price at all (the unpriced BTTS forward test was 15 pp optimistic)


def blend(p_model, p_sb) -> float | None:
    """model/market blend used for publication; the model alone when the market has no view."""
    return None if p_model is None else float(p_model)


def publish_p(p_model, p_sb) -> float | None:
    """The probability every surface shows: anchored to the de-vigged market and capped.

    `p_model` is the model probability, `p_sb` the de-vigged market probability (None when the book did not price
    the selection). With a price: 0.25 x model + 0.75 x market, capped at market + 3 pp and at 90 %. Without a
    price there is nothing to anchor to, so the model is used and capped at 80 %."""
    if p_model is None:
        return None
    try:
        p = float(p_model)
    except (TypeError, ValueError):
        return None
    if not (0 < p < 1):
        return None
    try:
        sb = float(p_sb) if p_sb is not None else None
    except (TypeError, ValueError):
        sb = None
    if sb is None or not (0 < sb < 1):
        return min(p, P_MAX_UNPRICED)
    anchored = (1.0 - MARKET_WEIGHT) * p + MARKET_WEIGHT * sb
    return max(0.01, min(anchored, sb + EDGE_CAP, P_MAX_PRICED))


# ---------------------------------------------------------------- which families are on
FAMILIES = ("unders", "dc", "team", "cards", "btts", "o05")


def _families_allowed() -> frozenset:
    """Families the model may still offer. Empty = the 2026-10-27 policy (none of the dropped ones)."""
    raw = os.getenv("MODEL_MARKETS", "").strip().lower()
    if not raw or raw in ("focus", "default"):
        return frozenset()
    if raw == "all":
        return frozenset(FAMILIES)
    return frozenset(x.strip() for x in raw.split(",") if x.strip() in FAMILIES)


ALLOW = _families_allowed()
# families the user did NOT ask to drop but may want to switch off later (default: both stay on)
DROP = frozenset(x.strip() for x in os.getenv("MODEL_DROP", "").lower().split(",") if x.strip() in ("corners", "result"))


def family_of(sel: str) -> str:
    """The dropped family a selection belongs to ('' when it is one we still offer)."""
    sel = (sel or "").strip().upper()
    if is_under(sel):
        return "unders"
    if is_double_chance(sel):
        return "dc"
    if is_cards(sel):
        return "cards"
    if is_btts(sel):
        return "btts"
    if is_team_goal(sel):
        return "team"
    if sel in NO_GOAL_SELS:
        return "o05"
    return ""


def allowed(sel: str) -> bool:
    """May the model offer this selection at all? Everything not in a dropped family, unless DROP says otherwise."""
    fam = family_of(sel)
    if fam:
        return fam in ALLOW
    sel = (sel or "").strip().upper()
    if DROP:
        if "corners" in DROP and is_corner(sel):
            return False
        if "result" in DROP and sel in ("H", "D", "A"):
            return False
    return True


# ---------------------------------------------------------------- probability floors
# Over 2.5 and 1X2 start from 55 % (user rules 2026-10-17 / 2026-10-19). Every other selection keeps the floor of the
# board that asks (70 % for goals lines, 65 % for corners in the shortlist). BTTS keeps its entry so a historical row
# still labels itself, even though the family is no longer offered.
# The env names carry a POLICY_ prefix on purpose: scan.yml already sets MIN_P_O25 / MIN_P_BTTS (0.60) for the older
# "Goals shortlists" star thresholds, and reusing those names silently moved this floor to 60 % in production once.
_x12_floor = _env_float("POLICY_MIN_P_1X2", 0.55)
SEL_MIN_P = {"O25": _env_float("POLICY_MIN_P_O25", 0.55), "BTTS": _env_float("POLICY_MIN_P_BTTS", 0.55),
             "H": _x12_floor, "D": _x12_floor, "A": _x12_floor}


def min_p(sel: str, default: float) -> float:
    """The probability floor for one selection: its own starting floor when the policy names one, else `default`."""
    return SEL_MIN_P.get(sel, default)


def describe() -> dict:
    """Machine-readable summary published with the shortlist rules (shown in the app)."""
    return {
        "focus": ["Over 1.5", "Over 2.5", "Corners (total first)"],
        "dropped": ["double chance", "team goals", "cards / bookings", "BTTS", "Over 0.5", "accumulators",
                    "unders (every market)"],
        "dropped_why": {"double chance": "-16.7 % ROI over 300 priced bets; the model sits below the market on it",
                        "team goals": "-6.4 % (home team to score -10.1 %) over 948 priced bets",
                        "cards / bookings": "-9.4 % over 37 priced bets",
                        "BTTS": "-7.0 % priced, and 15 pp optimistic in the unpriced forward test",
                        "Over 0.5": "-5.9 % over 42 priced bets"},
        "price_floor": PRICE_FLOOR,
        "price_vs_fair_to_promote": PRICE_VS_FAIR,
        "market_weight": MARKET_WEIGHT,
        "published_p_cap": {"priced": P_MAX_PRICED, "unpriced": P_MAX_UNPRICED},
        "strong_markets": {"min_p": STRONG_P_MIN, "min_odds": STRONG_ODDS_MIN,
                           "families": ["Over 1.5 total goals", "corners"]},
        "starting_floor": {"O25": SEL_MIN_P["O25"], "1X2": SEL_MIN_P["H"]},
        "kept_by_default": [name for name, key in (("corners (overs)", "corners"), ("1X2 (home / away)", "result"))
                            if key not in DROP],
    }
