"""High-conviction daily shortlist: analyse broadly, select strictly.

This module is a FILTER on top of what the pipeline already computed. It reads the model's probabilities,
the Sportybet prices, the de-vigged market view, the data-quality audit, the automatic warnings and the
research context; it never changes any of them and it never adds a probability of its own.

Every priced selection of every analysed match in the window the user sees goes through the same gate,
whatever the market. Market policy (user rules 2026-10-17, policy.py): the focus is Over 1.5, Over 2.5, BTTS and
bookings (1X2 and corners overs stay available); team goals, double chance and every under are dropped, and
Over 2.5 and BTTS START from a 55% model probability instead of 70%:

  hard gates (fail one = REJECTED)
    H1  the match passed the pipeline's own data checks (data_ok)
    H2  a verified Sportybet price exists (unknown = "N/A", never assumed)
    H3  odds inside the band: MIN_ODDS <= odds <= MAX_ODDS (1.15 to 1.90 — user rule)
    H4  model probability clears the bar for that market (stated explicitly in BARS)
    H5  the model/market gap is believable: <= MAX_EDGE over the de-vigged market (or the raw price when
        no de-vigged view exists). A much wider gap is the signature of a data fault, not strength
    H6  HO05/AO05 also need 4/5 recent scoring, 2/3 at the relevant venue, and 2/5 opponent concessions

  soft gates (fail one = WATCHLIST, with the exact reason)
    S1  data quality High or Medium (the audit's own grade)
    S2  confidence for this market is not Low (sample size x data quality, quality.confidence)
    S3  no 'warn'-level automatic warning on the match (model v raw data contradictions)
    S4  no unresolved conflict in the live research for the match
    S5  prices are this run's own fetch — carried-forward prices (a blocked fetch) go to the watchlist

  NOT gates (user rule, 2026-10-11): EV and market edge. Chasing positive EV had its own tab and it does
  not decide what qualifies here. Edge and EV are still DISPLAYED on every pick for information; the
  Positive EV tab remains the place for value hunting. Strength + data support decide membership.

Passing everything = QUALIFIED FOR FURTHER REVIEW. One selection per match (the best-ranked one); the others
from the same match are listed as correlated, never as separate opportunities. The list is grouped by market
and each market keeps its best MAX_PER_MARKET (10) — picking the bests, never padding. Today's matches only
(nothing from tomorrow or later); Overs only (Unders are never candidates). If nothing qualifies the answer
is "NO QUALIFYING SELECTIONS".

Ranking is a transparent composite of strength and data support, never EV:
    score = 0.40 x data-quality score + 0.40 x (probability above its market bar, scaled over 20 pp)
            + 0.20 x confidence (High 1.0 / Medium 0.6 / N/A 0.3)

Calibrated probability: no validated live calibration map is shipped with the model, so it is reported as
N/A rather than invented. The backtest calibration tables live in backtest/RESULTS.md.

Every decision (primary, watchlist, and the best rejected selection of each match) is written once per
match per day to data/shortlist.csv — the pre-match snapshot — and settled from results later, so the filter
itself can be evaluated walk-forward: does the shortlist beat the watchlist, and the watchlist the rejects?
"""
from __future__ import annotations

import math
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import safe as safe_mod
import calibration as calib
import policy

# ------------------------------------------------------------------ the rules (stated, applied consistently)
MIN_ODDS = float(os.getenv("SHORTLIST_MIN_ODDS", "1.15"))     # band floor: odds below this are rejected
MAX_ODDS = float(os.getenv("SHORTLIST_MAX_ODDS", "1.90"))     # band ceiling: odds above this are rejected
# Probability bar per market group. A selection the policy names starts from its own floor instead:
# Over 2.5, BTTS and 1X2 at 55% (policy.SEL_MIN_P); Over 1.5 and the other goals lines stay at 70%.
# ("dc" and "team" are gone — double chance and team goals are no longer offered.)
BARS = {"result": policy.SEL_MIN_P["H"], "goals": 0.70, "btts": policy.SEL_MIN_P["BTTS"], "corners": 0.65, "cards": 0.65}
MAX_EDGE = 0.12          # more than 12 pp over the de-vigged market = data fault, not edge
MAX_RAW_EDGE = 0.25      # no de-vigged view: gap over the raw implied price above this = data fault
MAX_PER_MARKET = int(os.getenv("SHORTLIST_MAX_PER_MARKET", "10"))  # best picks kept PER MARKET GROUP
IGNORE_UNDER = os.getenv("SHORTLIST_IGNORE_UNDER", "1") != "0"   # user rule: Overs only — Under selections are never candidates
UNDER_RE = None if not IGNORE_UNDER else policy.UNDER_RE      # every under in every market (incl. team corners / cards, no-BTTS)
MAX_WATCH = 10
# Dedicated 1X2 tab (user 2026-10-19): match-result board, independent of which market won the shortlist slot.
# 1X2 prices are often above the shortlist 1.90 cap, so this board uses its own band.
X12_MIN_ODDS = float(os.getenv("X12_MIN_ODDS", "1.20"))
X12_MAX_ODDS = float(os.getenv("X12_MAX_ODDS", "3.50"))
X12_MAX = int(os.getenv("X12_MAX", "40"))
KEEP_DAYS = 120
# Lanes (2026-10-17). One selection per match stays the rule, but "the best-scored candidate wins the match" meant Over 1.5
# won 286 of 303 matches (it is always the likelier of Over 1.5 / Over 2.5 / BTTS), so Over 2.5 could never appear whatever
# its floor and the 'goals' cap filled with Over 1.5. As in Bets of the Day, each market now CLAIMS its own matches, rarest
# first, and Over 1.5 (and the other goals lines) takes what is left; each lane keeps its best `max_per_market`.
# A match cut from one lane can still be claimed by a later one (its Over 1.5), and nothing is padded.
LANES = os.getenv("SHORTLIST_LANES", "1") != "0"
# 2026-10-21: the match-total corner and card markets get their own lanes, ahead of the team lines. One shared
# "corners" lane let the three team-corner lines fill every slot, so the total market never reached the shortlist —
# and therefore never reached the videos. Totals claim first; the team lanes keep a smaller cap.
LANE_ORDER = ("o25", "btts", "cards", "cards_team", "corners", "corners_team", "result", "goals")
LANE_CAP = {"cards_team": 5, "corners_team": 5}


def lane_of(x: dict) -> str:
    """The lane an evaluated selection competes in: Over 2.5 on its own, totals and team lines apart, every other
    goals line together."""
    if x.get("sel") == "O25":
        return "o25"
    market = x["market"]
    if market in ("corners", "cards") and str(x.get("sel") or "")[1:2] in ("H", "A"):
        return f"{market}_team"
    return market

COLS = ["day", "decided", "match_date", "kickoff", "country", "league", "home", "away", "sel", "label", "market",
        "odds", "p", "p_sb", "implied_raw", "edge_pp", "ev", "quality", "confidence", "status", "reasons",
        "rank", "score_rank", "result", "score", "settled_on"]

STATUS_PRIMARY, STATUS_WATCH, STATUS_REJECT = "primary", "watchlist", "rejected"


def _pct(x) -> str:
    return "N/A" if x is None or x != x else f"{100 * x:.0f}%"


def _num(x, nd: int = 2) -> str:
    return "N/A" if x is None or x != x else f"{x:.{nd}f}"


def _nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def _conf_key(sel: str, group: str) -> str:
    """Which audit confidence applies to a selection (quality.confidence is computed per market family)."""
    if sel in ("O15", "U15"):
        return "O15"
    if sel in ("O25", "U25"):
        return "O25"
    if sel in ("O35", "U35"):
        return "O35"
    if group == "btts":
        return "BTTS"
    if group in ("result", "dc"):
        return "X12"
    if group == "team":
        return "TG"
    return ""          # goals lines without their own grade, corners, cards: data quality decides alone


def evaluate(r, s, *, min_odds: float | None = None, max_odds: float | None = None) -> dict:
    """One selection through every gate. Returns the full record with reasons; changes nothing."""
    fx = r.fx
    audit = r.audit or {}
    q = audit.get("quality") or {}
    group = safe_mod.group(s.sel)
    odds = s.odds if s.priced else None
    implied = (1 / odds) if odds else None
    edge = None if s.p_sb is None else s.p_model - s.p_sb
    ev = None if odds is None else s.p_model * odds - 1
    ck = _conf_key(s.sel, group)
    conf = (audit.get("confidence") or {}).get(ck) if ck else None
    warns = [w for w in (audit.get("warnings") or []) if w.get("level") == "warn"]
    carried = getattr(r, "sb_asof", None)
    cx = audit.get("context") or {}
    conflicts = cx.get("conflicts") or []
    bar = policy.min_p(s.sel, BARS.get(group, 0.70))
    floor = MIN_ODDS if min_odds is None else min_odds
    ceil = MAX_ODDS if max_odds is None else max_odds

    hard, soft = [], []
    if not r.data_ok:
        hard.append("failed the pipeline's data checks")
    if odds is None:
        hard.append("odds N/A (not priced by Sportybet)")
    elif odds < floor:
        hard.append(f"odds {odds:.2f} below the {floor:.2f} floor")
    elif odds > ceil:
        hard.append(f"odds {odds:.2f} above the {ceil:.2f} ceiling (band {floor:.2f}\u2013{ceil:.2f})")
    if s.p_model < bar:
        hard.append(f"probability {100 * s.p_model:.0f}% below the {100 * bar:.0f}% bar for {group}")
    if s.sel in safe_mod.TEAM_GOAL_MARKETS:
        form_ok, form_reason = safe_mod.team_goal_form_status(r, s.sel)
        if not form_ok:
            hard.append(form_reason)
    if edge is not None and edge > MAX_EDGE:
        hard.append(f"model {100 * edge:.0f} pp above the market — data fault, not edge")
    elif edge is None and implied is not None and s.p_model - implied > MAX_RAW_EDGE:
        hard.append(f"model {100 * (s.p_model - implied):.0f} pp above the raw price — data fault, not edge")

    qual = q.get("overall")
    if qual not in ("High", "Medium"):
        soft.append(f"data quality {qual or 'N/A'}")
    if conf == "Low":
        soft.append("confidence Low for this market (small sample / weak data)")
    if warns:
        soft.append("warning: " + str(warns[0].get("text") or warns[0].get("code") or "model v raw data")[:90])
    if conflicts:
        soft.append("unresolved conflict in the live research")
    if carried:
        soft.append(f"price carried forward from {carried} (the book blocked the fetch) — value claim is only as fresh as that")

    status = STATUS_REJECT if hard else STATUS_WATCH if soft else STATUS_PRIMARY
    qscore = float(q.get("score") or 0.0)
    conf_score = {"High": 1.0, "Medium": 0.6}.get(conf, 0.3)
    score = (0.40 * qscore
             + 0.40 * min(max(s.p_model - bar, 0.0) / 0.20, 1.0)
             + 0.20 * conf_score)

    support = []
    hist = r.hist or {}
    hk = {"O15": "O15", "O25": "O25", "BTTS": "BTTS"}.get(s.sel)
    if hk and not _nan(hist.get(hk)):
        support.append(f"both teams' historical {hk} rate {100 * hist[hk]:.0f}%")
    if group in ("goals", "btts", "team") and not _nan(r.mod_h):
        support.append(f"model xG {r.mod_h:.2f}–{r.mod_a:.2f}")
    n_min = min(getattr(r.home, "n", 0) or 0, getattr(r.away, "n", 0) or 0)
    if n_min:
        support.append(f"{n_min}+ matches per team in the sample")
    if edge is not None and edge > 0:
        support.append(f"model {100 * edge:.1f} pp above the de-vigged market")
    risk = (soft[0] if soft else
            f"one-in-{max(2, round(1 / max(1 - s.p_model, 0.01)))} miss rate even if the model is right"
            if s.p_model >= 0.5 else "less likely than not")
    if warns and status == STATUS_PRIMARY:
        risk = str(warns[0].get("text"))

    return {
        "key": (fx["date"].strftime("%Y-%m-%d"), fx["country"], fx["home"], fx["away"]),
        "kickoff": fx["kickoff"].strftime("%Y-%m-%d %H:%M"), "country": fx["country"],
        "league": str(fx.get("league") or ""), "home": fx["home"], "away": fx["away"],
        "sel": s.sel, "label": safe_mod.label(s.sel, fx["home"], fx["away"]), "market": group,
        "odds": None if odds is None else round(odds, 2),
        "p": round(s.p_model, 3), "p_cal": None,
        "p_sb": None if s.p_sb is None else round(s.p_sb, 3),
        "implied_raw": None if implied is None else round(implied, 3),
        "edge_pp": None if edge is None else round(100 * edge, 1),
        "ev": None if ev is None else round(ev, 3),
        "quality": qual or "N/A", "quality_score": round(qscore, 2), "confidence": conf or "N/A",
        "bar": bar, "status": status, "reasons": hard or soft, "score": round(score, 3),
        "support": support[:3], "risk": risk,
    }


# ------------------------------------------------------------------ the analysis (user rule 2026-10-11)
# A data-written article per primary selection. Real numbers only: tracked form, goals, venue
# splits, head-to-head and verified prices, straight off the MatchRow. Nothing is invented —
# anything missing renders as N/A. Displayed in the app under each pick, with visuals.

def _form_str(p) -> str:
    out = []
    for m in (getattr(p, "last5", None) or [])[:5]:
        out.append("W" if m["gf"] > m["ga"] else ("L" if m["gf"] < m["ga"] else "D"))
    return "".join(out)          # newest first (last5 is newest-first)


def match_article(r, x: dict) -> dict:
    """Deep-dive article for one primary selection x, written from row r's own data."""
    H, A = r.home, r.away
    aid = f"{x['home']}|{x['away']}|{x['kickoff']}"
    odds = "N/A" if x.get("odds") is None else f"{x['odds']:.2f}"

    p1 = (f"Data and form. {H.name} arrive with {H.n} tracked matches, scoring "
          f"{_num(H.gf)} and conceding {_num(H.ga)} per match; last five: {_form_str(H) or 'N/A'} (newest first). "
          f"{A.name}: {A.n} tracked matches, {_num(A.gf)}–{_num(A.ga)} per match, last five {_form_str(A) or 'N/A'}.")
    if x.get("sel") in safe_mod.TEAM_GOAL_MARKETS:
        evidence = safe_mod.team_goal_form_evidence(r, x["sel"])
        if evidence and all(evidence.get(k) is not None for k in
                            ("attack_scored", "venue_scored", "opponent_conceded")):
            scorer = H.name if x["sel"] == "HO05" else A.name
            opponent = A.name if x["sel"] == "HO05" else H.name
            p1 += (f" Team-to-score evidence: {scorer} scored in {evidence['attack_scored']}/5 recent matches "
                   f"and {evidence['venue_scored']}/3 at {evidence['venue']}; {opponent} conceded in "
                   f"{evidence['opponent_conceded']}/5.")
    if not _nan(getattr(H, "venue_gf", float("nan"))) and (getattr(H, "venue_n", 0) or 0) >= 4 \
            and (getattr(A, "venue_n", 0) or 0) >= 4:
        p1 += (f" Venue split: {H.name} at home {_num(H.venue_gf)}–{_num(H.venue_ga)}; "
               f"{A.name} away {_num(A.venue_gf)}–{_num(A.venue_ga)}.")
    hist = getattr(r, "hist", None) or {}
    if not _nan(hist.get("O25")):
        p1 += f" Both teams' combined Over-2.5 rate this season: {100 * hist['O25']:.0f}%."

    edge = x.get("edge_pp")
    ev = x.get("ev")
    p2 = (f"The model's read. The Dixon–Coles engine prices {x['label']} at {_pct(x.get('p'))} — "
          f"{'above' if (edge or 0) >= 0 else 'below'} the {_pct(x.get('bar'))} evidence bar this market must clear"
          + (f" by {abs(edge):.1f} pp." if edge is not None else ".")
          + (f" Sportybet's de-vigged price implies {_pct(x.get('p_sb'))}, so the model sits {edge:.1f} pp "
             f"{'above' if (edge or 0) >= 0 else 'below'} the market (EV {_num(ev) if ev is not None else 'N/A'} — displayed, never a gate)."
             if x.get("p_sb") is not None else " No verified price view was available for this comparison."))

    p3 = ""
    h2h = getattr(r, "h2h", None) or []
    if h2h:
        n = len(h2h)
        hw = sum(1 for m in h2h if ((m["hg"] > m["ag"]) if m["home"] == x["home"] else (m["ag"] > m["hg"])))
        draw = sum(1 for m in h2h if m["hg"] == m["ag"])
        aw = n - hw - draw
        g = sum(m["hg"] + m["ag"] for m in h2h) / max(n, 1)
        p3 = (f"Head to head. Last {n} meetings: {x['home']} {hw}–{draw}–{aw} {A.name}, "
              f"averaging {g:.1f} goals; the model's expected goals for this meeting are "
              f"{_num(getattr(r, 'mod_h', float('nan')))}–{_num(getattr(r, 'mod_a', float('nan')))}. ")
    p3 += (f"Verdict: {x.get('confidence', 'N/A')} confidence on {x.get('quality', 'N/A')} data quality. "
           f"Main risk: {x.get('risk', 'N/A')}")

    return {"id": aid, "home": x["home"], "away": x["away"], "title": f"{x['home']} v {x['away']} — {x['label']} @ {odds}",
            "form": {"h": _form_str(H), "a": _form_str(A)},
            "stats": {"p": x.get("p"), "bar": x.get("bar"), "p_mkt": x.get("p_sb"), "edge_pp": edge},
            "paras": [p1, p2, p3.strip()]}


def build_article(analysed: list, prim: list, markets, now: datetime) -> dict | None:
    rows_by = {}
    for r in analysed:
        try:
            rows_by[(r.fx["country"], str(r.fx["home"]), str(r.fx["away"]))] = r
        except Exception:  # noqa: BLE001
            continue
    items = []
    for x in prim:
        r = rows_by.get((x.get("country"), x.get("home"), x.get("away")))
        if r is None:
            continue
        try:
            items.append(match_article(r, x))
        except Exception:  # noqa: BLE001 - one bad article must not take the board down
            continue
    if not items:
        return None
    mk = ", ".join(f"{k} {v}" for k, v in markets.most_common())
    return {"generated": now.strftime("%Y-%m-%d %H:%M"),
            "intro": (f"{len(prim)} selections made today's list ({mk}). Every analysis below is written "
                      "from the model's own data — tracked form, goals, head-to-head and verified prices. "
                      "No invented facts; anything missing shows as N/A."),
            "items": items}


def build(rows: list, now: datetime, window_end: datetime | None = None,
          max_per_market: int = MAX_PER_MARKET, cal_map: dict | None = None) -> dict:
    """The day's shortlist from the analysed rows. Pure: reads rows, returns a JSON-safe dict."""
    start = now + timedelta(minutes=10)
    analysed = [r for r in rows if r.fx["kickoff"] >= start and (window_end is None or r.fx["kickoff"] <= window_end)]
    screened = [r for r in analysed if r.data_ok and r.sb]
    sels_by_row = {}
    for r in analysed:
        try:
            ss = safe_mod.selections(r)
        except Exception:  # noqa: BLE001
            ss = []
        sels_by_row[id(r)] = ss
    per_match: list[dict] = []
    for r in analysed:
        recs = []
        for s in sels_by_row[id(r)]:
            if UNDER_RE is not None and UNDER_RE.match(s.sel or ""):
                continue    # user rule: ignore Unders in every market — Overs only
            try:
                recs.append(evaluate(r, s))
            except Exception:  # noqa: BLE001 - one bad selection must not take the board down
                continue
        if not recs:
            continue
        rank = {STATUS_PRIMARY: 0, STATUS_WATCH: 1, STATUS_REJECT: 2}
        recs.sort(key=lambda x: (rank[x["status"]], -x["score"]))
        best = recs[0]
        best["correlated"] = [x["label"] for x in recs[1:] if x["status"] == best["status"] != STATUS_REJECT][:3]
        per_match.append({"best": best, "all": recs})

    if LANES:
        # lane claiming: each market takes its best `max_per_market` matches in turn (see LANES above); the match's
        # selection becomes the claimed one, the rest of its candidates are listed as correlated
        claimed: dict = {}
        for lane in LANE_ORDER:
            pool = []
            for m in per_match:
                if m["best"]["key"] in claimed:
                    continue
                cands = [x for x in m["all"] if x["status"] == STATUS_PRIMARY and lane_of(x) == lane]
                if cands:
                    pool.append(max(cands, key=lambda x: x["score"]))
            pool.sort(key=lambda x: -x["score"])
            for x in pool[:LANE_CAP.get(lane, max_per_market)]:
                claimed[x["key"]] = x
        for m in per_match:
            x = claimed.get(m["best"]["key"])
            if x is not None and x is not m["best"]:
                x["correlated"] = [y["label"] for y in m["all"] if y is not x and y["status"] == STATUS_PRIMARY][:3]
                m["best"] = x
        by_market_cap = {id(x) for x in claimed.values()}
    qual_all = sorted((m["best"] for m in per_match if m["best"]["status"] == STATUS_PRIMARY), key=lambda x: -x["score"])
    watch = sorted((m["best"] for m in per_match if m["best"]["status"] == STATUS_WATCH), key=lambda x: -x["score"])
    # per-market cap: each market group keeps its best max_per_market — bests, never padding
    by_market: dict[str, list] = {}
    for x in qual_all:
        by_market.setdefault(x["market"], []).append(x)
    prim, over = [], []
    if LANES:
        # the lanes already applied the cap: a primary-status match that no lane claimed is beyond its market's cap
        for x in qual_all:
            (prim if id(x) in by_market_cap else over).append(x)
    else:
        for g, items in by_market.items():
            prim.extend(items[:max_per_market])
            over.extend(items[max_per_market:])
    prim.sort(key=lambda x: -x["score"])
    for x in over:                     # qualified but beyond its market's cap: watchlist, saying so
        x["status"] = STATUS_WATCH
        x["reasons"] = [f"qualified, but outside the top {max_per_market} of its market by ranking"]
    watch = sorted(over + watch, key=lambda x: -x["score"])
    by_m = {}
    for x in prim:
        by_m.setdefault(x["market"], []).append(x)
    for g, items in by_m.items():      # rank = position within the market group
        for i, x in enumerate(items, 1):
            x["rank"] = i
    rejected = [m["best"] for m in per_match if m["best"]["status"] == STATUS_REJECT]
    patterns = Counter()
    for m in per_match:
        if m["best"]["status"] == STATUS_REJECT:
            for reason in m["best"]["reasons"][:1]:
                patterns[_pattern(reason)] += 1
    watch_patterns = Counter(_pattern(x["reasons"][0]) for x in watch)
    markets = Counter(x["market"] for x in prim)
    article = build_article(analysed, prim, markets, now) if prim else None
    # calibration (2026-10-11 upgrade): honest probability where a validated map exists —
    # applied AFTER the gates; membership never depends on it
    for x in prim + watch:
        x["p_cal"] = calib.apply_map(x.get("p"), x.get("market"), cal_map)
    if prim:
        verdict = (f"{len(prim)} selection(s) across {len(by_market)} market group(s) qualified for further review "
                   f"(top {max_per_market} per market, odds {MIN_ODDS:.2f}\u2013{MAX_ODDS:.2f}, today only, Overs only). "
                   "Strength and data support decide the list — not EV. Review each before betting: this is a "
                   "shortlist, not an instruction to bet.")
    else:
        verdict = "NO QUALIFYING SELECTIONS — the evidence does not support a betting decision today. Standards were not lowered."

    return {
        "generated": now.strftime("%Y-%m-%d %H:%M"),
        "rules": {"min_odds": MIN_ODDS, "max_odds": MAX_ODDS, "bars": BARS, "bars_by_selection": dict(policy.SEL_MIN_P),
                  "market_policy": policy.describe(),
                  "max_edge_pp": 100 * MAX_EDGE, "max_per_market": max_per_market,
                  "band": f"{MIN_ODDS:.2f}\u2013{MAX_ODDS:.2f} (odds outside the band are rejected)",
                  "ev": "not a gate — strength and data support decide; value hunting lives on the Positive EV tab",
                  "diet": "every league the archive has enough data on (user rule 2026-10-17) — deep results history, 8+ teams, match statistics or a full-division table; plus the top divisions, the 22 main European divisions, the big African leagues and the UEFA Champions/Europa/Conference League; domestic cups, women/youth/friendlies, Japan/Australia and qualifiers stay out; both teams need 8+ recent matches with data",
                  "unders": "none in any market — Overs only (user rule)",
                  "dropped_markets": "team goals and double chance (user rule 2026-10-17)",
                  "day": "today's matches only (nothing from tomorrow or later)",
                  "implied_method": "de-vigged = Sportybet price with the bookmaker margin removed proportionally "
                                    "across the market's outcomes; raw = 1 / decimal odds",
                  "calibration": (cal_map or {"status": "N/A — no validated live calibration map yet; raw model probability shown"}),},
        "counts": {"analysed": len(analysed), "screened": len(screened),
                   "candidates": sum(len(m["all"]) for m in per_match),
                   "primary": len(prim), "watchlist": len(watch), "rejected": len(rejected)},
        "primary": prim, "watchlist": watch[:MAX_WATCH],
        "x12": collect_x12(analysed, sels_by_row),
        "rejected_patterns": [[k, v] for k, v in patterns.most_common(6) if v],
        "watch_patterns": [[k, v] for k, v in watch_patterns.most_common(4)],
        "markets": [[k, v] for k, v in markets.most_common()],
        "verdict": verdict,
        "article": article,
        "_rejected": rejected,          # for the ledger only; stripped before publication
        "_watch_all": watch,
    }


def _pattern(reason: str) -> str:
    r = reason.lower()
    for key, name in (("odds n/a", "not priced"), ("floor", "odds under the 1.15 floor"), ("ceiling", "odds over the 1.90 ceiling"),
                      ("below the", "probability under its market bar"), ("price too short", "price too short (negative EV)"),
                      ("data fault", "implausible model/market gap"), ("data checks", "failed data checks"),
                      ("data quality", "data quality low"), ("confidence low", "low confidence"),
                      ("warning", "model v raw-data warning"), ("conflict", "research conflict"),
                      ("outside the top", "beyond its market's cap")):
        if key in r:
            return name
    return reason[:40]


def collect_x12(analysed: list, sels_by_row: dict) -> list:
    """One 1X2 pick per match for the dedicated tab — independent of the shortlist winner."""
    out = []
    for r in analysed:
        best = None
        for s in sels_by_row.get(id(r), []) or []:
            if getattr(s, "sel", None) not in ("H", "D", "A"):
                continue
            rec = evaluate(r, s, min_odds=X12_MIN_ODDS, max_odds=X12_MAX_ODDS)
            if rec.get("status") != STATUS_PRIMARY:
                continue
            if best is None or rec["score"] > best["score"]:
                best = rec
        if best:
            out.append(dict(best))
    out.sort(key=lambda x: -x["score"])
    for i, x in enumerate(out[:X12_MAX], 1):
        x["rank"] = i
        x["p_cal"] = calib.apply_map(x.get("p"), x.get("market"), None)
    return out[:X12_MAX]



def public(board: dict) -> dict:
    """The publishable copy (no private ledger fields)."""
    return {k: v for k, v in board.items() if not k.startswith("_")}


# ------------------------------------------------------------------ the ledger (walk-forward evaluation)
def load(path: Path) -> pd.DataFrame:
    if path.exists():
        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False)
            for c in COLS:
                if c not in df.columns:
                    df[c] = ""
            return df[COLS]
        except (OSError, ValueError, pd.errors.ParserError):
            pass
    return pd.DataFrame(columns=COLS)


def record(df: pd.DataFrame, board: dict, now: datetime) -> tuple[pd.DataFrame, int]:
    """Write the first decision per match per day (the pre-match snapshot). Later runs never overwrite it."""
    day = now.strftime("%Y-%m-%d")
    seen = set(zip(df["day"], df["home"], df["away"])) if not df.empty else set()
    new = []
    items = [(x, STATUS_PRIMARY) for x in board.get("primary", [])] + \
            [(x, STATUS_WATCH) for x in (board.get("_watch_all") or board.get("watchlist", []))] + \
            [(x, STATUS_REJECT) for x in board.get("_rejected", [])]
    for x, st in items:
        k = (day, x["home"], x["away"])
        if k in seen:
            continue
        seen.add(k)
        new.append({"day": day, "decided": now.strftime("%Y-%m-%d %H:%M"), "match_date": x["key"][0],
                    "kickoff": x["kickoff"], "country": x["country"], "league": x["league"], "home": x["home"],
                    "away": x["away"], "sel": x["sel"], "label": x["label"], "market": x["market"],
                    "odds": "" if x["odds"] is None else x["odds"], "p": x["p"],
                    "p_sb": "" if x["p_sb"] is None else x["p_sb"],
                    "implied_raw": "" if x["implied_raw"] is None else x["implied_raw"],
                    "edge_pp": "" if x["edge_pp"] is None else x["edge_pp"], "ev": "" if x["ev"] is None else x["ev"],
                    "quality": x["quality"], "confidence": x["confidence"], "status": st,
                    "reasons": " | ".join(x["reasons"])[:300], "rank": x.get("rank", ""), "score_rank": x["score"],
                    "result": "pending", "score": "", "settled_on": ""})
    if new:
        add = pd.DataFrame(new, columns=COLS)
        df = add if df.empty else pd.concat([df, add], ignore_index=True)
    cut = (now - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    df = df[df["day"] >= cut]
    return df, len(new)


def settle(df: pd.DataFrame, results: pd.DataFrame, today: datetime) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    for i, r in df[df["result"] == "pending"].iterrows():
        row = safe_mod._lookup(results, r["country"], r["home"], r["away"], r["match_date"])
        if row is not None:
            ok = safe_mod.settle(r["sel"], row["hg"], row["ag"], row.get("hc"), row.get("ac"),
                                 safe_mod._cards(row, "h"), safe_mod._cards(row, "a"))
            if ok is not None:
                df.loc[i, ["result", "score", "settled_on"]] = ["hit" if ok else "miss",
                                                                f"{int(row['hg'])}-{int(row['ag'])}", today.strftime("%Y-%m-%d")]
                continue
        try:
            stale = (pd.Timestamp(today.date()) - pd.Timestamp(r["match_date"])).days > 21
        except (ValueError, TypeError):
            stale = True
        if stale:
            df.loc[i, ["result", "settled_on"]] = ["void", today.strftime("%Y-%m-%d")]
    # Self-heal rows graded before the 2026-10-21 corner/card fix (the ledger calls the column `result`).
    df, fixed = safe_mod.regrade_settled(df, results, today, status_col="result")
    if fixed:
        _log().info("shortlist ledger: re-graded %d corner/card row(s) settled the wrong way round", fixed)
    return df


def _log():
    """The scanner's logger without importing scanner (keeps this module pure and importable on its own)."""
    import logging
    return logging.getLogger("scanner")


def track_record(df: pd.DataFrame) -> dict:
    """Hit rate and flat-stake return per decision class — the evidence for or against the filter."""
    out = {}
    for st in (STATUS_PRIMARY, STATUS_WATCH, STATUS_REJECT):
        d = df[(df["status"] == st) & df["result"].isin(["hit", "miss"])]
        n = len(d)
        if not n:
            out[st] = {"n": 0}
            continue
        odds = pd.to_numeric(d["odds"], errors="coerce")
        hit = d["result"] == "hit"
        p = pd.to_numeric(d["p"], errors="coerce")
        priced = odds.notna() & (odds > 1)
        roi = float(((odds[priced] * hit[priced]).sum() - priced.sum()) / priced.sum()) if priced.sum() else None
        out[st] = {"n": n, "hit_rate": round(float(hit.mean()), 3), "expected": round(float(p.mean()), 3),
                   "roi": None if roi is None else round(roi, 3), "priced": int(priced.sum())}
    # performance-page extras (2026-10-11): per-market split + predicted-vs-actual bands (primary only)
    d = df[(df["status"] == STATUS_PRIMARY) & df["result"].isin(["hit", "miss"])].copy()
    if not d.empty:
        d["pv"] = pd.to_numeric(d["p"], errors="coerce")
        d["hit"] = (d["result"] == "hit").astype(float)
        bym = []
        for g, gd in d.groupby("market"):
            bym.append([g, int(len(gd)), round(float(gd["hit"].mean()), 3),
                        round(float(gd["pv"].mean()), 3) if gd["pv"].notna().any() else None])
        out["by_market"] = sorted(bym, key=lambda r: -r[1])
        bands, lo = [], 0.30
        while lo < 1.0:
            hi = round(lo + 0.10, 2)
            bd = d[d["pv"].between(lo, hi - 1e-9)]
            if len(bd):
                bands.append([round(lo, 2), round(hi, 2), int(len(bd)), round(float(bd["hit"].mean()), 3),
                              round(float(bd["pv"].mean()), 3)])
            lo = hi
        out["bands"] = bands
    return out


VIDEO_HISTORY_BACKFILL: dict[str, list[dict[str, str]]] = {
    # 2026-10-15 morning video was sent via one-shot workflow before briefing_history
    # was added to telegram_state.json; lock in the exact 7 matches featured in that video.
    "2026-10-15": [
        {"home": "Hearts", "away": "FC Nordsjaelland", "sel": "HO05"},
        {"home": "Lyon", "away": "Crystal Palace", "sel": "HO05"},
        {"home": "Union St.Gilloise", "away": "Real Sociedad", "sel": "O15"},
        {"home": "Ferencvaros", "away": "Viktoria Plzen", "sel": "HO05"},
        {"home": "Riga FC", "away": "Kairat Almaty", "sel": "HO05"},
        {"home": "FC Salzburg", "away": "AC Milan", "sel": "HO05"},
        {"home": "PFC CSKA Sofia", "away": "AS Monaco", "sel": "O15"},
    ],
}


def _is_video_market_row(r: dict) -> bool:
    label = str(r.get("label") or "").lower()
    if "under" in label:
        return False
    sel = str(r.get("sel") or "").upper()
    if sel.startswith(("O", "HO", "AO", "CO", "BO")):
        return True
    mkt = str(r.get("market") or "").lower()
    if mkt in ("goals", "corners", "cards", "bookings") and "over" in label:
        return True
    return any(k in label for k in ("over", "goal", "corner", "card", "booking"))


def yesterday_results(df: pd.DataFrame, now: datetime, video_picks: list | dict | None = None) -> dict:
    """Settled results of yesterday's video shortlist selections (strictly matches included in yesterday's video)."""
    today_s = now.strftime("%Y-%m-%d")
    yday_s = (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")
    if df is None or df.empty or "status" not in df.columns:
        return {"day": yday_s, "total": 0, "settled": 0, "hits": 0, "misses": 0, "voids": 0, "pending": 0, "hit_rate": None, "items": []}
    prim = df[df["status"] == STATUS_PRIMARY].copy()
    if prim.empty:
        return {"day": yday_s, "total": 0, "settled": 0, "hits": 0, "misses": 0, "voids": 0, "pending": 0, "hit_rate": None, "items": []}
    day_df = prim[prim["day"] == yday_s]
    target_day = yday_s
    if day_df.empty:
        # Fall back to the most recent prior shortlist day within 7 days that has settled primary rows
        min_day = (now.date() - timedelta(days=7)).strftime("%Y-%m-%d")
        prior = prim[(prim["day"] < today_s) & (prim["day"] >= min_day) & prim["result"].isin(["hit", "miss", "void"])]
        if not prior.empty:
            target_day = str(prior["day"].max())
            day_df = prim[prim["day"] == target_day]
    items = []
    for _, r in day_df.iterrows():
        odds_raw = str(r.get("odds", "")).strip()
        try:
            odds_val = round(float(odds_raw), 2) if odds_raw else None
        except ValueError:
            odds_val = None
        items.append({
            "day": str(r.get("day", target_day)),
            "kickoff": str(r.get("kickoff", "")),
            "country": str(r.get("country", "")),
            "league": str(r.get("league", "")),
            "home": str(r.get("home", "")),
            "away": str(r.get("away", "")),
            "sel": str(r.get("sel", "")),
            "label": str(r.get("label", "")),
            "market": str(r.get("market", "")),
            "odds": odds_val,
            "result": str(r.get("result", "pending")),
            "score": str(r.get("score", "")),
        })

    resolved_vp = None
    if isinstance(video_picks, dict):
        resolved_vp = video_picks.get(target_day) or VIDEO_HISTORY_BACKFILL.get(target_day)
    elif isinstance(video_picks, list):
        resolved_vp = video_picks
    else:
        resolved_vp = VIDEO_HISTORY_BACKFILL.get(target_day)

    if resolved_vp is not None:
        by_exact = {(x["home"], x["away"], x["sel"]): x for x in items if x.get("sel")}
        by_pair = {(x["home"], x["away"]): x for x in items}
        ordered = []
        seen_pairs = set()
        for vp in resolved_vp:
            if not isinstance(vp, dict):
                continue
            h = str(vp.get("home") or "")
            a = str(vp.get("away") or "")
            s = str(vp.get("sel") or "")
            if not h or not a or (h, a) in seen_pairs:
                continue
            matched = (by_exact.get((h, a, s)) if s else None) or by_pair.get((h, a))
            if matched is not None:
                ordered.append(matched)
                seen_pairs.add((h, a))
        items = ordered
    else:
        # When no explicit video history exists for that day, exclude pre-05:00 overnight games
        # that kicked off before the morning briefing window and restrict to video-eligible overs markets.
        morning_cut = f"{target_day} 05:00"
        morning_items = [x for x in items if not x.get("kickoff") or str(x["kickoff"]) >= morning_cut]
        if morning_items:
            items = morning_items
        reel_eligible = [x for x in items if _is_video_market_row(x)]
        if reel_eligible:
            items = reel_eligible[:7]

    hits = sum(1 for x in items if x["result"] == "hit")
    misses = sum(1 for x in items if x["result"] == "miss")
    voids = sum(1 for x in items if x["result"] == "void")
    pending = sum(1 for x in items if x["result"] == "pending")
    settled = hits + misses
    return {
        "day": target_day,
        "total": len(items),
        "settled": settled,
        "hits": hits,
        "misses": misses,
        "voids": voids,
        "pending": pending,
        "hit_rate": round(hits / settled, 3) if settled else None,
        "items": items,
    }


def markdown(board: dict) -> list[str]:
    """Compact report section."""
    c = board["counts"]
    L = ["## 🎯 High-conviction shortlist", "",
         f"_Analysed {c['analysed']} · passed screening {c['screened']} · shortlist {c['primary']} · "
         f"watchlist {c['watchlist']} · rejected {c['rejected']}. Odds band {MIN_ODDS:.2f}\u2013{MAX_ODDS:.2f}; "
         f"top {board['rules']['max_per_market']} per market group; one selection per match._", ""]
    if not board["primary"]:
        L += ["**NO QUALIFYING SELECTIONS.**", ""]
    for x in board["primary"]:
        imp = "N/A" if x["p_sb"] is None else "%.0f%%" % (100 * x["p_sb"])
        edge = "N/A" if x["edge_pp"] is None else "%+.1f pp" % x["edge_pp"]
        ev = "N/A" if x["ev"] is None else "%+.1f%%" % (100 * x["ev"])
        L.append("%d. **%s v %s** (%s) — %s @ %.2f · model %.0f%% · implied %s · edge %s · EV %s · data %s — "
                 "risk: %s · **QUALIFIED FOR FURTHER REVIEW**" % (x["rank"], x["home"], x["away"], x["league"], x["label"],
                                                                 x["odds"], 100 * x["p"], imp, edge, ev, x["quality"], x["risk"]))
    if board["watchlist"]:
        L += ["", "**Watchlist:** " + "; ".join(f"{x['home']} v {x['away']} ({x['label']}: {x['reasons'][0]})"
                                              for x in board["watchlist"][:5])]
    if board["rejected_patterns"]:
        L += ["", "_Main rejection reasons: " + ", ".join(f"{k} ({v})" for k, v in board["rejected_patterns"]) + "._"]
    L += ["", f"_{board['verdict']}_", ""]
    return L
