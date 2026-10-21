#!/usr/bin/env python3
"""Re-grade the published ledgers against the archived match statistics.

Run once after the 2026-10-21 settlement fix (and any time a grading bug is suspected):

    python tools/regrade_ledgers.py --state state          # dry run, prints what would change
    python tools/regrade_ledgers.py --state state --write   # rewrite the CSVs in place

It reads `data/ls/stages/*.json` (events + match statistics) and re-checks every corner / card row in
`data/safe_bets.csv`, `data/shortlist.csv` and `data/tracker.csv`. Goals, BTTS and 1X2 rows are never touched, and a
match whose statistic was never published is left exactly as it is — a missing stat is not a loss.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import safe  # noqa: E402

LEDGERS = (
    ("data/safe_bets.csv", "status"),
    ("data/shortlist.csv", "result"),
    ("data/tracker.csv", "status"),
)


def archive_results(state: Path) -> pd.DataFrame:
    """Every finished match the archive holds, with the statistics that grading needs."""
    rows = []
    for f in sorted((state / "data" / "ls" / "stages").glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        country, league = d.get("country"), d.get("league")
        stats = d.get("stats") or {}
        for eid, v in (d.get("events") or {}).items():
            if not isinstance(v, list) or len(v) < 7 or v[5] is None or v[6] is None:
                continue
            st = stats.get(eid) or []
            rows.append({
                "country": country, "league": league, "date": str(v[0])[:8],
                "home": v[2], "away": v[4], "hg": v[5], "ag": v[6],
                "hc": st[0] if len(st) > 0 else None, "ac": st[1] if len(st) > 1 else None,
                "hy": st[2] if len(st) > 2 else None, "ay": st[3] if len(st) > 3 else None,
                "hr": st[4] if len(st) > 4 else None, "ar": st[5] if len(st) > 5 else None,
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d", errors="coerce")
    return df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="state", help="directory holding data/ (the restored data branch)")
    ap.add_argument("--write", action="store_true", help="write the corrected CSVs back")
    ap.add_argument("--days", type=int, default=120, help="how far back to re-check (default 120)")
    args = ap.parse_args()

    state = Path(args.state)
    res = archive_results(state)
    if res.empty:
        print(f"no archived results under {state}/data/ls/stages — nothing to do")
        return 1
    print(f"archive: {len(res)} finished matches ({int(res['hc'].notna().sum())} with corner stats)")

    today = datetime.now()
    total = 0
    for rel, status_col in LEDGERS:
        path = state / rel
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if df.empty:
            continue
        before = df.copy()
        out, fixed = safe.regrade_settled(df, res, today, days=args.days, status_col=status_col)
        changed = int((out[status_col].astype(str) != before[status_col].astype(str)).sum())
        print(f"{rel}: {len(df)} rows, {changed} corrected")
        if changed:
            flips = out[status_col].astype(str) != before[status_col].astype(str)
            show = out[flips].groupby(["sel", out[status_col]]).size()
            print(show.to_string())
        total += changed
        if args.write and changed:
            out.to_csv(path, index=False)
    print(f"total corrected: {total}" + ("" if args.write else "  (dry run — pass --write to save)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
