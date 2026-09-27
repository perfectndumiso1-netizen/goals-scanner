"""Structured export for the Android app (format v3).

data/app/latest.json   slim index: meta, every fixture in the window (list fields only), shortlists, safest bets,
                       bets of the day, trackers, history index — small enough to refresh often
data/app/fx/<key>.json full detail for one fixture (stats, markets, selections, trends, h2h) — loaded on demand
data/app/meta.json     tiny heartbeat for the background checker (generated, run, alerts, tracked live ids)
data/app/alerts.json   the last new-bet alerts (id, time, title, text) — the app notifies the ones it has not seen
data/app/badges.json   team short name -> Livescore badge path (grows with every run)
The app reads everything straight from GitHub (raw.githubusercontent.com, `data` branch) — the repo is the backend.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

VERSION = 3
KEEP_DETAIL_DAYS = 3


def _f(x, nd=3):
    """float or None (NaN-safe), rounded."""
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)) or (isinstance(x, str) and x == ""):
            return None
        v = float(x)
        return None if math.isnan(v) else round(v, nd)
    except (TypeError, ValueError):
        return None


def fixture_id(date: str, country: str, home: str, away: str) -> str:
    return f"{date}|{country}|{home}|{away}"


def detail_key(fid: str) -> str:
    return hashlib.sha1(fid.encode("utf-8")).hexdigest()[:12]


def _lines(d: dict | None) -> dict | None:
    if not d:
        return None
    return {str(k): [_f(v[0], 2), _f(v[1], 2)] if isinstance(v, (tuple, list)) else _f(v, 3) for k, v in d.items()}


def _sb(sb: dict | None) -> dict | None:
    if not sb:
        return None
    out = {}
    if sb.get("1X2"):
        out["1X2"] = [_f(x, 2) for x in sb["1X2"]]
    if sb.get("DC"):
        out["DC"] = {k: _f(v, 2) for k, v in sb["DC"].items()}
    if sb.get("BTTS"):
        out["BTTS"] = [_f(x, 2) for x in sb["BTTS"]]
    for k in ("OU", "TGH", "TGA", "CORN", "CORNH", "CORNA", "CORN1H", "CARDS", "CARDSH", "CARDSA"):
        if sb.get(k):
            out[k] = _lines(sb[k])
    return out


def _count(exp, probs: dict | None) -> dict | None:
    if exp is None:
        return None
    return {"home": _f(exp.eh, 2), "away": _f(exp.ea, 2), "total": _f(exp.eh + exp.ea, 2),
            "p": {side: {str(k): _f(v, 3) for k, v in d.items()} for side, d in (probs or {}).items()}}


def _date(d) -> str:
    return d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)


def _matches(lst) -> list[dict]:
    return [{"date": _date(m["date"]), "venue": m["venue"], "opp": m["opp"], "gf": m["gf"], "ga": m["ga"],
             "league": m.get("league")} for m in (lst or [])]


def _profile(t) -> dict:
    return {"name": t.name, "n": int(t.n), "n_eff": _f(t.n_eff, 1), "venue_n": int(t.venue_n), "gf": _f(t.gf, 2), "ga": _f(t.ga, 2),
            "venue_gf": _f(t.venue_gf, 2), "venue_ga": _f(t.venue_ga, 2), "att": _f(t.att, 2), "def": _f(t.dfc, 2),
            "o15": _f(t.rate_o15), "o25": _f(t.rate_o25), "o35": _f(t.rate_o35), "btts": _f(t.rate_btts),
            "cs": _f(t.rate_cs), "fts": _f(t.rate_fts), "last_n": int(t.last_n), "last_o15": int(t.last_o15),
            "last_o25": int(t.last_o25), "last_btts": int(t.last_btts), "form5_goals": _f(t.form5_goals, 2),
            "xg_for": _f(t.xg_for, 2), "xg_against": _f(t.xg_against, 2),
            "sot_for": _f(t.sot_for, 2), "sot_against": _f(t.sot_against, 2),
            "venue_o15": _f(getattr(t, "venue_rate_o15", None)), "venue_o25": _f(getattr(t, "venue_rate_o25", None)),
            "venue_btts": _f(getattr(t, "venue_rate_btts", None)),
            "last5": _matches(t.last5), "venue_last5": _matches(getattr(t, "venue_last5", None))}


def update_badges(path: Path, rows: list, ls_map: dict, extra: dict | None = None) -> dict:
    """Persistent {team short name: Livescore image path}; grows with every run, so league tables and
    history pages can show badges for teams that are not in today's fixtures."""
    try:
        badges = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        badges = {}
    changed = False
    for name, img in (extra or {}).items():
        if img and badges.get(name) != img:
            badges[name] = img
            changed = True
    for r in rows:
        ls = ls_map.get(r.fx.name) or {}
        for side in ("home", "away"):
            img = ls.get(f"{side}_img")
            name = r.fx[side]
            if img and badges.get(name) != img:
                badges[name] = img
                changed = True
    if changed or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(sorted(badges.items())), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return badges


def _best(sels: list[dict], groups: tuple | None, min_odds: float, min_p: float) -> list | None:
    """[sel, p, odds] of the most probable priced selection (optionally restricted to groups / safety rules)."""
    best = None
    for d in sels:
        if not d.get("odds") or d["odds"] <= 1 or d.get("p") is None:
            continue
        if d["odds"] < min_odds or d["p"] < min_p or d["diff"]:
            continue
        if groups is not None and d["group"] not in groups:
            continue
        if best is None or (d["p"], d["odds"]) > (best[1], best[2]):
            best = [d["sel"], round(d["p"], 3), round(d["odds"], 2)]
    return best


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    if not path.exists() or path.read_text(encoding="utf-8") != body:
        path.write_text(body, encoding="utf-8")


def export(path: Path, *, ctx: dict, rows: list, picks: dict, tracker_summary: dict, notes: list[str], ls_map: dict,
           helpers: dict, reports_dir: Path, tz_label: str, thresholds: dict, backtest: dict, repo: str | None,
           days_index: list | None = None, safe_summary: dict | None = None, botd: list | None = None,
           alerts: list | None = None, coverage: dict | None = None, safe_groups: tuple = (), extra_badges: dict | None = None,
           report_run: bool = True) -> Path:
    render_details, stars, comp = helpers["render_details"], helpers["stars"], helpers["comp"]
    selections = helpers.get("selections") or (lambda r: [])
    now: datetime = ctx["now"]
    sf = ctx.get("safe") or {}
    min_odds, min_p = float(sf.get("min_odds") or 1.3), float(sf.get("min_p") or 0.7)
    app_dir = path.parent
    fx_dir = app_dir / "fx"
    tracked = set()
    index = []
    ids_by_key = {}
    badges = update_badges(app_dir / "badges.json", rows, ls_map, extra_badges)
    live_eids = []
    for r in rows:
        fx = r.fx
        date = fx["date"].strftime("%Y-%m-%d")
        fid = fixture_id(date, fx["country"], fx["home"], fx["away"])
        key = detail_key(fid)
        ids_by_key[(date, fx["country"], fx["home"], fx["away"])] = fid
        ls = ls_map.get(fx.name)
        x12 = r.extra.x12 or {}
        sels = selections(r)
        top = _best(sels, None, 1.25, 0.0)
        hi = sorted([[d["sel"], round(d["p"], 3), round(d["odds"], 2) if d.get("odds") else None] for d in sels
                     if d.get("p") is not None and d["p"] >= 0.70 and not d["diff"] and d["group"] in ("goals", "btts", "team", "corners", "cards")
                     and (not d.get("odds") or d["odds"] >= 1.15)], key=lambda x: -x[1])[:12]
        safe_best = _best(sels, safe_groups or None, min_odds, min_p) if r.data_ok else None
        eid = (ls or {}).get("eid")
        slim = {
            "id": fid, "d": key, "date": date, "kickoff": fx["kickoff"].strftime("%Y-%m-%d %H:%M"),
            "time_known": bool(fx.get("time_known", True)),
            "country": fx["country"], "league": fx["league"], "div": fx["div"], "competition": comp(r),
            "home": fx["home"], "away": fx["away"], "tier": fx.get("source") or "main",
            "data_ok": bool(r.data_ok), "basis": r.basis,
            "xg": [_f(r.lam_h, 2), _f(r.lam_a, 2)],
            "p": {"O15": _f(r.p_final["O15"]), "O25": _f(r.p_final["O25"]), "BTTS": _f(r.p_final["BTTS"])},
            "x12": [_f(x12.get("H")), _f(x12.get("D")), _f(x12.get("A"))],
            "priced": bool(r.sb), "top": top, "safe": safe_best, "hi": hi,
            "badges": {"home": badges.get(fx["home"]), "away": badges.get(fx["away"])},
            "livescore_id": eid, "sportybet_event": (r.sb_event or {}).get("id"),
        }
        index.append(slim)
        detail = dict(slim)
        detail.update({
            "home_long": (r.sb_event or {}).get("home") or (ls or {}).get("home") or fx["home"],
            "away_long": (r.sb_event or {}).get("away") or (ls or {}).get("away") or fx["away"],
            "referee": (fx.get("referee") or None) or None,
            "xg": {"home": _f(r.lam_h, 2), "away": _f(r.lam_a, 2), "total": _f(r.lam_h + r.lam_a, 2),
                   "model_home": _f(r.mod_h, 2), "model_away": _f(r.mod_a, 2),
                   "market_home": _f(r.mkt_h, 2), "market_away": _f(r.mkt_a, 2)},
            "p": {"O15": _f(r.p_final["O15"]), "O25": _f(r.p_final["O25"]), "O35": _f(r.p_final["O35"]),
                  "BTTS": _f(r.p_final["BTTS"]), "model_O25": _f(r.p_model["O25"]), "model_BTTS": _f(r.p_model["BTTS"]),
                  "market_O25": _f(r.p_market_o25), "fair_O25": _f(r.extra.p_o25_fair)},
            "stars": {m: stars(r.p_final[m], m) for m in ("O15", "O25", "BTTS")},
            "x12": {k: _f(v) for k, v in x12.items() if k in ("H", "D", "A", "1X", "12", "X2")} | (
                {"source": x12.get("source")} if x12.get("source") else {}),
            "team_goals": {k: _f(v) for k, v in (r.extra.tg or {}).items()},
            "corners": _count(r.extra.corners, r.extra.corner_p),
            "cards": _count(r.extra.cards, r.extra.card_p),
            "odds": {"home": _f(fx.get("odds_h"), 2), "draw": _f(fx.get("odds_d"), 2), "away": _f(fx.get("odds_a"), 2),
                     "over25": _f(fx.get("odds_over"), 2), "under25": _f(fx.get("odds_under"), 2),
                     "bfe_over25": _f(fx.get("bfe_over"), 2), "bfe_under25": _f(fx.get("bfe_under"), 2)},
            "sportybet": _sb(r.sb_full or r.sb),
            "teams": {"home": _profile(r.home), "away": _profile(r.away)},
            "league_avg": {"home_goals": _f(r.div_avg.mu_h, 2), "away_goals": _f(r.div_avg.mu_a, 2),
                           "o25": _f(r.div_avg.o25_rate)},
            "h2h": [{"date": _date(m["date"]), "home": m["home"], "away": m["away"], "hg": int(m["hg"]), "ag": int(m["ag"]),
                     "league": m.get("league")} for m in r.h2h[:10]],
            "league_ctx": {"btts": _f(getattr(r.div_avg, "btts_rate", None))},
            "sels": [[d["sel"], d["p"], d["p_model"], d["p_sb"], d["odds"], 1 if d["diff"] else 0] for d in sels],
            "trends": r.trends or {},
        })
        _write(fx_dir / f"{key}.json", detail)
    # prune detail files of fixtures older than a few days (day pages keep their own summary)
    keep = {detail_key(f["id"]) for f in index}
    cutoff = (now - timedelta(days=KEEP_DETAIL_DAYS)).timestamp()
    if fx_dir.exists():
        for p in fx_dir.glob("*.json"):
            if p.stem not in keep and p.stat().st_mtime < cutoff:
                p.unlink(missing_ok=True)
    # shortlists
    picks_out = {}
    for mkt, lst in picks.items():
        picks_out[mkt] = []
        for r in lst:
            fx = r.fx
            fid = ids_by_key[(fx["date"].strftime("%Y-%m-%d"), fx["country"], fx["home"], fx["away"])]
            tracked.add(fid)
            picks_out[mkt].append({"fixture": fid, "p": _f(r.p_final[mkt]), "stars": stars(r.p_final[mkt], mkt),
                                   "sportybet": _f(helpers["sb_price"](r, mkt), 2)})
    # safest bets of this run + bets of the day
    safe_out = {"min_odds": sf.get("min_odds"), "min_p": sf.get("min_p"), "groups": list(safe_groups),
                "bets": [], "today": {"date": now.strftime("%Y-%m-%d"), "bets": []}, "summary": safe_summary or {}}
    for b in sf.get("bets") or []:
        fid = ids_by_key.get(b.key) or fixture_id(*b.key)
        tracked.add(fid)
        safe_out["bets"].append({"id": f"{b.key[0]}|{b.home}|{b.away}|{b.sel}", "fixture": fid, "home": b.home, "away": b.away,
                                 "kickoff": b.kickoff, "league": b.league, "country": b.key[1],
                                 "sel": b.sel, "group": b.group, "label": b.label, "p": _f(b.p), "p_model": _f(b.p_model),
                                 "p_sb": _f(b.p_sb), "odds": _f(b.odds, 2), "fair": _f(1 / b.p, 2) if b.p else None,
                                 "badges": {"home": badges.get(b.home), "away": badges.get(b.away)}})
    for b in botd or []:
        fid = ids_by_key.get((b["kickoff"][:10], b["country"], b["home"], b["away"])) or \
            fixture_id(b["kickoff"][:10], b["country"], b["home"], b["away"])
        tracked.add(fid)
        safe_out["today"]["bets"].append({**b, "fixture": fid,
                                          "badges": {"home": badges.get(b["home"]), "away": badges.get(b["away"])}})
    for f in index:
        if f["id"] in tracked and f.get("livescore_id"):
            live_eids.append(f["livescore_id"])

    tracker_out = {m: {k: (_f(v) if isinstance(v, float) else v) for k, v in info.items()}
                   for m, info in (tracker_summary or {}).items()}
    reports = sorted({p.stem for p in reports_dir.glob("20??-??-??.md")}, reverse=True)[:60]
    meta = {
        "generated": now.strftime("%Y-%m-%d %H:%M"), "tz": tz_label, "run": ctx["run"], "report_run": bool(report_run),
        "window_start": ctx["start"].strftime("%Y-%m-%d %H:%M"), "window_end": ctx["end"].strftime("%Y-%m-%d %H:%M"),
        "fixtures": len(rows), "notes": notes, "repo": repo,
        "report_md": f"reports/{now:%Y-%m-%d}.md", "csv": f"reports/{now:%Y-%m-%d}.csv",
        "thresholds": {m: t["p"] for m, t in thresholds.items()}, "backtest": backtest,
        "next_run": ctx["window_end"].strftime("%Y-%m-%d %H:%M"), "refresh_minutes": 30,
        "coverage": coverage or {},
    }
    data = {
        "version": VERSION, "meta": meta,
        "fixtures": index, "picks": picks_out, "safe": safe_out, "tracker": tracker_out,
        "tracked": sorted(tracked), "history": {"reports": reports, "days": days_index or []},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")
    # heartbeat + alerts for the background checker
    alerts = alerts or []
    _write(app_dir / "alerts.json", alerts[-50:])
    _write(app_dir / "meta.json", {
        "version": VERSION, "generated": meta["generated"], "run": meta["run"], "report_run": bool(report_run),
        "next_run": meta["next_run"], "fixtures": len(rows), "safe_bets": len(safe_out["bets"]),
        "botd": [b["id"] for b in safe_out["today"]["bets"]],
        "alerts": [a["id"] for a in alerts[-30:]], "tracked_eids": sorted(set(live_eids)),
    })
    return path
