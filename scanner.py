#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Goals Scanner
=============
Daily scanner for football goals markets: Over 1.5, Over 2.5 and Both Teams To Score.

Data source: football-data.co.uk (free, no API key)
  * fixtures.csv / new_league_fixtures.csv -> upcoming matches (+ market odds where published)
  * season result files                    -> team form, goals, xG / shots where available

Outputs (relative to the repo root):
  reports/YYYY-MM-DD.md   full report for the day (shortlists, full scan, per-match stats)
  reports/YYYY-MM-DD.csv  every scanned match with every computed number
  reports/latest.md       copy of the newest report
  data/tracker.csv        running record of shortlisted matches, auto-settled once results arrive
  README.md               the block between <!-- SCAN:START --> and <!-- SCAN:END --> is refreshed

Optional: a Telegram push if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set in the environment.

Everything tunable lives in CONFIG below (most values can also be overridden with env vars).
"""
from __future__ import annotations

import html
import io
import logging
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

# ----------------------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"
DATA_DIR = ROOT / "data"
TRACKER_FILE = DATA_DIR / "tracker.csv"
README_FILE = ROOT / "README.md"

BASE = "https://www.football-data.co.uk"
FIXTURES_URL = f"{BASE}/fixtures.csv"
NEW_FIXTURES_URL = f"{BASE}/new_league_fixtures.csv"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# ----------------------------------------------------------------------------- config
CONFIG = {
    "TIMEZONE": "Europe/London",
    # matches kicking off between "now" and now + WINDOW_HOURS are scanned
    "WINDOW_HOURS": _env_float("WINDOW_HOURS", 24),
    # form weighting: a match HALF_LIFE_DAYS ago counts half as much as one played today
    "HALF_LIFE_DAYS": 120,
    "MAX_HISTORY_DAYS": 400,
    "MAX_MATCHES_PER_TEAM": 40,
    # minimum (time-weighted) matches per team before a match may be shortlisted
    "MIN_EFF_MATCHES": 4.0,
    # Bayesian shrinkage of team strengths towards league average (in matches)
    "SHRINK_K": 4.0,
    # how quickly venue-specific (home/away) form takes over from overall form
    "VENUE_K": 5.0,
    # weight given to bookmaker implied probability (Over 2.5 only) when odds exist
    "MARKET_WEIGHT": 0.4,
    # shortlist rules: final probability >= p AND average historical hit-rate of both teams >= hist
    "THRESHOLDS": {
        "O15": {"p": _env_float("MIN_P_O15", 0.84), "hist": 0.75},
        "O25": {"p": _env_float("MIN_P_O25", 0.60), "hist": 0.50},
        "BTTS": {"p": _env_float("MIN_P_BTTS", 0.62), "hist": 0.50},
    },
    "MAX_PICKS": int(_env_float("MAX_PICKS", 15)),
    "REQUEST_TIMEOUT": 30,
    "USER_AGENT": "Mozilla/5.0 (compatible; GoalsScanner/1.0)",
    # optional: restrict to some competitions, e.g. LEAGUES="E0,SP1,I1,D1,F1,BRA"
    "LEAGUES": [s.strip() for s in os.getenv("LEAGUES", "").split(",") if s.strip()],
}

MARKETS = {
    "O15": "Over 1.5 goals",
    "O25": "Over 2.5 goals",
    "BTTS": "Both teams to score",
}

# football-data.co.uk main divisions: code -> (country, competition)
MAIN_LEAGUES = {
    "E0": ("England", "Premier League"),
    "E1": ("England", "Championship"),
    "E2": ("England", "League One"),
    "E3": ("England", "League Two"),
    "EC": ("England", "National League"),
    "SC0": ("Scotland", "Premiership"),
    "SC1": ("Scotland", "Championship"),
    "SC2": ("Scotland", "League One"),
    "SC3": ("Scotland", "League Two"),
    "D1": ("Germany", "Bundesliga"),
    "D2": ("Germany", "2. Bundesliga"),
    "I1": ("Italy", "Serie A"),
    "I2": ("Italy", "Serie B"),
    "SP1": ("Spain", "La Liga"),
    "SP2": ("Spain", "Segunda División"),
    "F1": ("France", "Ligue 1"),
    "F2": ("France", "Ligue 2"),
    "N1": ("Netherlands", "Eredivisie"),
    "B1": ("Belgium", "Pro League"),
    "P1": ("Portugal", "Primeira Liga"),
    "T1": ("Turkey", "Süper Lig"),
    "G1": ("Greece", "Super League"),
}

# "extra" leagues: country name used in new_league_fixtures.csv -> file code
EXTRA_LEAGUES = {
    "Argentina": "ARG", "Austria": "AUT", "Brazil": "BRA", "China": "CHN",
    "Denmark": "DNK", "Finland": "FIN", "Ireland": "IRL", "Japan": "JPN",
    "Mexico": "MEX", "Norway": "NOR", "Poland": "POL", "Romania": "ROU",
    "Russia": "RUS", "Sweden": "SWE", "Switzerland": "SWZ", "USA": "USA",
}

log = logging.getLogger("scanner")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": CONFIG["USER_AGENT"]})


# ----------------------------------------------------------------------------- helpers
def fetch(url: str) -> bytes | None:
    """Download a file with a few retries. Returns None on 404 or persistent failure."""
    for attempt in range(3):
        try:
            r = SESSION.get(url, timeout=CONFIG["REQUEST_TIMEOUT"])
            if r.status_code == 404:
                return None
            if r.status_code == 200 and len(r.content) > 40:
                return r.content
            log.warning("HTTP %s for %s", r.status_code, url)
        except requests.RequestException as exc:
            log.warning("Request failed (%s): %s", url, exc)
        time.sleep(2 * (attempt + 1))
    return None


def read_csv(content: bytes | None, sep: str = ",") -> pd.DataFrame | None:
    if content is None:
        return None
    for enc in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(content), sep=sep, encoding=enc,
                             on_bad_lines="skip", skip_blank_lines=True)
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception:  # noqa: BLE001
            continue
    return None


def parse_dates(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    d = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")
    miss = d.isna()
    if miss.any():
        d[miss] = pd.to_datetime(s[miss], format="%d/%m/%y", errors="coerce")
    return d


def num(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce")
    return pd.Series(np.nan, index=df.index, dtype="float64")


def wmean(values, weights) -> float:
    v = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float)
    m = ~np.isnan(v)
    if m.sum() == 0 or w[m].sum() <= 0:
        return float("nan")
    return float((v[m] * w[m]).sum() / w[m].sum())


def poisson_cdf(k: int, lam: float) -> float:
    return sum(math.exp(-lam) * lam ** i / math.factorial(i) for i in range(k + 1))


def season_codes(now: datetime) -> list[str]:
    """Current and previous season codes as used by football-data.co.uk, e.g. ['2627', '2526']."""
    y = now.year if now.month >= 7 else now.year - 1
    cur = f"{y % 100:02d}{(y + 1) % 100:02d}"
    prev = f"{(y - 1) % 100:02d}{y % 100:02d}"
    return [cur, prev]


def pct(x) -> str:
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.0f}%"


def f2(x) -> str:
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.2f}"


def stars(p: float, thr: float) -> str:
    if p >= thr + 0.10:
        return "⭐⭐⭐"
    if p >= thr + 0.05:
        return "⭐⭐"
    return "⭐"


# ----------------------------------------------------------------------------- data loading
RESULT_COLS = ["country", "div", "league", "date", "home", "away", "hg", "ag",
               "hxg", "axg", "hst", "ast"]


def empty_results() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="float64" if c in ("hg", "ag", "hxg", "axg", "hst", "ast")
                                      else ("datetime64[ns]" if c == "date" else "object"))
                         for c in RESULT_COLS})


def load_main_results(divs: set[str], seasons: list[str]) -> pd.DataFrame:
    frames = []
    for div in sorted(divs):
        for season in seasons:
            df = read_csv(fetch(f"{BASE}/mmz4281/{season}/{div}.csv"))
            if df is None or not {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"} <= set(df.columns):
                log.info("No data for %s %s", div, season)
                continue
            df = df.dropna(subset=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"])
            if df.empty:
                continue
            country, league = MAIN_LEAGUES[div]
            frames.append(pd.DataFrame({
                "country": country, "div": div, "league": league,
                "date": parse_dates(df["Date"]),
                "home": df["HomeTeam"].astype(str).str.strip(),
                "away": df["AwayTeam"].astype(str).str.strip(),
                "hg": num(df, "FTHG"), "ag": num(df, "FTAG"),
                "hxg": num(df, "HxG"), "axg": num(df, "AxG"),
                "hst": num(df, "HST"), "ast": num(df, "AST"),
            }))
            log.info("Loaded %s %s: %d matches", div, season, len(df))
    return pd.concat(frames, ignore_index=True) if frames else empty_results()


def load_extra_results(codes: set[str], since: datetime) -> pd.DataFrame:
    frames = []
    for code in sorted(codes):
        df = read_csv(fetch(f"{BASE}/new/{code}.csv"))
        if df is None or not {"Date", "Home", "Away", "HG", "AG"} <= set(df.columns):
            log.info("No data for extra league %s", code)
            continue
        df = df.dropna(subset=["Date", "Home", "Away", "HG", "AG"])
        league = df["League"].astype(str).str.strip()
        out = pd.DataFrame({
            "country": df["Country"].astype(str).str.strip(),
            "div": code + ":" + league, "league": league,
            "date": parse_dates(df["Date"]),
            "home": df["Home"].astype(str).str.strip(),
            "away": df["Away"].astype(str).str.strip(),
            "hg": num(df, "HG"), "ag": num(df, "AG"),
            "hxg": np.nan, "axg": np.nan, "hst": np.nan, "ast": np.nan,
        })
        out = out[out["date"] >= since]
        frames.append(out)
        log.info("Loaded %s: %d matches since %s", code, len(out), since.date())
    return pd.concat(frames, ignore_index=True) if frames else empty_results()


def load_fixtures(tz: ZoneInfo) -> pd.DataFrame:
    """All upcoming fixtures from both feeds, normalised to one schema."""
    rows = []

    df = read_csv(fetch(FIXTURES_URL))
    if df is not None and "Div" in df.columns:
        df = df.dropna(subset=["Div", "Date", "HomeTeam", "AwayTeam"])
        df = df[df["Div"].isin(MAIN_LEAGUES)]
        dates = parse_dates(df["Date"])
        for i, r in df.iterrows():
            if pd.isna(dates[i]):
                continue
            country, league = MAIN_LEAGUES[r["Div"]]
            rows.append({
                "source": "main", "code": r["Div"], "country": country, "div": r["Div"],
                "league": league, "date": dates[i], "time": str(r.get("Time", "")).strip(),
                "home": str(r["HomeTeam"]).strip(), "away": str(r["AwayTeam"]).strip(),
                "odds_over": pd.to_numeric(r.get("Avg>2.5"), errors="coerce"),
                "odds_under": pd.to_numeric(r.get("Avg<2.5"), errors="coerce"),
                "b365_over": pd.to_numeric(r.get("B365>2.5"), errors="coerce"),
                "b365_under": pd.to_numeric(r.get("B365<2.5"), errors="coerce"),
                "odds_h": pd.to_numeric(r.get("AvgH"), errors="coerce"),
                "odds_d": pd.to_numeric(r.get("AvgD"), errors="coerce"),
                "odds_a": pd.to_numeric(r.get("AvgA"), errors="coerce"),
            })
    else:
        log.warning("Main fixtures feed unavailable")

    df = read_csv(fetch(NEW_FIXTURES_URL), sep="\t")
    if df is not None and "Country" in df.columns:
        df = df.dropna(subset=["Country", "Date", "Home", "Away"])
        dates = parse_dates(df["Date"])
        for i, r in df.iterrows():
            country = str(r["Country"]).strip()
            code = EXTRA_LEAGUES.get(country)
            if code is None or pd.isna(dates[i]):
                continue
            league = str(r["League"]).strip()
            rows.append({
                "source": "extra", "code": code, "country": country, "div": f"{code}:{league}",
                "league": league, "date": dates[i], "time": str(r.get("Time", "")).strip(),
                "home": str(r["Home"]).strip(), "away": str(r["Away"]).strip(),
                "odds_over": np.nan, "odds_under": np.nan, "b365_over": np.nan, "b365_under": np.nan,
                "odds_h": pd.to_numeric(r.get("AvgH"), errors="coerce"),
                "odds_d": pd.to_numeric(r.get("AvgD"), errors="coerce"),
                "odds_a": pd.to_numeric(r.get("AvgA"), errors="coerce"),
            })
    else:
        log.warning("Extra-league fixtures feed unavailable")

    fx = pd.DataFrame(rows)
    if fx.empty:
        return fx

    def kickoff(r):
        t = r["time"] if r["time"] and r["time"].lower() not in ("nan", "none", "") else "12:00"
        try:
            hh, mm = [int(x) for x in t.split(":")[:2]]
        except ValueError:
            hh, mm = 12, 0
        return datetime(r["date"].year, r["date"].month, r["date"].day, hh, mm, tzinfo=tz)

    fx["kickoff"] = fx.apply(kickoff, axis=1)
    fx["time_known"] = fx["time"].apply(lambda t: bool(t) and t.lower() not in ("nan", "none"))
    if CONFIG["LEAGUES"]:
        fx = fx[fx["code"].isin(CONFIG["LEAGUES"])]
    return fx.sort_values(["kickoff", "country", "league"]).reset_index(drop=True)


# ----------------------------------------------------------------------------- modelling
@dataclass
class DivAvg:
    mu_h: float
    mu_a: float
    n_eff: float
    o25_rate: float
    btts_rate: float


def decay_weights(dates: pd.Series, now: datetime) -> np.ndarray:
    days = (pd.Timestamp(now.date()) - dates).dt.days.clip(lower=0).to_numpy(dtype=float)
    return 0.5 ** (days / CONFIG["HALF_LIFE_DAYS"])


def compute_div_avgs(results: pd.DataFrame, now: datetime) -> dict[str, DivAvg]:
    out: dict[str, DivAvg] = {}
    if results.empty:
        return out
    w_all = decay_weights(results["date"], now)
    prior_h = wmean(results["hg"], w_all) if len(results) else 1.45
    prior_a = wmean(results["ag"], w_all) if len(results) else 1.20
    prior_h = 1.45 if math.isnan(prior_h) else prior_h
    prior_a = 1.20 if math.isnan(prior_a) else prior_a
    K = 30.0
    for div, g in results.groupby("div"):
        w = decay_weights(g["date"], now)
        n = float(w.sum())
        mu_h = wmean(g["hg"], w)
        mu_a = wmean(g["ag"], w)
        mu_h = (n * mu_h + K * prior_h) / (n + K) if not math.isnan(mu_h) else prior_h
        mu_a = (n * mu_a + K * prior_a) / (n + K) if not math.isnan(mu_a) else prior_a
        tot = g["hg"] + g["ag"]
        out[div] = DivAvg(mu_h, mu_a, n,
                          wmean((tot >= 3).astype(float), w),
                          wmean(((g["hg"] > 0) & (g["ag"] > 0)).astype(float), w))
    out["__global__"] = DivAvg(prior_h, prior_a, float(w_all.sum()), float("nan"), float("nan"))
    return out


def make_long(results: pd.DataFrame, div_avgs: dict[str, DivAvg]) -> pd.DataFrame:
    """One row per team per match (perspective table) with league-normalised goals."""
    if results.empty:
        return pd.DataFrame()
    g = div_avgs.get("__global__", DivAvg(1.45, 1.2, 0, float("nan"), float("nan")))
    mu_h = results["div"].map(lambda d: div_avgs.get(d, g).mu_h).astype(float)
    mu_a = results["div"].map(lambda d: div_avgs.get(d, g).mu_a).astype(float)
    common = {"country": results["country"], "date": results["date"], "div": results["div"],
              "league": results["league"]}
    home = pd.DataFrame({**common, "team": results["home"], "opp": results["away"], "venue": "H",
                         "gf": results["hg"], "ga": results["ag"],
                         "gf_norm": results["hg"] / mu_h, "ga_norm": results["ag"] / mu_a,
                         "xg_for": results["hxg"], "xg_against": results["axg"],
                         "sot_for": results["hst"], "sot_against": results["ast"]})
    away = pd.DataFrame({**common, "team": results["away"], "opp": results["home"], "venue": "A",
                         "gf": results["ag"], "ga": results["hg"],
                         "gf_norm": results["ag"] / mu_a, "ga_norm": results["hg"] / mu_h,
                         "xg_for": results["axg"], "xg_against": results["hxg"],
                         "sot_for": results["ast"], "sot_against": results["hst"]})
    long = pd.concat([home, away], ignore_index=True)
    long["total"] = long["gf"] + long["ga"]
    long["o15"] = (long["total"] >= 2).astype(float)
    long["o25"] = (long["total"] >= 3).astype(float)
    long["o35"] = (long["total"] >= 4).astype(float)
    long["btts"] = ((long["gf"] > 0) & (long["ga"] > 0)).astype(float)
    long["cs"] = (long["ga"] == 0).astype(float)
    long["fts"] = (long["gf"] == 0).astype(float)
    return long.sort_values("date", ascending=False).reset_index(drop=True)


@dataclass
class TeamProfile:
    name: str
    n: int = 0
    n_eff: float = 0.0
    venue_n: int = 0
    gf: float = float("nan")
    ga: float = float("nan")
    venue_gf: float = float("nan")
    venue_ga: float = float("nan")
    att: float = 1.0
    dfc: float = 1.0
    rate_o15: float = float("nan")
    rate_o25: float = float("nan")
    rate_o35: float = float("nan")
    rate_btts: float = float("nan")
    rate_cs: float = float("nan")
    rate_fts: float = float("nan")
    last_n: int = 0
    last_o15: int = 0
    last_o25: int = 0
    last_btts: int = 0
    form5_goals: float = float("nan")
    xg_for: float = float("nan")
    xg_against: float = float("nan")
    sot_for: float = float("nan")
    sot_against: float = float("nan")
    last5: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.n_eff >= CONFIG["MIN_EFF_MATCHES"]


def build_profile(long: pd.DataFrame, country: str, team: str, venue: str, now: datetime) -> TeamProfile:
    p = TeamProfile(name=team)
    if long.empty:
        return p
    rows = long[(long["country"] == country) & (long["team"] == team)].head(CONFIG["MAX_MATCHES_PER_TEAM"])
    if rows.empty:
        return p
    w = decay_weights(rows["date"], now)
    p.n = len(rows)
    p.n_eff = float(w.sum())
    p.gf, p.ga = wmean(rows["gf"], w), wmean(rows["ga"], w)
    att_all, def_all = wmean(rows["gf_norm"], w), wmean(rows["ga_norm"], w)

    vmask = (rows["venue"] == venue).to_numpy()
    p.venue_n = int(vmask.sum())
    if p.venue_n:
        wv = w[vmask]
        p.venue_gf = wmean(rows["gf"][vmask], wv)
        p.venue_ga = wmean(rows["ga"][vmask], wv)
        share = wv.sum() / (wv.sum() + CONFIG["VENUE_K"])
        att = share * wmean(rows["gf_norm"][vmask], wv) + (1 - share) * att_all
        dfc = share * wmean(rows["ga_norm"][vmask], wv) + (1 - share) * def_all
    else:
        att, dfc = att_all, def_all

    K = CONFIG["SHRINK_K"]
    p.att = (p.n_eff * att + K * 1.0) / (p.n_eff + K)
    p.dfc = (p.n_eff * dfc + K * 1.0) / (p.n_eff + K)

    p.rate_o15 = wmean(rows["o15"], w)
    p.rate_o25 = wmean(rows["o25"], w)
    p.rate_o35 = wmean(rows["o35"], w)
    p.rate_btts = wmean(rows["btts"], w)
    p.rate_cs = wmean(rows["cs"], w)
    p.rate_fts = wmean(rows["fts"], w)

    last10 = rows.head(10)
    p.last_n = len(last10)
    p.last_o15 = int(last10["o15"].sum())
    p.last_o25 = int(last10["o25"].sum())
    p.last_btts = int(last10["btts"].sum())
    p.form5_goals = float(rows.head(5)["total"].mean())
    p.xg_for = float(last10["xg_for"].mean()) if last10["xg_for"].notna().any() else float("nan")
    p.xg_against = float(last10["xg_against"].mean()) if last10["xg_against"].notna().any() else float("nan")
    p.sot_for = float(last10["sot_for"].mean()) if last10["sot_for"].notna().any() else float("nan")
    p.sot_against = float(last10["sot_against"].mean()) if last10["sot_against"].notna().any() else float("nan")
    p.last5 = [{"date": r.date, "venue": r.venue, "opp": r.opp, "gf": int(r.gf), "ga": int(r.ga),
                "league": r.league} for r in rows.head(5).itertuples()]
    return p


def head_to_head(results: pd.DataFrame, country: str, home: str, away: str, limit: int = 6) -> list[dict]:
    if results.empty:
        return []
    m = results[(results["country"] == country) &
                (((results["home"] == home) & (results["away"] == away)) |
                 ((results["home"] == away) & (results["away"] == home)))]
    m = m.sort_values("date", ascending=False).head(limit)
    return [{"date": r.date, "home": r.home, "away": r.away, "hg": int(r.hg), "ag": int(r.ag),
             "league": r.league} for r in m.itertuples()]


@dataclass
class MatchRow:
    fx: pd.Series
    home: TeamProfile
    away: TeamProfile
    lam_h: float
    lam_a: float
    p: dict          # market -> model probability
    p_market_o25: float
    p_final: dict    # market -> blended probability used for ranking
    hist: dict       # market -> average historical hit-rate of both teams
    h2h: list
    div_avg: DivAvg

    @property
    def data_ok(self) -> bool:
        return self.home.ok and self.away.ok

    @property
    def label(self) -> str:
        return f"{self.fx['home']} v {self.fx['away']}"


def analyse(fx: pd.Series, long: pd.DataFrame, results: pd.DataFrame,
            div_avgs: dict[str, DivAvg], now: datetime) -> MatchRow:
    g = div_avgs.get("__global__", DivAvg(1.45, 1.2, 0, float("nan"), float("nan")))
    da = div_avgs.get(fx["div"], g)
    H = build_profile(long, fx["country"], fx["home"], "H", now)
    A = build_profile(long, fx["country"], fx["away"], "A", now)

    lam_h = min(max(da.mu_h * H.att * A.dfc, 0.15), 4.5)
    lam_a = min(max(da.mu_a * A.att * H.dfc, 0.15), 4.5)
    lt = lam_h + lam_a
    p = {
        "O15": 1 - poisson_cdf(1, lt),
        "O25": 1 - poisson_cdf(2, lt),
        "O35": 1 - poisson_cdf(3, lt),
        "BTTS": (1 - math.exp(-lam_h)) * (1 - math.exp(-lam_a)),
    }

    oo, ou = fx["odds_over"], fx["odds_under"]
    if pd.notna(oo) and pd.notna(ou) and oo > 1 and ou > 1:
        p_mkt = (1 / oo) / (1 / oo + 1 / ou)
    else:
        p_mkt = float("nan")

    mw = CONFIG["MARKET_WEIGHT"]
    p_final = {
        "O15": p["O15"],
        "O25": (1 - mw) * p["O25"] + mw * p_mkt if not math.isnan(p_mkt) else p["O25"],
        "BTTS": p["BTTS"],
    }
    hist = {
        "O15": float(np.nanmean([H.rate_o15, A.rate_o15])) if H.n and A.n else float("nan"),
        "O25": float(np.nanmean([H.rate_o25, A.rate_o25])) if H.n and A.n else float("nan"),
        "BTTS": float(np.nanmean([H.rate_btts, A.rate_btts])) if H.n and A.n else float("nan"),
    }
    return MatchRow(fx, H, A, lam_h, lam_a, p, p_mkt, p_final, hist,
                    head_to_head(results, fx["country"], fx["home"], fx["away"]), da)


def select_picks(rows: list[MatchRow]) -> dict[str, list[MatchRow]]:
    picks: dict[str, list[MatchRow]] = {}
    for mkt, thr in CONFIG["THRESHOLDS"].items():
        attr = {"O15": "rate_o15", "O25": "rate_o25", "BTTS": "rate_btts"}[mkt]
        cand = [r for r in rows if r.data_ok and r.p_final[mkt] >= thr["p"]
                and not math.isnan(r.hist[mkt]) and r.hist[mkt] >= thr["hist"]
                # neither team may be far below the floor on its own
                and min(getattr(r.home, attr), getattr(r.away, attr)) >= thr["hist"] - 0.10]
        cand.sort(key=lambda r: r.p_final[mkt], reverse=True)
        picks[mkt] = cand[: CONFIG["MAX_PICKS"]]
    return picks


# ----------------------------------------------------------------------------- tracker
TRACKER_COLS = ["match_date", "kickoff", "country", "div", "league", "home", "away", "market",
                "p_model", "p_market", "p_final", "odds", "status", "score", "total_goals",
                "settled_on", "report_date"]


def load_tracker() -> pd.DataFrame:
    if TRACKER_FILE.exists():
        t = pd.read_csv(TRACKER_FILE, dtype=str, keep_default_na=False)
        for c in TRACKER_COLS:
            if c not in t.columns:
                t[c] = ""
        return t[TRACKER_COLS]
    return pd.DataFrame(columns=TRACKER_COLS)


def settle_tracker(t: pd.DataFrame, results: pd.DataFrame, today: datetime) -> pd.DataFrame:
    if t.empty:
        return t
    t = t.copy()
    for i, r in t[t["status"] == "pending"].iterrows():
        mdate = pd.Timestamp(r["match_date"])
        if not results.empty:
            m = results[(results["home"] == r["home"]) & (results["away"] == r["away"]) &
                        (results["country"] == r["country"]) &
                        ((results["date"] - mdate).abs() <= pd.Timedelta(days=3))]
            if not m.empty:
                row = m.iloc[0]
                hg, ag = int(row["hg"]), int(row["ag"])
                total = hg + ag
                hit = {"O15": total >= 2, "O25": total >= 3, "BTTS": hg > 0 and ag > 0}[r["market"]]
                t.loc[i, ["status", "score", "total_goals", "settled_on"]] = [
                    "hit" if hit else "miss", f"{hg}-{ag}", str(total), today.strftime("%Y-%m-%d")]
                continue
        if (pd.Timestamp(today.date()) - mdate).days > 21:
            t.loc[i, ["status", "settled_on"]] = ["void", today.strftime("%Y-%m-%d")]
    return t


def add_picks(t: pd.DataFrame, picks: dict[str, list[MatchRow]], today: datetime) -> pd.DataFrame:
    existing = set(zip(t["match_date"], t["home"], t["away"], t["market"]))
    new = []
    for mkt, rows in picks.items():
        for r in rows:
            key = (r.fx["kickoff"].strftime("%Y-%m-%d"), r.fx["home"], r.fx["away"], mkt)
            if key in existing:
                continue
            existing.add(key)
            odds = r.fx["odds_over"] if mkt == "O25" else float("nan")
            new.append({
                "match_date": key[0], "kickoff": r.fx["kickoff"].strftime("%Y-%m-%d %H:%M"),
                "country": r.fx["country"], "div": r.fx["div"], "league": r.fx["league"],
                "home": r.fx["home"], "away": r.fx["away"], "market": mkt,
                "p_model": f"{r.p[mkt]:.3f}",
                "p_market": "" if math.isnan(r.p_market_o25) or mkt != "O25" else f"{r.p_market_o25:.3f}",
                "p_final": f"{r.p_final[mkt]:.3f}",
                "odds": "" if pd.isna(odds) else f"{odds:.2f}",
                "status": "pending", "score": "", "total_goals": "", "settled_on": "",
                "report_date": today.strftime("%Y-%m-%d"),
            })
    if new:
        t = pd.concat([t, pd.DataFrame(new, columns=TRACKER_COLS)], ignore_index=True)
    return t


def tracker_summary(t: pd.DataFrame, today: datetime) -> dict:
    out = {}
    if t.empty:
        return out
    recent_cut = (today - timedelta(days=30)).strftime("%Y-%m-%d")
    for mkt in MARKETS:
        s = t[t["market"] == mkt]
        settled = s[s["status"].isin(["hit", "miss"])]
        hits = int((settled["status"] == "hit").sum())
        rec = settled[settled["match_date"] >= recent_cut]
        rec_hits = int((rec["status"] == "hit").sum())
        info = {"settled": len(settled), "hits": hits,
                "rate": hits / len(settled) if len(settled) else float("nan"),
                "recent_settled": len(rec), "recent_hits": rec_hits,
                "recent_rate": rec_hits / len(rec) if len(rec) else float("nan"),
                "pending": int((s["status"] == "pending").sum()),
                "avg_odds": float("nan"), "roi": float("nan")}
        if mkt == "O25":
            with_odds = settled[settled["odds"] != ""]
            if len(with_odds):
                odds = pd.to_numeric(with_odds["odds"], errors="coerce")
                won = (with_odds["status"] == "hit").astype(float)
                info["avg_odds"] = float(odds.mean())
                info["roi"] = float(((odds * won).sum() - len(with_odds)) / len(with_odds))
        out[mkt] = info
    return out


# ----------------------------------------------------------------------------- rendering
def ko(r: MatchRow) -> str:
    k = r.fx["kickoff"]
    return k.strftime("%a %d %b %H:%M") if r.fx["time_known"] else k.strftime("%a %d %b (time TBC)")


def comp(r: MatchRow) -> str:
    return f"{r.fx['country']} · {r.fx['league']}"


def form_str(r: MatchRow, mkt: str) -> str:
    H, A = r.home, r.away
    attr = {"O15": "last_o15", "O25": "last_o25", "BTTS": "last_btts"}[mkt]
    return f"H {getattr(H, attr)}/{H.last_n} · A {getattr(A, attr)}/{A.last_n}"


def market_str(r: MatchRow) -> str:
    if math.isnan(r.p_market_o25):
        return "–"
    return f"{r.fx['odds_over']:.2f} ({pct(r.p_market_o25)})"


def render_pick_table(rows: list[MatchRow], mkt: str) -> list[str]:
    thr = CONFIG["THRESHOLDS"][mkt]["p"]
    L = []
    if not rows:
        L.append("_No match met the criteria today._")
        return L
    if mkt == "O25":
        L.append("| # | Kick-off (UK) | Competition | Match | Model | Market (odds) | Final | Rating | Last-10 form | Model xG |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for i, r in enumerate(rows, 1):
            L.append(f"| {i} | {ko(r)} | {comp(r)} | **{r.label}** | {pct(r.p['O25'])} | {market_str(r)} | "
                     f"**{pct(r.p_final['O25'])}** | {stars(r.p_final['O25'], thr)} | {form_str(r, mkt)} | "
                     f"{r.lam_h:.1f} – {r.lam_a:.1f} |")
    else:
        L.append("| # | Kick-off (UK) | Competition | Match | Model | Rating | Last-10 form | Model xG |")
        L.append("|---|---|---|---|---|---|---|---|")
        for i, r in enumerate(rows, 1):
            L.append(f"| {i} | {ko(r)} | {comp(r)} | **{r.label}** | **{pct(r.p_final[mkt])}** | "
                     f"{stars(r.p_final[mkt], thr)} | {form_str(r, mkt)} | {r.lam_h:.1f} – {r.lam_a:.1f} |")
    return L


def render_tracker(summary: dict) -> list[str]:
    L = ["| Market | Settled | Hits | Hit rate | Last 30 days | Pending | Avg odds | Flat-stake return |",
         "|---|---|---|---|---|---|---|---|"]
    if not summary:
        L.append("| – | 0 | 0 | – | – | 0 | – | – |")
        return L
    for mkt, name in MARKETS.items():
        s = summary.get(mkt)
        if not s:
            continue
        recent = f"{s['recent_hits']}/{s['recent_settled']} ({pct(s['recent_rate'])})" if s["recent_settled"] else "–"
        roi = "–" if math.isnan(s["roi"]) else f"{100 * s['roi']:+.1f}%"
        L.append(f"| {name} | {s['settled']} | {s['hits']} | {pct(s['rate'])} | {recent} | {s['pending']} | "
                 f"{f2(s['avg_odds'])} | {roi} |")
    return L


def render_team_block(p: TeamProfile, venue_label: str) -> list[str]:
    L = [f"**{p.name}** ({venue_label}) — {p.n} matches used (weighted {p.n_eff:.1f}), {p.venue_n} {venue_label.lower()}",
         "", "| Stat | Value |", "|---|---|",
         f"| Goals for / against per game | {f2(p.gf)} / {f2(p.ga)} |",
         f"| {venue_label} goals for / against | {f2(p.venue_gf)} / {f2(p.venue_ga)} |",
         f"| Attack / defence strength (1.00 = league avg) | {f2(p.att)} / {f2(p.dfc)} |",
         f"| Over 1.5 / 2.5 / 3.5 rate | {pct(p.rate_o15)} / {pct(p.rate_o25)} / {pct(p.rate_o35)} |",
         f"| BTTS rate | {pct(p.rate_btts)} |",
         f"| Clean sheets / failed to score | {pct(p.rate_cs)} / {pct(p.rate_fts)} |",
         f"| Avg total goals, last 5 | {f2(p.form5_goals)} |"]
    if not math.isnan(p.xg_for):
        L.append(f"| xG for / against (last 10) | {f2(p.xg_for)} / {f2(p.xg_against)} |")
    if not math.isnan(p.sot_for):
        L.append(f"| Shots on target for / against (last 10) | {p.sot_for:.1f} / {p.sot_against:.1f} |")
    if p.last5:
        parts = []
        for m in p.last5:
            res = "W" if m["gf"] > m["ga"] else ("L" if m["gf"] < m["ga"] else "D")
            parts.append(f"{res} {m['gf']}-{m['ga']} {'v' if m['venue'] == 'H' else '@'} {m['opp']}")
        L.append(f"| Last 5 | {' · '.join(parts)} |")
    L.append("")
    return L


def render_details(r: MatchRow) -> list[str]:
    L = [f"<details><summary><b>{html.escape(r.label)}</b> — {html.escape(comp(r))}, {ko(r)} · "
         f"O2.5 {pct(r.p_final['O25'])} · BTTS {pct(r.p_final['BTTS'])}"
         f"{'' if r.data_ok else ' · ⚠️ low data'}</summary>", ""]
    L.append(f"* Model expected goals: **{r.lam_h:.2f} – {r.lam_a:.2f}** (total {r.lam_h + r.lam_a:.2f}) · "
             f"P(O1.5) {pct(r.p['O15'])} · P(O2.5) {pct(r.p['O25'])} · P(O3.5) {pct(r.p['O35'])} · "
             f"P(BTTS) {pct(r.p['BTTS'])}")
    if not math.isnan(r.p_market_o25):
        L.append(f"* Market: Over 2.5 @ {r.fx['odds_over']:.2f} / Under 2.5 @ {r.fx['odds_under']:.2f} "
                 f"(implied O2.5 {pct(r.p_market_o25)}) · 1X2 {f2(r.fx['odds_h'])} / {f2(r.fx['odds_d'])} / {f2(r.fx['odds_a'])}")
    elif pd.notna(r.fx["odds_h"]):
        L.append(f"* Market 1X2: {f2(r.fx['odds_h'])} / {f2(r.fx['odds_d'])} / {f2(r.fx['odds_a'])} (no O/U odds published in feed)")
    L.append(f"* League context: avg {r.div_avg.mu_h:.2f} home + {r.div_avg.mu_a:.2f} away goals · "
             f"O2.5 in {pct(r.div_avg.o25_rate)} · BTTS in {pct(r.div_avg.btts_rate)} of matches")
    L.append("")
    L += render_team_block(r.home, "Home")
    L += render_team_block(r.away, "Away")
    if r.h2h:
        parts = [f"{m['date']:%d %b %y}: {m['home']} {m['hg']}-{m['ag']} {m['away']}" for m in r.h2h]
        tot = [m["hg"] + m["ag"] for m in r.h2h]
        L.append(f"**Head-to-head** (last {len(r.h2h)}): avg {np.mean(tot):.1f} goals, "
                 f"O2.5 in {sum(t >= 3 for t in tot)}/{len(tot)}, "
                 f"BTTS in {sum(m['hg'] > 0 and m['ag'] > 0 for m in r.h2h)}/{len(tot)}  ")
        L.append("; ".join(parts))
    else:
        L.append("_No head-to-head data in the last two seasons._")
    L += ["", "</details>", ""]
    return L


def render_report(ctx: dict, rows: list[MatchRow], picks: dict, summary: dict, notes: list[str]) -> str:
    now = ctx["now"]
    L = [f"# ⚽ Goals Scanner — {now:%A %d %B %Y}", ""]
    comps = {comp(r) for r in rows}
    L.append(f"**Scan window:** {ctx['start']:%a %d %b %H:%M} → {ctx['end']:%a %d %b %H:%M} (UK time) · "
             f"**{len(rows)} fixtures** across **{len(comps)} competitions** · generated {now:%H:%M} UK")
    L.append("")
    if notes:
        L.append("> " + "  \n> ".join(notes))
        L.append("")

    L.append("## 🎯 Shortlist")
    L.append("")
    for mkt, name in MARKETS.items():
        thr = CONFIG["THRESHOLDS"][mkt]
        L.append(f"### {name} — {len(picks.get(mkt, []))} pick(s)")
        L.append(f"_Criteria: final probability ≥ {pct(thr['p'])} and both teams' average {name} hit-rate ≥ {pct(thr['hist'])}._")
        L.append("")
        L += render_pick_table(picks.get(mkt, []), mkt)
        L.append("")

    L.append("## 📊 Full scan — every fixture, ranked by Over 2.5 probability")
    L.append("")
    if rows:
        L.append("| Kick-off (UK) | Competition | Match | Model xG | O1.5 | O2.5 | BTTS | Market O2.5 | O2.5 final | O2.5 last-10 form | Data |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in sorted(rows, key=lambda r: r.p_final["O25"], reverse=True):
            flag = "✅" if r.data_ok else f"⚠️ {r.home.n}/{r.away.n} games"
            L.append(f"| {ko(r)} | {comp(r)} | {r.label} | {r.lam_h:.1f} – {r.lam_a:.1f} | {pct(r.p['O15'])} | "
                     f"{pct(r.p['O25'])} | {pct(r.p['BTTS'])} | {market_str(r)} | **{pct(r.p_final['O25'])}** | "
                     f"{form_str(r, 'O25')} | {flag} |")
    else:
        L.append("_No fixtures found in the scan window._")
    L.append("")

    if rows:
        L.append("## 🔍 Match details (click to expand)")
        L.append("")
        for r in sorted(rows, key=lambda r: (r.fx["kickoff"], comp(r))):
            L += render_details(r)

    L.append("## 📈 Shortlist tracker (auto-settled from results)")
    L.append("")
    L += render_tracker(summary)
    L.append("")
    L.append("_Flat-stake return is for model evaluation only: 1 unit on every Over 2.5 pick at the average market odds._")
    L.append("")

    L.append("## ℹ️ Method")
    L.append("")
    L += [
        "* Team attack/defence strengths come from goals scored and conceded in the last two seasons, "
        f"normalised by league averages, time-weighted (half-life {CONFIG['HALF_LIFE_DAYS']} days), "
        "blended with home/away-specific form and shrunk towards league average for small samples.",
        "* Expected goals for each side = league average × attack strength × opponent defence strength; "
        "probabilities come from a Poisson model on those expected goals.",
        f"* For Over 2.5 the model probability is blended with the bookmaker-implied probability "
        f"({int(CONFIG['MARKET_WEIGHT'] * 100)}% market weight) whenever odds are published in the feed.",
        "* Data: football-data.co.uk. Kick-off times are UK time. ⚠️ marks teams with too little history "
        "(typically newly promoted from a division not covered) — they are never shortlisted.",
        "* This is statistical information, not advice. Past hit-rates do not guarantee future results.",
    ]
    L.append("")
    return "\n".join(L)


def render_readme_block(ctx: dict, rows: list[MatchRow], picks: dict, summary: dict, report_rel: str) -> str:
    now = ctx["now"]
    L = [f"### Latest scan — {now:%A %d %B %Y} ({now:%H:%M} UK)", "",
         f"{len(rows)} fixtures scanned · window {ctx['start']:%a %H:%M} → {ctx['end']:%a %H:%M} UK · "
         f"[open full report]({report_rel})", ""]
    for mkt, name in MARKETS.items():
        sel = picks.get(mkt, [])
        L.append(f"**{name}** — {len(sel)} pick(s)")
        L.append("")
        if sel:
            L.append("| Kick-off | Match | Competition | Final prob. | Rating |")
            L.append("|---|---|---|---|---|")
            for r in sel[:8]:
                L.append(f"| {ko(r)} | **{r.label}** | {comp(r)} | {pct(r.p_final[mkt])} | "
                         f"{stars(r.p_final[mkt], CONFIG['THRESHOLDS'][mkt]['p'])} |")
            if len(sel) > 8:
                L.append(f"| … | _{len(sel) - 8} more in the full report_ | | | |")
        else:
            L.append("_None met the criteria._")
        L.append("")
    L.append("**Tracker**")
    L.append("")
    L += render_tracker(summary)
    L.append("")
    return "\n".join(L)


def update_readme(block: str) -> None:
    start, end = "<!-- SCAN:START -->", "<!-- SCAN:END -->"
    text = README_FILE.read_text(encoding="utf-8") if README_FILE.exists() else f"# Goals Scanner\n\n{start}\n{end}\n"
    if start in text and end in text:
        pre, rest = text.split(start, 1)
        _, post = rest.split(end, 1)
        text = f"{pre}{start}\n{block}\n{end}{post}"
    else:
        text = f"{text.rstrip()}\n\n{start}\n{block}\n{end}\n"
    README_FILE.write_text(text, encoding="utf-8")


def rows_to_csv(rows: list[MatchRow], path: Path) -> None:
    recs = []
    for r in rows:
        fx = r.fx
        recs.append({
            "kickoff_uk": fx["kickoff"].strftime("%Y-%m-%d %H:%M"), "country": fx["country"],
            "competition": fx["league"], "div": fx["div"], "home": fx["home"], "away": fx["away"],
            "xg_home_model": round(r.lam_h, 3), "xg_away_model": round(r.lam_a, 3),
            "p_over15": round(r.p["O15"], 3), "p_over25": round(r.p["O25"], 3),
            "p_over35": round(r.p["O35"], 3), "p_btts": round(r.p["BTTS"], 3),
            "odds_over25_avg": fx["odds_over"], "odds_under25_avg": fx["odds_under"],
            "odds_over25_b365": fx["b365_over"], "odds_under25_b365": fx["b365_under"],
            "p_market_over25": None if math.isnan(r.p_market_o25) else round(r.p_market_o25, 3),
            "p_final_over15": round(r.p_final["O15"], 3), "p_final_over25": round(r.p_final["O25"], 3),
            "p_final_btts": round(r.p_final["BTTS"], 3),
            "odds_home": fx["odds_h"], "odds_draw": fx["odds_d"], "odds_away": fx["odds_a"],
            "home_matches": r.home.n, "home_gf": r.home.gf, "home_ga": r.home.ga,
            "home_att": r.home.att, "home_def": r.home.dfc, "home_o15_rate": r.home.rate_o15,
            "home_o25_rate": r.home.rate_o25, "home_btts_rate": r.home.rate_btts,
            "home_cs_rate": r.home.rate_cs, "home_fts_rate": r.home.rate_fts,
            "home_last10_o25": f"{r.home.last_o25}/{r.home.last_n}",
            "home_xg_for": r.home.xg_for, "home_xg_against": r.home.xg_against,
            "away_matches": r.away.n, "away_gf": r.away.gf, "away_ga": r.away.ga,
            "away_att": r.away.att, "away_def": r.away.dfc, "away_o15_rate": r.away.rate_o15,
            "away_o25_rate": r.away.rate_o25, "away_btts_rate": r.away.rate_btts,
            "away_cs_rate": r.away.rate_cs, "away_fts_rate": r.away.rate_fts,
            "away_last10_o25": f"{r.away.last_o25}/{r.away.last_n}",
            "away_xg_for": r.away.xg_for, "away_xg_against": r.away.xg_against,
            "league_avg_home_goals": r.div_avg.mu_h, "league_avg_away_goals": r.div_avg.mu_a,
            "league_o25_rate": r.div_avg.o25_rate, "h2h_matches": len(r.h2h),
            "h2h_avg_goals": np.mean([m["hg"] + m["ag"] for m in r.h2h]) if r.h2h else None,
            "data_ok": r.data_ok,
        })
    pd.DataFrame(recs).round(3).to_csv(path, index=False)


def telegram_text(ctx: dict, rows: list[MatchRow], picks: dict, report_url: str | None) -> str:
    now = ctx["now"]
    L = [f"⚽ <b>Goals Scanner — {now:%a %d %b}</b>", f"{len(rows)} fixtures scanned"]
    for mkt, name in MARKETS.items():
        sel = picks.get(mkt, [])
        L.append("")
        L.append(f"<b>{name}</b> ({len(sel)})")
        if not sel:
            L.append("none today")
        for r in sel[:8]:
            L.append(f"• {r.fx['kickoff']:%H:%M} {html.escape(r.label)} — {html.escape(r.fx['league'])} — "
                     f"<b>{pct(r.p_final[mkt])}</b>")
        if len(sel) > 8:
            L.append(f"… +{len(sel) - 8} more")
    if report_url:
        L += ["", f'<a href="{report_url}">Full report</a>']
    return "\n".join(L)


def send_telegram(text: str) -> None:
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        log.info("Telegram not configured – skipping push")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > 3800:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    chunks.append(cur)
    for c in chunks:
        try:
            r = SESSION.post(url, json={"chat_id": chat, "text": c, "parse_mode": "HTML",
                                        "disable_web_page_preview": True}, timeout=20)
            if r.status_code != 200:
                log.warning("Telegram error %s: %s", r.status_code, r.text[:200])
        except requests.RequestException as exc:
            log.warning("Telegram failed: %s", exc)


# ----------------------------------------------------------------------------- main
def main() -> None:
    tz = ZoneInfo(CONFIG["TIMEZONE"])
    override = os.getenv("SCAN_NOW")  # e.g. "2026-09-26 07:00" for testing
    now = datetime.strptime(override, "%Y-%m-%d %H:%M").replace(tzinfo=tz) if override else datetime.now(tz)
    start = now - timedelta(minutes=5)
    end = now + timedelta(hours=CONFIG["WINDOW_HOURS"])
    ctx = {"now": now, "start": start, "end": end}
    log.info("Scan window %s -> %s", start, end)

    REPORTS_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)

    fixtures = load_fixtures(tz)
    todays = fixtures[(fixtures["kickoff"] >= start) & (fixtures["kickoff"] <= end)] if not fixtures.empty else fixtures
    log.info("%d upcoming fixtures in feed, %d inside the window", len(fixtures), len(todays))

    tracker = load_tracker()
    pending = tracker[tracker["status"] == "pending"] if not tracker.empty else tracker

    # which history files do we need? whole country systems, so promoted/relegated teams keep their history
    countries = set(todays["country"]) if not todays.empty else set()
    countries |= set(pending["country"]) if not pending.empty else set()
    main_divs = {d for d, (c, _) in MAIN_LEAGUES.items() if c in countries}
    extra_codes = {code for c, code in EXTRA_LEAGUES.items() if c in countries}

    seasons = season_codes(now)
    since = datetime(now.year, now.month, now.day) - timedelta(days=CONFIG["MAX_HISTORY_DAYS"])
    results = pd.concat([load_main_results(main_divs, seasons), load_extra_results(extra_codes, since)],
                        ignore_index=True)
    results = results.dropna(subset=["date", "hg", "ag"])
    results = results[results["date"] >= since].sort_values("date", ascending=False).reset_index(drop=True)
    log.info("History pool: %d matches", len(results))

    div_avgs = compute_div_avgs(results, now)
    long = make_long(results, div_avgs)

    rows = [analyse(fx, long, results, div_avgs, now) for _, fx in todays.iterrows()]
    picks = select_picks(rows)

    notes = []
    missing = sorted({comp(r) for r in rows if r.fx["div"] not in div_avgs})
    if missing:
        notes.append("No results history found yet for: " + ", ".join(missing) + " (season may not have started in the feed).")
    lowdata = sum(1 for r in rows if not r.data_ok)
    if lowdata:
        notes.append(f"{lowdata} fixture(s) flagged ⚠️ low data and excluded from shortlists.")

    today_str = now.strftime("%Y-%m-%d")
    tracker = settle_tracker(tracker, results, now)
    tracker = add_picks(tracker, picks, now)
    tracker.to_csv(TRACKER_FILE, index=False)
    summary = tracker_summary(tracker, now)

    report_md = render_report(ctx, rows, picks, summary, notes)
    (REPORTS_DIR / f"{today_str}.md").write_text(report_md, encoding="utf-8")
    (REPORTS_DIR / "latest.md").write_text(report_md, encoding="utf-8")
    rows_to_csv(rows, REPORTS_DIR / f"{today_str}.csv")
    update_readme(render_readme_block(ctx, rows, picks, summary, f"reports/{today_str}.md"))

    repo = os.getenv("GITHUB_REPOSITORY")
    server = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    branch = os.getenv("GITHUB_REF_NAME", "main")
    report_url = f"{server}/{repo}/blob/{branch}/reports/{today_str}.md" if repo else None
    send_telegram(telegram_text(ctx, rows, picks, report_url))

    for mkt, name in MARKETS.items():
        log.info("%s: %d pick(s)", name, len(picks[mkt]))
    log.info("Done. Report: %s", REPORTS_DIR / f"{today_str}.md")


if __name__ == "__main__":
    main()
