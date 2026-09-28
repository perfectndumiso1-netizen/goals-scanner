#!/usr/bin/env python3
"""
Data-audit report for one analysed match, from the exported per-match file (data/app/fx/<key>.json).

    python audit.py "Leganes" "Castellon"                 # find the match in the current publication
    python audit.py --file state/data/app/fx/4670a609b180.json --out reports/audit.md

Prints the same evidence the app shows in the Data tab: data quality, sample composition of both teams, home/away
splits (historical frequencies), the raw matches used, head-to-head strength, the model's lambda decomposition,
the market comparison layer and the automatic warnings. Nothing is recomputed here — the numbers are the ones the
scanner published, so the report is a faithful trace of that run.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import quality

ROOT = Path(__file__).resolve().parent
STATE = Path(os.getenv("STATE_DIR") or ROOT).resolve()


def find_detail(app_dir: Path, home: str, away: str) -> Path | None:
    latest = app_dir / "latest.json"
    if latest.exists():
        d = json.loads(latest.read_text(encoding="utf-8"))
        for f in d.get("fixtures") or []:
            if home.lower() in f.get("home", "").lower() and away.lower() in f.get("away", "").lower():
                p = app_dir / "fx" / f"{f['d']}.json"
                if p.exists():
                    return p
    for p in (app_dir / "fx").glob("*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if home.lower() in d.get("home", "").lower() and away.lower() in d.get("away", "").lower():
            return p
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("home", nargs="?"); ap.add_argument("away", nargs="?")
    ap.add_argument("--file"); ap.add_argument("--out")
    ap.add_argument("--app-dir", default=str(STATE / "data" / "app"))
    a = ap.parse_args()
    if a.file:
        path = Path(a.file)
    elif a.home and a.away:
        path = find_detail(Path(a.app_dir), a.home, a.away)
        if path is None:
            print(f"no analysed match '{a.home} v {a.away}' in {a.app_dir}", file=sys.stderr)
            return 1
    else:
        ap.error("give HOME AWAY or --file")
    d = json.loads(path.read_text(encoding="utf-8"))
    if not d.get("quality"):
        print("this match file has no evidence layer (published before the data-first engine)", file=sys.stderr)
    md = quality.audit_markdown(d)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(md, encoding="utf-8")
        print(f"written {a.out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
