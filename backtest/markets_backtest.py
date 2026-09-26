#!/usr/bin/env python3
"""
Backtests for the v3 markets: corners, cards (bookings), 1X2 / double chance, team goals,
the parlay strategy (2.70-3.50 combined odds) and the value finder.

Uses the cached football-data.co.uk files downloaded by backtest.py (main leagues only:
corners / cards / referee / kick-off times are not published for the extra leagues).
"""
from __future__ import annotations

import glob
import itertools
import math
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import nbinom, poisson

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import backtest as bt  # noqa: E402
from scanner import MAIN_LEAGUES, parse_dates  # noqa: E402

EVAL_START, TRAIN_END = bt.EVAL_START, bt.TRAIN_END


# --------------------------------------------------------------------------- data
def load() -> pd.DataFrame:
    frames = []
    for fn in sorted(glob.glob(str(HERE / "cache" / "2*_*.csv"))):
        season, div = Path(fn).stem.split("_")
        df = pd.read_csv(fn, encoding="utf-8-sig", on_bad_lines="skip").dropna(subset=["HomeTeam", "AwayTeam", "FTHG", "FTAG"])
        g = lambda c: pd.to_numeric(df[c], errors="coerce") if c in df.columns else pd.Series(np.nan, index=df.index)
        frames.append(pd.DataFrame({
            "season": season, "div": div, "country": MAIN_LEAGUES[div][0], "league": MAIN_LEAGUES[div][1],
            "date": parse_dates(df["Date"]), "time": df["Time"].astype(str).str.strip() if "Time" in df else "",
            "home": df["HomeTeam"].astype(str).str.strip(), "away": df["AwayTeam"].astype(str).str.strip(),
            "referee": df["Referee"].astype(str).str.strip() if "Referee" in df else "",
            "hg": g("FTHG"), "ag": g("FTAG"), "hc": g("HC"), "ac": g("AC"),
            "hy": g("HY"), "ay": g("AY"), "hr": g("HR"), "ar": g("AR"),
            "oh": g("AvgH"), "od": g("AvgD"), "oa": g("AvgA"), "oo": g("Avg>2.5"), "ou": g("Avg<2.5"),
            "mh": g("MaxH"), "md": g("MaxD"), "ma": g("MaxA"), "mo": g("Max>2.5"), "mu": g("Max<2.5"),
            "psh": g("PSH"), "psd": g("PSD"), "psa": g("PSA"), "pso": g("P>2.5"), "psu": g("P<2.5"),
            "bfh": g("BFEH"), "bfd": g("BFED"), "bfa": g("BFEA"), "bfo": g("BFE>2.5"), "bfu": g("BFE<2.5"),
            "coh": g("AvgCH"), "cod": g("AvgCD"), "coa": g("AvgCA"), "coo": g("AvgC>2.5"), "cou": g("AvgC<2.5"),
        }))
    df = pd.concat(frames, ignore_index=True).dropna(subset=["date"])
    df = df.sort_values(["date", "div"]).reset_index(drop=True)
    df["ord"] = df["date"].map(pd.Timestamp.toordinal)
    df["hcards"] = df["hy"].fillna(0) + df["hr"].fillna(0)
    df["acards"] = df["ay"].fillna(0) + df["ar"].fillna(0)
    df.loc[df["hy"].isna(), ["hcards", "acards"]] = np.nan
    return df


# --------------------------------------------------------------------------- generic rolling count model
def roll_counts(df: pd.DataFrame, hcol: str, acol: str, HL=120, K=20, KV=20, max_n=40, max_days=400,
                div_K=30.0, use_ref=False, K_ref=10.0) -> pd.DataFrame:
    """Expected home/away counts (goals, corners, cards...) using only earlier matches.
    Optional referee factor (cards): referee's counts per game relative to league, shrunk with K_ref."""
    ords, divs, countries = df["ord"].to_numpy(), df["div"].to_numpy(), df["country"].to_numpy()
    homes, aways = df["home"].to_numpy(), df["away"].to_numpy()
    hv, av = df[hcol].to_numpy(dtype=float), df[acol].to_numpy(dtype=float)
    refs = df["referee"].to_numpy()
    team_hist, div_hist, ref_hist = defaultdict(list), defaultdict(lambda: ([], [], [])), defaultdict(list)
    glob_ = ([], [], [])
    cache, pcache = {}, {}

    def prior(d):
        if d not in pcache:
            o = np.asarray(glob_[0])
            if len(o) == 0:
                pcache[d] = (np.nan, np.nan)
            else:
                m = o >= d - max_days
                w = 0.5 ** ((d - o[m]) / HL)
                pcache[d] = (float((w * np.asarray(glob_[1])[m]).sum() / w.sum()), float((w * np.asarray(glob_[2])[m]).sum() / w.sum()))
        return pcache[d]

    def div_avg(div, d):
        key = (div, d)
        if key not in cache:
            ph, pa = prior(d)
            o = np.asarray(div_hist[div][0])
            if len(o) == 0:
                cache[key] = (ph, pa)
            else:
                m = o >= d - max_days
                w = 0.5 ** ((d - o[m]) / HL)
                n = w.sum()
                mh = (w * np.asarray(div_hist[div][1])[m]).sum() / n
                ma = (w * np.asarray(div_hist[div][2])[m]).sum() / n
                cache[key] = ((n * mh + div_K * ph) / (n + div_K), (n * ma + div_K * pa) / (n + div_K))
        return cache[key]

    def profile(recs, d, venue):
        sel = [r for r in recs[-max_n:] if r[0] >= d - max_days]
        if not sel:
            return None
        sw = swa = swd = sv = sva = svd = 0.0
        for o, v, f, a, dv in sel:
            w = 0.5 ** ((d - o) / HL)
            mh_, ma_ = div_avg(dv, d)
            fn, an = (f / mh_, a / ma_) if v == 1 else (f / ma_, a / mh_)
            sw += w; swa += w * fn; swd += w * an
            if v == venue:
                sv += w; sva += w * fn; svd += w * an
        att, dfc = swa / sw, swd / sw
        if sv > 0:
            sh = sv / (sv + KV)
            att = sh * (sva / sv) + (1 - sh) * att
            dfc = sh * (svd / sv) + (1 - sh) * dfc
        return (sw * att + K) / (sw + K), (sw * dfc + K) / (sw + K), sw

    def ref_factor(ref, d, div):
        if not use_ref or not ref or ref == "nan":
            return 1.0, 0.0
        recs = [r for r in ref_hist[ref] if r[0] >= d - 2 * max_days]
        if not recs:
            return 1.0, 0.0
        sw = sx = 0.0
        for o, tot, dv in recs:
            w = 0.5 ** ((d - o) / (2 * HL))
            mh_, ma_ = div_avg(dv, d)
            sw += w; sx += w * tot / (mh_ + ma_)
        return (sw * (sx / sw) + K_ref) / (sw + K_ref), sw

    out = np.full((len(df), 6), np.nan)
    n, i = len(df), 0
    while i < n:
        d = ords[i]; j = i
        while j < n and ords[j] == d:
            j += 1
        for k in range(i, j):
            if np.isnan(hv[k]) or np.isnan(av[k]):
                continue
            H = profile(team_hist[(countries[k], homes[k])], d, 1)
            A = profile(team_hist[(countries[k], aways[k])], d, 0)
            if H is None or A is None:
                continue
            mh_, ma_ = div_avg(divs[k], d)
            if np.isnan(mh_):
                continue
            rf, rn = ref_factor(refs[k], d, divs[k])
            out[k] = (mh_ * H[0] * A[1] * rf, ma_ * A[0] * H[1] * rf, H[2], A[2], rf, rn)
        for k in range(i, j):
            if np.isnan(hv[k]) or np.isnan(av[k]):
                continue
            team_hist[(countries[k], homes[k])].append((d, 1, hv[k], av[k], divs[k]))
            team_hist[(countries[k], aways[k])].append((d, 0, av[k], hv[k], divs[k]))
            dh = div_hist[divs[k]]; dh[0].append(d); dh[1].append(hv[k]); dh[2].append(av[k])
            glob_[0].append(d); glob_[1].append(hv[k]); glob_[2].append(av[k])
            if use_ref and refs[k] and refs[k] != "nan":
                ref_hist[refs[k]].append((d, hv[k] + av[k], divs[k]))
        i = j
    return pd.DataFrame(out, columns=["eh", "ea", "h_neff", "a_neff", "ref_factor", "ref_n"], index=df.index)


def nb_sf(k: np.ndarray, mu: np.ndarray, r: float) -> np.ndarray:
    """P(X >= k) for a negative binomial with mean mu and size r (r=inf -> Poisson)."""
    if math.isinf(r):
        return poisson.sf(k - 1, mu)
    p = r / (r + mu)
    return nbinom.sf(k - 1, r, p)


def fit_r(y: np.ndarray, mu: np.ndarray) -> float:
    best, best_ll = math.inf, -math.inf
    for r in (5, 10, 20, 30, 50, 80, 120, 200, math.inf):
        ll = poisson.logpmf(y, mu).sum() if math.isinf(r) else nbinom.logpmf(y, r, r / (r + mu)).sum()
        if ll > best_ll:
            best, best_ll = r, ll
    return best


def calib(p, y, edges) -> pd.DataFrame:
    t = bt.calibration_table(p, y, edges)
    for c in ("predicted", "actual"):
        t[c] = t[c].map("{:.1%}".format)
    t["gap"] = t["gap"].map("{:+.1%}".format)
    return t


# --------------------------------------------------------------------------- sections
def corners_section(df, out):
    out.append("## Corners\n")
    ok = df["hc"].notna()
    best = None
    for K in (10, 20, 40, 80):
        r = roll_counts(df, "hc", "ac", K=K)
        ev = df[ok & r["eh"].notna() & (df["date"] >= EVAL_START)]
        rr = r.loc[ev.index]
        tot = (ev["hc"] + ev["ac"]).to_numpy(); mu = (rr["eh"] + rr["ea"]).to_numpy()
        tr = (ev["date"] <= TRAIN_END).to_numpy()
        rsize = fit_r(tot[tr], mu[tr])
        p10 = nb_sf(np.full(len(ev), 10), mu, rsize)
        ll_tr, ll_te = bt.logloss(p10[tr], tot[tr] >= 10), bt.logloss(p10[~tr], tot[~tr] >= 10)
        base = np.full(len(ev), (tot[tr] >= 10).mean())
        row = dict(K=K, r=rsize, train_ll=ll_tr, test_ll=ll_te, base_test=bt.logloss(base[~tr], tot[~tr] >= 10),
                   mae_test=float(np.abs(mu[~tr] - tot[~tr]).mean()), base_mae=float(np.abs(tot[~tr] - tot[tr].mean()).mean()))
        print("corners", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()}, flush=True)
        if best is None or row["train_ll"] < best[0]["train_ll"]:
            best = (row, r, rsize)
    row, r, rsize = best
    out.append(f"Model: team corner rates for/against (league-normalised, decayed, shrinkage K={row['K']}), negative binomial "
               f"size r={rsize}. Test log-loss for 'Over 9.5 corners': **{row['test_ll']:.4f}** vs league-average baseline "
               f"{row['base_test']:.4f}; mean absolute error on total corners {row['mae_test']:.2f} vs {row['base_mae']:.2f} baseline.\n")
    ev = df[ok & r["eh"].notna() & (df["date"] > TRAIN_END)]
    rr = r.loc[ev.index]
    tot = (ev["hc"] + ev["ac"]).to_numpy(); mu = (rr["eh"] + rr["ea"]).to_numpy()
    for line in (8.5, 9.5, 10.5, 11.5):
        p = nb_sf(np.full(len(ev), math.ceil(line)), mu, rsize)
        out.append(f"**Over {line} total corners** — test seasons\n")
        out.append(calib(p, tot > line, (0, .3, .4, .5, .6, .7, .8, 1.01)).to_markdown(index=False) + "\n")
    # team corners
    rh = fit_r(ev["hc"].to_numpy()[: len(ev)], rr["eh"].to_numpy()) if len(ev) else 30
    for line in (3.5, 4.5, 5.5):
        p = nb_sf(np.full(len(ev), math.ceil(line)), rr["eh"].to_numpy(), rh)
        out.append(f"**Home team over {line} corners** — test seasons (NB size {rh})\n")
        out.append(calib(p, ev["hc"].to_numpy() > line, (0, .3, .4, .5, .6, .7, .8, 1.01)).to_markdown(index=False) + "\n")
    return row["K"], rsize, rh


def cards_section(df, out):
    out.append("## Cards (bookings)\n")
    ok = df["hcards"].notna()
    results = {}
    for use_ref in (False, True):
        for K in (10, 20, 40):
            r = roll_counts(df, "hcards", "acards", K=K, use_ref=use_ref)
            ev = df[ok & r["eh"].notna() & (df["date"] >= EVAL_START)]
            rr = r.loc[ev.index]
            tot = (ev["hcards"] + ev["acards"]).to_numpy(); mu = (rr["eh"] + rr["ea"]).to_numpy()
            tr = (ev["date"] <= TRAIN_END).to_numpy()
            rsize = fit_r(tot[tr], mu[tr])
            p = nb_sf(np.full(len(ev), 5), mu, rsize)
            base = np.full(len(ev), (tot[tr] >= 5).mean())
            uk = ev["referee"].ne("").to_numpy() & ev["referee"].ne("nan").to_numpy()
            row = dict(referee=use_ref, K=K, r=rsize, train_ll=bt.logloss(p[tr], tot[tr] >= 5), test_ll=bt.logloss(p[~tr], tot[~tr] >= 5),
                       base_test=bt.logloss(base[~tr], tot[~tr] >= 5),
                       test_ll_uk=bt.logloss(p[~tr & uk], tot[~tr & uk] >= 5), base_uk=bt.logloss(base[~tr & uk], tot[~tr & uk] >= 5))
            print("cards", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()}, flush=True)
            results[(use_ref, K)] = (row, r, rsize)
    bestkey = min(results, key=lambda k: results[k][0]["train_ll"])
    row, r, rsize = results[bestkey]
    noref = min((k for k in results if not k[0]), key=lambda k: results[k][0]["train_ll"])
    out.append(f"Model: team card rates (received / provoked, league-normalised, decayed, shrinkage K={row['K']}), "
               f"{'with' if row['referee'] else 'without'} a referee factor, negative binomial size r={rsize}. "
               f"Test log-loss for 'Over 4.5 cards': **{row['test_ll']:.4f}** vs baseline {row['base_test']:.4f}. "
               f"In the UK leagues (where referees are known): with referee {row['test_ll_uk']:.4f} vs without "
               f"{results[noref][0]['test_ll_uk']:.4f} vs baseline {row['base_uk']:.4f}.\n")
    ev = df[ok & r["eh"].notna() & (df["date"] > TRAIN_END)]
    rr = r.loc[ev.index]
    tot = (ev["hcards"] + ev["acards"]).to_numpy(); mu = (rr["eh"] + rr["ea"]).to_numpy()
    for line in (3.5, 4.5, 5.5):
        p = nb_sf(np.full(len(ev), math.ceil(line)), mu, rsize)
        out.append(f"**Over {line} total cards** — test seasons\n")
        out.append(calib(p, tot > line, (0, .3, .4, .5, .6, .7, .8, 1.01)).to_markdown(index=False) + "\n")
    return row["referee"], row["K"], rsize


def final_lambdas(res: pd.DataFrame, w=0.9) -> tuple[np.ndarray, np.ndarray]:
    lh, la = res["lh"].to_numpy().copy(), res["la"].to_numpy().copy()
    has = ~np.isnan(res["mlh"].to_numpy())
    lh[has] = (1 - w) * lh[has] + w * res["mlh"].to_numpy()[has]
    la[has] = (1 - w) * la[has] + w * res["mla"].to_numpy()[has]
    return lh, la


def one_x_two_section(res, out):
    """1X2 / double chance / team goals from the goals engine output (main leagues, with odds)."""
    out.append("## 1X2, double chance and team goals\n")
    ev = res[(res["date"] >= EVAL_START) & res["lh"].notna() & res["oh"].notna() & (res["source"] == "main")].copy()
    lh, la = final_lambdas(ev)
    P = bt.probs_from_matrix(bt.score_matrix(lh, la, -0.05))
    inv = 1 / ev[["oh", "od", "oa"]].to_numpy(); mk = inv / inv.sum(axis=1, keepdims=True)
    yH, yA = (ev["hg"] > ev["ag"]).to_numpy(), (ev["hg"] < ev["ag"]).to_numpy(); yD = ~yH & ~yA
    tr = (ev["date"] <= TRAIN_END).to_numpy()
    rows = []
    for w in (0.0, 0.5, 0.8, 0.9, 1.0):
        pH = (1 - w) * P["HW"] + w * mk[:, 0]; pA = (1 - w) * P["AW"] + w * mk[:, 2]; pD = 1 - pH - pA
        ll = lambda m: float(-np.mean(np.log(np.clip(np.where(yH[m], pH[m], np.where(yA[m], pA[m], pD[m])), 1e-6, 1))))
        rows.append({"market weight": w, "train 1X2 log-loss": round(ll(tr), 4), "test 1X2 log-loss": round(ll(~tr), 4)})
    out.append("Multi-class log-loss of the 1X2 probabilities (score matrix vs bookmaker-implied, blended):\n")
    out.append(pd.DataFrame(rows).to_markdown(index=False) + "\n")
    w = 0.9
    pH = (1 - w) * P["HW"] + w * mk[:, 0]; pA = (1 - w) * P["AW"] + w * mk[:, 2]; pD = 1 - pH - pA
    te = ~tr
    out.append("**Calibration (test seasons, 90% market):** home win / draw / away win / double chance 1X\n")
    for name, p, y in (("Home win", pH, yH), ("Draw", pD, yD), ("Away win", pA, yA), ("Double chance 1X", pH + pD, yH | yD)):
        t = calib(p[te], y[te], (0, .2, .3, .4, .5, .6, .7, .8, .9, 1.01)); t.insert(0, "market", name)
        out.append(t.to_markdown(index=False) + "\n")
    # team goals from the score matrix
    g = np.arange(bt.MAXG + 1)
    M = bt.score_matrix(lh, la, -0.05)
    ph_o05 = 1 - M[:, 0, :].sum(axis=1); pa_o05 = 1 - M[:, :, 0].sum(axis=1)
    ph_o15 = 1 - M[:, :2, :].sum(axis=(1, 2)); pa_o15 = 1 - M[:, :, :2].sum(axis=(1, 2))
    out.append("**Team goals (test seasons):**\n")
    for name, p, y in (("Home over 0.5", ph_o05, ev["hg"] > 0), ("Home over 1.5", ph_o15, ev["hg"] > 1),
                       ("Away over 0.5", pa_o05, ev["ag"] > 0), ("Away over 1.5", pa_o15, ev["ag"] > 1)):
        t = calib(p[te], y.to_numpy()[te], (0, .3, .4, .5, .6, .7, .8, .9, 1.01)); t.insert(0, "market", name)
        out.append(t.to_markdown(index=False) + "\n")
    ev["pH"], ev["pD"], ev["pA"] = pH, pD, pA
    ev["pO25"] = bt.probs_from_matrix(bt.score_matrix(lh, la, -0.05))["O25"]
    return ev


def build_parlays(legs: list[dict], lo=2.70, hi=3.50, n_parlays=3, max_legs=4) -> list[list[dict]]:
    """legs: dicts with keys match, p, odds. Greedy: best-probability combo in the odds band, distinct matches."""
    legs = sorted(legs, key=lambda l: -l["p"])[:40]
    chosen = []
    used_matches: set = set()
    for _ in range(n_parlays):
        pool = [l for l in legs if l["match"] not in used_matches]
        best, best_p = None, 0.0
        for k in range(2, max_legs + 1):
            for combo in itertools.combinations(pool, k):
                if len({c["match"] for c in combo}) < k:
                    continue
                odds = float(np.prod([c["odds"] for c in combo]))
                if odds < lo or odds > hi:
                    continue
                p = float(np.prod([c["p"] for c in combo]))
                if p > best_p:
                    best, best_p = combo, p
            if best is not None and k >= 3:
                break
        if best is None:
            break
        chosen.append(list(best))
        used_matches |= {c["match"] for c in best}
    return chosen


def parlay_section(ev, out):
    out.append("## Parlay strategy (3 per run, 2.70–3.50 combined odds, legs = 1X2 / double chance / O-U 2.5)\n")
    te = ev[ev["date"] > TRAIN_END].copy()
    hh = te["time"].str.slice(0, 2).apply(lambda s: int(s) if s.isdigit() else 15)
    # run windows in UK time approximating 07:00 / 12:00 / 17:00 SAST: [06,11), [11,16), [16,06)
    te["window"] = np.select([hh < 6, hh < 11, hh < 16], ["evening-prev", "morning", "afternoon"], "evening")
    te.loc[te["window"] == "evening-prev", "date"] = te.loc[te["window"] == "evening-prev", "date"] - pd.Timedelta(days=1)
    te.loc[te["window"] == "evening-prev", "window"] = "evening"
    results = []
    for (d, win), g in te.groupby(["date", "window"]):
        legs = []
        for r in g.itertuples():
            m = f"{r.home} v {r.away}"
            yH, yA = r.hg > r.ag, r.hg < r.ag; yD = not yH and not yA
            dc = lambda o1, o2: 1 / (1 / o1 + 1 / o2)
            cands = [("Home", r.pH, r.oh, yH), ("Draw", r.pD, r.od, yD), ("Away", r.pA, r.oa, yA),
                     ("1X", r.pH + r.pD, dc(r.oh, r.od), yH or yD), ("X2", r.pD + r.pA, dc(r.od, r.oa), yD or yA),
                     ("12", r.pH + r.pA, dc(r.oh, r.oa), yH or yA)]
            if not np.isnan(r.oo) and r.oo > 1 and r.ou > 1:
                cands += [("Over 2.5", r.pO25, r.oo, r.hg + r.ag >= 3), ("Under 2.5", 1 - r.pO25, r.ou, r.hg + r.ag < 3)]
            for name, p, o, hit in cands:
                if o and o > 1.01 and o < 6:
                    legs.append({"match": m, "sel": name, "p": p, "odds": o, "hit": bool(hit)})
        for pl in build_parlays(legs):
            odds = float(np.prod([l["odds"] for l in pl])); p = float(np.prod([l["p"] for l in pl]))
            results.append({"date": d, "window": win, "legs": len(pl), "odds": odds, "p": p, "hit": all(l["hit"] for l in pl)})
    R = pd.DataFrame(results)
    if R.empty:
        out.append("_No parlays could be built._\n"); return
    summ = {"parlays": len(R), "days": R["date"].nunique(), "avg legs": round(R["legs"].mean(), 2), "avg odds": round(R["odds"].mean(), 2),
            "avg model probability": f"{R['p'].mean():.1%}", "actual hit rate": f"{R['hit'].mean():.1%}",
            "ROI (1 unit per parlay)": f"{(R['odds'] * R['hit']).sum() / len(R) - 1:+.1%}"}
    out.append(f"Simulated on the test seasons (2025/26–26/27) with **real opening odds**: {summ}\n")
    by = R.groupby("window").agg(parlays=("hit", "size"), hit_rate=("hit", "mean"), avg_odds=("odds", "mean"), avg_p=("p", "mean"),
                                 roi=("hit", lambda h: (R.loc[h.index, "odds"] * h).sum() / len(h) - 1))
    by["hit_rate"] = by["hit_rate"].map("{:.1%}".format); by["avg_p"] = by["avg_p"].map("{:.1%}".format); by["roi"] = by["roi"].map("{:+.1%}".format)
    out.append(by.round(2).to_markdown() + "\n")
    R["month"] = R["date"].dt.to_period("M").astype(str)
    bym = R.groupby("month").agg(parlays=("hit", "size"), hits=("hit", "sum"), roi=("hit", lambda h: (R.loc[h.index, "odds"] * h).sum() / len(h) - 1))
    bym["roi"] = bym["roi"].map("{:+.1%}".format)
    out.append("By month:\n"); out.append(bym.to_markdown() + "\n")
    out.append("_Interpretation: a parlay at ~3.0 needs to win 1 in 3 to break even. The model probability tells you what to expect; "
               "the ROI shows what the bookmaker margin does to it._\n")


def value_section(df, out):
    out.append("## Value finder check (best available price vs sharp reference)\n")
    ev = df[(df["date"] >= EVAL_START) & df["oo"].notna() & df["mo"].notna()].copy()
    rows = []
    # reference fair probability: Pinnacle where available else Betfair Exchange
    ref_o = ev["pso"].where(ev["pso"].notna(), ev["bfo"]); ref_u = ev["psu"].where(ev["psu"].notna(), ev["bfu"])
    ok = ref_o.notna() & ref_u.notna() & (ref_o > 1) & (ref_u > 1)
    ev = ev[ok]; ref_o, ref_u = ref_o[ok], ref_u[ok]
    fair_o = (1 / ref_o) / (1 / ref_o + 1 / ref_u); fair_u = 1 - fair_o
    y_o = (ev["hg"] + ev["ag"] >= 3).to_numpy()
    for side, fair, best, avg, y in (("Over 2.5", fair_o, ev["mo"], ev["oo"], y_o), ("Under 2.5", fair_u, ev["mu"], ev["ou"], ~y_o)):
        for thr in (0.0, 0.02, 0.04, 0.06):
            for label, price in (("best price (Max)", best), ("average price (Avg)", avg)):
                m = (fair * price - 1 > thr).to_numpy()
                if m.sum() < 30:
                    continue
                rows.append({"selection": side, "edge >": f"{thr:.0%}", "price": label, "bets": int(m.sum()),
                             "hit rate": f"{y[m].mean():.1%}", "avg odds": round(float(price[m].mean()), 2),
                             "ROI": f"{(price[m] * y[m]).sum() / m.sum() - 1:+.1%}"})
    out.append("Reference = Pinnacle (to 2024/25) or Betfair Exchange (after), margin removed. "
               "'Edge' = fair probability × price − 1. Main leagues, Aug 2023 – Sep 2026, opening prices.\n")
    out.append(pd.DataFrame(rows).to_markdown(index=False) + "\n")
    out.append("_The 'best price' rows need accounts at whichever bookmaker is top that day; the 'average price' rows are "
               "what a typical single bookmaker offers._\n")


def main():
    t0 = time.time()
    df = load()
    print(f"loaded {len(df):,} main-league matches", flush=True)
    out = ["# Markets backtest (v3)\n", f"_Generated {pd.Timestamp.now():%Y-%m-%d %H:%M}. Main leagues, {len(df):,} matches 2022-26; "
           f"evaluation from {EVAL_START:%b %Y}; train = to {TRAIN_END:%b %Y}, test = after._\n"]
    params = {}
    params["corners"] = corners_section(df, out); print("corners done", round(time.time() - t0), flush=True)
    params["cards"] = cards_section(df, out); print("cards done", round(time.time() - t0), flush=True)
    base = pd.read_pickle(HERE / "base_k40.pkl") if (HERE / "base_k40.pkl").exists() else bt.run_model(bt.load_all(), HL=120, K=40, KV=20)
    res = bt.add_model_columns(base, rho=-0.05, w_lambda=0.9)
    # attach kick-off times for the parlay windows
    tm = df[["date", "div", "home", "away", "time"]]
    res = res.merge(tm, on=["date", "div", "home", "away"], how="left"); res["time"] = res["time"].fillna("")
    ev = one_x_two_section(res, out); print("1x2 done", round(time.time() - t0), flush=True)
    parlay_section(ev, out); print("parlays done", round(time.time() - t0), flush=True)
    value_section(df, out); print("value done", round(time.time() - t0), flush=True)
    (HERE / "MARKETS_RESULTS.md").write_text("\n".join(out), encoding="utf-8")
    print("params:", params)
    print(f"written MARKETS_RESULTS.md in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
