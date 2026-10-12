#!/usr/bin/env python3
"""Phase-B evidence run for the research layer (2026-10-11).

The research engine collects lineups / fatigue / motivation / weather with weight 0 (RESEARCH_ADJUST=0,
Phase-B gate). Lineups and weather cannot be replayed retroactively (no archive), but two categories CAN
be reconstructed from results history and tested against the settled shortlist ledger:

  fatigue     — days of rest and match congestion over the last 14 days per team
  motivation  — league-table pressure approximated from recent points-per-game gaps (late-season/derby shape)

For every settled pick we compute the factor, then ask: does it explain the model's RESIDUAL
(outcome 0/1 minus the model's probability)? If a factor systematically moves the residual it
deserves a weight; if not, the weight stays 0 — exactly the Phase-B rule.

Usage:
    python backtest/research_backtest.py --ledger data/shortlist.csv
    python backtest/research_backtest.py --ledger https://raw.githubusercontent.com/<owner>/<repo>/data/data/shortlist.csv [--token XXX]
"""
from __future__ import annotations

import argparse
import io
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FD = {  # football-data division -> country (big leagues only; the ledger covers the diet, this is the overlap)
    "E0": "England", "E1": "England", "SP1": "Spain", "SP2": "Spain", "I1": "Italy", "I2": "Italy",
    "D1": "Germany", "D2": "Germany", "F1": "France", "F2": "France", "N1": "Netherlands",
    "B1": "Belgium", "P1": "Portugal", "SC0": "Scotland", "T1": "Turkey", "G1": "Greece",
}


def _norm(t: str) -> str:
    t = str(t).lower().strip()
    for suf in (" fc", " afc", " sc", " cf", " bk", " if", " sk", " united", " city", " town", " county",
                " Athletic Club", " calcio", " football club"):
        if t.endswith(suf):
            t = t[: -len(suf)]
    return "".join(ch for ch in t if ch.isalnum())


def load_results() -> pd.DataFrame:
    """Two seasons of the big-league CSVs — enough rest/congestion history for the ledger window."""
    frames = []
    year = datetime.now().year
    seasons = [f"{(year - k) % 100:02d}{(year - k + 1) % 100:02d}" for k in range(1, 3)]
    for div in FD:
        for s in seasons:
            url = f"https://www.football-data.co.uk/mmz4281/{s}/{div}.csv"
            try:
                r = requests.get(url, timeout=30)
                if r.status_code != 200 or len(r.content) < 2000:
                    continue
                df = pd.read_csv(io.StringIO(r.content.decode("utf-8", "ignore")))
                if "Date" not in df.columns:
                    continue
                d = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
                ok = df[[c for c in df.columns if c in ("HomeTeam", "AwayTeam", "FTHG", "FTAG")]].copy()
                ok["date"] = d
                ok["div"] = div
                frames.append(ok[["date", "div", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]].dropna(subset=["date"]))
            except Exception:
                continue
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).sort_values("date")
    out["_h"], out["_a"] = out["HomeTeam"].map(_norm), out["AwayTeam"].map(_norm)
    return out


def factors(res: pd.DataFrame, match_date: str, home: str, away: str) -> dict | None:
    """Rest / congestion / recent-form-gap for one fixture, from strictly earlier matches only."""
    try:
        d = pd.Timestamp(match_date)
    except (ValueError, TypeError):
        return None
    h, a = _norm(home), _norm(away)
    hist = res[res["date"] < d]
    if hist.empty:
        return None
    out = {}
    for side, team in (("h", h), ("a", a)):
        t = hist[(hist["_h"] == team) | (hist["_a"] == team)]
        last = t["date"].max() if len(t) else None
        out[f"rest_{side}"] = (d - last).days if last is not None else None
        win14 = t[t["date"] >= d - timedelta(days=14)]
        pts = sum((1 if (r.FTHG > r.FTAG) == (r._h == team) else 0) if r.FTHG != r.FTAG else 1 for r in win14.itertuples())
        out[f"cong_{side}"] = len(win14)
        out[f"ppg14_{side}"] = pts / max(len(win14), 1)
    if out["rest_h"] is None or out["rest_a"] is None:
        return None
    out["rest_edge"] = out["rest_h"] - out["rest_a"]                    # + = home better rested
    out["cong_edge"] = out["cong_a"] - out["cong_h"]                    # + = home less congested
    out["form_edge"] = out["ppg14_h"] - out["ppg14_a"]                  # + = home in better recent shape
    return out


def bucket_report(rows: list[dict], key: str, edges=(-3, 1, 4)) -> list[tuple[str, int, float, float]]:
    """Mean residual per factor bucket: residual = outcome - model_p. + means the model UNDER-rated."""
    by = defaultdict(list)
    for r in rows:
        v = r.get(key)
        if v is None:
            continue
        if v < edges[0]:
            by[f"< {edges[0]}"].append(r)
        elif v < edges[1]:
            by[f"{edges[0]}..{edges[1]}"].append(r)
        elif v < edges[2]:
            by[f"{edges[1]}..{edges[2]}"].append(r)
        else:
            by[f">= {edges[2]}"].append(r)
    return [(k, len(v), sum(x["out"] for x in v) / len(v), sum(x["res"] for x in v) / len(v))
            for k, v in sorted(by.items())]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=str(ROOT / "data" / "shortlist.csv"))
    ap.add_argument("--token", default="")
    ap.add_argument("--out", default=str(ROOT / "backtest" / "RESEARCH_RESULTS.md"))
    a = ap.parse_args()
    led = a.ledger
    if led.startswith("http"):
        hdr = {"Authorization": f"Bearer {a.token}"} if a.token else {}
        led = io.StringIO(requests.get(led, headers=hdr, timeout=60).text)
    df = pd.read_csv(led, dtype=str, keep_default_na=False)
    df = df[df["result"].isin(["hit", "miss"])].copy()
    df["pv"] = pd.to_numeric(df["p"], errors="coerce")
    df = df.dropna(subset=["pv"])
    df["out"] = (df["result"] == "hit").astype(float)
    print(f"settled picks in ledger: {len(df)}")
    res = load_results()
    print(f"history matches loaded: {len(res)}")
    rows = []
    for r in df.itertuples():
        f = factors(res, r.match_date, r.home, r.away)
        if not f:
            continue
        f.update(out=r.out, res=r.out - r.pv, market=r.market, status=r.status)
        rows.append(f)
    print(f"picks matched to history: {len(rows)}")
    L = ["# Phase-B research evidence (auto-run 2026-10-11)", "",
         "Residual = actual outcome (1/0) minus the model's probability, averaged per factor bucket.",
         "Positive residual = the model UNDER-rated those picks. A factor earns a weight only if the",
         "pattern is monotone and the sample is big enough (n >= 150 total).", ""]
    verdicts = {}
    for key, name, edges in (("rest_edge", "Fatigue: rest advantage (days, home view)", (-3, 1, 4)),
                             ("cong_edge", "Fatigue: congestion advantage (matches, home view)", (-2, 0, 2)),
                             ("form_edge", "Motivation/form: recent 14-day points-gap", (-0.5, 0.0, 0.5))):
        rep = bucket_report(rows, key, edges)
        n = sum(x[1] for x in rep)
        L.append(f"## {name}")
        L.append("")
        L.append("| Bucket | n | Actual hit | Mean residual |")
        L.append("|---|---|---|---|")
        for k, bn, hit, mres in rep:
            L.append(f"| {k} | {bn} | {hit:.3f} | {mres:+.3f} |")
        # monotone verdict: correlation across buckets weighted by n
        vals = [(hit, mres, bn) for _, bn, hit, mres in rep]
        ok = n >= 150 and len(vals) >= 3 and sum(1 for i in range(1, len(vals)) if (vals[i][1] - vals[i - 1][1]) * (vals[i][0] - vals[i - 1][0]) > 0) >= len(vals) - 1
        verdicts[key] = "EVIDENCE — candidate for a small weight (needs the engine's cap)" if ok else "no reliable signal — weight stays 0"
        L.append("")
        L.append(f"**Verdict:** {verdicts[key]} (n={n}).")
        L.append("")
    Path(a.out).write_text("\n".join(L), encoding="utf-8")
    print(f"written: {a.out}")
    for k, v in verdicts.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
