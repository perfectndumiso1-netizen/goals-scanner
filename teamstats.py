"""Team pages for the app: data/app/teams/<div>.json — league table, per-team season stats, home/away splits,
goal-market rates and the last 10 results. Built from the same results pool the model uses (football-data.co.uk)."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

CALENDAR_YEAR = {"USA", "Brazil", "Argentina", "Japan", "China", "Norway", "Sweden", "Finland", "Ireland", "Canada",
                 "Chile", "Colombia", "Uruguay", "Paraguay", "Peru", "Ecuador", "Bolivia", "Venezuela", "Iceland",
                 "Estonia", "Latvia", "Lithuania", "Belarus", "Kazakhstan", "South Korea", "Korea Republic", "Vietnam",
                 "Faroe Islands", "Georgia", "Armenia", "Uzbekistan", "Singapore", "Philippines", "Thailand"}


def slug(div: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", str(div)).strip("_")


def season_start(country: str, now: datetime) -> pd.Timestamp:
    if country in CALENDAR_YEAR:
        return pd.Timestamp(year=now.year, month=1, day=1)
    year = now.year if now.month >= 7 else now.year - 1
    return pd.Timestamp(year=year, month=7, day=1)


def _f(x, nd=2):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return None
        return round(float(x), nd)
    except (TypeError, ValueError):
        return None


def _mean(s: pd.Series, nd=2):
    s = pd.to_numeric(s, errors="coerce").dropna()
    return round(float(s.mean()), nd) if len(s) else None


def _rate(mask: pd.Series):
    return round(float(mask.mean()), 3) if len(mask) else None


def _long(df: pd.DataFrame) -> pd.DataFrame:
    """One row per team per match."""
    h = pd.DataFrame({"date": df["date"], "league": df["league"], "div": df["div"], "team": df["home"], "opp": df["away"],
                      "venue": "H", "gf": df["hg"], "ga": df["ag"], "xgf": df.get("hxg"), "xga": df.get("axg"),
                      "sotf": df.get("hst"), "sota": df.get("ast"), "cf": df.get("hc"), "ca": df.get("ac"),
                      "kf": df.get("hy", 0).fillna(0) + df.get("hr", 0).fillna(0) if "hy" in df else None,
                      "ka": df.get("ay", 0).fillna(0) + df.get("ar", 0).fillna(0) if "ay" in df else None})
    a = pd.DataFrame({"date": df["date"], "league": df["league"], "div": df["div"], "team": df["away"], "opp": df["home"],
                      "venue": "A", "gf": df["ag"], "ga": df["hg"], "xgf": df.get("axg"), "xga": df.get("hxg"),
                      "sotf": df.get("ast"), "sota": df.get("hst"), "cf": df.get("ac"), "ca": df.get("hc"),
                      "kf": df.get("ay", 0).fillna(0) + df.get("ar", 0).fillna(0) if "ay" in df else None,
                      "ka": df.get("hy", 0).fillna(0) + df.get("hr", 0).fillna(0) if "hy" in df else None})
    if "hy" in df:   # cards unknown where yellow cards are not published
        h.loc[df["hy"].isna().to_numpy(), ["kf", "ka"]] = float("nan")
        a.loc[df["ay"].isna().to_numpy(), ["kf", "ka"]] = float("nan")
    lg = pd.concat([h, a], ignore_index=True)
    lg["res"] = lg.apply(lambda r: "W" if r.gf > r.ga else ("L" if r.gf < r.ga else "D"), axis=1)
    lg["pts"] = lg["res"].map({"W": 3, "D": 1, "L": 0})
    return lg.sort_values("date", ascending=False).reset_index(drop=True)


def _evidence(n: int) -> str:
    """Sample-size label shared with quality.py (1-4 Very small, 5-9 Small, 10-19 Moderate, 20-39 Strong, 40+ Very strong)."""
    try:
        import quality
        return quality.evidence_label(n)
    except Exception:
        return "No data" if n < 1 else "Very small" if n < 5 else "Small" if n < 10 else "Moderate" if n < 20 else "Strong" if n < 40 else "Very strong"


def _split(g: pd.DataFrame) -> dict:
    n = len(g)
    return {"p": n, "evidence": _evidence(n), "w": int((g["res"] == "W").sum()), "d": int((g["res"] == "D").sum()), "l": int((g["res"] == "L").sum()),
            "gf": int(g["gf"].sum()), "ga": int(g["ga"].sum()), "pts": int(g["pts"].sum()),
            "ppg": round(float(g["pts"].mean()), 2) if n else None,
            "gf_avg": _mean(g["gf"]), "ga_avg": _mean(g["ga"]),
            "o15": _rate(g["gf"] + g["ga"] >= 2), "o25": _rate(g["gf"] + g["ga"] >= 3), "o35": _rate(g["gf"] + g["ga"] >= 4),
            "btts": _rate((g["gf"] > 0) & (g["ga"] > 0)), "cs": _rate(g["ga"] == 0), "fts": _rate(g["gf"] == 0),
            "win": _rate(g["res"] == "W")}


def _trend_window(g: pd.DataFrame, n: int | None = None) -> dict | None:
    """Trend block for the team's last n matches (n=None: the whole list). None when fewer than
    3 matches — a trend is only computed from real data, never zero-filled."""
    g = g if n is None else g.head(n)
    n = len(g)
    if n < 3:
        return None
    gf, ga = g["gf"], g["ga"]
    return {"n": n, "evidence": _evidence(n), "pts": int(g["pts"].sum()), "ppg": round(float(g["pts"].mean()), 2),
            "gf_avg": _mean(gf), "ga_avg": _mean(ga),
            "o15": _rate(gf + ga >= 2), "o25": _rate(gf + ga >= 3), "o35": _rate(gf + ga >= 4),
            "btts": _rate((gf > 0) & (ga > 0)), "cs": _rate(ga == 0), "fts": _rate(gf == 0),
            "win": _rate(g["res"] == "W"),
            "scored_in_n": int((gf > 0).sum()), "conceded_in_n": int((ga > 0).sum())}


def team_record(lg_team: pd.DataFrame, season: pd.DataFrame, name: str, country: str, league: str, div: str,
                since: pd.Timestamp, prev: pd.DataFrame | None = None) -> dict:
    rec = {"name": name, "country": country, "league": league, "div": div, "season_from": since.strftime("%Y-%m-%d"),
           "all": _split(season), "home": _split(season[season["venue"] == "H"]),
           "away": _split(season[season["venue"] == "A"]),
           "avg": {"xg_for": _mean(season["xgf"]), "xg_against": _mean(season["xga"]),
                   "sot_for": _mean(season["sotf"]), "sot_against": _mean(season["sota"]),
                   "corners_for": _mean(season["cf"]), "corners_against": _mean(season["ca"]),
                   "cards_for": _mean(season["kf"]), "cards_against": _mean(season["ka"])},
           # how many season matches actually carry each field (missing fields stay None / N/A, never 0)
           "avg_n": {"xg": int(pd.to_numeric(season["xgf"], errors="coerce").notna().sum()),
                     "sot": int(pd.to_numeric(season["sotf"], errors="coerce").notna().sum()),
                     "corners": int(pd.to_numeric(season["cf"], errors="coerce").notna().sum()),
                     "cards": int(pd.to_numeric(season["kf"], errors="coerce").notna().sum())},
           "form": "".join(season.head(5)["res"].tolist()[::-1]),
           "last": [{"date": r.date.strftime("%Y-%m-%d"), "venue": r.venue, "opp": r.opp, "gf": int(r.gf), "ga": int(r.ga),
                     "r": r.res, "league": r.league} for r in lg_team.head(10).itertuples()],
           # trend windows (last 5/10/20, season, previous season) — None = N/A, never zero-filled
           "trends": {"last5": _trend_window(lg_team, 5), "last10": _trend_window(lg_team, 10),
                      "last20": _trend_window(lg_team, 20), "season": _trend_window(season),
                      "previous_season": _trend_window(prev) if prev is not None else None}}
    # streaks (current)
    seq = season["res"].tolist()
    if seq:
        cur = seq[0]
        n = 0
        for x in seq:
            if x != cur:
                break
            n += 1
        rec["streak"] = f"{n}{cur}"
    # scoring streaks
    rec["scored_in_last"] = int(sum(1 for g in season.head(10)["gf"] if g > 0))
    rec["conceded_in_last"] = int(sum(1 for g in season.head(10)["ga"] if g > 0))
    return rec


def export(results: pd.DataFrame, now: datetime, out_dir: Path, squad_lookup=None) -> list[str]:
    """Write one JSON per division; returns the list of div slugs written."""
    if results is None or results.empty:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    index: list[dict] = []
    lg_all = _long(results)
    for (country, div), df in results.groupby(["country", "div"]):
        league = str(df["league"].iloc[0])
        since = season_start(country, now)
        season_df = df[df["date"] >= since]
        if season_df.empty:
            # season not started in the feed yet: fall back to the last 180 days so the page is never empty
            since = pd.Timestamp(now.date()) - pd.Timedelta(days=180)
            season_df = df[df["date"] >= since]
        lg_season = _long(season_df) if not season_df.empty else lg_all.iloc[0:0]
        teams = sorted(set(season_df["home"]) | set(season_df["away"]))
        table = []
        records = {}
        lg_country = lg_all[lg_all["team"].isin(teams)]
        for t in teams:
            s = lg_season[lg_season["team"] == t]
            prev = lg_country[(lg_country["team"] == t) & (lg_country["date"] < since)]
            rec = team_record(lg_country[lg_country["team"] == t], s, t, country, league, div, since,
                              prev=prev if len(prev) else None)
            if squad_lookup is not None:
                try:
                    rec["squad"] = squad_lookup(div, t)
                except Exception:  # noqa: BLE001
                    rec["squad"] = None
            records[t] = rec
            index.append({"n": t, "c": country, "d": div, "l": league})
            a = rec["all"]
            table.append({"team": t, "p": a["p"], "w": a["w"], "d": a["d"], "l": a["l"], "gf": a["gf"], "ga": a["ga"],
                          "gd": a["gf"] - a["ga"], "pts": a["pts"], "form": rec["form"]})
        table.sort(key=lambda r: (-r["pts"], -r["gd"], -r["gf"], r["team"]))
        for i, r in enumerate(table, 1):
            r["pos"] = i
            records[r["team"]]["pos"] = i
            records[r["team"]]["teams_in_league"] = len(table)
        data = {"div": div, "country": country, "league": league, "season_from": since.strftime("%Y-%m-%d"),
                "updated": now.strftime("%Y-%m-%d"), "matches": int(len(season_df)),
                "avg_goals": _mean(season_df["hg"] + season_df["ag"]),
                "o25_rate": _rate(season_df["hg"] + season_df["ag"] >= 3) if len(season_df) else None,
                "btts_rate": _rate((season_df["hg"] > 0) & (season_df["ag"] > 0)) if len(season_df) else None,
                "table": table, "teams": records}
        path = out_dir / f"{slug(div)}.json"
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
        if not path.exists() or path.read_text(encoding="utf-8") != body:
            path.write_text(body, encoding="utf-8")
        written.append(slug(div))
    # global team index for the app's search (club -> its team page), one compact file
    index.sort(key=lambda x: (x["n"].lower(), x["c"].lower(), x["d"]))
    seen: set[tuple] = set()
    uniq = [x for x in index if not ((x["n"], x["d"]) in seen or seen.add((x["n"], x["d"])))]
    idx_body = json.dumps({"generated": now.strftime("%Y-%m-%d"), "count": len(uniq), "teams": uniq},
                          ensure_ascii=False, separators=(",", ":"))
    idx_path = out_dir / "teams-index.json"
    if not idx_path.exists() or idx_path.read_text(encoding="utf-8") != idx_body:
        idx_path.write_text(idx_body, encoding="utf-8")
    return written
