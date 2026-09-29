#!/usr/bin/env python3
"""
Error analysis for the Goals Scanner model — WHERE the predictions systematically fail.

Read-only study on top of the existing backtest harness (backtest/backtest.py +
backtest/model_variants.py, no look-ahead). It does NOT modify the model: it replays the
CURRENT production model (two-strength shrinkage K_s=5 / K=40, as in scanner.py), re-derives
the full score matrix for the 1X2 and low-score checks, and stratifies every error by the
model's actual inputs:

  * league / country / season            (systematic bias + temporal drift)
  * model total lambda and league tempo  (mispriced scoring levels)
  * team sample size (effective weight)  (thin-history behaviour)
  * strength gap |lh - la|               (mismatch behaviour)
  * month / day of week / venue          (calendar & venue effects)
  * confident-error rate per input       (inputs associated with the worst mistakes)
  * low-score cells (0-0, 1-1, 4+, 5+)   (Dixon-Coles territory)
  * 1X2 calibration
  * market reference (where bookmakers disagree with the model — who is right, N/A where no odds)

Usage:
    python backtest/error_analysis.py            # ~60s: replays the production model
    python backtest/error_analysis.py --out x.md

Outputs a markdown report (default: backtest/ERROR_ANALYSIS.md).
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
from backtest import EVAL_START, MAXG, calibration_table, logloss, brier, probs_from_matrix, score_matrix  # noqa: E402

MIN_N = 120          # minimum group size for a row to be shown in bias tables
CONF = 0.75          # "confident" = model probability at/above this (or <= 1 - this for the other side)


def pct(x):
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.1%}"


def gapf(x):
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:+.1%}"


def f2(x):
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.3f}"


def md(df: pd.DataFrame) -> str:
    return df.to_markdown(index=False) + "\n"


# --------------------------------------------------------------------------- load
def load() -> pd.DataFrame:
    """Replay the CURRENT production model (two-strength shrinkage, validated 2026-09-28 — see
    backtest/RESULTS.md) with the same no-look-ahead engine, and take the league-tempo averages
    (mu_h/mu_a, which do not depend on team shrinkage) from the base single-K run."""
    from backtest import load_all, run_model, add_model_columns
    from model_variants import replay

    t0 = time.time()
    df = load_all()
    print(f"data loaded in {time.time() - t0:.0f}s ({len(df):,} matches)", flush=True)
    res = replay(df, HL=120.0, K=40.0, KV=20.0, K_s=5.0)         # CURRENT production model (two-K)
    res = add_model_columns(res, rho=-0.05, with_market=False)   # dc_* probabilities, as in production
    res_base = run_model(df, HL=120.0, K=40.0, KV=20.0)          # same engine, base variant (for mu_h/mu_a)
    res["mu_h"] = res_base["mu_h"].to_numpy()
    res["mu_a"] = res_base["mu_a"].to_numpy()
    for c in ("tot", "y15", "y25", "ybtts", "h_o15", "h_o25", "h_btts", "a_o15", "a_o25", "a_btts"):
        res[c] = res_base[c].to_numpy()
    print(f"production-model replay done in {time.time() - t0:.0f}s", flush=True)
    ev = res[(res["date"] >= EVAL_START) & res["lh"].notna()].copy()
    ev["split"] = np.where(ev["date"] <= pd.Timestamp("2025-06-30"), "train (23/24–24/25)", "test (25/26–26/27)")
    ev["month"] = ev["date"].dt.month
    ev["dow"] = ev["date"].dt.dayofweek            # 0 = Monday
    ev["league"] = ev["country"] + " · " + ev["league"]
    ev["lsum"] = ev["lh"] + ev["la"]               # model total expected goals
    ev["mu"] = ev["mu_h"] + ev["mu_a"]             # league-average total goals (model input)
    ev["gap"] = (ev["lh"] - ev["la"]).abs()        # strength gap (model input)
    ev["neff"] = np.minimum(ev["h_neff"], ev["a_neff"])
    ev["e15"] = ev["y15"] - ev["dc_O15"]
    ev["e25"] = ev["y25"] - ev["dc_O25"]
    ev["ebtts"] = ev["ybtts"] - ev["dc_BTTS"]
    return ev


def full_probs(ev: pd.DataFrame) -> dict[str, np.ndarray]:
    """Re-derive the full score matrix from the stored model lambdas (1X2 + low-score cells).
    Uses the production Dixon-Coles correction (rho=-0.05), as scanner.py does for result probs."""
    M = score_matrix(ev["lh"].to_numpy(), ev["la"].to_numpy(), -0.05)
    g = np.arange(MAXG + 1)
    out = {
        "P_H": M[:, g[:, None] > g[None, :]].sum(axis=1),
        "P_A": M[:, g[:, None] < g[None, :]].sum(axis=1),
    }
    out["P_D"] = 1 - out["P_H"] - out["P_A"]
    out["P_00"] = M[:, 0, 0]
    out["P_11"] = M[:, 1, 1]
    out["P_4p"] = M[:, (g[:, None] + g[None, :]) >= 4].sum(axis=1)
    out["P_5p"] = M[:, (g[:, None] + g[None, :]) >= 5].sum(axis=1)
    out["P_HG1"] = M[:, 1:, :].sum(axis=(1, 2))
    out["P_AG1"] = M[:, :, 1:].sum(axis=(1, 2))
    return out


def bias_table(ev: pd.DataFrame, key: pd.Series | str, min_n: int = MIN_N) -> pd.DataFrame:
    """Mean signed error (actual - predicted) per group for O1.5 / O2.5 / BTTS, with Brier on O2.5."""
    k = ev[key] if isinstance(key, str) else key
    rows = []
    for name, g in ev.groupby(k, observed=True):
        if len(g) < min_n:
            continue
        rows.append({
            "group": name, "n": len(g),
            "O1.5 gap": g["e15"].mean(), "O2.5 gap": g["e25"].mean(), "BTTS gap": g["ebtts"].mean(),
            "O2.5 Brier": brier(g["dc_O25"], g["y25"]), "O2.5 actual": g["y25"].mean(),
        })
    t = pd.DataFrame(rows).sort_values("n", ascending=False)
    for c in ("O1.5 gap", "O2.5 gap", "BTTS gap"):
        t[c] = t[c].map(gapf)
    t["O2.5 Brier"] = t["O2.5 Brier"].map(f2)
    t["O2.5 actual"] = t["O2.5 actual"].map(pct)
    return t


def confident_errors(ev: pd.DataFrame, pcol: str, ycol: str) -> pd.DataFrame:
    """Confidently-wrong matches (p >= CONF and y=0, or p <= 1-CONF and y=1), rate per input group."""
    p, y = ev[pcol], ev[ycol]
    ev = ev.copy()
    ev["conf_wrong"] = ((p >= CONF) & (y == 0)).astype(int) + ((p <= 1 - CONF) & (y == 1)).astype(int)
    ev["abs_err"] = (y - p).abs()
    return ev


# --------------------------------------------------------------------------- report
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "ERROR_ANALYSIS.md"))
    args = ap.parse_args()

    t0 = time.time()
    ev = load()
    F = full_probs(ev)
    for k, v in F.items():
        ev[k] = v
    ev["yH"] = (ev["hg"] > ev["ag"]).astype(int)
    ev["yA"] = (ev["ag"] > ev["hg"]).astype(int)
    ev["yD"] = 1 - ev["yH"] - ev["yA"]
    n = len(ev)
    nt = int((ev["source"] == "main").sum())

    o = []
    o.append("# Model error analysis — where the predictions systematically fail\n")
    o.append(f"_Generated {datetime.now():%Y-%m-%d %H:%M}. Read-only study: the model, its parameters and every "
             f"published probability are **unchanged**. Predictions are a no-look-ahead replay of the **current "
             f"production model** (two-strength log-space shrinkage — strength K=5, tempo K=40; validated "
             f"2026-09-28, see backtest/RESULTS.md; half-life 120 d, venue K=20, Dixon-Coles rho = -0.05). "
             f"Only matches played strictly before each match date are used; league-tempo inputs are taken from "
             f"the identical base single-K=40 replay (backtest/predictions.pkl)._\n")
    o.append(f"**Dataset:** {n:,} matches with a model prediction, {EVAL_START:%b %Y} → {ev['date'].max():%d %b %Y}, "
             f"{ev['league'].nunique()} leagues in {ev['country'].nunique()} countries "
             f"({nt:,} main-league matches with bookmaker odds; the rest without odds).\n")
    years = ev["date"].dt.year.value_counts().sort_index()
    o.append("Matches by calendar year: " + " · ".join(f"{k}: {v:,}" for k, v in years.items()) +
             " (2026 is partial, through " + f"{ev['date'].max():%d %b}" + ").\n")
    o.append("**What 'gap' means below:** actual hit rate minus the model's average predicted probability. "
             "A positive gap = the model under-predicted that market in the group; negative = over-predicted. "
             "Groups with fewer than " + str(MIN_N) + " matches are hidden (too noisy to be evidence).\n")

    # ---------------------------------------------------------------- baseline
    o.append("## 1. Baseline accuracy (all evaluation matches)\n")
    rows = []
    for name, p, y in [("Over 1.5", ev["dc_O15"], ev["y15"]), ("Over 2.5", ev["dc_O25"], ev["y25"]),
                       ("BTTS", ev["dc_BTTS"], ev["ybtts"]), ("Home win", ev["P_H"], ev["yH"]),
                       ("Draw", ev["P_D"], ev["yD"]), ("Away win", ev["P_A"], ev["yA"])]:
        rows.append({"market": name, "n": len(p), "avg predicted": pct(p.mean()), "actual": pct(y.mean()),
                     "gap": gapf(y.mean() - p.mean()), "log-loss": f"{logloss(p, y):.4f}", "Brier": f"{brier(p, y):.4f}"})
    o.append(md(pd.DataFrame(rows)))

    # ---------------------------------------------------------------- calibration
    o.append("## 2. Calibration by predicted probability (signed gap)\n")
    for name, p, y, edges in [
        ("Over 2.5", ev["dc_O25"], ev["y25"], (0, .35, .4, .45, .5, .55, .6, .65, .7, .75, .8, 1.01)),
        ("Over 1.5", ev["dc_O15"], ev["y15"], (0, .75, .8, .85, .88, .9, .93, .96, 1.01)),
        ("BTTS", ev["dc_BTTS"], ev["ybtts"], (0, .35, .4, .45, .5, .55, .6, .65, .7, .75, 1.01))]:
        ct = calibration_table(p, y, edges)
        ct["predicted"] = ct["predicted"].map(pct); ct["actual"] = ct["actual"].map(pct); ct["gap"] = ct["gap"].map(gapf)
        o.append(f"**{name}**\n")
        o.append(md(ct))

    # ---------------------------------------------------------------- by league
    o.append("## 3. Systematic bias by league (|O2.5 gap| ranked)\n")
    lt = bias_table(ev, "league").copy()
    lt["_num"] = lt["O2.5 gap"].str.replace("+", "", regex=False).str.rstrip("%").astype(float)
    lt = lt.sort_values("_num", ascending=False, key=abs)
    over = lt[lt["O2.5 gap"].str.startswith("+")].sort_values("_num", ascending=False).head(5)
    under = lt[lt["O2.5 gap"].str.startswith("-")].sort_values("_num").head(5)
    lt = lt.drop(columns="_num")
    o.append(md(lt.head(20)))
    o.append(f"\n_Shown: top 20 of {len(lt)} leagues by |O2.5 gap| (all leagues with ≥{MIN_N} matches below)._")
    o.append("\n**Most over-predicted (model too bullish):** " +
             "; ".join(f"{r['group']} ({r['O2.5 gap']}, n={int(r['n'])})" for _, r in over.iterrows()) + ".\n")
    o.append("**Most under-predicted (model too cautious):** " +
             "; ".join(f"{r['group']} ({r['O2.5 gap']}, n={int(r['n'])})" for _, r in under.iterrows()) + ".\n")

    # ---------------------------------------------------------------- by season / month / dow
    o.append("## 4. Temporal pattern (drift, season start, calendar)\n")
    ev["year"] = ev["date"].dt.year
    o.append("**By calendar year** (drift check: the model must stay calibrated as data ages)\n")
    o.append(md(bias_table(ev, "year", min_n=50)))
    m = ev.copy()
    m["phase"] = pd.Series(np.select(
        [m["month"].isin([8, 9]), m["month"].isin([10, 11]), m["month"] == 12, m["month"] == 1,
         m["month"].isin([2, 3]), m["month"].isin([4, 5, 6])],
        ["Aug–Sep (season start)", "Oct–Nov", "Dec (midwinter)", "Jan (winter)",
         "Feb–Mar (spring)", "Apr–May (end of season)"],
        default="July (summer-hemisphere seasons)"), index=m.index)
    o.append("**By month of year** (European seasons dominate the data)\n")
    o.append(md(bias_table(m, "phase", min_n=100)))
    ev["dow_label"] = pd.cut(ev["dow"], [-0.5, 4.5, 5.5, 6.5], labels=["Mon–Fri", "Saturday", "Sunday"])
    o.append("**By day of week**\n")
    o.append(md(bias_table(ev, "dow_label", min_n=100)))

    # ---------------------------------------------------------------- by model input
    o.append("## 5. Error by the model's own inputs\n")
    ev["lsum_b"] = pd.cut(ev["lsum"], [0, 1.7, 2.0, 2.3, 2.6, 2.9, 5.0],
                          labels=["λ < 1.7 (very low)", "1.7–2.0", "2.0–2.3", "2.3–2.6", "2.6–2.9", "λ > 2.9 (high)"])
    o.append("**By model total expected goals (λ = lh + la)**\n")
    o.append(md(bias_table(ev, "lsum_b")))
    ev["mu_b"] = pd.cut(ev["mu"], [0, 2.4, 2.7, 3.0, 3.3, 5.0],
                        labels=["league avg < 2.4", "2.4–2.7", "2.7–3.0", "3.0–3.3", "league avg > 3.3"])
    o.append("**By league-average goals (the model's tempo input mu_h + mu_a)**\n")
    o.append(md(bias_table(ev, "mu_b")))
    ev["neff_b"] = pd.cut(ev["neff"], [0, 1, 2, 4, 8, 16, 100],
                          labels=["< 1 (≈ no recent matches)", "1–2", "2–4", "4–8", "8–16", "> 16 (strong sample)"])
    o.append("**By the weaker team's effective sample size (recent weighted matches — the data the model has on the weaker side)**\n")
    o.append(md(bias_table(ev, "neff_b")))
    ev["gap_b"] = pd.cut(ev["gap"], [0, .25, .5, .8, 1.2, 5],
                         labels=["≈ even (Δλ < 0.25)", "0.25–0.5", "0.5–0.8", "0.8–1.2", "Δλ > 1.2 (mismatch)"])
    o.append("**By strength gap |lh − la|**\n")
    o.append(md(bias_table(ev, "gap_b")))
    ev["venue_b"] = np.where(ev["lh"] >= ev["la"], "home side favoured", "away side favoured")
    o.append("**By which side the model favours** (venue check: home-favoured vs away-favoured games)\n")
    o.append(md(bias_table(ev, "venue_b", min_n=100)))

    # ---------------------------------------------------------------- team-goals (home/away asymmetry)
    o.append("**Team-goals asymmetry** — model P(team scores) vs actual (input: side of the pitch)\n")
    rows = []
    for name, p, y in [("Home team scores", ev["P_HG1"], (ev["hg"] > 0).astype(int)),
                       ("Away team scores", ev["P_AG1"], (ev["ag"] > 0).astype(int))]:
        rows.append({"market": name, "n": n, "avg predicted": pct(p.mean()), "actual": pct(y.mean()),
                     "gap": gapf(y.mean() - p.mean()), "Brier": f"{brier(p, y):.4f}"})
    o.append(md(pd.DataFrame(rows)))

    # ---------------------------------------------------------------- confident errors
    o.append("## 6. Confident errors — where the model is wrong with conviction\n")
    o.append("The app publishes a selection when the model probability clears its production bar "
             "(O1.5 ≥ 84%, O2.5 ≥ 60%, BTTS ≥ 60%, result ≥ 70%). A **confident error** is a published "
             "call that went the other way — the mistake that actually costs money. Note the model's O2.5/"
             "BTTS probabilities naturally sit in the ~30–65% band (shrinkage keeps λ close to league "
             "averages), so these bars are the meaningful confidence levels for those markets.\n")
    tiers = {"O1.5": ("dc_O15", "y15", 0.84), "O2.5": ("dc_O25", "y25", 0.60), "BTTS": ("dc_BTTS", "ybtts", 0.60)}
    for mkt, (pcol, ycol, thr) in tiers.items():
        ev[f"pub_{mkt}"] = ev[pcol] >= thr
        ev[f"puberr_{mkt}"] = ev[f"pub_{mkt}"] & (ev[ycol] == 0)
        pub = ev[f"pub_{mkt}"]
        o.append(f"**{mkt} (bar {thr:.0%})** — published on {pct(pub.mean())} of matches "
                 f"({int(pub.sum()):,} calls); hit rate when published: "
                 f"{pct(ev.loc[pub, ycol].mean())} vs predicted {pct(ev.loc[pub, pcol].mean())}; "
                 f"confident-error rate {pct(ev[f'puberr_{mkt}'].mean())} of all matches.\n")
    ev["pub_1X2"] = (ev["P_H"] >= 0.70) | (ev["P_A"] >= 0.70)
    ev["puberr_1X2"] = ((ev["P_H"] >= 0.70) & (ev["yH"] == 0)) | ((ev["P_A"] >= 0.70) & (ev["yA"] == 0))
    pub = ev["pub_1X2"]
    fav = ev[["P_H", "P_A"]].max(axis=1).to_numpy()
    fav_side = np.where(ev["P_H"].to_numpy() >= ev["P_A"].to_numpy(), ev["yH"].to_numpy(), ev["yA"].to_numpy())
    pm = pub.to_numpy()
    o.append(f"**Result H/A (bar 70%)** — published on {pct(pub.mean())} of matches ({int(pub.sum()):,} calls); "
             f"hit rate when published: {pct(fav_side[pm].mean())} vs predicted {pct(fav[pm].mean())}; "
             f"confident-error rate {pct(ev['puberr_1X2'].mean())} of all matches.\n")
    o.append("**Confident-error rate by league (O2.5, leagues with ≥ 40 published calls)**\n")
    rows = []
    for name, g in ev.groupby("league"):
        pub = g["pub_O2.5"].sum()
        if pub < 40:
            continue
        rows.append({"league": name, "published": int(pub), "hit rate": pct(g.loc[g["pub_O2.5"], "y25"].mean()),
                     "conf-error rate": pct(g["puberr_O2.5"].mean()), "avg predicted": pct(g.loc[g["pub_O2.5"], "dc_O25"].mean())})
    o.append(md(pd.DataFrame(rows).sort_values("conf-error rate", ascending=False).head(12)))
    o.append("\n**Confident-error rate by model input (O2.5)** — the table that answers "
             "*'which inputs are associated with the confident mistakes'*\n")
    rows = []
    for label, key in [("λ total", "lsum_b"), ("league tempo (mu)", "mu_b"), ("weaker-team sample", "neff_b"),
                       ("strength gap", "gap_b"), ("calendar year", "year"), ("day of week", "dow_label")]:
        for gname, g in ev.groupby(key, observed=True):
            if len(g) < 150:
                continue
            rows.append({"input": label, "group": str(gname), "n": len(g),
                         "published share": pct(g["pub_O2.5"].mean()),
                         "conf-error rate": pct(g["puberr_O2.5"].mean()),
                         "mean |error|": f"{(g['y25'] - g['dc_O25']).abs().mean():.3f}"})
    o.append(md(pd.DataFrame(rows)))
    tot_err = int(ev["puberr_O2.5"].sum())
    o.append(f"\n**Where the confident O2.5 errors live** — share of ALL confident errors ({tot_err:,} over the period) "
             "falling in each input bucket, with *lift* = share ÷ the bucket's share of all matches "
             "(lift > 1 = errors are over-concentrated there; lift < 1 = under-concentrated):\n")
    rows = []
    for label, key in [("λ total", "lsum_b"), ("league tempo (mu)", "mu_b"), ("weaker-team sample", "neff_b"),
                       ("strength gap", "gap_b"), ("calendar year", "year"), ("day of week", "dow_label")]:
        for gname, g in ev.groupby(key, observed=True):
            if len(g) < 150:
                continue
            e = int(g["puberr_O2.5"].sum())
            share = e / tot_err
            base = len(g) / len(ev)
            rows.append({"input": label, "group": str(gname), "n": len(g), "confident errors": e,
                         "share of all errors": pct(share), "lift": f"{share / base:.2f}"})
    o.append(md(pd.DataFrame(rows)))

    # ---------------------------------------------------------------- 1X2
    o.append("## 7. 1X2 (result market)\n")
    o.append("Calibration of the model's win/draw/loss probabilities (re-derived from the same score matrix):\n")
    rows = []
    for name, p, y in [("Home win", ev["P_H"], ev["yH"]), ("Draw", ev["P_D"], ev["yD"]), ("Away win", ev["P_A"], ev["yA"])]:
        rows.append({"outcome": name, "avg predicted": pct(p.mean()), "actual": pct(y.mean()),
                     "gap": gapf(y.mean() - p.mean()), "log-loss": f"{logloss(p, y):.4f}"})
    o.append(md(pd.DataFrame(rows)))
    ct = calibration_table(ev["P_H"], ev["yH"], (0, .3, .4, .5, .6, .7, .8, 1.01))
    ct["predicted"] = ct["predicted"].map(pct); ct["actual"] = ct["actual"].map(pct); ct["gap"] = ct["gap"].map(gapf)
    o.append("**Home-win probability calibration**\n")
    o.append(md(ct))
    o.append("**1X2 gap by league (top 12 by |home-win gap|)**\n")
    rows = []
    for name, g in ev.groupby("league"):
        if len(g) < MIN_N:
            continue
        rows.append({"league": name, "n": len(g), "H gap": g["yH"].mean() - g["P_H"].mean(),
                     "D gap": g["yD"].mean() - g["P_D"].mean(), "A gap": g["yA"].mean() - g["P_A"].mean()})
    x12 = pd.DataFrame(rows).assign(_a=lambda t: t["H gap"].abs()).sort_values("_a", ascending=False).drop(columns="_a")
    for c in ("H gap", "D gap", "A gap"):
        x12[c] = x12[c].map(gapf)
    o.append(md(x12.head(12)))

    # ---------------------------------------------------------------- low scores
    o.append("## 8. Low scores and extreme totals (Dixon-Coles territory)\n")
    rows = []
    for name, p, y in [("0-0 score", ev["P_00"], (ev["hg"] == 0) & (ev["ag"] == 0)),
                       ("1-1 score", ev["P_11"], (ev["hg"] == 1) & (ev["ag"] == 1)),
                       ("4+ goals", ev["P_4p"], ev["tot"] >= 4),
                       ("5+ goals", ev["P_5p"], ev["tot"] >= 5)]:
        yy = y.astype(int)
        rows.append({"cell": name, "actual": pct(yy.mean()), "model": pct(p.mean()),
                     "gap (actual−model)": gapf(yy.mean() - p.mean()), "Brier": f"{brier(p, yy):.4f}"})
    o.append(md(pd.DataFrame(rows)))
    o.append("**0-0 by λ total** (where does the model misprice the low end most?)\n")
    rows = []
    for gname, g in ev.groupby("lsum_b", observed=True):
        if len(g) < 100:
            continue
        yy = ((g["hg"] == 0) & (g["ag"] == 0)).astype(int)
        rows.append({"λ total": str(gname), "n": len(g), "actual 0-0": pct(yy.mean()), "model 0-0": pct(g["P_00"].mean()),
                     "gap": gapf(yy.mean() - g["P_00"].mean())})
    o.append(md(pd.DataFrame(rows)))

    # ---------------------------------------------------------------- market reference
    o.append("## 9. Where the bookmaker disagrees (reference only — never a model input)\n")
    o.append("On the main leagues (odds available) the opening O/U 2.5 price is shown **for comparison only**, "
             "in line with the data-first rule. This table says where the market and the model split — and "
             "who the subsequent result agreed with. It is context for any future decision, not a change.\n")
    mo = ev[ev["mkt_o25"].notna()].copy()
    rows = []
    for name, g in mo.groupby("league"):
        if len(g) < 200:
            continue
        m_side = (g["mkt_o25"] > 0.5).to_numpy()
        mo_side = (g["dc_O25"] > 0.5).to_numpy()
        res_side = (g["y25"].to_numpy() == 1)
        dis = m_side != mo_side
        rows.append({"league": name, "n": len(g),
                     "disagree on side of 50%": pct(dis.mean()),
                     "market right where they split": pct((dis & (m_side == res_side)).mean()),
                     "model right where they split": pct((dis & (mo_side == res_side)).mean()),
                     "model O2.5 gap": gapf(g["e25"].mean()), "market O2.5 gap": gapf((g["y25"] - g["mkt_o25"]).mean())})
    o.append(md(pd.DataFrame(rows).sort_values("n", ascending=False).head(12)))

    # ---------------------------------------------------------------- input correlations
    o.append("## 10. Input–error associations (Spearman rank correlation)\n")
    o.append("Association, not causation. Two columns: **signed error** (actual − predicted) and **|error|** "
             "(magnitude of the mistake). The signed column is partly structural — higher λ raises the "
             "prediction, which mechanically lowers the signed error — so the honest signal is the |error| "
             "column: on 40k+ matches |ρ| ≥ 0.03 is a real association.\n")
    from scipy.stats import spearmanr
    inputs = {"model λ home (lh)": "lh", "model λ away (la)": "la", "strength gap |lh−la|": "gap",
              "league avg goals (mu)": "mu", "weaker-team sample (neff)": "neff",
              "home O2.5 hit-rate": "h_o25", "away O2.5 hit-rate": "a_o25",
              "home BTTS hit-rate": "h_btts", "away BTTS hit-rate": "a_btts",
              "home sample (h_n)": "h_n", "away sample (a_n)": "a_n"}
    rows = []
    for label, col in inputs.items():
        c1, _ = spearmanr(ev[col], ev["e25"], nan_policy="omit")
        c2, _ = spearmanr(ev[col], (ev["y25"] - ev["dc_O25"]).abs(), nan_policy="omit")
        rows.append({"input": label, "ρ vs signed O2.5 error": f"{c1:+.4f}", "ρ vs |O2.5 error|": f"{c2:+.4f}"})
    o.append(md(pd.DataFrame(rows)))

    # ---------------------------------------------------------------- summary
    o.append("## 11. What the evidence says — inputs associated with systematic error, ranked\n")
    o.append("""1. **Clear mismatches (strength gap Δλ > 1.2) are the largest pure calibration bias and the main
   reservoir of confident O2.5 errors.** In the 3,307 matches where the model sees a big strength gap, goals
   are under-priced: O2.5 +2.4 %, O1.5 +1.5 %. They also hold 34.2 % of all confident O2.5 errors from 8.5 %
   of matches (lift 4.0; confident-error rate 17.1 % vs 1.8 % in even games), and the model's O2.5 calls
   concentrate there (52.9 % of all published O2.5). The 2026-09-28 two-K shrinkage already cut this bias
   sharply (the old single-K variant under-priced Δλ 0.8–1.2 by +10.7 %); a +2.4 % residual remains where the
   gap is largest. The high-λ bucket (λ > 2.9) is similar: 100 % of confident errors live there (lift 3.5),
   mostly structural — the 60 % bar is only cleared in high-λ matches — with a +0.8 % residual under-price.
2. **League identity — both goals and result.** On goals the model under-prices in Finland (+3.1 %),
   England League One (+2.5 %), MLS (+2.5 %), Switzerland (+2.4 %) and Norway (+1.9 %), and over-prices in
   Russia (−3.1 %). The Scandinavian leagues also carry the highest confident-O2.5 error rates per match
   (Norway 8.5 %, Finland 5.8 %, Sweden 5.0 %). On results, home wins are over-priced in the Bundesliga
   (−2.6 %), Eredivisie (−2.5 %) and MLS (−2.0 %) while draws are under-priced in Italy Serie B (+5.2 %),
   Eredivisie (+3.3 %), Argentina Copa (+3.0 %) and Ireland (+2.9 %); home wins are under-priced in Brazil
   (+2.0 %), Scotland League Two (+1.9 %) and Norway (+1.8 %). League-average tempo (mu) alone is a weaker
   signal than league identity in the production model (mu ≥ 3.0 bucket: O2.5 gap only +0.3 %) — but
   confident O2.5 errors still cluster there (59.9 % of all, lift 4.95) because the 60 % bar is only cleared
   in high-tempo matches.
3. **1X2 is well calibrated in the production model — the old favourite–longshot pathology is gone.** The
   0.60–0.70 home-win bucket now runs −1.9 % (predicted 64.2 % vs actual 62.3 %, n=3,515) and 0.80+ runs
   +0.5 % — versus +21.5 % in the old single-K variant. The remaining result-market issues are league-level
   home/draw tilts (point 2), plus draws under-priced overall by +0.9 %. The 70 % result bar is reachable
   (4.1 % of matches, 1,612 calls) and its hit rate (76.6 %) beats the predicted rate (75.6 %).
4. **All four production publish bars are honest-to-slightly-conservative** — no published market is
   over-confident: O1.5 ≥ 84 % → 86.0 % actual vs 85.8 % predicted (2,072 calls); O2.5 ≥ 60 % → 65.1 % vs
   63.5 % (4,729 calls); BTTS ≥ 60 % → 62.9 % vs 62.2 % (4,058 calls); result ≥ 70 % → 76.6 % vs 75.6 %
   (1,612 calls). The app's ⭐ tier is publishing calls it slightly over-hedges, not calls it over-sells.
5. **Small but real effects:** 0-0 is under-priced by 2.3 pp when the model expects a very low-scoring match
   (λ 1.7–2.0: actual 17.8 % vs model 15.5 %); the weaker team's sample size is bimodal (1–2 recent matches:
   O2.5 under-priced +6.5 %, n=219; 4–8: over-priced −2.6 %, n=1,261); season end (Apr–May, +2.3 %) is
   under-priced more than the middle of the season; 2026 so far runs +1.9 % under-priced — the largest yearly
   gap of the four evaluation years (2024: −0.1 %, 2025: +0.4 %) and worth monitoring rather than acting on.
6. **What is NOT associated with errors:** day of week (goals gaps all within ±1 %; Sunday confident-error
   lift 1.26 — weak), which side the model favours (O2.5 +0.6 % home-favoured vs +1.0 % away-favoured), the
   middle months, and team sample size away from the extremes. No Monday/Sunday or home/away structural flaw.

**Bottom line:** the production model's systematic failures are one-directional and modest in size — it
under-prices goals in clear mismatches and in specific high-scoring leagues (Finland, England L1, MLS,
Switzerland, Norway), over-prices home wins in the Bundesliga/Eredivisie/MLS and under-prices draws in Serie
B/Eredivisie/Copa/Ireland, and shows a mild 2026 under-pricing drift that is still within the range of the
other years. Everything it publishes at its production bars is honest to conservative. Per the agreement,
nothing has been changed; this report is the evidence base for any future adjustment.""")

    Path(args.out).write_text("\n".join(o), encoding="utf-8")
    print(f"written {args.out} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
