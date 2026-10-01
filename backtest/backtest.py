#!/usr/bin/env python3
"""
Backtest for the Goals Scanner model.

Replays several seasons chronologically. For every match, team strengths and league averages
are computed only from matches played strictly before that date (no look-ahead), exactly the way
the daily scanner does it, then a family of probability models is evaluated against what happened.

Usage:
    python backtest/backtest.py              # full evaluation with the production parameters
    python backtest/backtest.py --grid       # search half-life / shrinkage parameters
    python backtest/backtest.py --rho        # fit the Dixon-Coles low-score correction
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy.stats import poisson

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scanner import EXTRA_LEAGUES, MAIN_LEAGUES, parse_dates, read_csv  # noqa: E402

CACHE = Path(__file__).resolve().parent / "cache"
CACHE.mkdir(exist_ok=True)
BASE = "https://www.football-data.co.uk"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "Mozilla/5.0 (GoalsScanner backtest)"

MAIN_DIVS = list(MAIN_LEAGUES)
SEASONS = ["2223", "2324", "2425", "2526", "2627"]   # 2223 is warm-up history only
EVAL_START = pd.Timestamp("2023-08-01")
TRAIN_END = pd.Timestamp("2025-06-30")               # tune on 23/24 + 24/25, validate on 25/26 + 26/27
MAXG = 10                                            # score matrix size


# --------------------------------------------------------------------------- data
def cached(url: str, name: str) -> bytes | None:
    fn = CACHE / name
    if fn.exists():
        return fn.read_bytes()
    r = SESSION.get(url, timeout=60)
    if r.status_code != 200:
        return None
    fn.write_bytes(r.content)
    return r.content


def num(df, col):
    return pd.to_numeric(df[col], errors="coerce") if col in df.columns else pd.Series(np.nan, index=df.index)


def load_main() -> pd.DataFrame:
    frames = []
    for s in SEASONS:
        for d in MAIN_DIVS:
            df = read_csv(cached(f"{BASE}/mmz4281/{s}/{d}.csv", f"{s}_{d}.csv"))
            if df is None or "HomeTeam" not in df.columns:
                continue
            df = df.dropna(subset=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"])
            frames.append(pd.DataFrame({
                "season": s, "country": MAIN_LEAGUES[d][0], "div": d, "league": MAIN_LEAGUES[d][1],
                "date": parse_dates(df["Date"]),
                "home": df["HomeTeam"].astype(str).str.strip(), "away": df["AwayTeam"].astype(str).str.strip(),
                "hg": num(df, "FTHG"), "ag": num(df, "FTAG"),
                "oo": num(df, "Avg>2.5"), "ou": num(df, "Avg<2.5"),          # opening market average
                "hxg": num(df, "HxG"), "axg": num(df, "AxG"),               # xG (published from season 26/27 only)
                "coo": num(df, "AvgC>2.5"), "cou": num(df, "AvgC<2.5"),      # closing market average
                "oh": num(df, "AvgH"), "od": num(df, "AvgD"), "oa": num(df, "AvgA"),
                "source": "main",
            }))
    return pd.concat(frames, ignore_index=True)


def load_extra(since: pd.Timestamp) -> pd.DataFrame:
    frames = []
    for country, code in EXTRA_LEAGUES.items():
        df = read_csv(cached(f"{BASE}/new/{code}.csv", f"extra_{code}.csv"))
        if df is None or "Home" not in df.columns:
            continue
        df = df.dropna(subset=["Date", "Home", "Away", "HG", "AG"])
        league = df["League"].astype(str).str.strip()
        out = pd.DataFrame({
            "season": df["Season"].astype(str), "country": country, "div": code + ":" + league, "league": league,
            "date": parse_dates(df["Date"]),
            "home": df["Home"].astype(str).str.strip(), "away": df["Away"].astype(str).str.strip(),
            "hg": num(df, "HG"), "ag": num(df, "AG"),
            "oo": np.nan, "ou": np.nan, "coo": np.nan, "cou": np.nan,
            "oh": num(df, "AvgH"), "od": num(df, "AvgD"), "oa": num(df, "AvgA"),
            "source": "extra",
        })
        frames.append(out[out["date"] >= since])
    return pd.concat(frames, ignore_index=True)


def load_all() -> pd.DataFrame:
    df = pd.concat([load_main(), load_extra(pd.Timestamp("2022-07-01"))], ignore_index=True)
    df = df.dropna(subset=["date", "hg", "ag"]).sort_values(["date", "div"]).reset_index(drop=True)
    df["hg"] = df["hg"].astype(int)
    df["ag"] = df["ag"].astype(int)
    df["ord"] = df["date"].map(pd.Timestamp.toordinal)
    return df


# --------------------------------------------------------------------------- rolling model
def run_model(df: pd.DataFrame, HL: float = 120, K: float = 4, KV: float = 5, max_n: int = 40,
              max_days: int = 400, div_K: float = 30.0) -> pd.DataFrame:
    """Chronological replay. Returns per-match expected goals + team descriptors (no look-ahead)."""
    ords = df["ord"].to_numpy()
    divs = df["div"].to_numpy()
    countries = df["country"].to_numpy()
    homes = df["home"].to_numpy()
    aways = df["away"].to_numpy()
    hgs = df["hg"].to_numpy()
    ags = df["ag"].to_numpy()

    team_hist: dict = defaultdict(list)                 # (country, team) -> [(ord, venue, gf, ga, div)]
    div_hist: dict = defaultdict(lambda: ([], [], []))  # div -> (ords, hg, ag)
    glob = ([], [], [])
    div_cache: dict = {}
    prior_cache: dict = {}

    def prior(d):
        if d in prior_cache:
            return prior_cache[d]
        o = np.asarray(glob[0])
        if len(o) == 0:
            prior_cache[d] = (1.45, 1.20)
            return prior_cache[d]
        m = o >= d - max_days
        w = 0.5 ** ((d - o[m]) / HL)
        hg = np.asarray(glob[1])[m]
        ag = np.asarray(glob[2])[m]
        prior_cache[d] = (float((w * hg).sum() / w.sum()), float((w * ag).sum() / w.sum())) if w.sum() > 0 else (1.45, 1.20)
        return prior_cache[d]

    def div_avg(div, d):
        key = (div, d)
        if key in div_cache:
            return div_cache[key]
        ph, pa = prior(d)
        o = np.asarray(div_hist[div][0])
        if len(o) == 0:
            div_cache[key] = (ph, pa)
            return div_cache[key]
        m = o >= d - max_days
        w = 0.5 ** ((d - o[m]) / HL)
        n = w.sum()
        if n <= 0:
            div_cache[key] = (ph, pa)
            return div_cache[key]
        hg = np.asarray(div_hist[div][1])[m]
        ag = np.asarray(div_hist[div][2])[m]
        mh = (w * hg).sum() / n
        ma = (w * ag).sum() / n
        div_cache[key] = ((n * mh + div_K * ph) / (n + div_K), (n * ma + div_K * pa) / (n + div_K))
        return div_cache[key]

    def profile(recs, d, venue):
        lo = d - max_days
        sel = [r for r in recs[-max_n:] if r[0] >= lo]
        if not sel:
            return None
        sw = swa = swd = sv = sva = svd = s15 = s25 = sb = 0.0
        for o, v, gf, ga, dv in sel:
            w = 0.5 ** ((d - o) / HL)
            mh, ma = div_avg(dv, d)
            if v == 1:
                gfn, gan = gf / mh, ga / ma
            else:
                gfn, gan = gf / ma, ga / mh
            sw += w
            swa += w * gfn
            swd += w * gan
            tot = gf + ga
            if tot >= 2:
                s15 += w
            if tot >= 3:
                s25 += w
            if gf > 0 and ga > 0:
                sb += w
            if v == venue:
                sv += w
                sva += w * gfn
                svd += w * gan
        att_all, def_all = swa / sw, swd / sw
        if sv > 0:
            share = sv / (sv + KV)
            att = share * (sva / sv) + (1 - share) * att_all
            dfc = share * (svd / sv) + (1 - share) * def_all
        else:
            att, dfc = att_all, def_all
        att = (sw * att + K) / (sw + K)
        dfc = (sw * dfc + K) / (sw + K)
        return att, dfc, len(sel), sw, s15 / sw, s25 / sw, sb / sw

    out = np.full((len(df), 14), np.nan)
    n = len(df)
    i = 0
    while i < n:
        d = ords[i]
        j = i
        while j < n and ords[j] == d:
            j += 1
        for k in range(i, j):
            H = profile(team_hist[(countries[k], homes[k])], d, 1)
            A = profile(team_hist[(countries[k], aways[k])], d, 0)
            if H is None or A is None:
                continue
            mh, ma = div_avg(divs[k], d)
            lh = min(max(mh * H[0] * A[1], 0.15), 4.5)
            la = min(max(ma * A[0] * H[1], 0.15), 4.5)
            out[k] = (lh, la, H[2], H[3], A[2], A[3], H[4], H[5], H[6], A[4], A[5], A[6], mh, ma)
        for k in range(i, j):
            team_hist[(countries[k], homes[k])].append((d, 1, hgs[k], ags[k], divs[k]))
            team_hist[(countries[k], aways[k])].append((d, 0, ags[k], hgs[k], divs[k]))
            dh = div_hist[divs[k]]
            dh[0].append(d); dh[1].append(hgs[k]); dh[2].append(ags[k])
            glob[0].append(d); glob[1].append(hgs[k]); glob[2].append(ags[k])
        i = j

    cols = ["lh", "la", "h_n", "h_neff", "a_n", "a_neff", "h_o15", "h_o25", "h_btts",
            "a_o15", "a_o25", "a_btts", "mu_h", "mu_a"]
    res = pd.concat([df.reset_index(drop=True), pd.DataFrame(out, columns=cols)], axis=1)
    res["tot"] = res["hg"] + res["ag"]
    res["y15"] = (res["tot"] >= 2).astype(int)
    res["y25"] = (res["tot"] >= 3).astype(int)
    res["ybtts"] = ((res["hg"] > 0) & (res["ag"] > 0)).astype(int)
    return res


# --------------------------------------------------------------------------- probability models
def score_matrix(lh: np.ndarray, la: np.ndarray, rho: float = 0.0) -> np.ndarray:
    """(n, MAXG+1, MAXG+1) matrix of score probabilities; rho != 0 applies the Dixon-Coles correction."""
    g = np.arange(MAXG + 1)
    ph = poisson.pmf(g[None, :], lh[:, None])
    pa = poisson.pmf(g[None, :], la[:, None])
    M = ph[:, :, None] * pa[:, None, :]
    if rho:
        M[:, 0, 0] *= 1 - lh * la * rho
        M[:, 1, 0] *= 1 + la * rho
        M[:, 0, 1] *= 1 + lh * rho
        M[:, 1, 1] *= 1 - rho
        M = np.clip(M, 1e-12, None)
    M /= M.sum(axis=(1, 2), keepdims=True)
    return M


def probs_from_matrix(M: np.ndarray) -> dict[str, np.ndarray]:
    g = np.arange(MAXG + 1)
    tot = g[:, None] + g[None, :]
    return {
        "O15": M[:, tot >= 2].sum(axis=1),
        "O25": M[:, tot >= 3].sum(axis=1),
        "BTTS": M[:, 1:, 1:].sum(axis=(1, 2)),
        "HW": M[:, g[:, None] > g[None, :]].sum(axis=1),
        "AW": M[:, g[:, None] < g[None, :]].sum(axis=1),
    }


def market_probs(res: pd.DataFrame, closing: bool = False) -> pd.Series:
    oo, ou = (res["coo"], res["cou"]) if closing else (res["oo"], res["ou"])
    p = (1 / oo) / (1 / oo + 1 / ou)
    return p.where((oo > 1) & (ou > 1))


def market_lambdas(res: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Expected goals implied by the (opening) market: total from the O/U 2.5 price, split from 1X2."""
    p_over = market_probs(res).to_numpy()
    inv = 1 / res[["oh", "od", "oa"]].to_numpy()
    p3 = inv / inv.sum(axis=1, keepdims=True)
    ok = ~np.isnan(p_over) & ~np.isnan(p3).any(axis=1)
    lt = np.full(len(res), np.nan)
    lo, hi = np.full(ok.sum(), 0.3), np.full(ok.sum(), 7.0)
    target = p_over[ok]
    for _ in range(40):
        mid = (lo + hi) / 2
        f = 1 - poisson.cdf(2, mid)
        lo = np.where(f < target, mid, lo)
        hi = np.where(f >= target, mid, hi)
    lt[ok] = (lo + hi) / 2
    # split: find share s so that P(home win) - P(away win) matches the market
    diff_target = (p3[ok, 0] - p3[ok, 2])
    s_lo, s_hi = np.full(ok.sum(), 0.05), np.full(ok.sum(), 0.95)
    for _ in range(30):
        s = (s_lo + s_hi) / 2
        P = probs_from_matrix(score_matrix(lt[ok] * s, lt[ok] * (1 - s)))
        f = P["HW"] - P["AW"]
        s_lo = np.where(f < diff_target, s, s_lo)
        s_hi = np.where(f >= diff_target, s, s_hi)
    s = (s_lo + s_hi) / 2
    lh = np.full(len(res), np.nan)
    la = np.full(len(res), np.nan)
    lh[ok] = lt[ok] * s
    la[ok] = lt[ok] * (1 - s)
    return lh, la


# --------------------------------------------------------------------------- metrics
def logloss(p, y):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    y = np.asarray(y, float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(p, y):
    return float(np.mean((np.asarray(p, float) - np.asarray(y, float)) ** 2))


def calibration_table(p, y, edges=(0, .4, .45, .5, .55, .6, .65, .7, .75, .8, 1.01)) -> pd.DataFrame:
    p = np.asarray(p, float)
    y = np.asarray(y, float)
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p >= lo) & (p < hi)
        if m.sum():
            rows.append({"bucket": f"{lo:.2f}–{min(hi, 1):.2f}", "n": int(m.sum()),
                         "predicted": p[m].mean(), "actual": y[m].mean(), "gap": y[m].mean() - p[m].mean()})
    return pd.DataFrame(rows)


def simulate_picks(res: pd.DataFrame, pcol: str, ycol: str, thr_p: float, thr_hist: float,
                   hist_cols: tuple[str, str], max_picks: int = 15, min_neff: float = 4.0) -> pd.DataFrame:
    c = res[(res[pcol] >= thr_p) & (res["h_neff"] >= min_neff) & (res["a_neff"] >= min_neff)]
    if thr_hist is not None:
        h1, h2 = hist_cols
        hist = (c[h1] + c[h2]) / 2
        c = c[(hist >= thr_hist) & (c[[h1, h2]].min(axis=1) >= thr_hist - 0.10)]
    c = c.sort_values(["date", pcol], ascending=[True, False])
    c = c.groupby("date", group_keys=False).head(max_picks)
    return c


def pick_stats(c: pd.DataFrame, ycol: str, pcol: str, odds_cols: tuple[str, str] | None = None) -> dict:
    if c.empty:
        return {"picks": 0}
    days = c["date"].nunique()
    d = {"picks": len(c), "per_day": len(c) / max(days, 1), "hit_rate": c[ycol].mean(),
         "avg_pred": c[pcol].mean()}
    if odds_cols:
        o_open, o_close = odds_cols
        m = c[o_open].notna()
        if m.any():
            d["avg_odds"] = c.loc[m, o_open].mean()
            d["roi_open"] = ((c.loc[m, o_open] * c.loc[m, ycol]).sum() - m.sum()) / m.sum()
        m2 = c[o_close].notna()
        if m2.any():
            d["roi_close"] = ((c.loc[m2, o_close] * c.loc[m2, ycol]).sum() - m2.sum()) / m2.sum()
    return d


# --------------------------------------------------------------------------- evaluation
def add_model_columns(res: pd.DataFrame, rho: float = 0.0, w_lambda: float = 0.0, with_market: bool = True) -> pd.DataFrame:
    """Adds probability columns: pois_*, dc_* (rho), mkt_o25, blend_* (market-lambda blend)."""
    res = res.copy()
    ok = res["lh"].notna()
    lh, la = res.loc[ok, "lh"].to_numpy(), res.loc[ok, "la"].to_numpy()
    P = probs_from_matrix(score_matrix(lh, la, 0.0))
    for k in ("O15", "O25", "BTTS"):
        res.loc[ok, f"pois_{k}"] = P[k]
    if rho:
        P = probs_from_matrix(score_matrix(lh, la, rho))
        for k in ("O15", "O25", "BTTS"):
            res.loc[ok, f"dc_{k}"] = P[k]
    res["mkt_o25"] = market_probs(res)
    res["mkt_o25_close"] = market_probs(res, closing=True)
    if not with_market:
        return res
    mlh, mla = market_lambdas(res)
    res["mlh"], res["mla"] = mlh, mla
    if w_lambda:
        has = ok & ~np.isnan(mlh)
        blh = np.where(has, (1 - w_lambda) * res["lh"] + w_lambda * mlh, res["lh"])
        bla = np.where(has, (1 - w_lambda) * res["la"] + w_lambda * mla, res["la"])
        m = ~np.isnan(blh)
        P = probs_from_matrix(score_matrix(blh[m], bla[m], rho))
        for k in ("O15", "O25", "BTTS"):
            res.loc[m, f"blend_{k}"] = P[k]
    return res


def fit_rho(res: pd.DataFrame) -> pd.DataFrame:
    tr = res[(res["date"] >= EVAL_START) & (res["date"] <= TRAIN_END) & res["lh"].notna()]
    lh, la = tr["lh"].to_numpy(), tr["la"].to_numpy()
    hg, ag = tr["hg"].to_numpy().clip(max=MAXG), tr["ag"].to_numpy().clip(max=MAXG)
    rows = []
    for rho in np.arange(-0.25, 0.101, 0.025):
        M = score_matrix(lh, la, float(rho))
        ll = float(np.mean(np.log(M[np.arange(len(tr)), hg, ag])))
        rows.append({"rho": round(float(rho), 3), "score_loglik": ll})
    return pd.DataFrame(rows)


def evaluate(res: pd.DataFrame, label: str, out: list[str]) -> None:
    ev = res[(res["date"] >= EVAL_START) & res["pois_O25"].notna()].copy()
    ev["split"] = np.where(ev["date"] <= TRAIN_END, "train (23/24–24/25)", "test (25/26–26/27)")
    out.append(f"## {label}\n")
    out.append(f"Matches with a prediction from {EVAL_START:%b %Y}: **{len(ev):,}** "
               f"(main leagues with odds: {int((ev['source']=='main').sum()):,}; extra leagues: {int((ev['source']=='extra').sum()):,})\n")

    # --- model comparison per market (log-loss; lower is better)
    out.append("### Accuracy by model (log-loss, lower = better; Brier in brackets)\n")
    rows = []
    for split, g in ev.groupby("split"):
        gm = g[g["mkt_o25"].notna()]
        base = {"O15": g["y15"].mean(), "O25": g["y25"].mean(), "BTTS": g["ybtts"].mean()}
        for name, cols in [("League average (no model)", None), ("Team hit-rates only", "rates"),
                           ("Poisson (current)", "pois"), ("Dixon-Coles", "dc"),
                           ("Market odds only (O2.5)", "mkt"), ("Current blend 60/40 (O2.5)", "cur"),
                           ("Market-xG blend", "blend")]:
            r = {"split": split, "model": name}
            for k, y in (("O15", "y15"), ("O25", "y25"), ("BTTS", "ybtts")):
                if cols is None:
                    p = np.full(len(g), base[k]); yy = g[y]
                elif cols == "rates":
                    hc = {"O15": ("h_o15", "a_o15"), "O25": ("h_o25", "a_o25"), "BTTS": ("h_btts", "a_btts")}[k]
                    p = (g[hc[0]] + g[hc[1]]) / 2; yy = g[y]
                elif cols == "mkt":
                    if k != "O25": r[k] = "–"; continue
                    p = gm["mkt_o25"]; yy = gm[y]
                elif cols == "cur":
                    if k != "O25": r[k] = "–"; continue
                    p = 0.6 * gm["pois_O25"] + 0.4 * gm["mkt_o25"]; yy = gm[y]
                else:
                    c = f"{cols}_{k}"
                    if c not in g: r[k] = "–"; continue
                    p = g[c]; yy = g[y]
                    if cols == "blend":
                        p = gm[c]; yy = gm[y]
                r[k] = f"{logloss(p, yy):.4f} ({brier(p, yy):.4f})"
            rows.append(r)
    t = pd.DataFrame(rows)
    out.append(t.to_markdown(index=False) + "\n")

    # --- calibration of the current O2.5 final probability, test split
    te = ev[ev["split"].str.startswith("test")]
    out.append("### Calibration — Over 2.5, test seasons\n")
    for name, p in [("Poisson model alone", te["pois_O25"]),
                    ("Current final (60% model / 40% market where odds exist)",
                     np.where(te["mkt_o25"].notna(), 0.6 * te["pois_O25"] + 0.4 * te["mkt_o25"].fillna(0), te["pois_O25"]))]:
        out.append(f"**{name}**\n")
        ct = calibration_table(p, te["y25"])
        ct["predicted"] = ct["predicted"].map("{:.1%}".format); ct["actual"] = ct["actual"].map("{:.1%}".format)
        ct["gap"] = ct["gap"].map("{:+.1%}".format)
        out.append(ct.to_markdown(index=False) + "\n")
    out.append("**BTTS (Poisson)**\n")
    ct = calibration_table(te["pois_BTTS"], te["ybtts"], edges=(0, .45, .5, .55, .6, .65, .7, 1.01))
    for c in ("predicted", "actual"): ct[c] = ct[c].map("{:.1%}".format)
    ct["gap"] = ct["gap"].map("{:+.1%}".format)
    out.append(ct.to_markdown(index=False) + "\n")
    out.append("**Over 1.5 (Poisson)**\n")
    ct = calibration_table(te["pois_O15"], te["y15"], edges=(0, .7, .75, .8, .84, .88, .92, 1.01))
    for c in ("predicted", "actual"): ct[c] = ct[c].map("{:.1%}".format)
    ct["gap"] = ct["gap"].map("{:+.1%}".format)
    out.append(ct.to_markdown(index=False) + "\n")


def shortlist_report(res: pd.DataFrame, out: list[str], pcols: dict[str, str], title: str) -> None:
    ev = res[(res["date"] >= EVAL_START) & res["pois_O25"].notna()].copy()
    ev["split"] = np.where(ev["date"] <= TRAIN_END, "train", "test")
    out.append(f"### {title}\n")
    rules = {"O15": (0.84, 0.75, ("h_o15", "a_o15"), "y15"), "O25": (0.60, 0.50, ("h_o25", "a_o25"), "y25"),
             "BTTS": (0.62, 0.50, ("h_btts", "a_btts"), "ybtts")}
    rows = []
    for mkt, (tp, th, hc, y) in rules.items():
        for split, g in ev.groupby("split"):
            c = simulate_picks(g, pcols[mkt], y, tp, th, hc)
            s = pick_stats(c, y, pcols[mkt], ("oo", "coo") if mkt == "O25" else None)
            rows.append({"market": mkt, "split": split, **{k: (f"{v:.1%}" if "rate" in k or "roi" in k or k == "avg_pred" else f"{v:.2f}" if isinstance(v, float) else v) for k, v in s.items()}})
    out.append(pd.DataFrame(rows).fillna("–").to_markdown(index=False) + "\n")


def threshold_curve(res: pd.DataFrame, pcol: str, ycol: str, hist_cols, hist_floor: float,
                    thresholds, odds=True) -> pd.DataFrame:
    ev = res[(res["date"] >= EVAL_START) & res[pcol].notna()]
    rows = []
    for t in thresholds:
        for split_name, g in (("train", ev[ev["date"] <= TRAIN_END]), ("test", ev[ev["date"] > TRAIN_END])):
            c = simulate_picks(g, pcol, ycol, t, hist_floor, hist_cols)
            s = pick_stats(c, ycol, pcol, ("oo", "coo") if odds else None)
            rows.append({"threshold": f"≥{t:.0%}", "split": split_name, "picks": s.get("picks", 0),
                         "per day": f"{s.get('per_day', 0):.1f}", "hit rate": f"{s.get('hit_rate', float('nan')):.1%}",
                         "predicted": f"{s.get('avg_pred', float('nan')):.1%}",
                         **({"avg odds": f"{s.get('avg_odds', float('nan')):.2f}",
                             "ROI open": f"{s.get('roi_open', float('nan')):+.1%}",
                             "ROI close": f"{s.get('roi_close', float('nan')):+.1%}"} if odds else {})})
    return pd.DataFrame(rows)


def league_table(res: pd.DataFrame, pcol: str) -> pd.DataFrame:
    ev = res[(res["date"] >= EVAL_START) & res[pcol].notna()]
    rows = []
    for (country, league), g in ev.groupby(["country", "league"]):
        if len(g) < 150:
            continue
        c = simulate_picks(g, pcol, "y25", 0.60, None, None)
        rows.append({"league": f"{country} · {league}", "matches": len(g), "O2.5 rate": f"{g['y25'].mean():.0%}",
                     "log-loss": round(logloss(g[pcol], g["y25"]), 4),
                     "picks": len(c), "pick hit rate": f"{c['y25'].mean():.0%}" if len(c) else "–",
                     "pick predicted": f"{c[pcol].mean():.0%}" if len(c) else "–",
                     "gap": f"{(c['y25'].mean() - c[pcol].mean()):+.0%}" if len(c) else "–"})
    return pd.DataFrame(rows).sort_values("log-loss")


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grid", action="store_true", help="parameter grid search (train split, O2.5 log-loss)")
    ap.add_argument("--rho", action="store_true", help="fit Dixon-Coles rho on the train split")
    ap.add_argument("--HL", type=float, default=120)
    ap.add_argument("--K", type=float, default=40)
    ap.add_argument("--KV", type=float, default=20)
    ap.add_argument("--rho-value", type=float, default=-0.05)
    ap.add_argument("--w-lambda", type=float, default=0.9, help="weight of market-implied xG in the blend")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "RESULTS.md"))
    args = ap.parse_args()

    t0 = time.time()
    df = load_all()
    print(f"loaded {len(df):,} matches in {time.time() - t0:.0f}s", flush=True)

    if args.grid:
        rows = []
        for HL in (60, 120, 240, 400):
            for K in (4, 8, 16, 32):
                for KV in (5,):
                    t1 = time.time()
                    res = run_model(df, HL=HL, K=K, KV=KV)
                    res = add_model_columns(res, with_market=False)
                    tr = res[(res["date"] >= EVAL_START) & (res["date"] <= TRAIN_END) & res["pois_O25"].notna()]
                    te = res[(res["date"] > TRAIN_END) & res["pois_O25"].notna()]
                    rows.append({"HL": HL, "K": K, "KV": KV,
                                 "train_O25": logloss(tr["pois_O25"], tr["y25"]), "train_BTTS": logloss(tr["pois_BTTS"], tr["ybtts"]),
                                 "test_O25": logloss(te["pois_O25"], te["y25"]), "test_BTTS": logloss(te["pois_BTTS"], te["ybtts"])})
                    print(rows[-1], f"{time.time() - t1:.0f}s", flush=True)
        g = pd.DataFrame(rows).sort_values("train_O25")
        g.to_csv(Path(__file__).resolve().parent / "grid.csv", index=False)
        print(g.to_string(index=False))
        return

    res = run_model(df, HL=args.HL, K=args.K, KV=args.KV)
    print(f"model replay done in {time.time() - t0:.0f}s", flush=True)

    if args.rho:
        print(fit_rho(res).to_string(index=False))
        return

    res = add_model_columns(res, rho=args.rho_value, w_lambda=args.w_lambda)
    for k in ("O15", "O25", "BTTS"):   # production v2 final probability: market blend where odds exist, else model
        res[f"fin_{k}"] = res[f"blend_{k}"].fillna(res[f"dc_{k}"]) if f"blend_{k}" in res else res[f"dc_{k}" if args.rho_value else f"pois_{k}"]
    res.to_pickle(Path(__file__).resolve().parent / "predictions.pkl")

    out = [f"# Backtest results\n", f"_Generated {datetime.now():%Y-%m-%d %H:%M}. Parameters: half-life {args.HL:g} days, "
           f"shrinkage K={args.K:g}, venue K={args.KV:g}, Dixon-Coles rho={args.rho_value:g}, market-xG weight={args.w_lambda:g}._\n"]
    evaluate(res, "Model accuracy", out)
    out.append("## Shortlist simulation (current rules, top-15 per day)\n")
    shortlist_report(res, out, {"O15": "pois_O15", "O25": "pois_O25", "BTTS": "pois_BTTS"}, "Poisson only")
    res["cur_O25"] = np.where(res["mkt_o25"].notna(), 0.6 * res["pois_O25"] + 0.4 * res["mkt_o25"].fillna(0), res["pois_O25"])
    shortlist_report(res, out, {"O15": "pois_O15", "O25": "cur_O25", "BTTS": "pois_BTTS"}, "Current production (60/40 market blend for O2.5)")
    if args.w_lambda:
        for k in ("O15", "O25", "BTTS"):
            res[f"blendf_{k}"] = res[f"blend_{k}"].fillna(res[f"dc_{k}" if args.rho_value else f"pois_{k}"])
        shortlist_report(res, out, {"O15": "blendf_O15", "O25": "blendf_O25", "BTTS": "blendf_BTTS"}, "Candidate: Dixon-Coles + market-xG blend")

    # ---- production v2 rules: final probability only, with tiers
    out.append("## Shortlist simulation — production v2 rules (final probability, no team-form floors)\n")
    tiers = {"O15": (0.84, 0.87, 0.90), "O25": (0.60, 0.64, 0.68), "BTTS": (0.60, 0.63, 0.66)}
    ycols = {"O15": "y15", "O25": "y25", "BTTS": "ybtts"}
    rows = []
    ev2 = res[(res["date"] >= EVAL_START) & res["fin_O25"].notna()].copy()
    ev2["split"] = np.where(ev2["date"] <= TRAIN_END, "train (23/24–24/25)", "test (25/26–26/27)")
    for mkt, (t1, t2, t3) in tiers.items():
        for split, g in ev2.groupby("split"):
            c = simulate_picks(g, f"fin_{mkt}", ycols[mkt], t1, None, None)
            y = ycols[mkt]
            r = {"market": mkt, "split": split, "picks": len(c), "per day": round(len(c) / max(c["date"].nunique(), 1), 1),
                 "hit rate": f"{c[y].mean():.1%}", "predicted": f"{c[f'fin_{mkt}'].mean():.1%}",
                 "⭐⭐ hit rate": f"{c[c[f'fin_{mkt}'] >= t2][y].mean():.1%} (n={int((c[f'fin_{mkt}'] >= t2).sum())})",
                 "⭐⭐⭐ hit rate": f"{c[c[f'fin_{mkt}'] >= t3][y].mean():.1%} (n={int((c[f'fin_{mkt}'] >= t3).sum())})"}
            if mkt == "O25":
                m = c["oo"].notna()
                r["ROI @ open odds"] = f"{((c.loc[m, 'oo'] * c.loc[m, y]).sum() - m.sum()) / max(m.sum(), 1):+.1%}"
            rows.append(r)
    out.append(pd.DataFrame(rows).fillna("–").to_markdown(index=False) + "\n")
    out.append("_The ROI line is a reality check, not a promise: shortlisting by probability means backing short-priced "
               "favourites, and the bookmaker margin (~5%) is not overcome on average._\n")

    out.append("## Threshold curves (production v2 final probability)\n")
    out.append("**Over 2.5**\n")
    out.append(threshold_curve(res, "fin_O25", "y25", None, None, np.arange(0.55, 0.751, 0.025)).to_markdown(index=False) + "\n")
    out.append("**BTTS**\n")
    out.append(threshold_curve(res, "fin_BTTS", "ybtts", None, None, np.arange(0.55, 0.751, 0.025), odds=False).to_markdown(index=False) + "\n")
    out.append("**Over 1.5**\n")
    out.append(threshold_curve(res, "fin_O15", "y15", None, None, np.arange(0.78, 0.941, 0.02), odds=False).to_markdown(index=False) + "\n")

    out.append("## By league — Over 2.5 (production v2 final probability, all evaluation seasons)\n")
    out.append(league_table(res, "fin_O25").to_markdown(index=False) + "\n")

    Path(args.out).write_text("\n".join(out), encoding="utf-8")
    print(f"written {args.out} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
