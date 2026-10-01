#!/usr/bin/env python3
"""Boost studies from the Liam Hartley video review (2026-10-01) — read-only research, nothing is adopted
automatically; every adoption decision uses the strict gate: test-season log-loss must improve and no market
may regress by more than 0.0005.

  A. parameter sweep   HL / venue-K / max-n (rho free on the base replay) — his "ML optimization" future plan,
                       done properly: select on the train window, confirm on the untouched test window.
  B. market-bias study favorite-longshot / public-money bias in bookmaker prices (his value-betting thesis),
                       measured on our own priced matches per season — feeds a display-only note if robust.
  C. xG ratings check  ratings built from xG where published (season 26/27 only — football-data added HxG/AxG
                       this season, older seasons have none, Understat is blocked) — evaluated on the 26/27 window.

Usage: python3 backtest/boost_studies.py [--skip-sweep] [--skip-bias] [--skip-xg]
Results are appended incrementally to backtest/BOOST_RESULTS.md; replays are cached in backtest/cache_boost/.
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from backtest import EVAL_START, TRAIN_END, load_all, logloss, probs_from_matrix, score_matrix  # noqa: E402
from model_variants import evaluate, replay  # noqa: E402

CACHE = HERE / "cache_boost"
CACHE.mkdir(exist_ok=True)
OUT = HERE / "BOOST_RESULTS.md"
MK = ["O15", "O25", "BTTS", "HW", "AW"]
BASE = dict(HL=120.0, K=40.0, KV=20.0, K_s=5.0, max_n=40, max_days=400, div_K=30.0)
GATE = 0.0005
lines: list[str] = []


def say(msg: str = "") -> None:
    print(msg, flush=True)
    lines.append(msg)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def mean5(d: dict) -> float:
    return sum(d[k] for k in MK) / 5.0


def key_of(**kw) -> str:
    p = {**BASE, **kw}
    return "r_" + "_".join(f"{k}{v}" for k, v in sorted(p.items()))


def get_replay(df: pd.DataFrame, **kw):
    """replay with on-disk cache (full res frame incl. odds columns)."""
    name = key_of(**kw)
    f = CACHE / f"{name}.pkl"
    if f.exists():
        return pd.read_pickle(f)
    t = time.time()
    p = {**BASE, **kw}
    res = replay(df, **p)
    res.to_pickle(f)
    say(f"  replay {name} in {time.time() - t:.0f}s")
    return res


def line_of(tag: str, ev: dict) -> str:
    tr, te = ev["train"], ev["test"]
    return (f"| {tag} | {tr['n']:,} | {mean5(tr):.4f} | {te['n']:,} | "
            + " | ".join(f"{te[k]:.4f}" for k in MK) + f" | {mean5(te):.4f} |")


HDR = ("| variant | train n | train mean LL | test n | test O15 | test O25 | test BTTS | test HW "
       "| test AW | test mean LL |\n|:--|--:|--:|--:|--:|--:|--:|--:|--:|--:|")


def gate(base_ev: dict, cand_ev: dict) -> tuple[bool, list[str]]:
    """adopt iff test mean improves AND no test market regresses by more than GATE."""
    reasons = []
    d_mean = mean5(cand_ev["test"]) - mean5(base_ev["test"])
    if d_mean >= 0:
        reasons.append(f"test mean not better ({d_mean:+.4f})")
    for k in MK:
        d = cand_ev["test"][k] - base_ev["test"][k]
        if d > GATE:
            reasons.append(f"{k} regresses {d:+.4f}")
    return (not reasons), reasons


# ---------------------------------------------------------------------------- A. parameter sweep
def sweep(df: pd.DataFrame) -> dict:
    say("\n## A. Parameter sweep (select on train ≤ 2025-06-30, confirm on test 25/26–26/27)\n")
    say("_base = production: HL=120, KV=20, K tempo=40, K strength=5, max_n=40, div_K=30, rho=-0.05, clamp 0.15–4.5_\n")
    base_res = get_replay(df)
    base_ev = evaluate(base_res, rho=-0.05)
    say(HDR)
    say(line_of("**base (production)**", base_ev))
    say("_sanity vs backtest/RESULTS.md two-K row (n=14,135): O15 0.5395 O25 0.6808 BTTS 0.6842 HW 0.6507 AW 0.5825_\n")

    # rho: free — only touches the score matrix inside evaluate()
    say("### rho (Dixon-Coles low-score correction)\n")
    say("| rho | train mean | test mean | test O15 | test O25 | test BTTS | test HW | test AW |\n|:--|--:|--:|--:|--:|--:|--:|--:|")
    best_rho, best_rho_tr = -0.05, mean5(base_ev["train"])
    for r in (0.0, -0.03, -0.05, -0.08, -0.10):
        ev = evaluate(base_res, rho=r)
        say(f"| {r:+.2f} | {mean5(ev['train']):.4f} | {mean5(ev['test']):.4f} | "
            + " | ".join(f"{ev['test'][k]:.4f}" for k in MK) + " |")
        if mean5(ev["train"]) < best_rho_tr:
            best_rho_tr, best_rho = mean5(ev["train"]), r
    say(f"train selects rho = {best_rho:+.2f} (production -0.05)\n")

    def one_param(name: str, values: list, base_val, kw_name: str) -> float:
        say(f"### {name}\n")
        say("| value | train mean | test mean | test O15 | test O25 | test BTTS | test HW | test AW | gate vs base |\n|:--|--:|--:|--:|--:|--:|--:|--:|--:|")
        best_v, best_tr = base_val, mean5(base_ev["train"])
        for v in values:
            if v == base_val:
                ev, tag = base_ev, "prod"
            else:
                res = get_replay(df, **{kw_name: v})
                ev = evaluate(res, rho=-0.05)
                ok, why = gate(base_ev, ev)
                tag = "ok" if ok else "FAIL: " + "; ".join(why)
            say(f"| {v} | {mean5(ev['train']):.4f} | {mean5(ev['test']):.4f} | "
                + " | ".join(f"{ev['test'][k]:.4f}" for k in MK) + f" | {tag} |")
            if mean5(ev["train"]) < best_tr:
                best_tr, best_v = mean5(ev["train"]), v
        say(f"train selects {name} = {best_v} (production {base_val})\n")
        return best_v

    sel_hl = one_param("HL (form half-life days)", [60, 90, 120, 150, 180], 120.0, "HL")
    sel_kv = one_param("KV (venue blend K)", [10, 20, 30, 40], 20.0, "KV")
    sel_nn = one_param("max_n (matches per team)", [30, 40, 60], 40, "max_n")

    # compose the train-selected set; confirm with one replay under the gate
    comp_kw = {}
    if sel_hl != 120.0:
        comp_kw["HL"] = sel_hl
    if sel_kv != 20.0:
        comp_kw["KV"] = sel_kv
    if sel_nn != 40:
        comp_kw["max_n"] = sel_nn
    if best_rho != -0.05:
        comp_kw["__rho"] = best_rho  # handled below
    rho_comp = comp_kw.pop("__rho", -0.05)
    say("### Composed candidate\n")
    if not comp_kw and rho_comp == -0.05:
        say("**No parameter moved off production — nothing to compose. Sweep adopts nothing.**\n")
        return {"adopted": {}, "base_ev": base_ev}
    res = get_replay(df, **comp_kw) if comp_kw else base_res
    comp_ev = evaluate(res, rho=rho_comp)
    say(HDR)
    say(line_of(f"composed {comp_kw} rho={rho_comp:+.2f}", comp_ev))
    say(line_of("base (production)", base_ev))
    ok, why = gate(base_ev, comp_ev)
    adopted = {**comp_kw}
    if rho_comp != -0.05:
        adopted["DC_RHO"] = rho_comp
    if ok:
        say(f"**GATE PASSED — adopt: {adopted}**\n")
    else:
        say(f"**GATE FAILED — adopt nothing ({'; '.join(why)})**\n")
        adopted = {}
    return {"adopted": adopted, "base_ev": base_ev}


# ---------------------------------------------------------------------------- B. market-bias study
def bias(df: pd.DataFrame) -> None:
    say("\n## B. Market-bias study (favorite-longshot / public money)\n")
    say("_proportional de-margin on opening average prices; every outcome of every priced match is one row; "
        "gap = actual − implied (percentage points). Robust = same sign in ≥3 seasons with n≥150 there._\n")
    d = df[(df["source"] == "main") & (df["date"] >= EVAL_START)].copy()
    d = d.dropna(subset=["oh", "od", "oa", "oo", "ou"])
    d = d[(d[["oh", "od", "oa", "oo", "ou"]] > 1).all(axis=1)]
    # --- O2.5 two-way
    inv = (1 / d["oo"] + 1 / d["ou"])
    d["p25"] = (1 / d["oo"]) / inv
    d["y25"] = (d["hg"] + d["ag"] >= 3).astype(int)
    edges = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95, 1.001]
    d["b25"] = pd.cut(d["p25"], edges, right=False)
    say("### Over 2.5 market\n")
    say("| implied bucket | n | mean implied | actual | gap (pp) | robust? |\n|:--|--:|--:|--:|--:|:--|")
    for b, g in d.groupby("b25", observed=True):
        if len(g) < 100:
            continue
        imp, act = g["p25"].mean(), g["y25"].mean()
        gap = (act - imp) * 100
        per_season = []
        for s, gs in g.groupby("season"):
            if len(gs) >= 150:
                per_season.append(np.sign((gs["y25"].mean() - gs["p25"].mean())))
        robust = (len(per_season) >= 3 and all(x == np.sign(gap) for x in per_season) and abs(gap) >= 1.0)
        say(f"| {b.left:.2f}–{b.right:.2f} | {len(g):,} | {100 * imp:.1f}% | {100 * act:.1f}% | {gap:+.1f} | {'YES' if robust else ''} |")
    # --- 1X2 favorite-longshot: pool the three outcomes
    inv3 = 1 / d[["oh", "od", "oa"]].to_numpy()
    p3 = inv3 / inv3.sum(axis=1, keepdims=True)
    y_h = (d["hg"] > d["ag"]).to_numpy().astype(int)
    y_d = (d["hg"] == d["ag"]).to_numpy().astype(int)
    y_a = (d["hg"] < d["ag"]).to_numpy().astype(int)
    imp_all = np.concatenate([p3[:, 0], p3[:, 1], p3[:, 2]])
    y_all = np.concatenate([y_h, y_d, y_a])
    seas_all = np.concatenate([d["season"].to_numpy()] * 3)
    fl = pd.DataFrame({"p": imp_all, "y": y_all, "season": seas_all})
    fl["b"] = pd.cut(fl["p"], edges, right=False)
    say("\n### 1X2 favorite-longshot (all outcomes pooled)\n")
    say("| implied bucket | n | mean implied | actual | gap (pp) | robust? |\n|:--|--:|--:|--:|--:|:--|")
    for b, g in fl.groupby("b", observed=True):
        if len(g) < 200:
            continue
        imp, act = g["p"].mean(), g["y"].mean()
        gap = (act - imp) * 100
        per_season = []
        for s, gs in g.groupby("season"):
            if len(gs) >= 300:
                per_season.append(np.sign((gs["y"].mean() - gs["p"].mean())))
        robust = (len(per_season) >= 3 and all(x == np.sign(gap) for x in per_season) and abs(gap) >= 1.0)
        say(f"| {b.left:.2f}–{b.right:.2f} | {len(g):,} | {100 * imp:.1f}% | {100 * act:.1f}% | {gap:+.1f} | {'YES' if robust else ''} |")
    say("\n_interpretation: a positive gap in the low buckets = longshots win more than implied (public loves "
        "longshots); a negative gap there = classic favorite-longshot bias (longshots overpriced → value sits "
        "with favourites). Robust rows only feed a display note — odds never filter anything._\n")


# ---------------------------------------------------------------------------- C. xG window check
def replay_xg(df: pd.DataFrame, xg_w: float, HL=120.0, K=40.0, KV=20.0, max_n=40, max_days=400,
              div_K=30.0, K_s=5.0) -> pd.DataFrame:
    """model_variants.replay with per-match xG blending: where a match publishes xG, the normalised xG ratio
    is log-blended with the normalised goals ratio by weight xg_w; leagues/seasons without xG keep goals.
    The goals league baseline (mu_h/mu_a) still sets the scale — xG only re-weights attack/defence."""
    ords = df["ord"].to_numpy(); divs = df["div"].to_numpy(); countries = df["country"].to_numpy()
    homes = df["home"].to_numpy(); aways = df["away"].to_numpy()
    hgs = df["hg"].to_numpy(); ags = df["ag"].to_numpy()
    hxgs = df["hxg"].to_numpy(dtype=float) if "hxg" in df.columns else np.full(len(df), np.nan)
    axgs = df["axg"].to_numpy(dtype=float) if "axg" in df.columns else np.full(len(df), np.nan)

    team_hist: dict = defaultdict(list)
    div_hist: dict = defaultdict(lambda: ([], [], []))
    div_xg: dict = defaultdict(lambda: ([], [], []))       # div -> (ords, hxg, axg)
    glob = ([], [], [])
    div_cache: dict = {}; prior_cache: dict = {}; divx_cache: dict = {}

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

    def div_avg_xg(div, d):
        """(home xG avg, away xG avg) when the division has >= 8 published xG matches in the window, else None."""
        key = (div, d)
        if key in divx_cache:
            return divx_cache[key]
        o = np.asarray(div_xg[div][0])
        res_ = None
        if len(o):
            m = o >= d - max_days
            w = 0.5 ** ((d - o[m]) / HL); n = w.sum()
            hx = np.asarray(div_xg[div][1])[m]; ax = np.asarray(div_xg[div][2])[m]
            okh = np.isfinite(hx); oka = np.isfinite(ax)
            if n > 0 and okh.sum() >= 8 and oka.sum() >= 8:
                res_ = (float((w[okh] * hx[okh]).sum() / w[okh].sum()),
                        float((w[oka] * ax[oka]).sum() / w[oka].sum()))
        divx_cache[key] = res_
        return res_

    def norm(gf, ga, xgf, xga, v, dv, d):
        mh, ma = div_avg(dv, d)
        if v == 1:
            gfn, gan = gf / mh, ga / ma
        else:
            gfn, gan = gf / ma, ga / mh
        if xg_w <= 0 or not (np.isfinite(xgf) and np.isfinite(xga)):
            return gfn, gan
        dx = div_avg_xg(dv, d)
        if dx is None:
            return gfn, gan
        mxh, mxa = dx
        if v == 1:
            xfn, xan = xgf / mxh, xga / mxa
        else:
            xfn, xan = xgf / mxa, xga / mxh
        e1 = math.log(max(gfn, 0.01)); e2 = math.log(max(gan, 0.01))
        f1 = math.log(max(xfn, 0.01)); f2 = math.log(max(xan, 0.01))
        return math.exp(xg_w * f1 + (1 - xg_w) * e1), math.exp(xg_w * f2 + (1 - xg_w) * e2)

    def profile(key, d, venue):
        recs = team_hist.get(key)
        if not recs:
            return None
        lo = d - max_days
        sel = [r for r in recs[-max_n:] if r[0] >= lo]
        if not sel:
            return None
        sw = swa = swd = sv = sva = svd = 0.0
        for o, v, gf, ga, xgf, xga, dv in sel:
            w = 0.5 ** ((d - o) / HL)
            gfn, gan = norm(gf, ga, xgf, xga, v, dv, d)
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
        # two-K shrinkage (production): strength K_s, tempo K, log space
        la, ld = math.log(max(att, 0.05)), math.log(max(dfc, 0.05))
        s = (la - ld) * sw / (sw + K_s)
        t = (la + ld) * sw / (sw + K)
        return math.exp((t + s) / 2), math.exp((t - s) / 2), len(sel), sw

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
            team_hist[hk].append((d, 1, hgs[k], ags[k], hxgs[k], axgs[k], divs[k]))
            team_hist[ak].append((d, 0, ags[k], hgs[k], axgs[k], hxgs[k], divs[k]))
            dh = div_hist[divs[k]]; dh[0].append(d); dh[1].append(hgs[k]); dh[2].append(ags[k])
            dx = div_xg[divs[k]]; dx[0].append(d); dx[1].append(hxgs[k]); dx[2].append(axgs[k])
            glob[0].append(d); glob[1].append(hgs[k]); glob[2].append(ags[k])
        i = j
    res = pd.concat([df.reset_index(drop=True), pd.DataFrame(out, columns=["lh", "la", "h_n", "h_neff", "a_n", "a_neff"])], axis=1)
    return res


def evaluate_window(res: pd.DataFrame, start: pd.Timestamp, rho: float = -0.05) -> dict:
    ev = res[(res["date"] >= start) & res["lh"].notna() & (res["h_neff"] >= 4) & (res["a_neff"] >= 4)].copy()
    P = probs_from_matrix(score_matrix(ev["lh"].to_numpy(), ev["la"].to_numpy(), rho))
    y15 = (ev["hg"] + ev["ag"] >= 2).astype(int); y25 = (ev["hg"] + ev["ag"] >= 3).astype(int)
    yb = ((ev["hg"] > 0) & (ev["ag"] > 0)).astype(int); yh = (ev["hg"] > ev["ag"]).astype(int); ya = (ev["hg"] < ev["ag"]).astype(int)
    out = {"n": int(len(ev))}
    for k, p, y in (("O15", P["O15"], y15), ("O25", P["O25"], y25), ("BTTS", P["BTTS"], yb), ("HW", P["HW"], yh), ("AW", P["AW"], ya)):
        out[k] = logloss(p.to_numpy() if hasattr(p, "to_numpy") else p, y.to_numpy())
    out["mean"] = sum(out[k] for k in MK) / 5
    return out


def xg_check(df: pd.DataFrame) -> None:
    say("\n## C. xG ratings — 26/27 window check\n")
    say("_football-data publishes HxG/AxG from season 26/27 only (older seasons have none; Understat is blocked). "
        "Evaluation window = matches since 2026-07-01 with ≥4 time-weighted matches per team. Small n → the bar "
        "for adoption is high; anything inconclusive is NOT adopted._\n")
    base_res = get_replay(df)          # production params (xG weight 0)
    n_xg = int(np.isfinite(df.get("hxg", pd.Series(dtype=float)).to_numpy(dtype=float)).sum()) if "hxg" in df.columns else 0
    say(f"matches with published xG in the pool: {n_xg:,}")
    base = evaluate_window(base_res, pd.Timestamp("2026-07-01"))
    say("| variant | n | O15 | O25 | BTTS | HW | AW | mean LL | gate vs base |\n|:--|--:|--:|--:|--:|--:|--:|--:|:--|")
    say(f"| base (goals only) | {base['n']:,} | {base['O15']:.4f} | {base['O25']:.4f} | {base['BTTS']:.4f} | {base['HW']:.4f} | {base['AW']:.4f} | {base['mean']:.4f} | — |")
    adopted_w = None
    for w in (0.3, 0.5, 0.7, 1.0):
        name = CACHE / f"r_xgw{w}.pkl"
        if name.exists():
            res = pd.read_pickle(name)
        else:
            t = time.time()
            res = replay_xg(df, xg_w=w)
            res.to_pickle(name)
            say(f"  replay xg_w={w} in {time.time() - t:.0f}s")
        r = evaluate_window(res, pd.Timestamp("2026-07-01"))
        d_mean = r["mean"] - base["mean"]
        worst = max(r[k] - base[k] for k in MK)
        ok = r["n"] >= 300 and d_mean <= -0.001 and worst <= 0.001
        tag = "CANDIDATE" if ok else ("inconclusive" if r["n"] < 300 else "no gain")
        if ok and adopted_w is None:
            adopted_w = w
        say(f"| xg_w={w} | {r['n']:,} | {r['O15']:.4f} | {r['O25']:.4f} | {r['BTTS']:.4f} | {r['HW']:.4f} | {r['AW']:.4f} | {r['mean']:.4f} | {tag} |")
    if adopted_w:
        say(f"**GATE PASSED at w={adopted_w}** — but with this n, re-validate when 26/27 reaches ≥3,000 evaluated matches.")
    else:
        say("**No xG variant clears the gate — xG stays display-only (as today). Re-run when the 26/27 sample is bigger.**")
    say("")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-sweep", action="store_true")
    ap.add_argument("--skip-bias", action="store_true")
    ap.add_argument("--skip-xg", action="store_true")
    args = ap.parse_args()
    say("# Boost studies — video takeaways (Liam Hartley / Systematic Sports)\n")
    say(f"_run {time.strftime('%Y-%m-%d %H:%M')}; gate: test mean must improve and no market may regress by >{GATE}_")
    t = time.time()
    df = load_all()
    say(f"loaded {len(df):,} matches in {time.time() - t:.0f}s")
    if not args.skip_sweep:
        sweep(df)
    if not args.skip_bias:
        bias(df)
    if not args.skip_xg:
        xg_check(df)
    say(f"\n_done in {time.time() - t:.0f}s._")


if __name__ == "__main__":
    main()
