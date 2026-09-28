#!/usr/bin/env python3
"""
Variant test for the football-data model (no market inputs anywhere):

  base        current production ratings (league-normalised goals, time decay, shrinkage K, venue blend KV)
  cap         same, with goals capped at CAP per match when building the ratings (robustness to 6-0 type results)
  opp         opponent-adjusted ratings: every past match is normalised by the opponent's own (raw, shrunk) rating
              at the time of evaluation, so 2 goals against a leaky defence count for less than 2 against a tight one
  opp+cap     both

Chronological replay without look-ahead (same data as backtest.py). Evaluated on the goals markets and on the
match result (home / draw / away) from the Dixon-Coles score matrix, against the market as a reference only.

Usage: python backtest/model_variants.py [--quick]
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest import EVAL_START, TRAIN_END, load_all, logloss, probs_from_matrix, score_matrix  # noqa: E402


def shrink(att: float, dfc: float, sw: float, K: float, K_s: float | None) -> tuple[float, float]:
    """Shrinkage towards the league average (1.0). With K_s the *strength* (attack/defence ratio, log space) is
    shrunk with K_s and the *tempo* (attack x defence) with K: strength differences between teams are more
    persistent than their goal tempo, so they need less shrinkage than the totals do."""
    if K_s is None:
        return (sw * att + K) / (sw + K), (sw * dfc + K) / (sw + K)
    la, ld = math.log(max(att, 0.05)), math.log(max(dfc, 0.05))
    s = (la - ld) * sw / (sw + K_s)
    t = (la + ld) * sw / (sw + K)
    return math.exp((t + s) / 2), math.exp((t - s) / 2)


def replay(df: pd.DataFrame, HL=120.0, K=40.0, KV=20.0, max_n=40, max_days=400, div_K=30.0,
           opp_adjust=False, cap=None, K_raw=None, K_s=None) -> pd.DataFrame:
    ords = df["ord"].to_numpy(); divs = df["div"].to_numpy(); countries = df["country"].to_numpy()
    homes = df["home"].to_numpy(); aways = df["away"].to_numpy(); hgs = df["hg"].to_numpy(); ags = df["ag"].to_numpy()
    K_raw = K if K_raw is None else K_raw
    team_hist: dict = defaultdict(list)                 # key -> [(ord, venue, gf, ga, div, opp_key)]
    div_hist: dict = defaultdict(lambda: ([], [], []))
    glob = ([], [], [])
    div_cache: dict = {}; prior_cache: dict = {}; raw_cache: dict = {}

    def prior(d):
        if d in prior_cache:
            return prior_cache[d]
        o = np.asarray(glob[0])
        if len(o) == 0:
            prior_cache[d] = (1.45, 1.20); return prior_cache[d]
        m = o >= d - max_days
        w = 0.5 ** ((d - o[m]) / HL)
        hg = np.asarray(glob[1])[m]; ag = np.asarray(glob[2])[m]
        prior_cache[d] = (float((w * hg).sum() / w.sum()), float((w * ag).sum() / w.sum())) if w.sum() > 0 else (1.45, 1.20)
        return prior_cache[d]

    def div_avg(div, d):
        key = (div, d)
        if key in div_cache:
            return div_cache[key]
        ph, pa = prior(d)
        o = np.asarray(div_hist[div][0])
        if len(o) == 0:
            div_cache[key] = (ph, pa); return div_cache[key]
        m = o >= d - max_days
        w = 0.5 ** ((d - o[m]) / HL); n = w.sum()
        if n <= 0:
            div_cache[key] = (ph, pa); return div_cache[key]
        hg = np.asarray(div_hist[div][1])[m]; ag = np.asarray(div_hist[div][2])[m]
        mh = (w * hg).sum() / n; ma = (w * ag).sum() / n
        div_cache[key] = ((n * mh + div_K * ph) / (n + div_K), (n * ma + div_K * pa) / (n + div_K))
        return div_cache[key]

    def norm(gf, ga, v, dv, d):
        if cap is not None:
            gf, ga = min(gf, cap), min(ga, cap)
        mh, ma = div_avg(dv, d)
        return (gf / mh, ga / ma) if v == 1 else (gf / ma, ga / mh)

    def raw_rating(key, d):
        """all-venue shrunk rating without opponent adjustment (first pass), cached per (team, day)"""
        ck = (key, d)
        if ck in raw_cache:
            return raw_cache[ck]
        recs = team_hist.get(key)
        if not recs:
            raw_cache[ck] = (1.0, 1.0); return raw_cache[ck]
        lo = d - max_days
        sw = sa = sd = 0.0
        for o, v, gf, ga, dv, _opp in recs[-max_n:]:
            if o < lo:
                continue
            w = 0.5 ** ((d - o) / HL)
            gfn, gan = norm(gf, ga, v, dv, d)
            sw += w; sa += w * gfn; sd += w * gan
        if sw <= 0:
            raw_cache[ck] = (1.0, 1.0); return raw_cache[ck]
        raw_cache[ck] = ((sw * (sa / sw) + K_raw) / (sw + K_raw), (sw * (sd / sw) + K_raw) / (sw + K_raw))
        return raw_cache[ck]

    def profile(key, d, venue):
        recs = team_hist.get(key)
        if not recs:
            return None
        lo = d - max_days
        sel = [r for r in recs[-max_n:] if r[0] >= lo]
        if not sel:
            return None
        sw = swa = swd = sv = sva = svd = 0.0
        for o, v, gf, ga, dv, opp in sel:
            w = 0.5 ** ((d - o) / HL)
            gfn, gan = norm(gf, ga, v, dv, d)
            if opp_adjust:
                oa, od = raw_rating(opp, d)
                gfn, gan = gfn / od, gan / oa
            sw += w; swa += w * gfn; swd += w * gan
            if v == venue:
                sv += w; sva += w * gfn; svd += w * gan
        att_all, def_all = swa / sw, swd / sw
        if sv > 0:
            share = sv / (sv + KV)
            att = share * (sva / sv) + (1 - share) * att_all
            dfc = share * (svd / sv) + (1 - share) * def_all
        else:
            att, dfc = att_all, def_all
        a, d_ = shrink(att, dfc, sw, K, K_s)
        return a, d_, len(sel), sw

    out = np.full((len(df), 6), np.nan)
    n = len(df); i = 0
    while i < n:
        d = ords[i]; j = i
        while j < n and ords[j] == d:
            j += 1
        for k in range(i, j):
            hk, ak = (countries[k], homes[k]), (countries[k], aways[k])
            H = profile(hk, d, 1); A = profile(ak, d, 0)
            if H is None or A is None:
                continue
            mh, ma = div_avg(divs[k], d)
            out[k] = (min(max(mh * H[0] * A[1], 0.15), 4.5), min(max(ma * A[0] * H[1], 0.15), 4.5), H[2], H[3], A[2], A[3])
        for k in range(i, j):
            hk, ak = (countries[k], homes[k]), (countries[k], aways[k])
            team_hist[hk].append((d, 1, hgs[k], ags[k], divs[k], ak))
            team_hist[ak].append((d, 0, ags[k], hgs[k], divs[k], hk))
            dh = div_hist[divs[k]]; dh[0].append(d); dh[1].append(hgs[k]); dh[2].append(ags[k])
            glob[0].append(d); glob[1].append(hgs[k]); glob[2].append(ags[k])
        i = j
    res = pd.concat([df.reset_index(drop=True), pd.DataFrame(out, columns=["lh", "la", "h_n", "h_neff", "a_n", "a_neff"])], axis=1)
    return res


def evaluate(res: pd.DataFrame, rho: float = -0.05) -> dict:
    ev = res[(res["date"] >= EVAL_START) & res["lh"].notna() & (res["h_neff"] >= 4) & (res["a_neff"] >= 4)].copy()
    P = probs_from_matrix(score_matrix(ev["lh"].to_numpy(), ev["la"].to_numpy(), rho))
    y15 = (ev["hg"] + ev["ag"] >= 2).astype(int); y25 = (ev["hg"] + ev["ag"] >= 3).astype(int)
    yb = ((ev["hg"] > 0) & (ev["ag"] > 0)).astype(int); yh = (ev["hg"] > ev["ag"]).astype(int); ya = (ev["hg"] < ev["ag"]).astype(int)
    out = {}
    for split, m in (("train", ev["date"] <= TRAIN_END), ("test", ev["date"] > TRAIN_END)):
        m = m.to_numpy()
        out[split] = {"n": int(m.sum()),
                      "O15": logloss(P["O15"][m], y15[m]), "O25": logloss(P["O25"][m], y25[m]), "BTTS": logloss(P["BTTS"][m], yb[m]),
                      "HW": logloss(P["HW"][m], yh[m]), "AW": logloss(P["AW"][m], ya[m])}
        # market reference for the result (average bookmaker prices, proportional de-margin)
        inv = 1 / ev.loc[m, ["oh", "od", "oa"]].to_numpy(dtype=float)
        ok = np.isfinite(inv).all(axis=1)
        if ok.sum() > 100:
            p3 = inv[ok] / inv[ok].sum(axis=1, keepdims=True)
            out[split]["mkt_HW"] = logloss(p3[:, 0], yh[m].to_numpy()[ok]); out[split]["mkt_AW"] = logloss(p3[:, 2], ya[m].to_numpy()[ok])
            out[split]["HW_on_priced"] = logloss(P["HW"][m][ok], yh[m].to_numpy()[ok]); out[split]["AW_on_priced"] = logloss(P["AW"][m][ok], ya[m].to_numpy()[ok])
        # calibration of the top O15 / HW buckets
        for key, y, edges in (("O15", y15, (0.84, 0.88, 1.01)), ("HW", yh, (0.5, 0.6, 1.01))):
            for lo, hi in zip(edges[:-1], edges[1:]):
                b = m & (P[key] >= lo) & (P[key] < hi)
                if b.sum():
                    out[split][f"{key}[{lo:.2f}-{hi:.2f})"] = (int(b.sum()), round(float(P[key][b].mean()), 3), round(float(y[b].mean()), 3))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="main leagues only")
    args = ap.parse_args()
    t0 = time.time()
    df = load_all()
    if args.quick:
        df = df[df["source"] == "main"].reset_index(drop=True)
    print(f"loaded {len(df):,} matches in {time.time() - t0:.0f}s", flush=True)
    variants = [("base K40", dict()), ("cap5 K40", dict(cap=5)), ("opp K40", dict(opp_adjust=True)),
                ("opp K60", dict(opp_adjust=True, K=60.0)), ("opp+cap5 K40", dict(opp_adjust=True, cap=5))]
    rows = []
    for name, kw in variants:
        t1 = time.time()
        res = replay(df, **kw)
        ev = evaluate(res)
        print(f"{name:14s} {time.time() - t1:4.0f}s  " + "  ".join(f"{s}: n={ev[s]['n']} O15 {ev[s]['O15']:.4f} O25 {ev[s]['O25']:.4f} BTTS {ev[s]['BTTS']:.4f} HW {ev[s]['HW']:.4f} AW {ev[s]['AW']:.4f}" for s in ("train", "test")), flush=True)
        for s in ("train", "test"):
            extra = {k: v for k, v in ev[s].items() if "[" in k or k.startswith("mkt") or k.endswith("priced")}
            print(f"    {s}: {extra}")
        rows.append({"variant": name, **{f"{s}_{k}": v for s in ("train", "test") for k, v in ev[s].items() if isinstance(v, (int, float))}})
    pd.DataFrame(rows).to_csv(Path(__file__).resolve().parent / "model_variants.csv", index=False)


if __name__ == "__main__":
    main()
