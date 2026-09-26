"""Parlay builder + ledger (v3).

Strategy (chosen from backtest/PARLAY_EXPERIMENT.md, real opening prices, 2023-26):
* legs only from markets with real prices: 1X2, double chance, Over/Under 2.5;
* each leg carries a *calibrated* probability (90% sharp-market fair price via power de-margin, 10% model);
* the parlay maximises expected return  prod(p_i * odds_i)  subject to combined odds in [2.70, 3.50],
  2-4 legs from distinct matches; the three parlays of a run use disjoint matches.
  Backtest: this beats the naive "highest-probability legs" rule by ~10 points of ROI, but it is still
  negative at average prices (train -3.6%, test -12.7%) — the report says so.
"""
from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BAND = (2.70, 3.50)
N_PARLAYS = 3
MAX_LEGS = 4
POOL = 30
MAX_LEG_ODDS = 6.0
LEDGER_COLS = ["parlay_id", "created", "run", "window_end", "n_legs", "legs", "odds", "p", "ev", "price_source",
               "status", "settled_on", "note"]

SEL_LABEL = {"H": "Home win", "D": "Draw", "A": "Away win", "1X": "Home or draw (1X)", "12": "Home or away (12)",
             "X2": "Draw or away (X2)", "O25": "Over 2.5 goals", "U25": "Under 2.5 goals"}


@dataclass
class Leg:
    date: str
    country: str
    league: str
    home: str
    away: str
    kickoff: str
    sel: str          # H D A 1X 12 X2 O25 U25
    odds: float
    p: float          # calibrated probability
    source: str       # "Sportybet" or "avg market"

    @property
    def match(self) -> str:
        return f"{self.home} v {self.away}"

    @property
    def key(self) -> tuple:
        return (self.date, self.country, self.home, self.away)

    @property
    def ev(self) -> float:
        return self.p * self.odds - 1

    @property
    def fair_odds(self) -> float:
        return 1 / self.p if self.p > 0 else float("nan")

    @property
    def label(self) -> str:
        return SEL_LABEL.get(self.sel, self.sel)


def candidate_legs(fx: pd.Series, p12: dict, p_o25: float, prices: dict | None, source: str) -> list[Leg]:
    """prices: {"1X2": (h, d, a), "DC": {"1X":..,"12":..,"X2":..}, "OU": {2.5: (over, under)}}."""
    if not prices:
        return []
    legs = []
    date = fx["date"].strftime("%Y-%m-%d")
    ko = fx["kickoff"].strftime("%Y-%m-%d %H:%M")
    base = dict(date=date, country=fx["country"], league=fx["league"], home=fx["home"], away=fx["away"], kickoff=ko, source=source)
    h, d, a = prices.get("1X2") or (None, None, None)
    dc = prices.get("DC") or {}
    ou = (prices.get("OU") or {}).get(2.5) or (None, None)
    cands = [("H", p12.get("H"), h), ("D", p12.get("D"), d), ("A", p12.get("A"), a),
             ("1X", p12.get("1X"), dc.get("1X")), ("12", p12.get("12"), dc.get("12")), ("X2", p12.get("X2"), dc.get("X2"))]
    if p_o25 is not None and not math.isnan(p_o25):
        cands += [("O25", p_o25, ou[0]), ("U25", 1 - p_o25, ou[1])]
    for sel, p, o in cands:
        if p is None or o is None or math.isnan(p) or p <= 0.02 or not (1.01 < o <= MAX_LEG_ODDS):
            continue
        legs.append(Leg(sel=sel, odds=float(o), p=float(p), **base))
    return legs


def build_parlays(legs: list[Leg], lo: float = BAND[0], hi: float = BAND[1], n_parlays: int = N_PARLAYS,
                  max_legs: int = MAX_LEGS) -> list[list[Leg]]:
    """Max expected return combos inside the odds band; distinct matches within and across parlays."""
    legs = sorted(legs, key=lambda l: -(l.p * l.odds))[:POOL]
    chosen: list[list[Leg]] = []
    used: set = set()
    for _ in range(n_parlays):
        pool = [l for l in legs if l.key not in used]
        best, best_v = None, -1.0
        for k in range(2, max_legs + 1):
            for combo in itertools.combinations(pool, k):
                if len({c.key for c in combo}) < k:
                    continue
                odds = float(np.prod([c.odds for c in combo]))
                if odds < lo or odds > hi:
                    continue
                v = float(np.prod([c.p * c.odds for c in combo]))
                if v > best_v:
                    best, best_v = combo, v
        if best is None:
            break
        chosen.append(sorted(best, key=lambda l: l.kickoff))
        used |= {c.key for c in best}
    return chosen


def parlay_odds(pl: list[Leg]) -> float:
    return float(np.prod([l.odds for l in pl]))


def parlay_p(pl: list[Leg]) -> float:
    return float(np.prod([l.p for l in pl]))


def legs_key(pl: list[Leg]) -> str:
    return "|".join(sorted(f"{l.date}:{l.home}:{l.away}:{l.sel}" for l in pl))


# ----------------------------------------------------------------------------- ledger
def load_ledger(path: Path) -> pd.DataFrame:
    if path.exists():
        t = pd.read_csv(path, dtype=str, keep_default_na=False)
        for c in LEDGER_COLS:
            if c not in t.columns:
                t[c] = ""
        return t[LEDGER_COLS]
    return pd.DataFrame(columns=LEDGER_COLS)


def _legs_from_json(s: str) -> list[Leg]:
    try:
        return [Leg(**{k: v for k, v in d.items() if k in Leg.__dataclass_fields__}) for d in json.loads(s)]
    except (ValueError, TypeError):
        return []


def existing_keys(ledger: pd.DataFrame) -> set:
    return {legs_key(_legs_from_json(s)) for s in ledger["legs"]} if not ledger.empty else set()


def add_parlays(ledger: pd.DataFrame, parlays: list[list[Leg]], now: datetime, run: str, window_end: datetime,
                source: str) -> tuple[pd.DataFrame, list[str]]:
    """Append new parlays (identical leg-sets already in the ledger are not duplicated). Returns ids."""
    keys = existing_keys(ledger)
    ids = []
    new = []
    day = now.strftime("%Y%m%d")
    seq = int(sum(ledger["parlay_id"].str.startswith(day)) if not ledger.empty else 0)
    for pl in parlays:
        k = legs_key(pl)
        if k in keys:
            match = ledger[ledger["legs"].map(lambda s: legs_key(_legs_from_json(s)) == k)]
            ids.append(str(match["parlay_id"].iloc[0]) if not match.empty else "")
            continue
        seq += 1
        pid = f"{day}-{seq:02d}"
        ids.append(pid)
        keys.add(k)
        new.append({"parlay_id": pid, "created": now.strftime("%Y-%m-%d %H:%M"), "run": run,
                    "window_end": window_end.strftime("%Y-%m-%d %H:%M"), "n_legs": str(len(pl)),
                    "legs": json.dumps([asdict(l) for l in pl], ensure_ascii=False),
                    "odds": f"{parlay_odds(pl):.2f}", "p": f"{parlay_p(pl):.3f}",
                    "ev": f"{parlay_p(pl) * parlay_odds(pl) - 1:+.3f}", "price_source": source,
                    "status": "pending", "settled_on": "", "note": ""})
    if new:
        ledger = pd.concat([ledger, pd.DataFrame(new, columns=LEDGER_COLS)], ignore_index=True)
    return ledger, ids


def leg_result(leg: Leg, results: pd.DataFrame) -> bool | None:
    if results.empty:
        return None
    mdate = pd.Timestamp(leg.date)
    m = results[(results["home"] == leg.home) & (results["away"] == leg.away) & (results["country"] == leg.country) &
                ((results["date"] - mdate).abs() <= pd.Timedelta(days=3))]
    if m.empty:
        return None
    hg, ag = int(m.iloc[0]["hg"]), int(m.iloc[0]["ag"])
    return {"H": hg > ag, "D": hg == ag, "A": hg < ag, "1X": hg >= ag, "12": hg != ag, "X2": hg <= ag,
            "O25": hg + ag >= 3, "U25": hg + ag < 3}[leg.sel]


def settle(ledger: pd.DataFrame, results: pd.DataFrame, today: datetime) -> pd.DataFrame:
    if ledger.empty:
        return ledger
    ledger = ledger.copy()
    for i, r in ledger[ledger["status"] == "pending"].iterrows():
        legs = _legs_from_json(r["legs"])
        if not legs:
            ledger.loc[i, ["status", "settled_on", "note"]] = ["void", today.strftime("%Y-%m-%d"), "unreadable legs"]
            continue
        outcomes = [leg_result(l, results) for l in legs]
        notes = [f"{l.match} {l.label}: {'✅' if o else ('❌' if o is False else '⏳')}" for l, o in zip(legs, outcomes)]
        if any(o is False for o in outcomes):
            ledger.loc[i, ["status", "settled_on", "note"]] = ["lost", today.strftime("%Y-%m-%d"), "; ".join(notes)]
        elif all(o is True for o in outcomes):
            ledger.loc[i, ["status", "settled_on", "note"]] = ["won", today.strftime("%Y-%m-%d"), "; ".join(notes)]
        else:
            oldest = min(pd.Timestamp(l.date) for l in legs)
            if (pd.Timestamp(today.date()) - oldest).days > 21:
                ledger.loc[i, ["status", "settled_on", "note"]] = ["void", today.strftime("%Y-%m-%d"), "result not found"]
    return ledger


def summary(ledger: pd.DataFrame, today: datetime) -> dict:
    out = {"all": _stats(ledger), "30d": _stats(ledger[ledger["created"] >= (today - timedelta(days=30)).strftime("%Y-%m-%d")])
           if not ledger.empty else _stats(ledger), "by_run": {}, "pending": int((ledger["status"] == "pending").sum()) if not ledger.empty else 0}
    if not ledger.empty:
        for run, g in ledger.groupby("run"):
            out["by_run"][run] = _stats(g)
    return out


def _stats(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {"n": 0, "won": 0, "rate": float("nan"), "roi": float("nan"), "avg_odds": float("nan"), "exp_rate": float("nan")}
    s = df[df["status"].isin(["won", "lost"])]
    if s.empty:
        return {"n": 0, "won": 0, "rate": float("nan"), "roi": float("nan"), "avg_odds": float("nan"), "exp_rate": float("nan")}
    odds = pd.to_numeric(s["odds"], errors="coerce").fillna(0)
    won = (s["status"] == "won").astype(float)
    p = pd.to_numeric(s["p"], errors="coerce")
    return {"n": len(s), "won": int(won.sum()), "rate": float(won.mean()), "roi": float((odds * won).sum() / len(s) - 1),
            "avg_odds": float(odds.mean()), "exp_rate": float(p.mean())}


def recent(ledger: pd.DataFrame, n: int = 12) -> list[dict]:
    if ledger.empty:
        return []
    out = []
    for r in ledger.sort_values("created", ascending=False).head(n).itertuples():
        out.append({"id": r.parlay_id, "created": r.created, "run": r.run, "odds": r.odds, "p": r.p, "status": r.status,
                    "legs": _legs_from_json(r.legs), "note": r.note})
    return out
