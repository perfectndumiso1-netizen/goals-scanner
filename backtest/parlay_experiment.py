"""Parlay-construction experiment: de-margin method x selection objective, train vs test seasons.

Run: python3 backtest/parlay_experiment.py   (~3-5 min)
"""
from __future__ import annotations

import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import backtest as bt  # noqa: E402
import markets_backtest as mb  # noqa: E402

TRAIN_END, EVAL_START = bt.TRAIN_END, bt.EVAL_START


def demargin_power(odds: np.ndarray) -> np.ndarray:
    """odds: (n, m) decimal prices. Returns fair probabilities via the power method (sum p_i^k = 1)."""
    inv = 1 / odds
    k = np.ones(len(odds))
    for _ in range(30):  # Newton on f(k) = sum inv^k - 1
        f = (inv ** k[:, None]).sum(axis=1) - 1
        fp = ((inv ** k[:, None]) * np.log(inv)).sum(axis=1)
        step = f / np.where(np.abs(fp) < 1e-12, -1e-12, fp)
        k = np.clip(k - step, 0.5, 3.0)
    p = inv ** k[:, None]
    return p / p.sum(axis=1, keepdims=True)


def demargin_prop(odds: np.ndarray) -> np.ndarray:
    inv = 1 / odds
    return inv / inv.sum(axis=1, keepdims=True)


def build(legs, lo, hi, n_parlays, max_legs, objective, min_p=0.0, prefer_short=True):
    legs = [l for l in legs if l["p"] >= min_p]
    key = (lambda l: -l["p"]) if objective == "prob" else (lambda l: -(l["pc"] * l["odds"]))
    legs = sorted(legs, key=key)[:28]
    chosen, used = [], set()
    for _ in range(n_parlays):
        pool = [l for l in legs if l["match"] not in used]
        best, best_v = None, -1.0
        for k in range(2, max_legs + 1):
            for combo in itertools.combinations(pool, k):
                if len({c["match"] for c in combo}) < k:
                    continue
                odds = float(np.prod([c["odds"] for c in combo]))
                if odds < lo or odds > hi:
                    continue
                if objective == "prob":
                    v = float(np.prod([c["p"] for c in combo]))
                else:  # expected return with calibrated probabilities
                    v = float(np.prod([c["pc"] * c["odds"] for c in combo]))
                if v > best_v:
                    best, best_v = combo, v
            if prefer_short and best is not None and k >= 3:
                break
        if best is None:
            break
        chosen.append(list(best))
        used |= {c["match"] for c in best}
    return chosen


def simulate(ev, lo=2.70, hi=3.50, objective="prob", min_p=0.0, max_legs=4, prefer_short=True, label=""):
    te = ev.copy()
    hh = te["time"].str.slice(0, 2).apply(lambda s: int(s) if s.isdigit() else 15)
    te["window"] = np.select([hh < 6, hh < 11, hh < 16], ["evening-prev", "morning", "afternoon"], "evening")
    te.loc[te["window"] == "evening-prev", "date"] = te.loc[te["window"] == "evening-prev", "date"] - pd.Timedelta(days=1)
    te.loc[te["window"] == "evening-prev", "window"] = "evening"
    results = []
    dc = lambda o1, o2: 1 / (1 / o1 + 1 / o2)
    for (d, win), g in te.groupby(["date", "window"]):
        legs = []
        for r in g.itertuples():
            m = f"{r.home} v {r.away}"
            yH, yA = r.hg > r.ag, r.hg < r.ag
            yD = not yH and not yA
            cands = [("Home", r.pH, r.cH, r.oh, yH), ("Draw", r.pD, r.cD, r.od, yD), ("Away", r.pA, r.cA, r.oa, yA),
                     ("1X", r.pH + r.pD, r.cH + r.cD, dc(r.oh, r.od), yH or yD),
                     ("X2", r.pD + r.pA, r.cD + r.cA, dc(r.od, r.oa), yD or yA),
                     ("12", r.pH + r.pA, r.cH + r.cA, dc(r.oh, r.oa), yH or yA)]
            if not np.isnan(r.oo) and r.oo > 1 and r.ou > 1:
                cands += [("Over 2.5", r.pO25, r.cO, r.oo, r.hg + r.ag >= 3), ("Under 2.5", 1 - r.pO25, r.cU, r.ou, r.hg + r.ag < 3)]
            for name, p, pc, o, hit in cands:
                if o and 1.01 < o < 6:
                    legs.append({"match": m, "sel": name, "p": p, "pc": pc, "odds": o, "hit": bool(hit)})
        for pl in build(legs, lo, hi, 3, max_legs, objective, min_p, prefer_short):
            odds = float(np.prod([l["odds"] for l in pl]))
            results.append({"date": d, "window": win, "legs": len(pl), "odds": odds,
                            "p": float(np.prod([l["p"] for l in pl])), "pc": float(np.prod([l["pc"] for l in pl])),
                            "hit": all(l["hit"] for l in pl), "train": d <= TRAIN_END,
                            "sels": ",".join(l["sel"] for l in pl)})
    R = pd.DataFrame(results)
    rows = []
    for name, part in (("train", R[R["train"]]), ("test", R[~R["train"]])):
        if part.empty:
            continue
        rows.append({"strategy": label, "split": name, "parlays": len(part), "avg_legs": round(part["legs"].mean(), 2),
                     "avg_odds": round(part["odds"].mean(), 2), "p_prop": f"{part['p'].mean():.1%}", "p_cal": f"{part['pc'].mean():.1%}",
                     "hit": f"{part['hit'].mean():.1%}", "roi": f"{(part['odds'] * part['hit']).sum() / len(part) - 1:+.1%}"})
    mix = R[~R["train"]]["sels"].str.split(",").explode().value_counts(normalize=True).head(6).round(2).to_dict()
    return rows, mix, R


def main():
    t0 = time.time()
    df = mb.load()
    base = pd.read_pickle(HERE / "base_k40.pkl")
    res = bt.add_model_columns(base, rho=-0.05, w_lambda=0.9)
    tm = df[["date", "div", "home", "away", "time"]]
    res = res.merge(tm, on=["date", "div", "home", "away"], how="left")
    res["time"] = res["time"].fillna("")
    ev = res[(res["date"] >= EVAL_START) & res["lh"].notna() & res["oh"].notna() & (res["source"] == "main")].copy()
    lh, la = mb.final_lambdas(ev)
    M = bt.score_matrix(lh, la, -0.05)
    P = bt.probs_from_matrix(M)
    O = ev[["oh", "od", "oa"]].to_numpy()
    prop, powr = demargin_prop(O), demargin_power(O)
    yH, yA = (ev["hg"] > ev["ag"]).to_numpy(), (ev["hg"] < ev["ag"]).to_numpy()
    yD = ~yH & ~yA
    tr = (ev["date"] <= TRAIN_END).to_numpy()
    out = ["# Parlay construction experiment\n"]
    # --- 1. de-margin method comparison (pure market, w=1) and blends
    rows = []
    for mname, mk in (("proportional", prop), ("power", powr)):
        for w in (0.9, 1.0):
            pH = (1 - w) * P["HW"] + w * mk[:, 0]
            pA = (1 - w) * P["AW"] + w * mk[:, 2]
            pD = 1 - pH - pA
            ll = lambda m: float(-np.mean(np.log(np.clip(np.where(yH[m], pH[m], np.where(yA[m], pA[m], pD[m])), 1e-6, 1))))
            # calibration gap for favourites (p>=0.6) and longshots (p<0.25) on all outcomes, test split
            allp = np.concatenate([pH[~tr], pD[~tr], pA[~tr]])
            ally = np.concatenate([yH[~tr], yD[~tr], yA[~tr]])
            fav = allp >= 0.6
            dog = allp < 0.25
            rows.append({"de-margin": mname, "market w": w, "train LL": round(ll(tr), 4), "test LL": round(ll(~tr), 4),
                         "fav (p>=60%) pred/actual": f"{allp[fav].mean():.1%} / {ally[fav].mean():.1%} (n={fav.sum()})",
                         "longshot (p<25%) pred/actual": f"{allp[dog].mean():.1%} / {ally[dog].mean():.1%} (n={dog.sum()})"})
    out.append("## 1X2 de-margin method\n")
    out.append(pd.DataFrame(rows).to_markdown(index=False) + "\n")
    # O/U 2.5 calibrated probability: power de-margin of the two-way market blended 90% with model
    has = ev["oo"].notna() & ev["ou"].notna() & (ev["oo"] > 1) & (ev["ou"] > 1)
    OU = ev.loc[has, ["oo", "ou"]].to_numpy()
    pou = np.full((len(ev), 2), np.nan)
    pou[has.to_numpy()] = demargin_power(OU)
    ev["pO25"] = P["O25"]
    ev["cO"] = np.where(has, 0.1 * P["O25"] + 0.9 * np.nan_to_num(pou[:, 0]), P["O25"])
    ev["cU"] = 1 - ev["cO"]
    w = 0.9
    ev["pH"] = (1 - w) * P["HW"] + w * prop[:, 0]
    ev["pA"] = (1 - w) * P["AW"] + w * prop[:, 2]
    ev["pD"] = 1 - ev["pH"] - ev["pA"]
    ev["cH"] = (1 - w) * P["HW"] + w * powr[:, 0]
    ev["cA"] = (1 - w) * P["AW"] + w * powr[:, 2]
    ev["cD"] = 1 - ev["cH"] - ev["cA"]
    print("probabilities ready", round(time.time() - t0), flush=True)
    # --- 2. strategies
    configs = [
        dict(objective="prob", label="A: max probability (current), prop. de-margin"),
        dict(objective="ev", label="B: max expected return, power de-margin"),
        dict(objective="ev", min_p=0.55, label="C: max expected return, legs p>=55%"),
        dict(objective="ev", prefer_short=False, label="D: max expected return, any 2-4 legs"),
        dict(objective="prob", max_legs=2, label="E: max probability, 2 legs only"),
        dict(objective="ev", max_legs=2, label="F: max expected return, 2 legs only"),
    ]
    allrows, mixes = [], {}
    for c in configs:
        rows, mix, R = simulate(ev, **c)
        allrows += rows
        mixes[c["label"]] = mix
        print(c["label"], rows, round(time.time() - t0), flush=True)
    out.append("## Strategies (3 parlays per run window, odds 2.70-3.50, real opening Avg odds)\n")
    out.append(pd.DataFrame(allrows).to_markdown(index=False) + "\n")
    out.append("Leg mix on test seasons:\n")
    for k, v in mixes.items():
        out.append(f"- {k}: {v}")
    (HERE / "PARLAY_EXPERIMENT.md").write_text("\n".join(out), encoding="utf-8")
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
