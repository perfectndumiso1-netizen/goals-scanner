"""Historical data handling: chronological replay of the match record (historical base + Livescore
results) through the ratings and player statistics, the tennis tracker (data/tennis/tracker.csv) and
settlement of tracked selections. Football's data/tracker.csv is never touched.
"""
from __future__ import annotations

import csv
import gzip
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import config as C
from . import data as D
from .model import Ratings
from .stats import PlayerStats

log = logging.getLogger("tennis.history")
TRACKER_FIELDS = ["date", "tournament", "round", "surface", "player_a", "player_b", "market", "selection", "line",
                  "model_probability", "fair_odds", "bookmaker_odds", "implied", "edge_pp", "result", "won",
                  "match_id", "data_quality", "recorded_at", "settled_at"]
_STAT = D.STAT_COLS


def base_records(base: pd.DataFrame):
    """Iterate the historical base as plain dicts (already sorted chronologically by data.build_base)."""
    cols = list(base.columns)
    idx = {c: i for i, c in enumerate(cols)}
    for row in base.itertuples(index=False, name=None):
        rec = {"date": row[idx["date"]], "surface": row[idx["surface"]] if isinstance(row[idx["surface"]], str) else None,
               "tour": row[idx["tour"]], "level": row[idx["level"]], "best_of": int(row[idx["best_of"]]) if row[idx["best_of"]] == row[idx["best_of"]] else 3,
               "tournament": row[idx["tourney_name"]], "round": row[idx["round"]], "w": row[idx["w_id"]], "l": row[idx["l_id"]],
               "opp_name_w": row[idx["l_name"]], "opp_name_l": row[idx["w_name"]], "w_name": row[idx["w_name"]], "l_name": row[idx["l_name"]],
               "score": row[idx["score"]], "retired": bool(row[idx["retired"]]), "src": "sackmann",
               "w_rank": row[idx["w_rank"]], "l_rank": row[idx["l_rank"]]}
        for c in ("w_games", "l_games", "w_sets", "l_sets", "tiebreaks"):
            v = row[idx[c]]
            rec[c] = None if v != v else int(v)
        for c in _STAT:
            for side in ("w", "l"):
                v = row[idx[f"{side}_{c}"]]
                rec[f"{side}_{c}"] = None if v != v else float(v)
        yield rec


def livescore_records(results: list[dict], index: D.PlayerIndex, resolver: D.SurfaceResolver) -> list[dict]:
    """Finished Livescore matches → replay records (no statistics: Livescore publishes none)."""
    out = []
    for e in results:
        if not e.get("winner") or not e.get("sets"):
            continue
        w_side, l_side = ("p1", "p2") if e["winner"] == 1 else ("p2", "p1")
        w = index.resolve(e[w_side]["name"], e[w_side].get("ioc"), e["tour"], e[w_side]["ls_id"])
        l = index.resolve(e[l_side]["name"], e[l_side].get("ioc"), e["tour"], e[l_side]["ls_id"])
        month = int(e["day"][5:7])
        surf = resolver.resolve(e["tournament"], month)["surface"]
        sets = e["sets"] if e["winner"] == 1 else [[b, a] for a, b in e["sets"]]
        score = " ".join(f"{a}-{b}" for a, b in sets)
        wg, lg = sum(a for a, _ in sets), sum(b for _, b in sets)
        ws, ls = sum(1 for a, b in sets if a > b), sum(1 for a, b in sets if b > a)
        tb = sum(1 for a, b in sets if (a, b) in ((7, 6), (6, 7)))
        rec = {"date": e["day"], "surface": surf, "tour": e["tour"], "level": e["level"],
               "best_of": 5 if e["level"] == "G" and e["tour"] == "atp" else 3, "tournament": e["tournament"],
               "round": "Q" if e.get("qualifying") else None, "w": w["pid"], "l": l["pid"], "w_name": w["name"], "l_name": l["name"],
               "opp_name_w": l["name"], "opp_name_l": w["name"], "score": score, "retired": bool(e.get("retired")),
               "w_games": wg, "l_games": lg, "w_sets": ws, "l_sets": ls, "tiebreaks": tb, "src": "livescore", "ls_id": e["ls_id"],
               "w_rank": None, "l_rank": None}
        for c in _STAT:
            rec[f"w_{c}"] = None
            rec[f"l_{c}"] = None
        out.append(rec)
    out.sort(key=lambda r: r["date"])
    return out


def replay(records, ratings: Ratings, stats: PlayerStats | None = None, on_match=None, skip_levels: tuple = ()) -> int:
    """Chronological replay. For every match: predict (from earlier matches only) → callback → observe → update."""
    n = 0
    for rec in records:
        if rec["level"] in skip_levels:
            continue
        pred = ratings.predict(rec["w"], rec["l"], rec["surface"], rec["best_of"])
        if on_match is not None:
            on_match(rec, pred)
        if stats is not None:
            rec["exp_w"] = pred["p_match"]
            rec["rating_w"], rec["rating_l"] = pred["rating_a"], pred["rating_b"]
            stats.observe(rec)
        ratings.update(rec["w"], rec["l"], rec["surface"], rec["date"], rec["best_of"])
        n += 1
    return n


# ------------------------------------------------------------------ tracker
def _read_tracker() -> list[dict]:
    if not C.TRACKER.exists():
        return []
    with C.TRACKER.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write_tracker(rows: list[dict]) -> None:
    C.TRACKER.parent.mkdir(parents=True, exist_ok=True)
    with C.TRACKER.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=TRACKER_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def record_selections(rows: list[dict]) -> int:
    """Append selections not yet tracked (key: match_id + market + selection + line)."""
    cur = _read_tracker()
    seen = {(r["match_id"], r["market"], r["selection"], r.get("line", "")) for r in cur}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    added = 0
    for r in rows:
        key = (r["match_id"], r["market"], r["selection"], str(r.get("line", "") or ""))
        if key in seen:
            continue
        seen.add(key)
        cur.append({**{k: "" for k in TRACKER_FIELDS}, **{k: ("" if v is None else v) for k, v in r.items()}, "recorded_at": now})
        added += 1
    if added:
        _write_tracker(cur)
    return added


def settle(results_by_id: dict[str, dict]) -> int:
    """Fill result/won for tracked selections whose match has a stored result. Retirements settle the
    winner market only; game markets stay 'void'."""
    cur = _read_tracker()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    n = 0
    for r in cur:
        if r.get("won") not in ("", None):
            continue
        e = results_by_id.get(r["match_id"])
        if not e or not e.get("finished") or not e.get("winner"):
            continue
        sets = e["sets"]
        g1, g2 = sum(a for a, _ in sets), sum(b for _, b in sets)
        won: str | None = None
        result = f"{'/'.join(f'{a}-{b}' for a, b in sets)}"
        line = float(r["line"]) if r.get("line") not in ("", None) else None
        sel = r["selection"]
        if r["market"] == "winner":
            won = "1" if (sel == "player_a") == (e["winner"] == 1) else "0"
        elif e.get("retired"):
            won = "void"
        elif r["market"] == "total_games" and line is not None:
            won = "1" if ((g1 + g2 > line) == (sel == "over")) else "0"
        elif r["market"] in ("p1_games", "p2_games") and line is not None:
            g = g1 if r["market"] == "p1_games" else g2
            won = "1" if ((g > line) == (sel == "over")) else "0"
        elif r["market"] == "game_handicap" and line is not None:
            margin = (g1 - g2) if sel == "player_a" else (g2 - g1)
            won = "void" if abs(margin + line) < 1e-9 else ("1" if margin + line > 0 else "0")
        if won is not None:
            r["result"], r["won"], r["settled_at"] = result, won, now
            n += 1
    if n:
        _write_tracker(cur)
    return n


def tracker_summary() -> dict:
    cur = _read_tracker()
    done = [r for r in cur if r.get("won") in ("0", "1")]
    out = {"tracked": len(cur), "settled": len(done), "won": sum(1 for r in done if r["won"] == "1")}
    by: dict[str, dict] = {}
    for r in done:
        b = by.setdefault(r["market"], {"n": 0, "won": 0, "p_sum": 0.0})
        b["n"] += 1
        b["won"] += r["won"] == "1"
        try:
            b["p_sum"] += float(r["model_probability"])
        except (TypeError, ValueError):
            pass
    out["by_market"] = {k: {"n": v["n"], "won": v["won"], "hit_rate": round(v["won"] / v["n"], 3), "avg_model_p": round(v["p_sum"] / v["n"], 3)} for k, v in by.items()}
    return out


def write_day_file(day: str, payload: dict) -> Path:
    """Full per-day analysis (every match, all inputs) kept gzip-compressed for audit — ~150 KB/day instead of 1.5 MB."""
    C.HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    p = C.HISTORY_DIR / f"{day}.json.gz"
    with gzip.open(p, "wt", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
    return p


def read_day_file(day: str) -> dict | None:
    p = C.HISTORY_DIR / f"{day}.json.gz"
    if not p.exists():
        return None
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        return json.load(fh)
