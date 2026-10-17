"""High-probability selections (internal name kept: "safe" bets) and the day card.

Every fixture gets a list of *selections* across the modelled markets (match result, Over goals lines, BTTS,
corners and cards overs — team goals, double chance and every under were dropped on 2026-10-17, see policy.py) with
two separate views: the football-data MODEL probability and the probability
IMPLIED by the Sportybet price (de-margined). Data-first engine (2026-09-28): the probability used for ranking and
thresholds is the model probability alone (Sel.p == Sel.p_model). The market view is a comparison layer only:
a disagreement of more than DIFF_FLAG is shown on the match page but never excludes a selection — odds never
filter which matches can be bet (user decision 2026-10-01). The market never changes a model probability.

"High-probability selections" = priced selections with model probability >= MIN_P (Over 2.5 and BTTS start from
55%), ranked by model probability
(ledger data/safe_bets.csv, auto-settled from results). There is no minimum-odds floor and no market-contradiction
hold-back: the price is displayed, never used to filter (user decision 2026-10-01). Trebles are legacy code, no
longer produced.
No selection is ever labelled safe, guaranteed or a banker in user-facing text.
"""
from __future__ import annotations

import json
import re
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import markets
import policy

MIN_P = 0.70         # probability at least 70% — the only bar (odds never filter, user decision 2026-10-01);
                     # Over 2.5 and BTTS START from 55% (user rule 2026-10-17, see policy.SEL_MIN_P)
TREBLES = 3
LEGS = 3
MAX_BETS = 40
DIFF_FLAG = 0.12     # model and Sportybet views differ by more than this -> flag

GROUPS = {"result": "Match result", "dc": "Double chance", "goals": "Total goals", "btts": "Both teams to score",
          "team": "Team goals", "corners": "Corners", "cards": "Cards"}

SAFE_BET_COLS = ["match_date", "kickoff", "country", "div", "league", "home", "away", "sel", "label", "p", "p_model",
                 "p_sb", "odds", "status", "score", "settled_on", "run", "report_date", "botd", "kind"]
# v4: safest bets specialise in goals, corners and cards (match-result / double-chance stay on the match page only)
# 2026-10-17: team goals are dropped altogether (policy.py); the group stays in GROUPS so old rows still label
SAFE_GROUPS = ("goals", "btts", "corners", "cards")
# v5: overs only — no "under x goals / corners / cards", no "team under", no "no BTTS" (user decision)
OVERS_ONLY = True

# A team-to-score recommendation must have recent scoring support, including at its actual venue.
# This is an eligibility filter only; it never changes the probability produced by the model.
TEAM_GOAL_MARKETS = frozenset(("HO05", "AO05"))
TEAM_GOAL_LAST_N = 5
TEAM_GOAL_MIN_SCORED = 4
TEAM_GOAL_VENUE_N = 3
TEAM_GOAL_MIN_VENUE_SCORED = 2
TEAM_GOAL_MIN_OPP_CONCEDED = 2


def is_under(sel: str) -> bool:
    """Any under-style selection in any market (policy.py): total, team, corner and card unders and 'no BTTS'."""
    return policy.is_under(sel)


def _recent(profile, field: str) -> list:
    try:
        return list(getattr(profile, field, None) or [])
    except TypeError:
        return []


def _positive_goal_count(matches: list, field: str, required: int) -> int | None:
    sample = matches[:required]
    if len(sample) < required:
        return None
    count = 0
    for match in sample:
        try:
            count += float(match.get(field) or 0) > 0
        except (AttributeError, TypeError, ValueError):
            continue
    return count


def team_goal_form_evidence(r, sel: str) -> dict | None:
    """Return pre-match form counts for a team-to-score market, or None for other markets."""
    if sel not in TEAM_GOAL_MARKETS:
        return None
    home_pick = sel == "HO05"
    scorer = getattr(r, "home" if home_pick else "away", None)
    opponent = getattr(r, "away" if home_pick else "home", None)
    attack = _recent(scorer, "last5")
    venue = _recent(scorer, "venue_last5")
    defense = _recent(opponent, "last5")
    return {
        "attack_scored": _positive_goal_count(attack, "gf", TEAM_GOAL_LAST_N),
        "attack_n": min(len(attack), TEAM_GOAL_LAST_N),
        "venue_scored": _positive_goal_count(venue, "gf", TEAM_GOAL_VENUE_N),
        "venue_n": min(len(venue), TEAM_GOAL_VENUE_N),
        "opponent_conceded": _positive_goal_count(defense, "ga", TEAM_GOAL_LAST_N),
        "opponent_n": min(len(defense), TEAM_GOAL_LAST_N),
        "venue": "home" if home_pick else "away",
    }


def team_goal_form_status(r, sel: str) -> tuple[bool, str]:
    """Fail closed on weak or insufficient recent scoring evidence for HO05/AO05 picks."""
    evidence = team_goal_form_evidence(r, sel)
    if evidence is None:
        return True, ""
    if evidence["attack_scored"] is None:
        return False, f"recent-form gate: only {evidence['attack_n']}/5 team matches available; need 5/5"
    if evidence["attack_scored"] < TEAM_GOAL_MIN_SCORED:
        return False, (f"recent-form gate: team scored in {evidence['attack_scored']}/5 recent matches; "
                       f"need at least {TEAM_GOAL_MIN_SCORED}/5")
    if evidence["venue_scored"] is None:
        return False, (f"recent-form gate: only {evidence['venue_n']}/3 recent {evidence['venue']} matches available; "
                       "need 3/3")
    if evidence["venue_scored"] < TEAM_GOAL_MIN_VENUE_SCORED:
        return False, (f"recent-form gate: team scored in {evidence['venue_scored']}/3 recent {evidence['venue']} matches; "
                       f"need at least {TEAM_GOAL_MIN_VENUE_SCORED}/3")
    if evidence["opponent_conceded"] is None:
        return False, f"recent-form gate: only {evidence['opponent_n']}/5 opponent matches available; need 5/5"
    if evidence["opponent_conceded"] < TEAM_GOAL_MIN_OPP_CONCEDED:
        return False, (f"recent-form gate: opponent conceded in {evidence['opponent_conceded']}/5 recent matches; "
                       f"need at least {TEAM_GOAL_MIN_OPP_CONCEDED}/5")
    return True, ""


def team_goal_form_ok(r, sel: str) -> bool:
    return team_goal_form_status(r, sel)[0]


# bets-of-the-day card: one section per market family, up to BOTD_PER_GROUP picks each, distinct matches per section
# (key, title, selection filter, minimum probability, picks per section). The card focuses on Over 1.5, Over 2.5, BTTS
# and bookings (user rule 2026-10-17: no team goals, no double chance, no unders). 1X2 / BTTS / Over 2.5 only enter
# with a strong signal (model at or above the section floor — 70%, or 55% for Over 2.5 and BTTS — AND recent form
# backing it — see scanner.strong_signal). One market per match across the whole card.
# Blocks of the "Bets of the day" card, in display order. A block shows only the bets that meet its
# threshold that day (1-2 is fine, never padded); a block that has no qualifying bet is hidden.
# `thr` is the section's default floor; a selection the policy names (Over 2.5, BTTS: 55%) starts from its own floor
# (policy.min_p). 2026-10-17: team goals left the Over 1.5 section; unders no longer exist upstream (policy.py).
BOTD_GROUPS = [
    ("o15", "Goals · Over 1.5", lambda sel: sel == "O15", 0.70, 7),
    ("o25", "Over 2.5 goals", lambda sel: sel in ("O25", "O35"), 0.70, 7),
    ("btts", "Both teams to score", lambda sel: sel == "BTTS", 0.70, 7),
    ("result", "1X2", lambda sel: sel in ("H", "A"), 0.70, 5),   # five 1X2 picks a day (user request)
    ("corners", "Corners", lambda sel: sel.startswith(("CO", "CH", "CA")), 0.65, 7),
    ("cards", "Bookings", lambda sel: sel.startswith(("KO", "KH", "KA")), 0.65, 7),
]


def botd_floor(gkey: str) -> float:
    """The lowest probability a section accepts (what the card shows as the section's minimum)."""
    for key, _title, match, thr, _cap in BOTD_GROUPS:
        if key == gkey:
            named = [f for code, f in policy.SEL_MIN_P.items() if match(code)]
            return min([thr] + named)
    return MIN_P
SIGNAL_SECTIONS = ("result", "btts", "o25")
BOTD_PER_GROUP = 3
ACCA_COLS = ["acca_id", "created", "run", "window_end", "n_legs", "legs", "odds", "p", "status", "settled_on", "note"]


# ----------------------------------------------------------------------------- selection codes
def _line(code: str) -> float:
    """'O25' -> 2.5, 'CU105' -> 10.5"""
    digits = "".join(ch for ch in code if ch.isdigit())
    return int(digits) / 10.0


def label(sel: str, home: str = "Home", away: str = "Away") -> str:
    if sel in ("H", "D", "A"):
        return {"H": f"{home} to win", "D": "Draw", "A": f"{away} to win"}[sel]
    if sel in ("1X", "12", "X2"):
        return {"1X": f"{home} or draw", "12": f"{home} or {away}", "X2": f"Draw or {away}"}[sel]
    if sel == "BTTS":
        return "Both teams to score"
    if sel == "NBTTS":
        return "Not both teams to score"
    if sel[0] in "OU" and sel[1:].isdigit():
        return f"{'Over' if sel[0] == 'O' else 'Under'} {_line(sel):.1f} goals"
    if sel[0] in "HA" and sel[1] in "OU":
        team = home if sel[0] == "H" else away
        return f"{team} {'over' if sel[1] == 'O' else 'under'} {_line(sel):.1f} goals"
    if sel[:2] in ("CH", "CA"):
        team = home if sel[1] == "H" else away
        return f"{team} {'over' if sel[2] == 'O' else 'under'} {_line(sel):.1f} corners"
    if sel[:2] in ("KH", "KA"):
        team = home if sel[1] == "H" else away
        return f"{team} {'over' if sel[2] == 'O' else 'under'} {_line(sel):.1f} cards"
    if sel[0] == "C":
        return f"{'Over' if sel[1] == 'O' else 'Under'} {_line(sel):.1f} corners"
    if sel[0] == "K":
        return f"{'Over' if sel[1] == 'O' else 'Under'} {_line(sel):.1f} cards"
    return sel


def group(sel: str) -> str:
    if sel in ("H", "D", "A"):
        return "result"
    if sel in ("1X", "12", "X2"):
        return "dc"
    if sel in ("BTTS", "NBTTS"):
        return "btts"
    if sel[0] in "OU":
        return "goals"
    if sel[0] in "HA":
        return "team"
    if sel[0] == "C":
        return "corners"
    return "cards"


def settle(sel: str, hg, ag, hc=None, ac=None, hcards=None, acards=None) -> bool | None:
    """True / False, or None when the selection cannot be graded from the available result data."""
    if hg is None or ag is None or _nan(hg) or _nan(ag):
        return None
    hg, ag = int(hg), int(ag)
    tot = hg + ag
    if sel in ("H", "D", "A", "1X", "12", "X2"):
        return {"H": hg > ag, "D": hg == ag, "A": ag > hg, "1X": hg >= ag, "12": hg != ag, "X2": ag >= hg}[sel]
    if sel == "BTTS":
        return hg > 0 and ag > 0
    if sel == "NBTTS":
        return not (hg > 0 and ag > 0)
    if sel[0] in "OU" and sel[1:].isdigit():
        return tot > _line(sel) if sel[0] == "O" else tot < _line(sel)
    if sel[0] in "HA" and sel[1] in "OU":
        g = hg if sel[0] == "H" else ag
        return g > _line(sel) if sel[1] == "O" else g < _line(sel)
    if sel[0] == "C":
        if hc is None or ac is None or _nan(hc) or _nan(ac):
            return None
        c = int(hc) + int(ac)
        return c > _line(sel) if sel[1] == "O" else c < _line(sel)
    if sel[0] == "K":
        if hcards is None or acards is None or _nan(hcards) or _nan(acards):
            return None
        k = int(hcards) + int(acards)
        return k > _line(sel) if sel[1] == "O" else k < _line(sel)
    return None


def _nan(x) -> bool:
    try:
        return isinstance(x, float) and math.isnan(x)
    except TypeError:
        return False


# ----------------------------------------------------------------------------- selections per fixture
def _two_way(o1, o2) -> float | None:
    if not o1 or not o2 or o1 <= 1 or o2 <= 1:
        return None
    return (1 / o1) / (1 / o1 + 1 / o2)


def _valid(p) -> bool:
    return p is not None and not (isinstance(p, float) and math.isnan(p)) and 0 < p < 1


@dataclass
class Sel:
    sel: str
    p_model: float
    p_sb: float | None
    odds: float | None

    @property
    def p(self) -> float:
        """Ranking probability = the football-data model probability (never blended with the market)."""
        return self.p_model

    @property
    def diff_pp(self) -> float | None:
        return None if self.p_sb is None else 100 * (self.p_model - self.p_sb)

    @property
    def ev(self) -> float | None:
        return None if not self.priced else self.p_model * self.odds - 1

    @property
    def group(self) -> str:
        return group(self.sel)

    @property
    def priced(self) -> bool:
        return self.odds is not None and self.odds > 1

    @property
    def diff(self) -> bool:
        return self.p_sb is not None and abs(self.p_model - self.p_sb) > DIFF_FLAG


def selections(r) -> list[Sel]:
    """All modelled selections of a MatchRow with model / Sportybet probabilities and the Sportybet price."""
    sb = r.sb or {}
    out: list[Sel] = []

    def add(code, p_model, p_sb=None, odds=None):
        if not policy.allowed(code):
            return      # market policy (2026-10-17): no team goals, no double chance, no unders in any market
        if not _valid(p_model):
            return
        price = float(odds) if odds and odds > 1 else None
        # user rule (2026-10-01): when BOTH the model and the market price this under 1.15 odds, the
        # selection is worthless — drop it everywhere (the match stays; its other markets remain listed)
        if price is not None and price < 1.15 and (1.0 / float(p_model)) < 1.15:
            return
        out.append(Sel(code, float(p_model), float(p_sb) if _valid(p_sb) else None, price))

    # match result / double chance
    x12 = r.extra.x12 or {}
    h, d, a = sb.get("1X2") or (None, None, None)
    m = markets.power_demargin([h, d, a]) if all(o and o > 1 for o in (h, d, a)) else None
    for code, o, idx in (("H", h, 0), ("D", d, 1), ("A", a, 2)):
        add(code, x12.get(code), m[idx] if m else None, o)
    dc = sb.get("DC") or {}
    for code, pair in (("1X", (0, 1)), ("12", (0, 2)), ("X2", (1, 2))):
        add(code, x12.get(code), (m[pair[0]] + m[pair[1]]) if m else None, dc.get(code))
    # total goals
    ou = sb.get("OU") or {}
    for line, key in ((0.5, "O05"), (1.5, "O15"), (2.5, "O25"), (3.5, "O35"), (4.5, "O45"), (5.5, "O55")):
        po = r.p_final.get(key)
        if not _valid(po):
            continue
        over, under = ou.get(line) or (None, None)
        p_sb_over = _two_way(over, under)
        add(key, po, p_sb_over, over)
        if line >= 1.5:
            add("U" + key[1:], 1 - po, (1 - p_sb_over) if p_sb_over is not None else None, under)
    # both teams to score
    pb = r.p_final.get("BTTS")
    yes, no = sb.get("BTTS") or (None, None)
    p_sb_b = _two_way(yes, no)
    add("BTTS", pb, p_sb_b, yes)
    add("NBTTS", 1 - pb if _valid(pb) else None, (1 - p_sb_b) if p_sb_b is not None else None, no)
    # team goals
    tg = r.extra.tg or {}
    for side, key in (("H", "TGH"), ("A", "TGA")):
        lines = sb.get(key) or {}
        for line, pk in ((0.5, f"{side}_o05"), (1.5, f"{side}_o15")):
            po = tg.get(pk)
            if not _valid(po):
                continue
            over, under = lines.get(line) or (None, None)
            p_sb_over = _two_way(over, under)
            add(f"{side}O{int(line * 10):02d}", po, p_sb_over, over)
            if line >= 1.5:
                add(f"{side}U{int(line * 10):02d}", 1 - po, (1 - p_sb_over) if p_sb_over is not None else None, under)
    # corners / cards (model; prices only when the full market list was fetched)
    full = r.sb_full or {}
    for prefix, probs, key in (("C", (r.extra.corner_p or {}).get("total"), "CORN"),
                               ("K", (r.extra.card_p or {}).get("total"), "CARDS")):
        if not probs:
            continue
        # user rule 2026-10-13: corners & bookings belong to the odds feature — the list feed now carries
        # the total lines for every priced fixture, the per-event full list adds deeper/team lines
        lines = full.get(key) or sb.get(key) or {}
        for line, po in probs.items():
            if not _valid(po):
                continue
            over, under = lines.get(float(line)) or (None, None)
            p_sb_over = _two_way(over, under)
            code = f"{int(float(line) * 10):03d}" if float(line) >= 10 else f"{int(float(line) * 10):02d}"
            add(f"{prefix}O{code}", po, p_sb_over, over)
            add(f"{prefix}U{code}", 1 - po, (1 - p_sb_over) if p_sb_over is not None else None, under)
    # team corners / cards (home/away over-under; prices come with the per-event full list)
    cp, kp = r.extra.corner_p or {}, r.extra.card_p or {}
    for prefix, pmap, lkh, lka in (("C", cp, "CORNH", "CORNA"), ("K", kp, "CARDSH", "CARDSA")):
        if not pmap:
            continue
        for side, pk, lk in (("H", "home", lkh), ("A", "away", lka)):
            tprobs = pmap.get(pk) or {}
            tlines = full.get(lk) or {}
            for line, po in tprobs.items():
                if not _valid(po):
                    continue
                over, under = tlines.get(float(line)) or (None, None)
                p_sb_over = _two_way(over, under)
                tcode = f"{int(float(line) * 10):03d}" if float(line) >= 10 else f"{int(float(line) * 10):02d}"
                add(f"{prefix}{side}O{tcode}", po, p_sb_over, over)
                add(f"{prefix}{side}U{tcode}", 1 - po, (1 - p_sb_over) if p_sb_over is not None else None, under)
    return out


def sel_dict(s: Sel, home: str, away: str) -> dict:
    """p / p_model = model probability; p_sb = market implied (comparison); fair = 1 / model probability;
    diff_pp = model − market in percentage points; ev = model probability × price − 1."""
    return {"sel": s.sel, "group": s.group, "label": label(s.sel, home, away), "p": round(s.p, 3),
            "p_model": round(s.p_model, 3), "p_sb": round(s.p_sb, 3) if s.p_sb is not None else None,
            "odds": round(s.odds, 2) if s.odds else None, "fair": round(1 / s.p, 2) if s.p > 0 else None,
            "diff": s.diff, "diff_pp": None if s.diff_pp is None else round(s.diff_pp, 1),
            "ev": None if s.ev is None else round(s.ev, 3)}


# ----------------------------------------------------------------------------- safest bets / trebles
@dataclass
class Bet:
    key: tuple           # (date, country, home, away)
    div: str
    league: str
    home: str
    away: str
    kickoff: str
    sel: str
    p: float
    p_model: float
    p_sb: float | None
    odds: float

    @property
    def label(self) -> str:
        return label(self.sel, self.home, self.away)

    @property
    def group(self) -> str:
        return group(self.sel)


def safest(rows: list, now: datetime, window_end: datetime, min_p: float = MIN_P,
           groups: tuple = SAFE_GROUPS, trebles: bool = False) -> dict:
    start = now + timedelta(minutes=10)
    bets: list[Bet] = []
    for r in rows:
        if not r.data_ok or r.fx["kickoff"] < start:
            continue
        fx = r.fx
        key = (fx["date"].strftime("%Y-%m-%d"), fx["country"], fx["home"], fx["away"])
        for s in selections(r):
            if s.sel in ("O05", "U55"):
                continue  # user decision 2026-10-01: Over 0.5 / Under 5.5 add no value on the safest board
            if not s.priced or s.p < policy.min_p(s.sel, min_p) or s.group not in groups:
                continue
            if OVERS_ONLY and is_under(s.sel):
                continue
            if s.sel in TEAM_GOAL_MARKETS and not team_goal_form_ok(r, s.sel):
                continue
            bets.append(Bet(key, fx["div"], fx["league"], fx["home"], fx["away"], fx["kickoff"].strftime("%Y-%m-%d %H:%M"),
                            s.sel, s.p, s.p_model, s.p_sb, s.odds))
    bets.sort(key=lambda b: (-b.p, -b.odds))
    # one market per match (the most probable): a clean record of which markets perform
    seen_match: set[tuple] = set()
    one = []
    for b in bets:
        if b.key in seen_match:
            continue
        seen_match.add(b.key)
        one.append(b)
    bets = one[:MAX_BETS]

    def pool_for(cands):
        best: dict[tuple, Bet] = {}
        for b in cands:
            if b.key not in best or (b.p, b.odds) > (best[b.key].p, best[b.key].odds):
                best[b.key] = b
        return sorted(best.values(), key=lambda b: (-b.p, -b.odds))

    short = [b for b in bets if datetime.strptime(b.kickoff, "%Y-%m-%d %H:%M") <= window_end.replace(tzinfo=None)]
    pool = pool_for(short)
    extended = False
    if len(pool) < TREBLES * LEGS:
        pool = pool_for(bets)
        extended = True
    out_trebles = []
    if trebles:
        for i in range(TREBLES):
            chunk = pool[i * LEGS:(i + 1) * LEGS]
            if len(chunk) < LEGS:
                break
            out_trebles.append(sorted(chunk, key=lambda b: b.kickoff))
    return {"bets": bets, "trebles": out_trebles, "extended": extended, "min_p": min_p,
            "floors": dict(policy.SEL_MIN_P)}


def acca_odds(legs: list[Bet]) -> float:
    o = 1.0
    for l in legs:
        o *= l.odds
    return o


def acca_p(legs: list[Bet]) -> float:
    p = 1.0
    for l in legs:
        p *= l.p
    return p


# ----------------------------------------------------------------------------- ledgers
def load_csv(path: Path, cols: list[str]) -> pd.DataFrame:
    if path.exists():
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        return df[cols]
    return pd.DataFrame(columns=cols)


def add_bets(df: pd.DataFrame, bets: list[Bet], now: datetime, run: str, kind: str = "safe") -> tuple[pd.DataFrame, list[Bet]]:
    """Append bets not yet in the ledger; returns (ledger, newly added bets) so new finds can be announced."""
    if "kind" not in df.columns:
        df["kind"] = "safe"
    existing = set(zip(df["match_date"], df["home"], df["away"], df["sel"]))
    # one market per match, whichever came first — but a row for a market the policy has since dropped (2026-10-17)
    # is history, not a rival: it must not stop the match from getting its new pick on the day the rule landed
    live_rows = df[df["sel"].astype(str).map(policy.allowed)] if not df.empty else df
    matches = set(zip(live_rows["match_date"], live_rows["home"], live_rows["away"]))
    new, added = [], []
    for b in bets:
        k = (b.key[0], b.home, b.away, b.sel)
        if k in existing:
            continue
        if (b.key[0], b.home, b.away) in matches:      # one market per match, whichever came first
            continue
        existing.add(k)
        matches.add((b.key[0], b.home, b.away))
        added.append(b)
        new.append({"match_date": b.key[0], "kickoff": b.kickoff, "country": b.key[1], "div": b.div, "league": b.league,
                    "home": b.home, "away": b.away, "sel": b.sel, "label": b.label, "p": f"{b.p:.3f}",
                    "p_model": f"{b.p_model:.3f}", "p_sb": f"{b.p_sb:.3f}" if b.p_sb is not None else "",
                    "odds": f"{b.odds:.2f}", "status": "pending", "score": "", "settled_on": "", "run": run,
                    "report_date": now.strftime("%Y-%m-%d"), "botd": "", "kind": kind})
    if new:
        df = pd.concat([df, pd.DataFrame(new, columns=SAFE_BET_COLS)], ignore_index=True)
    return df, added


def bet_id(match_date: str, home: str, away: str, sel: str) -> str:
    return f"{match_date}|{home}|{away}|{sel}"


def botd_candidates(rows: list, now: datetime, signal=None) -> list[Bet]:
    """Selections eligible for the day card: priced, overs only, model probability at or above the section
    threshold — odds never filter (no minimum price, market disagreements included; user decision 2026-10-01).
    Team-to-score picks need the shared recent-form gate; 1X2 / BTTS / Over 2.5 need `signal(r, sel)`."""
    start = now + timedelta(minutes=10)
    out: list[Bet] = []
    for r in rows:
        if not r.data_ok or r.fx["kickoff"] < start:
            continue
        fx = r.fx
        key = (fx["date"].strftime("%Y-%m-%d"), fx["country"], fx["home"], fx["away"])
        for s in selections(r):
            if not s.priced or is_under(s.sel):
                continue
            if s.sel in TEAM_GOAL_MARKETS and not team_goal_form_ok(r, s.sel):
                continue
            for gkey, _title, match, thr, _cap in BOTD_GROUPS:
                thr = policy.min_p(s.sel, thr)      # Over 2.5 / BTTS start from 55%, the rest keep the section floor
                if not match(s.sel) or s.p < thr:
                    continue
                if gkey in SIGNAL_SECTIONS:
                    if s.p_model < thr:
                        break
                    if signal is not None and not signal(r, s.sel):
                        break
                out.append(Bet(key, fx["div"], fx["league"], fx["home"], fx["away"], fx["kickoff"].strftime("%Y-%m-%d %H:%M"),
                               s.sel, s.p, s.p_model, s.p_sb, s.odds))
                break
    out.sort(key=lambda b: (-b.p, -b.odds))
    return out


def botd_group(sel: str) -> str | None:
    for gkey, _title, match, _thr, _cap in BOTD_GROUPS:
        if match(sel):
            return gkey
    return None


def pick_bets_of_the_day(df: pd.DataFrame, now: datetime, n: int = BOTD_PER_GROUP,
                         candidates: list[Bet] | None = None, run: str = "") -> pd.DataFrame:
    """Sticky, grouped 'bets of the day': for every section of BOTD_GROUPS the most probable eligible selections on
    today's matches, up to the section's cap (7 per block, never padded — a block shows only bets that meet its
    threshold and is hidden when it has none), one market per match across the whole card. Picked by the first run
    that sees them and kept for the day; a section is only topped up while it has fewer picks than its cap.
    Candidates not yet in the ledger are added with kind='botd' so they are graded like everything else
    (`n` is kept for compatibility and no longer used)."""
    today = now.strftime("%Y-%m-%d")
    df = df.copy()
    for col, default in (("botd", ""), ("kind", "safe")):
        if col not in df.columns:
            df[col] = default
    df["botd"] = df["botd"].replace({"1": "o15"})           # v4 cards were goals-only
    # market policy (2026-10-17): a PENDING pick made earlier under the old rules that the policy no longer allows
    # (team goals, double chance, unders) leaves today's card. Settled picks stay — they are history. A row that was
    # added only for the card is removed (no board shows it); one that also belongs to the safest record just loses
    # the card flag. Without this the sticky card would keep showing dropped markets until midnight.
    if not df.empty and "sel" in df.columns:
        stale = ((df["match_date"] == today) & (df["botd"].astype(str) != "") & (df["status"] == "pending")
                 & ~df["sel"].astype(str).map(policy.allowed))
        if stale.any():
            only_card = stale & (df["kind"].fillna("safe").replace("", "safe") == "botd")
            df.loc[stale & ~only_card, "botd"] = ""
            df = df[~only_card].reset_index(drop=True)
    # candidates from this run's rows (today only), most probable first
    cands = [b for b in (candidates or []) if b.key[0] == today]
    cands.sort(key=lambda b: (-b.p, -b.odds))
    df_today = df[df["match_date"] == today]
    # one market per match across the whole card
    used = set(zip(df_today.loc[df_today["botd"].astype(str) != "", "home"], df_today.loc[df_today["botd"].astype(str) != "", "away"]))
    # fill priority: 1X2 and Over 2.5 claim their matches first (Goals has the deepest candidate pool and would
    # otherwise consume every match before the signal-gated sections get a chance); display order is unchanged
    groups_by_key = {g[0]: g for g in BOTD_GROUPS}
    for gkey in ("result", "o25", "o15", "btts", "corners", "cards"):
        g = groups_by_key[gkey]
        match, thr, cap = g[2], g[3], g[4]
        have = int((df_today["botd"] == gkey).sum())
        if have >= cap:
            continue
        for b in cands:
            if have >= cap:
                break
            if botd_group(b.sel) != gkey or (b.home, b.away) in used:
                continue
            same_match = (df["match_date"] == today) & (df["home"] == b.home) & (df["away"] == b.away)
            mask = same_match & (df["sel"] == b.sel)
            if mask.any():
                idx = df.index[mask][0]
                if df.loc[idx, "status"] != "pending" or df.loc[idx, "botd"]:
                    continue
                df.loc[idx, "botd"] = gkey
            elif (same_match & df["sel"].astype(str).map(policy.allowed)).any():
                # the match already carries another market in the ledger: keep one market per match
                # (ledger rows for markets the policy has since dropped do not count — they are history, not rivals)
                continue
            else:
                df, _ = add_bets(df, [b], now, run, kind="botd")
                df.loc[df.index[-1], "botd"] = gkey
            used.add((b.home, b.away))
            have += 1
    return df


def bets_of_the_day(df: pd.DataFrame, now: datetime) -> dict:
    """{"date", "groups": [{key, title, bets}], "bets": flat list} for today's card."""
    today = now.strftime("%Y-%m-%d")
    out = {"date": today, "groups": [], "bets": []}
    if df.empty or "botd" not in df.columns:
        return out
    rows = df[(df["match_date"] == today) & (df["botd"].astype(str) != "")]
    flat = []
    for r in rows.itertuples():
        flat.append({"id": bet_id(r.match_date, r.home, r.away, r.sel), "kickoff": r.kickoff, "country": r.country,
                     "league": r.league, "home": r.home, "away": r.away, "sel": r.sel, "group": group(r.sel),
                     "section": r.botd if r.botd in {g[0] for g in BOTD_GROUPS} else "o15",
                     "label": r.label, "p": float(r.p) if r.p else None, "odds": float(r.odds) if r.odds else None,
                     "status": r.status, "score": r.score or None})
    flat.sort(key=lambda b: (-(b["p"] or 0), b["kickoff"]))
    for gkey, title, _match, thr, _cap in BOTD_GROUPS:
        bets = [b for b in flat if b["section"] == gkey]
        if bets:
            out["groups"].append({"key": gkey, "title": title, "min_p": botd_floor(gkey), "bets": bets})
    out["bets"] = flat
    return out


def legs_json(legs: list[Bet]) -> str:
    return json.dumps([{"date": l.key[0], "country": l.key[1], "league": l.league, "home": l.home, "away": l.away,
                        "kickoff": l.kickoff, "sel": l.sel, "odds": round(l.odds, 2), "p": round(l.p, 4)} for l in legs])


def add_accas(df: pd.DataFrame, trebles: list[list[Bet]], now: datetime, run: str, window_end: datetime) -> tuple[pd.DataFrame, list[str]]:
    def key_of(legs):
        return "|".join(sorted(f"{l['date']}:{l['home']}:{l['away']}:{l['sel']}" for l in legs))
    existing = {}
    for r in df.itertuples():
        try:
            existing[key_of(json.loads(r.legs))] = r.acca_id
        except (TypeError, ValueError):
            continue
    day = now.strftime("%Y%m%d")
    seq = sum(1 for x in df["acca_id"] if str(x).startswith(f"S{day}-"))
    ids, new = [], []
    for legs in trebles:
        lj = json.loads(legs_json(legs))
        k = key_of(lj)
        if k in existing:
            ids.append(existing[k])
            continue
        seq += 1
        aid = f"S{day}-{seq:02d}"
        ids.append(aid)
        existing[k] = aid
        new.append({"acca_id": aid, "created": now.strftime("%Y-%m-%d %H:%M"), "run": run,
                    "window_end": window_end.strftime("%Y-%m-%d %H:%M"), "n_legs": str(len(legs)),
                    "legs": json.dumps(lj), "odds": f"{acca_odds(legs):.2f}", "p": f"{acca_p(legs):.3f}",
                    "status": "pending", "settled_on": "", "note": ""})
    if new:
        df = pd.concat([df, pd.DataFrame(new, columns=ACCA_COLS)], ignore_index=True)
    return df, ids


def _lookup(results: pd.DataFrame, country: str, home: str, away: str, date: str):
    if results is None or results.empty:
        return None
    try:
        mdate = pd.Timestamp(date)
    except (ValueError, TypeError):
        return None
    m = results[(results["home"] == home) & (results["away"] == away) & (results["country"] == country) &
                ((results["date"] - mdate).abs() <= pd.Timedelta(days=3))]
    return None if m.empty else m.iloc[0]


def _cards(row, side: str):
    y, r = row.get(f"{side}y"), row.get(f"{side}r")
    if y is None or _nan(y):
        return None
    return float(y) + (0.0 if r is None or _nan(r) else float(r))


def settle_bets(df: pd.DataFrame, results: pd.DataFrame, today: datetime) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    for i, r in df[df["status"] == "pending"].iterrows():
        row = _lookup(results, r["country"], r["home"], r["away"], r["match_date"])
        if row is not None:
            ok = settle(r["sel"], row["hg"], row["ag"], row.get("hc"), row.get("ac"), _cards(row, "h"), _cards(row, "a"))
            if ok is not None:
                df.loc[i, ["status", "score", "settled_on"]] = ["hit" if ok else "miss", f"{int(row['hg'])}-{int(row['ag'])}",
                                                                today.strftime("%Y-%m-%d")]
                continue
        if (pd.Timestamp(today.date()) - pd.Timestamp(r["match_date"])).days > 21:
            df.loc[i, ["status", "settled_on"]] = ["void", today.strftime("%Y-%m-%d")]
    return df


def settle_accas(df: pd.DataFrame, results: pd.DataFrame, today: datetime) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    for i, r in df[df["status"] == "pending"].iterrows():
        try:
            legs = json.loads(r["legs"])
        except (TypeError, ValueError):
            continue
        outcomes = []
        for l in legs:
            row = _lookup(results, l["country"], l["home"], l["away"], l["date"])
            ok = None
            if row is not None:
                ok = settle(l["sel"], row["hg"], row["ag"], row.get("hc"), row.get("ac"), _cards(row, "h"), _cards(row, "a"))
                l["score"] = f"{int(row['hg'])}-{int(row['ag'])}"
            l["result"] = None if ok is None else ("won" if ok else "lost")
            outcomes.append(ok)
        if any(o is False for o in outcomes):
            status = "lost"
        elif all(o is True for o in outcomes):
            status = "won"
        else:
            oldest = min(pd.Timestamp(l["date"]) for l in legs)
            status = "void" if (pd.Timestamp(today.date()) - oldest).days > 21 else "pending"
        if status != "pending":
            df.loc[i, ["status", "settled_on", "legs"]] = [status, today.strftime("%Y-%m-%d"), json.dumps(legs)]
        else:
            df.loc[i, "legs"] = json.dumps(legs)
    return df


def _stats(df: pd.DataFrame, won_label: str) -> dict:
    settled = df[df["status"].isin([won_label, "lost" if won_label == "won" else "miss"])]
    n = len(settled)
    won = int((settled["status"] == won_label).sum())
    odds = pd.to_numeric(settled["odds"], errors="coerce")
    p = pd.to_numeric(settled["p"], errors="coerce")
    ret = float(((odds * (settled["status"] == won_label)).sum() - n) / n) if n else None
    return {"n": n, "won": won, "rate": (won / n) if n else None, "exp_rate": float(p.mean()) if n else None,
            "avg_odds": float(odds.mean()) if n else None, "roi": ret}


def summary(bets: pd.DataFrame, accas: pd.DataFrame, today: datetime) -> dict:
    cut = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    all_bets = bets
    if not bets.empty and "kind" in bets.columns:
        bets = bets[bets["kind"].fillna("safe").replace("", "safe") != "botd"]     # the safest-bet record proper
    out = {"bets": {"all": _stats(bets, "hit"), "30d": _stats(bets[bets["match_date"] >= cut], "hit"),
                    "pending": int((bets["status"] == "pending").sum()) if not bets.empty else 0},
           "accas": {"all": _stats(accas, "won"), "30d": _stats(accas[accas["created"] >= cut], "won"),
                     "pending": int((accas["status"] == "pending").sum()) if not accas.empty else 0}}
    by_group = {}
    if not bets.empty:
        for g in GROUPS:
            sub = bets[bets["sel"].map(group) == g]
            if len(sub):
                by_group[g] = _stats(sub, "hit")
    out["bets"]["by_group"] = by_group
    bets = all_bets
    if not bets.empty and "botd" in bets.columns:
        bd = bets[bets["botd"].astype(str).replace({"1": "o15"}) != ""]
        out["botd"] = {"all": _stats(bd, "hit"), "30d": _stats(bd[bd["match_date"] >= cut], "hit"),
                       "pending": int((bd["status"] == "pending").sum()), "by_section": {}}
        for gkey, title, _m, _t, _c in BOTD_GROUPS:
            sub = bd[bd["botd"].astype(str).replace({"1": "o15"}) == gkey]
            if len(sub):
                out["botd"]["by_section"][gkey] = dict(_stats(sub, "hit"), title=title)
    else:
        out["botd"] = {"all": _stats(bets.iloc[0:0], "hit"), "30d": _stats(bets.iloc[0:0], "hit"), "pending": 0, "by_section": {}}
    return out
