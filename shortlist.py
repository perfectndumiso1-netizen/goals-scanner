"""High-conviction daily shortlist: analyse broadly, select strictly.

This module is a FILTER on top of what the pipeline already computed. It reads the model's probabilities,
the Sportybet prices, the de-vigged market view, the data-quality audit, the automatic warnings and the
research context; it never changes any of them and it never adds a probability of its own.

Every priced selection of every analysed match in the window the user sees goes through the same gate,
whatever the market (1X2, double chance, goals, BTTS, team goals, corners, bookings):

  hard gates (fail one = REJECTED)
    H1  the match passed the pipeline's own data checks (data_ok)
    H2  a verified Sportybet price exists (unknown = "N/A", never assumed)
    H3  odds inside the band: MIN_ODDS <= odds <= MAX_ODDS (1.15 to 1.90 — user rule. Below the floor the
        price is too short to be worth a pick; above the ceiling the pick is a coin-flip punt, not a
        high-conviction selection)
    H4  model probability clears the bar for that market (stated explicitly in BARS)
    H5  the model is at least as likely as the price says (EV >= 0 at Sportybet's own price)
    H6  the model/market gap is believable: <= MAX_EDGE over the de-vigged market. A wider gap is the
        signature of a data fault (friendly, cup qualifier, wrong team), not value — the same rule the
        accas and the app's outlier quarantine use

  soft gates (fail one = WATCHLIST, with the exact reason)
    S1  a de-vigged market view exists, so the edge is measured against the market, not against a price that
        still contains the bookmaker's margin
    S2  edge over the de-vigged market >= MIN_EDGE (otherwise it is a high-probability pick, not value)
    S2b the edge beats the model's usual gap on that market today (median over the board) by MIN_EDGE — a gap
        the model shows on every match is a systematic model/market difference, not match-specific value
    S3  data quality High or Medium (the audit's own grade)
    S4  confidence for this market is not Low (sample size x data quality, quality.confidence)
    S5  no 'warn'-level automatic warning on the match (model v raw data contradictions)
    S6  no unresolved conflict in the live research for the match

Passing everything = QUALIFIED FOR FURTHER REVIEW. One selection per match (the best-ranked one); the others
from the same match are listed as correlated, never as separate opportunities. The list is grouped by market
and each market keeps its best MAX_PER_MARKET (10) — picking the bests, never padding. If nothing qualifies
the answer is "NO QUALIFYING SELECTIONS".

Ranking is a transparent composite, not probability alone:
    score = 0.30 x data-quality score + 0.30 x min(excess edge / 0.08, 1) + 0.20 x min(EV / 0.10, 1)
            + 0.20 x (probability above its market bar, scaled over 25 pp)

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

# ------------------------------------------------------------------ the rules (stated, applied consistently)
MIN_ODDS = float(os.getenv("SHORTLIST_MIN_ODDS", "1.15"))     # band floor: odds below this are rejected
MAX_ODDS = float(os.getenv("SHORTLIST_MAX_ODDS", "1.90"))     # band ceiling: odds above this are rejected
BARS = {"result": 0.60, "dc": 0.70, "goals": 0.70, "btts": 0.70, "team": 0.70, "corners": 0.65, "cards": 0.65}
MIN_EDGE = 0.02          # beat the de-vigged market by at least 2 pp to count as value
MAX_EDGE = 0.12          # more than 12 pp over the de-vigged market = data fault, not edge
MAX_RAW_EDGE = 0.25      # no de-vigged view: gap over the raw implied price above this = data fault
BASELINE_MIN_N = 15      # a market needs this many priced selections today before its usual gap is measured
MAX_PER_MARKET = int(os.getenv("SHORTLIST_MAX_PER_MARKET", "10"))  # best picks kept PER MARKET GROUP
MAX_WATCH = 10
KEEP_DAYS = 120

COLS = ["day", "decided", "match_date", "kickoff", "country", "league", "home", "away", "sel", "label", "market",
        "odds", "p", "p_sb", "implied_raw", "edge_pp", "ev", "quality", "confidence", "status", "reasons",
        "rank", "score_rank", "result", "score", "settled_on"]

STATUS_PRIMARY, STATUS_WATCH, STATUS_REJECT = "primary", "watchlist", "rejected"


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


def evaluate(r, s, baseline: dict | None = None) -> dict:
    """One selection through every gate. Returns the full record with reasons; changes nothing.

    `baseline` = median model-minus-market gap per selection code across today's board. An edge that is no
    bigger than the model's usual gap on that market is a systematic model/market difference, not value
    specific to this match (spec rule 7: the edge must not be an artifact)."""
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
    bar = BARS.get(group, 0.70)

    hard, soft = [], []
    if not r.data_ok:
        hard.append("failed the pipeline's data checks")
    if odds is None:
        hard.append("odds N/A (not priced by Sportybet)")
    elif odds < MIN_ODDS:
        hard.append(f"odds {odds:.2f} below the {MIN_ODDS:.2f} floor")
    elif odds > MAX_ODDS:
        hard.append(f"odds {odds:.2f} above the {MAX_ODDS:.2f} ceiling (band {MIN_ODDS:.2f}\u2013{MAX_ODDS:.2f})")
    if s.p_model < bar:
        hard.append(f"probability {100 * s.p_model:.0f}% below the {100 * bar:.0f}% bar for {group}")
    if ev is not None and ev < 0:
        hard.append(f"price too short for the probability (EV {100 * ev:+.1f}%)")
    if edge is not None and edge > MAX_EDGE:
        hard.append(f"model {100 * edge:.0f} pp above the market — data fault, not edge")
    elif edge is None and implied is not None and s.p_model - implied > MAX_RAW_EDGE:
        hard.append(f"model {100 * (s.p_model - implied):.0f} pp above the raw price — data fault, not edge")

    base = (baseline or {}).get(s.sel)
    excess = None if edge is None else edge - (base or 0.0)
    if edge is None:
        soft.append("no de-vigged market view to measure the edge against")
    elif edge < MIN_EDGE:
        soft.append(f"edge {100 * edge:+.1f} pp — high probability, not value")
    elif base is not None and excess < MIN_EDGE:
        soft.append(f"edge {100 * edge:+.1f} pp is the model's usual gap on this market today "
                    f"(median {100 * base:+.1f} pp) — systematic, not specific to this match")
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
    score = (0.30 * qscore
             + 0.30 * (min(max(excess if excess is not None else 0.0, 0.0) / 0.08, 1.0))
             + 0.20 * (min(max(ev or 0.0, 0.0) / 0.10, 1.0))
             + 0.20 * min(max(s.p_model - bar, 0.0) / 0.25, 1.0))

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
    if edge is not None and edge >= MIN_EDGE:
        support.append(f"model {100 * edge:.1f} pp above the de-vigged market"
                       + (f" ({100 * excess:+.1f} pp beyond its usual gap on this market)" if base is not None else ""))
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
        "excess_pp": None if excess is None else round(100 * excess, 1),
        "ev": None if ev is None else round(ev, 3),
        "quality": qual or "N/A", "quality_score": round(qscore, 2), "confidence": conf or "N/A",
        "bar": bar, "status": status, "reasons": hard or soft, "score": round(score, 3),
        "support": support[:3], "risk": risk,
    }


def build(rows: list, now: datetime, window_end: datetime | None = None,
          max_per_market: int = MAX_PER_MARKET) -> dict:
    """The day's shortlist from the analysed rows. Pure: reads rows, returns a JSON-safe dict."""
    start = now + timedelta(minutes=10)
    analysed = [r for r in rows if r.fx["kickoff"] >= start and (window_end is None or r.fx["kickoff"] <= window_end)]
    screened = [r for r in analysed if r.data_ok and r.sb]
    sels_by_row = {}
    gaps: dict[str, list] = {}
    for r in analysed:
        try:
            ss = safe_mod.selections(r)
        except Exception:  # noqa: BLE001
            ss = []
        sels_by_row[id(r)] = ss
        if r.data_ok:
            for s in ss:
                if s.p_sb is not None and s.priced:
                    gaps.setdefault(s.sel, []).append(s.p_model - s.p_sb)
    baseline = {k: float(pd.Series(v).median()) for k, v in gaps.items() if len(v) >= BASELINE_MIN_N}
    per_match: list[dict] = []
    for r in analysed:
        recs = []
        for s in sels_by_row[id(r)]:
            try:
                recs.append(evaluate(r, s, baseline))
            except Exception:  # noqa: BLE001 - one bad selection must not take the board down
                continue
        if not recs:
            continue
        rank = {STATUS_PRIMARY: 0, STATUS_WATCH: 1, STATUS_REJECT: 2}
        recs.sort(key=lambda x: (rank[x["status"]], -x["score"]))
        best = recs[0]
        best["correlated"] = [x["label"] for x in recs[1:] if x["status"] == best["status"] != STATUS_REJECT][:3]
        per_match.append({"best": best, "all": recs})

    qual_all = sorted((m["best"] for m in per_match if m["best"]["status"] == STATUS_PRIMARY), key=lambda x: -x["score"])
    watch = sorted((m["best"] for m in per_match if m["best"]["status"] == STATUS_WATCH), key=lambda x: -x["score"])
    # per-market cap: each market group keeps its best max_per_market — bests, never padding
    by_market: dict[str, list] = {}
    for x in qual_all:
        by_market.setdefault(x["market"], []).append(x)
    prim, over = [], []
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
    genuine_value = sum(1 for x in prim if (x["edge_pp"] or 0) >= 100 * MIN_EDGE and (x["ev"] or 0) > 0)

    if prim:
        verdict = (f"{len(prim)} selection(s) across {len(by_market)} market group(s) qualified for further review "
                   f"(top {max_per_market} per market, odds {MIN_ODDS:.2f}\u2013{MAX_ODDS:.2f}); "
                   f"{genuine_value} show an estimated edge over the de-vigged market. Review each before betting — "
                   "this is a shortlist, not an instruction to bet.")
    else:
        verdict = "NO QUALIFYING SELECTIONS — the evidence does not support a betting decision today. Standards were not lowered."

    return {
        "generated": now.strftime("%Y-%m-%d %H:%M"),
        "rules": {"min_odds": MIN_ODDS, "max_odds": MAX_ODDS, "bars": BARS, "min_edge_pp": 100 * MIN_EDGE,
                  "max_edge_pp": 100 * MAX_EDGE, "max_per_market": max_per_market,
                  "band": f"{MIN_ODDS:.2f}\u2013{MAX_ODDS:.2f} (odds outside the band are rejected)",
                  "implied_method": "de-vigged = Sportybet price with the bookmaker margin removed proportionally "
                                    "across the market's outcomes; raw = 1 / decimal odds",
                  "calibration": "N/A — no validated live calibration map; raw model probability shown"},
        "counts": {"analysed": len(analysed), "screened": len(screened),
                   "candidates": sum(len(m["all"]) for m in per_match),
                   "primary": len(prim), "watchlist": len(watch), "rejected": len(rejected)},
        "primary": prim, "watchlist": watch[:MAX_WATCH],
        "rejected_patterns": [[k, v] for k, v in patterns.most_common(6) if v],
        "watch_patterns": [[k, v] for k, v in watch_patterns.most_common(4)],
        "markets": [[k, v] for k, v in markets.most_common()],
        "value": {"genuine": genuine_value, "high_prob_only": len(prim) - genuine_value},
        "verdict": verdict,
        "_rejected": rejected,          # for the ledger only; stripped before publication
        "_watch_all": watch,
    }


def _pattern(reason: str) -> str:
    r = reason.lower()
    for key, name in (("odds n/a", "not priced"), ("floor", "odds under the 1.15 floor"), ("ceiling", "odds over the 1.90 ceiling"),
                      ("below the", "probability under its market bar"), ("price too short", "price too short (negative EV)"),
                      ("data fault", "implausible model/market gap"), ("data checks", "failed data checks"),
                      ("no de-vigged", "no market view to measure value"), ("high probability, not value", "no edge over the market"),
                      ("data quality", "data quality low"), ("confidence low", "low confidence"),
                      ("warning", "model v raw-data warning"), ("conflict", "research conflict"),
                      ("outside the top", "beyond its market's cap"), ("usual gap", "edge is the model's usual gap (systematic)")):
        if key in r:
            return name
    return reason[:40]


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
    return df


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
    return out


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
