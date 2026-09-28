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
                  "match_id", "data_quality", "recorded_at", "settled_at", "kind"]
KINDS = ("day", "strong", "highlight", "favourite")   # a row may carry several, joined by '+'

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


def _key(r: dict) -> tuple:
    return (str(r["match_id"]), r["market"], r["selection"], str(r.get("line", "") if r.get("line") is not None else ""))


def record_selections(rows: list[dict]) -> int:
    """Append selections not yet tracked (key: match_id + market + selection + line). A selection that is
    already tracked under another kind gets the new kind added (e.g. 'favourite+day'); prices are never
    overwritten — the first recorded price is the one that is graded."""
    cur = _read_tracker()
    by_key = {_key(r): r for r in cur}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    added, changed = 0, False
    for r in rows:
        key = _key(r)
        kind = r.get("kind") or "day"
        if key in by_key:
            have = [k for k in str(by_key[key].get("kind") or "").split("+") if k]
            if kind not in have:
                by_key[key]["kind"] = "+".join(have + [kind])
                changed = True
            continue
        row = {**{k: "" for k in TRACKER_FIELDS}, **{k: ("" if v is None else v) for k, v in r.items() if k in TRACKER_FIELDS}, "recorded_at": now, "kind": kind}
        cur.append(row)
        by_key[key] = row
        added += 1
    if added or changed:
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


def _perf(rows: list[dict]) -> dict:
    """Settled record of a list of tracker rows: hits, hit rate, average model probability (the calibration check),
    flat-stake return at the recorded bookmaker price and at fair odds. Void selections are excluded."""
    done = [r for r in rows if r.get("won") in ("0", "1")]
    won = [r for r in done if r["won"] == "1"]
    p_sum = 0.0
    ret_book = 0.0
    for r in done:
        try:
            p_sum += float(r["model_probability"])
        except (TypeError, ValueError):
            pass
        try:
            ret_book += (float(r["bookmaker_odds"]) - 1) if r["won"] == "1" else -1.0
        except (TypeError, ValueError):
            pass
    n = len(done)
    return {"tracked": len(rows), "settled": n, "won": len(won), "void": sum(1 for r in rows if r.get("won") == "void"),
            "pending": sum(1 for r in rows if r.get("won") in ("", None)),
            "hit_rate": round(len(won) / n, 3) if n else None, "avg_model_p": round(p_sum / n, 3) if n else None,
            "flat_return_units": round(ret_book, 2) if n else None, "roi": round(ret_book / n, 3) if n else None}


def tracker_summary() -> dict:
    """Overall + per kind (day / strong / highlight / favourite) + per market. Evidence, not a claim: shown with n."""
    cur = _read_tracker()
    out = _perf(cur)
    out["by_kind"] = {k: _perf([r for r in cur if k in str(r.get("kind") or "").split("+")]) for k in KINDS}
    out["by_market"] = {m: _perf([r for r in cur if r["market"] == m]) for m in sorted({r["market"] for r in cur})}
    days: dict[str, list] = {}
    for r in cur:
        if "day" in str(r.get("kind") or "").split("+") or "strong" in str(r.get("kind") or "").split("+"):
            days.setdefault(r["date"], []).append(r)
    out["by_day"] = {d: _perf(rs) for d, rs in sorted(days.items())[-30:]}
    return out


def settlement_lookup() -> dict[tuple, dict]:
    """(match_id, market, selection, line) → {won, result} for every tracked row (for day files and match pages)."""
    return {_key(r): {"won": r.get("won") or None, "result": r.get("result") or None, "bookmaker_odds": r.get("bookmaker_odds") or None} for r in _read_tracker()}


def h2h(base: pd.DataFrame, ls_recs: list[dict], a: str, b: str, limit: int = 12) -> list[dict]:
    """Head-to-head list (context only — it is not a model input): archive matches plus Livescore results."""
    if not a or not b or a == b:
        return []
    m = base[((base["w_id"] == a) & (base["l_id"] == b)) | ((base["w_id"] == b) & (base["l_id"] == a))]
    out = [{"date": r.date, "tournament": r.tourney_name, "surface": r.surface if isinstance(r.surface, str) else None, "level": r.level,
            "winner": str(r.w_id), "score": r.score if isinstance(r.score, str) else None, "round": r.round if isinstance(r.round, str) else None}
           for r in m.itertuples(index=False)]
    out += [{"date": r["date"], "tournament": r["tournament"], "surface": r["surface"], "level": r["level"], "winner": str(r["w"]),
             "score": r["score"], "round": r.get("round")} for r in ls_recs if {str(r["w"]), str(r["l"])} == {str(a), str(b)}]
    out.sort(key=lambda r: r["date"], reverse=True)
    return out[:limit]


def result_of(e: dict | None) -> dict | None:
    """Compact final result of a Livescore event for day files / match pages."""
    if not e or not e.get("finished"):
        return None
    sets = e.get("sets") or []
    return {"winner": e.get("winner"), "score": " ".join(f"{x}-{y}" for x, y in sets) if sets else None, "retired": bool(e.get("retired")),
            "games": [sum(x for x, _ in sets), sum(y for _, y in sets)] if sets else None, "status": e.get("status")}


def update_day_files(matches_slim: list[dict], results_by_id: dict, today_sast: str, days_back: int = 3) -> list[str]:
    """Maintain data/app/tennis/days/<SAST day>.json: every match of that day (kept once it leaves the look-ahead
    window), its final result when known and the settlement of its selection / highlights. Returns the days touched."""
    from datetime import date as _date, timedelta as _td
    ddir = C.APP / "days"
    ddir.mkdir(parents=True, exist_ok=True)
    lookup = settlement_lookup()
    touched: dict[str, dict] = {}
    by_day: dict[str, list] = {}
    for m in matches_slim:
        by_day.setdefault(m["day_sast"], []).append(m)
    t0 = _date.fromisoformat(today_sast)
    days = set(by_day) | {(t0 - _td(days=i)).isoformat() for i in range(days_back + 1)}
    for day in sorted(days):
        p = ddir / f"{day}.json"
        cur = {}
        if p.exists():
            try:
                cur = json.loads(p.read_text())
            except Exception:                            # noqa: BLE001
                cur = {}
        entries = {str(x["id"]): x for x in cur.get("matches", []) if x.get("day_sast") == day}   # drops pre-selection-format entries
        for m in by_day.get(day, []):
            entries[str(m["id"])] = m                      # latest analysis wins while the match is upcoming
        if not entries:
            continue
        for x in entries.values():
            res = result_of(results_by_id.get(str(x["id"])))
            if res:
                x["result"] = res
            sel = x.get("selection")
            if sel:
                st = lookup.get((str(x["id"]), sel["market"], sel["selection"], str(sel.get("line") if sel.get("line") is not None else "")))
                if st and st["won"] is not None:
                    sel["won"], sel["result"] = st["won"], st["result"]
            for h in x.get("strong") or []:
                st = lookup.get((str(x["id"]), h["market"], h["selection"], str(h.get("line") if h.get("line") is not None else "")))
                if st and st["won"] is not None:
                    h["won"] = st["won"]
        ms = sorted(entries.values(), key=lambda x: x["start"])
        sels = [dict(x["selection"], match_id=x["id"]) for x in ms if x.get("selection")]
        settled = [s_ for s_ in sels if s_.get("won") in ("0", "1")]
        payload = {"day": day, "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "matches": ms,
                   "summary": {"matches": len(ms), "finished": sum(1 for x in ms if x.get("result")), "selections": len(sels),
                               "settled": len(settled), "won": sum(1 for s_ in settled if s_["won"] == "1"),
                               "strong": sum(1 for s_ in sels if s_.get("strong"))}}
        p.write_text(json.dumps(payload, ensure_ascii=False))
        touched[day] = payload["summary"]
    # index of all day files (newest first) for the app's Days tab
    index = []
    for p in sorted(ddir.glob("*.json"), reverse=True):
        if p.name == "index.json":
            continue
        try:
            j = json.loads(p.read_text())
            index.append({"day": j["day"], **j.get("summary", {})})
        except Exception:                                # noqa: BLE001
            continue
    (ddir / "index.json").write_text(json.dumps({"days": index[:90]}, ensure_ascii=False))
    return sorted(touched)


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
