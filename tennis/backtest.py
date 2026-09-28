"""Walk-forward backtest of the tennis engine on the historical base.

No look-ahead by construction: matches are replayed in chronological order and every prediction is
made before the match result updates the ratings/statistics (tennis/history.py::replay). Parameters are
chosen on the training period and reported on the later evaluation period.

Run:  TENNIS_STATE_DIR=... python3 -m tennis.backtest [--quick]
Writes tennis/BACKTEST_RESULTS.md and data/tennis/history/backtest_predictions.csv.gz
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import random
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from . import data as D
from . import history as H
from . import model as M
from . import stats as S

log = logging.getLogger("tennis.backtest")
TRAIN = ("2012-01-01", "2018-12-31")
TEST = ("2019-01-01", "2026-12-31")
BUCKETS = [(0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 0.75), (0.75, 0.80), (0.80, 0.85), (0.85, 0.90), (0.90, 0.95), (0.95, 1.001)]


def metrics(p: np.ndarray, y: np.ndarray) -> dict:
    """p = probability given to the eventual winner's side? No — p is P(player A wins), y = 1 if A won."""
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return {"n": int(len(p)), "accuracy": float(np.mean((p > 0.5) == (y == 1))), "brier": float(np.mean((p - y) ** 2)),
            "log_loss": float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))}


def calibration(p_fav: np.ndarray, fav_won: np.ndarray) -> list[dict]:
    rows = []
    for lo, hi in BUCKETS:
        m = (p_fav >= lo) & (p_fav < hi)
        n = int(m.sum())
        rows.append({"bucket": f"{int(lo*100)}-{min(int(hi*100), 100)}%", "n": n,
                     "predicted": float(p_fav[m].mean()) if n else None, "actual": float(fav_won[m].mean()) if n else None})
    return rows


def run_ratings(base: pd.DataFrame, k: float, shape: float, w: float, format_adjust: bool = True, since: str = TRAIN[0], scale: float = 400.0) -> pd.DataFrame:
    """One ratings-only replay; returns per-match predictions from `since` (orientation: favourite = side with p ≥ 0.5)."""
    R = M.Ratings(k=k, offset=C.ELO_OFFSET, shape=shape, surface_weight=w, format_adjust=format_adjust, scale=scale)
    rows = []
    rnd = random.Random(7)

    def cb(rec, pred):
        if rec["date"] < since:
            return
        p_w = pred["p_match"]                      # probability of the actual winner before the match
        # random orientation for A/B so that calibration is not conditioned on the outcome
        a_is_winner = rnd.random() < 0.5
        p_a = p_w if a_is_winner else 1 - p_w
        rows.append((rec["date"], rec["tour"], rec["level"], rec["best_of"], rec["surface"], p_a, 1 if a_is_winner else 0,
                     pred["n_a"], pred["n_b"], rec["w"], rec["l"], rec["retired"], rec["w_games"], rec["l_games"], rec["w_rank"], rec["l_rank"]))

    H.replay(H.base_records(base), R, None, cb)
    return pd.DataFrame(rows, columns=["date", "tour", "level", "best_of", "surface", "p_a", "y", "n_w", "n_l", "w", "l", "retired", "w_games", "l_games", "w_rank", "l_rank"])


def rated(df: pd.DataFrame, min_n: int = C.MIN_MATCHES_RATED) -> pd.DataFrame:
    return df[(df["n_w"] >= min_n) & (df["n_l"] >= min_n)]


def fmt(x, pct=False, d=4):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "N/A"
    return f"{x*100:.1f}%" if pct else f"{x:.{d}f}"


def md_table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(" --- " for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def ranking_baseline(df: pd.DataFrame) -> dict | None:
    """Reference: 'better-ranked player wins' (no probability, accuracy only) on matches where both ranks exist."""
    d = df.dropna(subset=["w_rank", "l_rank"])
    if not len(d):
        return None
    return {"n": int(len(d)), "accuracy": float((d["w_rank"] < d["l_rank"]).mean())}


def games_backtest(base: pd.DataFrame, k: float, shape: float, w: float, sample_n: int, seed: int = 3, scale: float = 400.0,
                   period: tuple = TEST, sigma: dict | None = None) -> dict:
    """Total/player games: replay with statistics; on a random sample of evaluation matches compute the
    Markov distribution pinned to the Elo probability and compare with actual games."""
    R = M.Ratings(k=k, offset=C.ELO_OFFSET, shape=shape, surface_weight=w, scale=scale)
    PS = S.PlayerStats(S.load_baselines() or S.serve_baselines(base))
    rnd = random.Random(seed)
    rows = []
    sigma = sigma or {}
    # pre-select evaluation matches (indices) to keep the run short
    elig = base.index[(base["date"] >= period[0]) & (base["date"] <= period[1]) & (~base["retired"].astype(bool)) & base["w_games"].notna() & base["level"].isin(["G", "M", "A", "PM", "P", "I", "C"])].tolist()
    chosen = set(rnd.sample(elig, min(sample_n, len(elig))))
    counter = {"i": -1}

    def cb(rec, pred):
        counter["i"] += 1
        if counter["i"] not in chosen:
            return
        if pred["n_a"] < C.MIN_MATCHES_RATED or pred["n_b"] < C.MIN_MATCHES_RATED:
            return
        fa = PS.features(rec["w"], rec["date"], rec["surface"], rec["tour"])
        fb = PS.features(rec["l"], rec["date"], rec["surface"], rec["tour"])
        base_sv = PS.baseline(rec["tour"], rec["surface"])
        ta, tb = fa.get("traits") or {}, fb.get("traits") or {}
        dom = 2 * base_sv + (ta.get("serve") or 0.0) + (tb.get("serve") or 0.0) - (ta.get("return") or 0.0) - (tb.get("return") or 0.0)
        has_traits = bool(ta) and bool(tb)
        slam = rec["level"] == "G"
        dist = M.match_distribution_mixture(pred["p_match"], dom, rec["best_of"], slam, sigma.get(rec["tour"], 0.0))
        total = rec["w_games"] + rec["l_games"]
        med = _median(dist["total_games"])
        fav_is_w = pred["p_match"] >= 0.5
        fav_pmf = dist["games_a"] if fav_is_w else dist["games_b"]
        fav_med = _median(fav_pmf)
        fav_games = rec["w_games"] if fav_is_w else rec["l_games"]
        fav_margin = (rec["w_games"] - rec["l_games"]) if fav_is_w else (rec["l_games"] - rec["w_games"])
        hcp_pmf = dist["handicap"] if fav_is_w else {-k: v for k, v in dist["handicap"].items()}
        hcp_line = -(_median(hcp_pmf) + 0.5)                       # favourite gives (median + 0.5) games → no push possible
        hcp_win, _, _ = M.handicap_probs(hcp_pmf, hcp_line)
        rows.append({"date": rec["date"], "tour": rec["tour"], "best_of": rec["best_of"], "surface": rec["surface"], "level": rec["level"],
                     "exp_total": dist["expected_total"], "actual_total": total, "p_over_med": M.over_prob(dist["total_games"], med + 0.5),
                     "over_med": int(total > med + 0.5), "med": med, "has_traits": has_traits, "dominance": dom,
                     "p_over_225": M.over_prob(dist["total_games"], 22.5), "over_225": int(total > 22.5),
                     # player-games market judged ex ante for the rating favourite (never for the known winner — that would be look-ahead)
                     "p_fav_games_over": M.over_prob(fav_pmf, fav_med + 0.5), "fav_games_over": int(fav_games > fav_med + 0.5),
                     # game handicap: favourite −line at the model's median margin, ex ante
                     "p_fav_cover": hcp_win, "fav_cover": int(fav_margin + hcp_line > 0), "hcp_push": int(abs(fav_margin + hcp_line) < 1e-9)})

    H.replay(H.base_records(base), R, PS, cb)
    df = pd.DataFrame(rows)
    out = {"n": int(len(df)), "frame": df}
    if not len(df):
        return out
    out["mean_expected_total"] = float(df["exp_total"].mean())
    out["mean_actual_total"] = float(df["actual_total"].mean())
    out["mae_total"] = float((df["exp_total"] - df["actual_total"]).abs().mean())
    out["over_median"] = metrics(df["p_over_med"].values, df["over_med"].values)
    out["over_median_calibration"] = _cal_generic(df["p_over_med"].values, df["over_med"].values, [(0.3, 0.4), (0.4, 0.45), (0.45, 0.5), (0.5, 0.55), (0.55, 0.6), (0.6, 0.7)])
    d3 = df[df["best_of"] == 3]
    out["over_22_5_bo3"] = metrics(d3["p_over_225"].values, d3["over_225"].values) if len(d3) else None
    out["over_22_5_calibration"] = _cal_generic(d3["p_over_225"].values, d3["over_225"].values, [(0.0, 0.3), (0.3, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 1.01)]) if len(d3) else []
    out["fav_games_over_median"] = metrics(df["p_fav_games_over"].values, df["fav_games_over"].values)
    out["fav_handicap"] = metrics(df["p_fav_cover"].values, df["fav_cover"].values)
    out["fav_handicap_calibration"] = _cal_generic(df["p_fav_cover"].values, df["fav_cover"].values, [(0.0, 0.4), (0.4, 0.45), (0.45, 0.5), (0.5, 0.55), (0.55, 0.6), (0.6, 1.01)])
    out["by_tour"] = {t: {"n": int(len(g)), "mean_expected": float(g["exp_total"].mean()), "mean_actual": float(g["actual_total"].mean())} for t, g in df.groupby("tour")}
    out["by_format"] = {int(b): {"n": int(len(g)), "mean_expected": float(g["exp_total"].mean()), "mean_actual": float(g["actual_total"].mean())} for b, g in df.groupby("best_of")}
    out["with_traits_share"] = float(df["has_traits"].mean())
    return out


def _median(pmf: dict[int, float]) -> int:
    acc = 0.0
    for k in sorted(pmf):
        acc += pmf[k]
        if acc >= 0.5:
            return k
    return max(pmf)


def _cal_generic(p, y, buckets):
    rows = []
    for lo, hi in buckets:
        m = (p >= lo) & (p < hi)
        n = int(m.sum())
        rows.append({"bucket": f"{int(lo*100)}-{int(min(hi,1)*100)}%", "n": n, "predicted": float(p[m].mean()) if n else None, "actual": float(y[m].mean()) if n else None})
    return rows


def main(quick: bool = False) -> Path:
    t0 = time.time()
    base = D.load_base()
    if quick:
        base = base[base["date"] >= "2009-01-01"]
    bl = S.load_baselines()
    if not bl:
        bl = S.serve_baselines(base)
        S.save_baselines(bl)
    lines = ["# Tennis engine — walk-forward backtest", "",
             f"Data: Jeff Sackmann's ATP (main tour + qualifying/Challengers) and WTA match files, archive snapshot June 2026 "
             f"({len(base):,} matches {base['date'].min()} → {base['date'].max()}). Replay in chronological order; every prediction "
             f"uses only earlier matches. Training period {TRAIN[0]}…{TRAIN[1]} for parameter choice, evaluation {TEST[0]}…{base['date'].max()}. "
             f"'Rated' = both players had ≥ {C.MIN_MATCHES_RATED} earlier matches in the data.", ""]
    # ---- 1. parameter selection on the training period (K schedule, then surface weight)
    grid_k = [(100, 0.3), (150, 0.3), (200, 0.3), (250, 0.4), (150, 0.2)] if not quick else [(250, 0.4)]
    results = []
    for k, shape in grid_k:
        df = run_ratings(base, k, shape, 0.5)
        tr = rated(df[(df["date"] >= TRAIN[0]) & (df["date"] <= TRAIN[1])])
        m = metrics(tr["p_a"].values, tr["y"].values)
        results.append((k, shape, 0.5, m["log_loss"], m["accuracy"], m["n"]))
        log.info("grid K=%s shape=%s w=0.5 → train log loss %.4f", k, shape, m["log_loss"])
    k_best, shape_best = min(results, key=lambda r: r[3])[:2]
    grid_w = [0.0, 0.25, 0.5, 0.75, 1.0] if not quick else [0.5]
    for w in grid_w:
        if w == 0.5 and not quick:
            continue
        df = run_ratings(base, k_best, shape_best, w)
        tr = rated(df[(df["date"] >= TRAIN[0]) & (df["date"] <= TRAIN[1])])
        m = metrics(tr["p_a"].values, tr["y"].values)
        results.append((k_best, shape_best, w, m["log_loss"], m["accuracy"], m["n"]))
        log.info("grid K=%s shape=%s w=%s → train log loss %.4f", k_best, shape_best, w, m["log_loss"])
    best = min(results, key=lambda r: r[3])
    k_best, shape_best, w_best = best[0], best[1], best[2]
    scale_rows = []
    for sc in ([400.0, 450.0, 500.0] if not quick else [400.0]):
        df = run_ratings(base, k_best, shape_best, w_best, scale=sc)
        tr = rated(df[(df["date"] >= TRAIN[0]) & (df["date"] <= TRAIN[1])])
        m = metrics(tr["p_a"].values, tr["y"].values)
        scale_rows.append((sc, m["log_loss"], m["accuracy"], m["n"]))
        log.info("scale %s → train log loss %.4f", sc, m["log_loss"])
    scale_best = min(scale_rows, key=lambda r: r[1])[0]
    lines += ["## 1. Parameter selection (training period, rated matches, log loss — lower is better)", "",
              md_table(["K", "shape", "surface weight", "log loss", "accuracy", "n"],
                       [[r[0], r[1], r[2], fmt(r[3]), fmt(r[4], True), f"{r[5]:,}"] for r in sorted(results, key=lambda r: r[3])]),
              "", f"Chosen: K = {k_best}, shape = {shape_best} (K schedule K/(matches+{C.ELO_OFFSET:g})^shape), surface weight = {w_best}.", "",
              "Logistic scale of the rating difference (training period):", "",
              md_table(["scale", "log loss", "accuracy", "n"], [[r[0], fmt(r[1]), fmt(r[2], True), f"{r[3]:,}"] for r in scale_rows]),
              "", f"Chosen scale: {scale_best:g}.", ""]
    # ---- 2. evaluation period with the chosen parameters
    df = run_ratings(base, k_best, shape_best, w_best, scale=scale_best)
    df_noadj = run_ratings(base, k_best, shape_best, w_best, format_adjust=False, scale=scale_best)
    te = df[(df["date"] >= TEST[0])]
    te_r = rated(te)
    m_all, m_r = metrics(te["p_a"].values, te["y"].values), metrics(te_r["p_a"].values, te_r["y"].values)
    rb = ranking_baseline(te_r)
    lines += ["## 2. Evaluation period (out of sample)", "",
              md_table(["Subset", "n", "accuracy", "Brier", "log loss"],
                       [["All matches (incl. players with little history)", f"{m_all['n']:,}", fmt(m_all["accuracy"], True), fmt(m_all["brier"]), fmt(m_all["log_loss"])],
                        ["Rated (both players ≥ 10 earlier matches)", f"{m_r['n']:,}", fmt(m_r["accuracy"], True), fmt(m_r["brier"]), fmt(m_r["log_loss"])],
                        ["Reference: better-ranked player wins (official ranking, rated subset with ranks)", f"{rb['n']:,}" if rb else "N/A", fmt(rb["accuracy"], True) if rb else "N/A", "—", "—"],
                        ["Reference: coin flip", "", "50.0%", "0.2500", "0.6931"]]), ""]
    # calibration (favourite orientation)
    p_fav = np.where(te_r["p_a"].values >= 0.5, te_r["p_a"].values, 1 - te_r["p_a"].values)
    fav_won = np.where(te_r["p_a"].values >= 0.5, te_r["y"].values, 1 - te_r["y"].values)
    cal = calibration(p_fav, fav_won)
    lines += ["## 3. Calibration (evaluation period, rated matches, favourite's probability)", "",
              md_table(["Probability bucket", "Predictions", "Mean predicted", "Actual win rate", "Gap (pp)"],
                       [[c["bucket"], f"{c['n']:,}", fmt(c["predicted"], True), fmt(c["actual"], True),
                         "N/A" if c["actual"] is None else f"{(c['actual']-c['predicted'])*100:+.1f}"] for c in cal]), ""]
    # breakdowns
    def block(title, key, order=None):
        rows = []
        groups = te_r.groupby(key)
        keys = order or sorted(groups.groups.keys(), key=str)
        for kk in keys:
            if kk not in groups.groups:
                continue
            g = groups.get_group(kk)
            mm = metrics(g["p_a"].values, g["y"].values)
            rows.append([kk, f"{mm['n']:,}", fmt(mm["accuracy"], True), fmt(mm["brier"]), fmt(mm["log_loss"])])
        return [f"### {title}", "", md_table([key, "n", "accuracy", "Brier", "log loss"], rows), ""]
    lines += ["## 4. Breakdowns (evaluation period, rated matches)", ""]
    lines += block("By surface", "surface", ["Hard", "Clay", "Grass"])
    lines += block("By tour", "tour", ["atp", "wta"])
    lines += block("By format", "best_of", [3, 5])
    lines += block("By level (G slam, M masters, A tour, PM/P/I WTA 1000/500/250, C challenger, D team)", "level")
    # format adjustment check on best-of-5
    b5 = te_r[te_r["best_of"] == 5]
    b5n = rated(df_noadj[(df_noadj["date"] >= TEST[0]) & (df_noadj["best_of"] == 5)])
    if len(b5):
        m5, m5n = metrics(b5["p_a"].values, b5["y"].values), metrics(b5n["p_a"].values, b5n["y"].values)
        lines += ["### Best-of-5 format handling", "",
                  md_table(["Variant", "n", "accuracy", "Brier", "log loss"],
                           [["Set-level mapping: bo5 probability derived from the set probability (used)", f"{m5['n']:,}", fmt(m5["accuracy"], True), fmt(m5["brier"]), fmt(m5["log_loss"])],
                            ["No format adjustment (bo5 treated as bo3)", f"{m5n['n']:,}", fmt(m5n["accuracy"], True), fmt(m5n["brier"]), fmt(m5n["log_loss"])]]), ""]
    # ---- 3. game markets: fit the day-form spread σ on the training period (moment match of mean total games), evaluate on the test period
    cands = [0.0, 0.08, 0.10, 0.12] if not quick else [0.0, 0.10]
    cal = {}
    for sg in cands:
        g = games_backtest(base, k_best, shape_best, w_best, sample_n=200 if quick else 900, scale=scale_best, period=TRAIN, sigma={"atp": sg, "wta": sg})
        cal[sg] = g["frame"] if g.get("n") else None
        log.info("sigma %.2f → training bias %s", sg, None if cal[sg] is None else round(float((cal[sg]["exp_total"] - cal[sg]["actual_total"]).mean()), 2))
    sigma, cal_rows = {}, []
    for tour in ("atp", "wta"):
        best_sg, best_bias = 0.0, None
        row = [tour]
        for sg in cands:
            f = cal[sg]
            sub = f[f["tour"] == tour] if f is not None else None
            if sub is None or len(sub) < 40:
                row.append("N/A")
                continue
            bias = float((sub["exp_total"] - sub["actual_total"]).mean())
            row.append(f"{bias:+.2f} (n={len(sub)})")
            if best_bias is None or abs(bias) < abs(best_bias):
                best_sg, best_bias = sg, bias
        sigma[tour] = best_sg
        row.append(best_sg)
        cal_rows.append(row)
    gb = games_backtest(base, k_best, shape_best, w_best, sample_n=400 if quick else 2500, scale=scale_best, period=TEST, sigma=sigma)
    lines += ["## 5. Game markets (Markov chain pinned to the Elo probability; random sample of evaluation matches, rated players, no retirements)", "",
              "An independent-points chain with fixed serve probabilities makes matches too long: real matches are more lopsided on the day than "
              "the players' average levels suggest. The game model therefore treats the serve-point difference on the day as Normal(d0, σ) "
              "(5-point Gauss-Hermite mixture, d0 solved so the mixture reproduces the rating probability). σ is the only fitted quantity: "
              "chosen per tour on the *training* period by matching the mean total games (bias closest to zero), then applied unchanged below.", "",
              md_table(["tour"] + [f"bias σ={sg}" for sg in cands] + ["chosen σ"], cal_rows), ""]
    if gb.get("n"):
        lines += [f"Sample: {gb['n']:,} matches; serve/return traits available for both players in {gb['with_traits_share']*100:.0f}% of them "
                  f"(tour/surface baseline used otherwise).", "",
                  md_table(["Quantity", "Value"],
                           [["Mean expected total games", fmt(gb["mean_expected_total"], d=2)], ["Mean actual total games", fmt(gb["mean_actual_total"], d=2)],
                            ["Mean absolute error of expected total", fmt(gb["mae_total"], d=2)],
                            ["Over model median line — accuracy / Brier / log loss", f"{fmt(gb['over_median']['accuracy'], True)} / {fmt(gb['over_median']['brier'])} / {fmt(gb['over_median']['log_loss'])}"],
                            ["Over 22.5 (best-of-3) — accuracy / Brier / log loss", "N/A" if not gb.get("over_22_5_bo3") else f"{fmt(gb['over_22_5_bo3']['accuracy'], True)} / {fmt(gb['over_22_5_bo3']['brier'])} / {fmt(gb['over_22_5_bo3']['log_loss'])}"],
                            ["Favourite's games over the model median (ex ante) — accuracy / Brier / log loss", f"{fmt(gb['fav_games_over_median']['accuracy'], True)} / {fmt(gb['fav_games_over_median']['brier'])} / {fmt(gb['fav_games_over_median']['log_loss'])}"],
                            ["Favourite covers the model's median game handicap (ex ante) — accuracy / Brier / log loss", f"{fmt(gb['fav_handicap']['accuracy'], True)} / {fmt(gb['fav_handicap']['brier'])} / {fmt(gb['fav_handicap']['log_loss'])}"]]), "",
                  "By tour / format (expected vs actual mean total games):", "",
                  md_table(["Group", "n", "expected", "actual"],
                           [[f"tour {t}", v["n"], fmt(v["mean_expected"], d=2), fmt(v["mean_actual"], d=2)] for t, v in gb["by_tour"].items()] +
                           [[f"best-of-{b}", v["n"], fmt(v["mean_expected"], d=2), fmt(v["mean_actual"], d=2)] for b, v in gb["by_format"].items()]), "",
                  "Calibration of P(over 22.5 games), best-of-3:", "",
                  md_table(["Bucket", "n", "predicted", "actual"], [[c["bucket"], c["n"], fmt(c["predicted"], True), fmt(c["actual"], True)] for c in gb["over_22_5_calibration"]]), "",
                  "Calibration of P(favourite covers the median game handicap):", "",
                  md_table(["Bucket", "n", "predicted", "actual"], [[c["bucket"], c["n"], fmt(c["predicted"], True), fmt(c["actual"], True)] for c in gb["fav_handicap_calibration"]]), ""]
    lines += ["## 6. What this does and does not show", "",
              "* Probabilities come from results only (Elo); bookmaker prices are not in the data set and were not used anywhere.",
              "* Calibration is judged on the evaluation period, which the parameter choice never saw.",
              "* Players with fewer than 10 earlier matches are predicted with provisional ratings; their matches are reported separately (line 'All matches').",
              "* Game-market figures use a random sample and serve traits frozen at the archive snapshot when replayed live; treat them as a first validation, not proof of edge.",
              "* No ROI is claimed: there are no historical Sportybet prices to compare against yet. The live tracker (data/tennis/tracker.csv) will accumulate that evidence.",
              "", f"Generated in {time.time()-t0:.0f} s by tennis/backtest.py."]
    out = C.REPO / "tennis" / "BACKTEST_RESULTS.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    te.to_csv(C.HISTORY_DIR / "backtest_predictions.csv.gz", index=False, compression="gzip")
    (C.HISTORY_DIR / "validated_params.json").write_text(json.dumps({"k": k_best, "shape": shape_best, "surface_weight": w_best, "scale": scale_best, "form_sigma": sigma}))
    log.info("backtest written to %s (K=%s shape=%s w=%s scale=%s sigma=%s)", out, k_best, shape_best, w_best, scale_best, sigma)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main(quick=a.quick)
