"""Structured export for the Android app: data/app/latest.json (one file, everything the app shows).
The app reads it straight from GitHub (raw.githubusercontent.com) — the repo is the backend."""
from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd

VERSION = 1


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


def _sheet(lines: list[str]) -> str:
    keep = [l for l in lines if not l.strip().startswith(("<details", "</details"))]
    return "\n".join(keep).strip()


def _profile(t) -> dict:
    return {"name": t.name, "n": int(t.n), "venue_n": int(t.venue_n), "gf": _f(t.gf, 2), "ga": _f(t.ga, 2),
            "venue_gf": _f(t.venue_gf, 2), "venue_ga": _f(t.venue_ga, 2), "att": _f(t.att, 2), "def": _f(t.dfc, 2),
            "o15": _f(t.rate_o15), "o25": _f(t.rate_o25), "o35": _f(t.rate_o35), "btts": _f(t.rate_btts),
            "cs": _f(t.rate_cs), "fts": _f(t.rate_fts), "last_n": int(t.last_n), "last_o15": int(t.last_o15),
            "last_o25": int(t.last_o25), "last_btts": int(t.last_btts), "form5_goals": _f(t.form5_goals, 2),
            "xg_for": _f(t.xg_for, 2), "xg_against": _f(t.xg_against, 2)}


def export(path: Path, *, ctx: dict, rows: list, picks: dict, pr: dict, parlay_ids: list, ledger: pd.DataFrame,
           tracker_summary: dict, notes: list[str], headlines: dict, ls_map: dict, helpers: dict,
           reports_dir: Path, tz_label: str, thresholds: dict, backtest: dict, repo: str | None) -> Path:
    render_details, stars, comp = helpers["render_details"], helpers["stars"], helpers["comp"]
    now: datetime = ctx["now"]
    tracked = set()
    fixtures = []
    ids_by_key = {}
    for r in rows:
        fx = r.fx
        date = fx["date"].strftime("%Y-%m-%d")
        fid = fixture_id(date, fx["country"], fx["home"], fx["away"])
        ids_by_key[(date, fx["country"], fx["home"], fx["away"])] = fid
        ls = ls_map.get(fx.name)
        x12 = r.extra.x12 or {}
        fixtures.append({
            "id": fid, "date": date, "kickoff": fx["kickoff"].strftime("%Y-%m-%d %H:%M"),
            "time_known": bool(fx.get("time_known", True)),
            "country": fx["country"], "league": fx["league"], "div": fx["div"], "competition": comp(r),
            "home": fx["home"], "away": fx["away"],
            "home_long": (r.sb_event or {}).get("home") or (ls or {}).get("home") or fx["home"],
            "away_long": (r.sb_event or {}).get("away") or (ls or {}).get("away") or fx["away"],
            "data_ok": bool(r.data_ok), "basis": r.basis, "referee": (fx.get("referee") or None) or None,
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
            "sportybet": _sb(r.sb_full or r.sb), "sportybet_event": (r.sb_event or {}).get("id"),
            "livescore_id": (ls or {}).get("eid"),
            "teams": {"home": _profile(r.home), "away": _profile(r.away)},
            "league_avg": {"home_goals": _f(r.div_avg.mu_h, 2), "away_goals": _f(r.div_avg.mu_a, 2),
                           "o25": _f(r.div_avg.o25_rate)},
            "h2h": [{"date": m["date"].strftime("%Y-%m-%d") if hasattr(m["date"], "strftime") else str(m["date"]),
                     "home": m["home"], "away": m["away"], "hg": int(m["hg"]), "ag": int(m["ag"])} for m in r.h2h[:5]],
            "sheet_md": _sheet(render_details(r)),
        })
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
    # parlays of this run
    parlays_out = []
    for pid, legs in zip(parlay_ids, pr["parlays"]):
        odds = 1.0
        p = 1.0
        legs_out = []
        for l in legs:
            odds *= l.odds
            p *= l.p
            fid = ids_by_key.get(l.key) or fixture_id(*l.key)
            tracked.add(fid)
            legs_out.append({"fixture": fid, "home": l.home, "away": l.away, "kickoff": l.kickoff,
                             "competition": f"{l.country} · {l.league}", "sel": l.sel, "label": l.label,
                             "odds": _f(l.odds, 2), "p": _f(l.p), "fair": _f(1 / l.p, 2) if l.p else None,
                             "edge": _f(l.p * l.odds - 1), "source": l.source})
        parlays_out.append({"id": pid, "odds": round(odds, 2), "p": round(p, 3), "ev": round(p * odds - 1, 3),
                            "legs": legs_out, "source": pr["source"], "extended": bool(pr["extended"])})
    # ledger (all rows, newest first, legs parsed)
    ledger_out = []
    if ledger is not None and not ledger.empty:
        for r in ledger.sort_values("created", ascending=False).head(60).itertuples():
            try:
                legs = json.loads(r.legs)
            except (TypeError, ValueError):
                legs = []
            for l in legs:
                l["fixture"] = fixture_id(l.get("date", ""), l.get("country", ""), l.get("home", ""), l.get("away", ""))
                if r.status == "pending":
                    tracked.add(l["fixture"])
            ledger_out.append({"id": r.parlay_id, "created": r.created, "run": r.run, "window_end": r.window_end,
                               "odds": _f(r.odds, 2), "p": _f(r.p), "ev": _f(r.ev), "source": r.price_source,
                               "status": r.status, "settled_on": r.settled_on or None, "note": r.note or "",
                               "legs": legs})
    ps = ctx.get("parlay_summary", {})

    def _st(d):
        return {k: (_f(v) if isinstance(v, float) else v) for k, v in (d or {}).items()}
    tracker_out = {m: {k: (_f(v) if isinstance(v, float) else v) for k, v in info.items()}
                   for m, info in (tracker_summary or {}).items()}
    reports = sorted({p.stem for p in reports_dir.glob("20??-??-??.md")}, reverse=True)[:60]
    data = {
        "version": VERSION,
        "meta": {
            "generated": now.strftime("%Y-%m-%d %H:%M"), "tz": tz_label, "run": ctx["run"],
            "window_start": ctx["start"].strftime("%Y-%m-%d %H:%M"), "window_end": ctx["end"].strftime("%Y-%m-%d %H:%M"),
            "parlay_window_end": ctx["window_end"].strftime("%Y-%m-%d %H:%M"),
            "fixtures": len(rows), "notes": notes, "repo": repo,
            "report_md": f"reports/{now:%Y-%m-%d}.md", "dossier_md": f"reports/{now:%Y-%m-%d}-parlays.md",
            "csv": f"reports/{now:%Y-%m-%d}.csv", "thresholds": {m: t["p"] for m, t in thresholds.items()},
            "backtest": backtest,
            "parlay_band": list(ctx.get("parlay_band", [])),
        },
        "fixtures": fixtures,
        "picks": picks_out,
        "parlays": parlays_out,
        "parlay_summary": {"all": _st(ps.get("all")), "30d": _st(ps.get("30d")),
                           "by_run": {k: _st(v) for k, v in (ps.get("by_run") or {}).items()},
                           "pending": ps.get("pending", 0)},
        "ledger": ledger_out,
        "tracker": tracker_out,
        "tracked": sorted(tracked),
        "headlines": {team: [{"title": h.get("title"), "source": h.get("source"), "when": h.get("when"),
                              "link": h.get("link")} for h in items] for team, items in (headlines or {}).items()},
        "history": {"reports": reports},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str), encoding="utf-8")
    return path
