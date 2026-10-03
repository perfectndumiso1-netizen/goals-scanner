"""Daily accas at a target price (3.00), built from the *vetted* part of the board, tracked and settled
like every other bet.

Why this exists: a probability-sorted board is not a betting plan. The highest model numbers on an
ungated board are its biggest errors — a friendly where the model rates the underdog 29% while the market
prices it 0.6%, a cup qualifier the model has at 64% against a 17% price. Those legs are exactly what a
"top picks" sort surfaces, and exactly what a punter building by hand will pick. So the legs are gated
first, and only then are accas built:

  gate (all of it, not any of it)
    · the match passed the pipeline's own data checks (`data_ok`) — the same gate the safest board uses;
    · it is priced by Sportybet and kicks off in the future;
    · leg odds inside [MIN_ODDS, MAX_LEG_ODDS] — a 3.00 acca never needs a 1.20 leg or a 6.00 one;
    · a de-vigged market probability exists (`p_sb`) so the edge is measurable against the market's view
      rather than against the raw price (which still contains the bookmaker's margin);
    · the model is genuinely likely to be right: p_model >= MIN_MODEL_P;
    · the model beats that de-vigged market by between MIN_EDGE and MAX_EDGE. Below: paying the vig for
      nothing. Above: a data fault, not an edge — the biggest gaps in the live feed are all broken data
      (see README of the acca work), so they are rejected rather than sold as value.

  build
    · maximise the COMBINED model probability subject to |odds - target| <= TOL — never fill the last
      gap with a short-priced leg "to reach the price". A 3.00 acca made of 6 legs at 1.20 costs about
      40% in vig where 2 legs at 1.73 costs about 15%;
    · at most MAX_LEGS legs (and at least MIN_LEGS: an acca is an acca);
    · one leg per match, and the N accas never share a match, so a single shock cannot take all of them.

The record is written to data/accas.csv (status pending -> won/lost) so the honest question can be settled
with evidence: does a model-built 3.00 acca return more than the 3.00 it costs, per unit staked?
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import safe as safe_mod
from safe import Bet

# ------------------------------------------------------------------ the plan
import os

TARGET = float(os.getenv("ACCA_TARGET", "3.00"))   # the price the user wants to play each day
N_ACCAS = int(os.getenv("ACCA_N", "3"))            # three a day (user request)
MIN_LEGS, MAX_LEGS = int(os.getenv("ACCA_MIN_LEGS", "2")), int(os.getenv("ACCA_MAX_LEGS", "3"))
# never pad: fewer legs at the same payout is strictly less vig. On a thin board the legs are too short to
# reach the target at all (a football-data-only day: 37 matches, best 3-leg price 2.90) — the honest answer
# there is no acca, and ACCA_MAX_LEGS=4 is the lever if you would rather have a longer build than none.
TOL = float(os.getenv("ACCA_TOL", "0.02"))         # how far from the target a build may land (2.98-3.02)

# ------------------------------------------------------------------ the gates
MIN_ODDS, MAX_LEG_ODDS = 1.19, 2.60
MIN_MODEL_P = 0.55
MIN_EDGE = 0.02        # must beat the de-vigged market at all
MAX_EDGE = 0.12        # beyond this the model is not "value", it is wrong (data fault)
VIG = 0.086            # measured median two-way margin in the feed — used for the honest no-edge line

ACCA_COLS = ["acca_id", "created", "run", "window_end", "target", "n_legs", "legs", "odds", "p", "p_market",
             "status", "settled_on", "note"]


def leg_edge(b: Bet) -> float | None:
    """Model probability minus the de-vigged market probability (percentage points are the caller's business)."""
    return None if b.p_sb is None else b.p_model - b.p_sb


def gate(bets: list[Bet], min_odds: float = MIN_ODDS, max_odds: float = MAX_LEG_ODDS, min_p: float = MIN_MODEL_P,
         min_edge: float = MIN_EDGE, max_edge: float = MAX_EDGE) -> list[Bet]:
    """The vetted pool: only legs where the model beats a de-vigged market by a believable margin."""
    out = []
    for b in bets:
        if b.odds is None or b.odds <= 1 or not (min_odds <= b.odds <= max_odds):
            continue
        if b.p_model is None or b.p_model < min_p:
            continue
        e = leg_edge(b)
        if e is None or e < min_edge or e > max_edge:
            continue
        out.append(b)
    return out


def pool_from_rows(rows: list, now: datetime, window_end: datetime | None = None) -> list[Bet]:
    """Every gated leg due to start inside the app window (the same fixture rows the boards are built from).

    `window_end` must be the end of the window the USER sees (scanner: ctx["app_end"] = now + APP_WINDOW_HOURS),
    not the next report hour — passing the next report hour silently empties the pool, because most of a day's
    fixtures kick off after it.
    """
    start = now + timedelta(minutes=10)
    bets: list[Bet] = []
    for r in rows:
        if not getattr(r, "data_ok", False):
            continue
        fx = r.fx
        ko = fx["kickoff"]
        if ko < start:
            continue
        if window_end is not None and ko > window_end:
            continue        # the app window, exactly: the builds must be playable within the day the user sees
        key = (fx["date"].strftime("%Y-%m-%d"), fx["country"], fx["home"], fx["away"])
        for s in safe_mod.selections(r):
            if not s.priced:
                continue
            bets.append(Bet(key, fx["div"], fx["league"], fx["home"], fx["away"],
                            fx["kickoff"].strftime("%Y-%m-%d %H:%M"), s.sel, s.p, s.p_model, s.p_sb, s.odds))
    return gate(bets)


def _one_per_match(bets: list[Bet]) -> list[Bet]:
    """Within a match keep a single leg — the one with the highest model probability (ties: shorter price)."""
    best: dict[tuple, Bet] = {}
    for b in bets:
        cur = best.get(b.key)
        if cur is None or (b.p, b.odds) > (cur.p, cur.odds):
            best[b.key] = b
    return list(best.values())


def best_combo(pool: list[Bet], target: float = TARGET, min_legs: int = MIN_LEGS, max_legs: int = MAX_LEGS,
               tol: float = TOL, step: float = 0.002) -> list[Bet] | None:
    """Highest combined model probability whose price lands on the target (one leg per match, <= max_legs legs).

    A small dynamic program over log-odds: for every (leg count, price bucket) it keeps the best combined
    probability seen. The tolerance is then checked on the ACTUAL price of each candidate — a bucket index
    is an approximation, and accepting a bucket that is `tol` away in log space silently accepts a price
    that is 3x further away in price space (2.93 passed as "3.00" until this was exact).
    """
    T = math.log(target)
    lo, hi = math.log(target - tol), math.log(target + tol)
    K = int(round(hi / step))                  # the axis must reach past the target
    dp: dict[tuple[int, int], tuple[float, list[Bet]]] = {(0, 0): (0.0, [])}
    for b in _one_per_match(pool):
        off = int(round(math.log(b.odds) / step))
        if off > K:
            continue
        nxt = dict(dp)
        for (k, i), (val, legs) in dp.items():
            if k >= max_legs or i + off > K:
                continue
            cand = (val + math.log(b.p_model), legs + [b])
            key = (k + 1, i + off)
            if key not in nxt or cand[0] > nxt[key][0]:
                nxt[key] = cand
        dp = nxt
    ok = []
    for (k, i), (val, legs) in dp.items():
        if not legs or not (min_legs <= k <= max_legs) or not (lo <= i * step <= hi):
            continue
        price = acca_odds(legs)
        if abs(price - target) <= tol:         # exact, not the bucket
            ok.append((val, legs))
    return max(ok, key=lambda x: x[0])[1] if ok else None


def plan(pool: list[Bet], target: float = TARGET, n: int = N_ACCAS, min_legs: int = MIN_LEGS,
         max_legs: int = MAX_LEGS, tol: float = TOL) -> list[list[Bet]]:
    """Up to `n` disjoint accas: build the best one, remove its matches, build the next, and so on."""
    out: list[list[Bet]] = []
    used: set[tuple] = set()
    for _ in range(max(0, n)):
        combo = best_combo([b for b in pool if b.key not in used], target, min_legs, max_legs, tol)
        if not combo:
            break
        out.append(sorted(combo, key=lambda b: b.kickoff))
        used.update(b.key for b in combo)
    return out


# ------------------------------------------------------------------ ledger
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


def acca_p_market(legs: list[Bet]) -> float:
    """What the market thinks the acca is worth — its de-vigged probability at publication, compounded."""
    p = 1.0
    for l in legs:
        p *= (l.p_sb if l.p_sb is not None else 1.0 / l.odds)   # no de-vigged view: fall back to the raw price
    return p


def legs_json(legs: list[Bet]) -> str:
    """The stored legs. The keys `date` / `country` / `home` / `away` / `sel` are the settlement contract
    (safe.settle_accas looks matches up with them); the rest is for the card and the record."""
    return json.dumps([{"date": l.key[0], "country": l.key[1], "league": l.league, "home": l.home, "away": l.away,
                        "kickoff": l.kickoff, "sel": l.sel, "label": l.label, "odds": round(l.odds, 2),
                        "p": round(l.p, 4), "p_market": round(l.p_sb, 4) if l.p_sb is not None else None,
                        "edge_pp": round(100 * (l.p_model - l.p_sb), 1) if l.p_sb is not None else None}
                       for l in legs])


def add(df: pd.DataFrame, plans: list[list[Bet]], now: datetime, run: str, window_end: datetime,
        target: float = TARGET) -> tuple[pd.DataFrame, list[str]]:
    """Append this run's builds; a build whose legs are already recorded keeps its existing id (no duplicates)."""
    def key_of(legs) -> str:
        return "|".join(sorted(f"{l['date']}:{l['home']}:{l['away']}:{l['sel']}" for l in legs))

    existing: dict[str, str] = {}
    if not df.empty:
        for r in df.itertuples():
            try:
                existing[key_of(json.loads(r.legs))] = r.acca_id
            except (TypeError, ValueError):
                continue
    day = now.strftime("%Y%m%d")
    seq = int(sum(1 for x in (df["acca_id"] if not df.empty else []) if str(x).startswith(f"A{day}-")))
    ids: list[str] = []
    new = []
    for legs in plans:
        lj = json.loads(legs_json(legs))
        k = key_of(lj)
        if k in existing:
            ids.append(existing[k])
            continue
        seq += 1
        aid = f"A{day}-{seq:02d}"
        ids.append(aid)
        existing[k] = aid
        new.append({"acca_id": aid, "created": now.strftime("%Y-%m-%d %H:%M"), "run": run,
                    "window_end": window_end.strftime("%Y-%m-%d %H:%M"), "target": f"{target:.2f}",
                    "n_legs": str(len(legs)), "legs": json.dumps(lj), "odds": f"{acca_odds(legs):.2f}",
                    "p": f"{acca_p(legs):.4f}", "p_market": f"{acca_p_market(legs):.4f}",
                    "status": "pending", "settled_on": "", "note": ""})
    if new:
        df = pd.concat([df, pd.DataFrame(new, columns=ACCA_COLS)], ignore_index=True)
    return df, ids


def settle(df: pd.DataFrame, results: pd.DataFrame, today: datetime) -> pd.DataFrame:
    """Same settlement engine as every other acca (legs settle on the archived results)."""
    return safe_mod.settle_accas(df, results, today)


def summary(df: pd.DataFrame, today: datetime) -> dict:
    """The record, in the only unit that matters: units returned per unit staked."""
    cut = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    all_stats = safe_mod._stats(df, "won")
    last30 = safe_mod._stats(df[df["created"] >= cut], "won") if not df.empty else {"n": 0}
    out = {"all": all_stats, "30d": last30, "pending": int((df["status"] == "pending").sum()) if not df.empty else 0}
    if all_stats.get("n"):
        out["break_even_note"] = (f"{all_stats['n']} settled · {all_stats['won']} won · "
                                  f"expected {all_stats['exp_rate']:.1%} · actual {all_stats['rate']:.1%} · "
                                  f"ROI {all_stats['roi']:+.1%}" if all_stats.get("roi") is not None else None)
    return out


def recent(df: pd.DataFrame, n: int = 12) -> list[dict]:
    """The newest builds, newest first, for the app's record list."""
    if df.empty:
        return []
    rows = []
    for r in df.tail(n).iloc[::-1].itertuples():
        try:
            legs = json.loads(r.legs)
        except (TypeError, ValueError):
            continue
        rows.append({"id": r.acca_id, "created": str(r.created), "odds": float(r.odds), "p": float(r.p),
                     "p_market": float(r.p_market) if str(r.p_market) not in ("", "nan") else None,
                     "n_legs": int(r.n_legs), "status": str(r.status), "settled_on": str(r.settled_on or ""),
                     "legs": legs, "target": float(r.target) if str(r.target) not in ("", "nan") else TARGET})
    return rows


def current(df: pd.DataFrame, ids: list[str]) -> list[dict]:
    """This run's builds, in publication shape (without fixture ids — appdata.py adds those)."""
    out = []
    for aid in ids:
        sub = df[df["acca_id"] == aid]
        if sub.empty:
            continue
        r = sub.iloc[0]
        try:
            legs = json.loads(r["legs"])
        except (TypeError, ValueError):
            continue
        out.append({"id": aid, "odds": float(r["odds"]), "p": float(r["p"]),
                    "p_market": float(r["p_market"]) if str(r["p_market"]) not in ("", "nan") else None,
                    "n_legs": int(r["n_legs"]), "status": str(r["status"]), "legs": legs})
    return out


def load(path: Path) -> pd.DataFrame:
    return safe_mod.load_csv(path, ACCA_COLS)
