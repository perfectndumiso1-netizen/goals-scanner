#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PlayReport scanner (v4)
==================
Automated football scanner, three times a day (07:00 / 12:00 / 17:00 SAST):
  * goals shortlists  – Over 1.5, Over 2.5, Both Teams To Score (backtested, calibrated model v2)
  * extra markets     – 1X2 / double chance, team goals, corners and cards (markets.py, backtested)
  * Sportybet prices  – real prices for the user's bookmaker (sporty.py), value check vs fair price
  * parlays           – 3 per run inside the 2.70-3.50 odds band, built from priced legs only (parlays.py),
                        recorded in data/parlays.csv and auto-graded
  * delivery          – Markdown + CSV in the repo, PDF report + PDF parlay dossier on Telegram

Data source: football-data.co.uk (free, no API key)
  * fixtures.csv / new_league_fixtures.csv -> upcoming matches (+ market odds where published)
  * season result files                    -> team form, goals, xG / shots where available

Outputs (relative to the repo root):
  reports/YYYY-MM-DD.md          full report (latest run of the day; earlier runs are overwritten)
  reports/YYYY-MM-DD-parlays.md  parlay dossier: full stats + headlines for every parlay match
  reports/YYYY-MM-DD.csv         every scanned match with every computed number
  reports/latest.md              copy of the newest report
  reports/pdf/                   PDF versions (not committed; sent to Telegram)
  data/tracker.csv               shortlist picks, auto-settled once results arrive
  data/parlays.csv               parlay ledger, auto-graded
  README.md                      the block between <!-- SCAN:START --> and <!-- SCAN:END --> is refreshed

Optional: a Telegram push if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set in the environment.

Everything tunable lives in CONFIG below (most values can also be overridden with env vars).
"""
from __future__ import annotations

import html
import io
import json
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

import markets
import news as news_mod
import parlays as parlay_mod
import sporty
import livescore
import trends as trends_mod
import worldfeed
import appdata
import safe as safe_mod
import history as history_mod
import teamstats

try:
    import pdfgen
except Exception:  # noqa: BLE001 - reportlab missing: Markdown/Telegram text still work
    pdfgen = None

# ----------------------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parent
# machine-written state (ledgers, archives, app data, reports) lives in STATE_DIR — on GitHub that is the `data`
# branch checkout, so the code branch's history never grows with the half-hourly runs
STATE = Path(os.getenv("STATE_DIR") or ROOT).resolve()
REPORTS_DIR = STATE / "reports"
DATA_DIR = STATE / "data"
FX_DIR = DATA_DIR / "app" / "fx"
LS_DIR = DATA_DIR / "ls"
CACHE_DIR = DATA_DIR / "cache"
TRACKER_FILE = DATA_DIR / "tracker.csv"
PARLAY_FILE = DATA_DIR / "parlays.csv"
APP_FILE = DATA_DIR / "app" / "latest.json"
DAYS_DIR = DATA_DIR / "app" / "days"
TEAMS_DIR = DATA_DIR / "app" / "teams"
SAFE_BETS_FILE = DATA_DIR / "safe_bets.csv"
SAFE_ACCAS_FILE = DATA_DIR / "safe_accas.csv"
PDF_DIR = REPORTS_DIR / "pdf"
README_FILE = ROOT / "README.md"

BASE = "https://www.football-data.co.uk"
FIXTURES_URL = f"{BASE}/fixtures.csv"
FEED_TZ = ZoneInfo("Europe/London")  # football-data.co.uk publishes kick-off times in UK time
NEW_FIXTURES_URL = f"{BASE}/new_league_fixtures.csv"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# ----------------------------------------------------------------------------- config
CONFIG = {
    # timezone used for the scan window, all displayed times and report dates
    "TIMEZONE": os.getenv("TIMEZONE", "Africa/Johannesburg"),
    "TZ_LABEL": os.getenv("TZ_LABEL", "SAST"),
    # matches kicking off between "now" and now + WINDOW_HOURS are scanned
    "WINDOW_HOURS": _env_float("WINDOW_HOURS", 24),
    # form weighting: a match HALF_LIFE_DAYS ago counts half as much as one played today
    "HALF_LIFE_DAYS": 120,
    "MAX_HISTORY_DAYS": 400,
    "MAX_MATCHES_PER_TEAM": 40,
    # minimum (time-weighted) matches per team before a match may be shortlisted
    "MIN_EFF_MATCHES": 4.0,
    # Bayesian shrinkage of team strengths towards league average (in matches).
    # Backtested 2023-26: K=40 is far better calibrated than small values (goal form is noisy).
    "SHRINK_K": 40.0,
    # how quickly venue-specific (home/away) form takes over from overall form (backtest: matters little)
    "VENUE_K": 20.0,
    # Dixon-Coles low-score correction (fitted on 2023-25 scores)
    "DC_RHO": -0.05,
    # weight of market-implied expected goals when odds exist. Backtest: the market beats the model
    # at every weight below ~0.9, so the model only fine-tunes the market where odds are published.
    "MARKET_XG_WEIGHT": 0.9,
    # shortlist rules: final probability >= p; tiers give ⭐⭐ / ⭐⭐⭐ ratings (values from the backtest)
    "THRESHOLDS": {
        "O15": {"p": _env_float("MIN_P_O15", 0.84), "tiers": (0.87, 0.90)},
        "O25": {"p": _env_float("MIN_P_O25", 0.60), "tiers": (0.64, 0.68)},
        "BTTS": {"p": _env_float("MIN_P_BTTS", 0.60), "tiers": (0.63, 0.66)},
    },
    # backtest hit-rates (test seasons 2025/26-26/27) shown in the report so expectations stay honest
    "BACKTEST": {
        "O15": "87% of shortlisted matches (⭐⭐ 88%, ⭐⭐⭐ 95%) over 900 picks",
        "O25": "67% of shortlisted matches (⭐⭐ 71%, ⭐⭐⭐ 77%) over 1,675 picks",
        "BTTS": "64% of shortlisted matches (⭐⭐ 65%, ⭐⭐⭐ 71%) over 1,800 picks",
    },
    "MAX_PICKS": int(_env_float("MAX_PICKS", 15)),
    # scheduled run hours (local time). Each run builds parlays for kick-offs before the next run.
    "RUN_HOURS": sorted({int(h) for h in os.getenv("RUN_HOURS", "7,12,17").split(",") if h.strip().isdigit()}) or [7, 12, 17],
    "PARLAYS_PER_RUN": int(_env_float("PARLAYS_PER_RUN", 3)),
    "PARLAY_ODDS": (_env_float("PARLAY_MIN_ODDS", 2.70), _env_float("PARLAY_MAX_ODDS", 3.50)),
    "PARLAY_MIN_MATCHES": 4,          # fewer priced matches before the next run -> use the whole 24 h window
    "SPORTYBET": os.getenv("SPORTYBET", "1") != "0",
    "NEWS": os.getenv("NEWS", "1") != "0",
    "PDF": os.getenv("PDF", "1") != "0",
    "LIVESCORE": os.getenv("LIVESCORE", "1") != "0",   # Livescore.com ids for the app's live tab
    "WORLD": os.getenv("WORLD", "1") != "0",           # every competition on Livescore (priced by Sportybet) — v4
    "FULL_MARKETS_MAX": int(_env_float("FULL_MARKETS_MAX", 160)),   # per-event Sportybet market fetches (corners / cards)
    "BOTD_N": int(_env_float("BOTD_N", 5)),            # bets of the day
    "REPORT_MAX_ROWS": int(_env_float("REPORT_MAX_ROWS", 120)),
    "H2H_SEASONS": int(_env_float("H2H_SEASONS", 5)),  # seasons of main-league history kept for head-to-head
    "REQUEST_TIMEOUT": 30,
    "USER_AGENT": "Mozilla/5.0 (compatible; GoalsScanner/1.0)",
    # optional: restrict to some competitions, e.g. LEAGUES="E0,SP1,I1,D1,F1,BRA"
    "LEAGUES": [s.strip() for s in os.getenv("LEAGUES", "").split(",") if s.strip()],
}

TZL = CONFIG["TZ_LABEL"]

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


def stars(p: float, mkt: str) -> str:
    t2, t3 = CONFIG["THRESHOLDS"][mkt]["tiers"]
    if p >= t3:
        return "⭐⭐⭐"
    if p >= t2:
        return "⭐⭐"
    return "⭐"


MAXG = 10  # score matrix size (goals 0..10)


def score_matrix(lh: float, la: float, rho: float = 0.0) -> np.ndarray:
    """Score probabilities P(home=i, away=j); rho != 0 applies the Dixon-Coles low-score correction."""
    g = np.arange(MAXG + 1)
    ph = np.exp(-lh) * lh ** g / np.array([math.factorial(int(k)) for k in g])
    pa = np.exp(-la) * la ** g / np.array([math.factorial(int(k)) for k in g])
    M = np.outer(ph, pa)
    if rho:
        M[0, 0] *= 1 - lh * la * rho
        M[1, 0] *= 1 + la * rho
        M[0, 1] *= 1 + lh * rho
        M[1, 1] *= 1 - rho
        M = np.clip(M, 1e-12, None)
    return M / M.sum()


def probs_from_matrix(M: np.ndarray) -> dict:
    g = np.arange(MAXG + 1)
    tot = g[:, None] + g[None, :]
    return {"O15": float(M[tot >= 2].sum()), "O25": float(M[tot >= 3].sum()), "O35": float(M[tot >= 4].sum()),
            "O05": float(M[tot >= 1].sum()), "O45": float(M[tot >= 5].sum()), "O55": float(M[tot >= 6].sum()),
            "BTTS": float(M[1:, 1:].sum()),
            "HW": float(M[g[:, None] > g[None, :]].sum()), "AW": float(M[g[:, None] < g[None, :]].sum())}


def market_lambdas(odds_h, odds_d, odds_a, odds_over, odds_under):
    """Expected goals implied by the market: total from the Over/Under 2.5 price, split from 1X2.
    Returns (lam_h, lam_a) or None when any price is missing."""
    vals = [odds_h, odds_d, odds_a, odds_over, odds_under]
    if any(v is None or (isinstance(v, float) and math.isnan(v)) or v <= 1 for v in vals):
        return None
    p_over = (1 / odds_over) / (1 / odds_over + 1 / odds_under)
    inv = np.array([1 / odds_h, 1 / odds_d, 1 / odds_a])
    p_h, _, p_a = inv / inv.sum()
    lo, hi = 0.3, 7.0
    for _ in range(40):                                  # total goals matching P(over 2.5)
        mid = (lo + hi) / 2
        if 1 - poisson_cdf(2, mid) < p_over:
            lo = mid
        else:
            hi = mid
    lt = (lo + hi) / 2
    lo, hi = 0.05, 0.95
    for _ in range(30):                                  # home share matching P(home) - P(away)
        s = (lo + hi) / 2
        P = probs_from_matrix(score_matrix(lt * s, lt * (1 - s)))
        if P["HW"] - P["AW"] < p_h - p_a:
            lo = s
        else:
            hi = s
    s = (lo + hi) / 2
    return lt * s, lt * (1 - s)


# ----------------------------------------------------------------------------- data loading
NUM_RESULT_COLS = ("hg", "ag", "hxg", "axg", "hst", "ast", "hc", "ac", "hy", "ay", "hr", "ar", "hth", "hta")
RESULT_COLS = ["country", "div", "league", "date", "home", "away", *NUM_RESULT_COLS, "referee", "home_id", "away_id"]


def empty_results() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="float64" if c in NUM_RESULT_COLS
                                      else ("datetime64[ns]" if c == "date" else "object"))
                         for c in RESULT_COLS})


def fetch_cached(url: str, name: str) -> bytes | None:
    """Immutable downloads (finished seasons) are kept under data/cache so the half-hourly runs stay light."""
    p = CACHE_DIR / name
    if p.exists():
        return p.read_bytes()
    content = fetch(url)
    if content:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            p.write_bytes(content)
        except OSError:
            pass
    return content


def load_main_results(divs: set[str], seasons: list[str], live_seasons: tuple[str, ...] = ()) -> pd.DataFrame:
    frames = []
    for div in sorted(divs):
        for season in seasons:
            url = f"{BASE}/mmz4281/{season}/{div}.csv"
            df = read_csv(fetch(url) if season in live_seasons else fetch_cached(url, f"fd_{season}_{div}.csv"))
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
                "hc": num(df, "HC"), "ac": num(df, "AC"),
                "hy": num(df, "HY"), "ay": num(df, "AY"), "hr": num(df, "HR"), "ar": num(df, "AR"),
                "hth": num(df, "HTHG"), "hta": num(df, "HTAG"),
                "referee": df["Referee"].astype(str).str.strip() if "Referee" in df.columns else "",
                "home_id": None, "away_id": None,
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
            "hc": np.nan, "ac": np.nan, "hy": np.nan, "ay": np.nan, "hr": np.nan, "ar": np.nan, "hth": np.nan, "hta": np.nan,
            "referee": "", "home_id": None, "away_id": None,
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
                "bfe_h": pd.to_numeric(r.get("BFEH"), errors="coerce"),
                "bfe_d": pd.to_numeric(r.get("BFED"), errors="coerce"),
                "bfe_a": pd.to_numeric(r.get("BFEA"), errors="coerce"),
                "bfe_over": pd.to_numeric(r.get("BFE>2.5"), errors="coerce"),
                "bfe_under": pd.to_numeric(r.get("BFE<2.5"), errors="coerce"),
                "max_over": pd.to_numeric(r.get("Max>2.5"), errors="coerce"),
                "max_under": pd.to_numeric(r.get("Max<2.5"), errors="coerce"),
                "referee": str(r.get("Referee", "") or "").strip(),
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
                "bfe_h": pd.to_numeric(r.get("BFEH"), errors="coerce"),
                "bfe_d": pd.to_numeric(r.get("BFED"), errors="coerce"),
                "bfe_a": pd.to_numeric(r.get("BFEA"), errors="coerce"),
                "bfe_over": np.nan, "bfe_under": np.nan, "max_over": np.nan, "max_under": np.nan, "referee": "",
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
        return datetime(r["date"].year, r["date"].month, r["date"].day, hh, mm, tzinfo=FEED_TZ).astimezone(tz)

    fx["kickoff"] = fx.apply(kickoff, axis=1)
    fx["time_known"] = fx["time"].apply(lambda t: bool(t) and t.lower() not in ("nan", "none"))
    fx["referee"] = fx["referee"].replace({"nan": "", "None": ""})
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
    hid = results["home_id"] if "home_id" in results.columns else pd.Series(None, index=results.index, dtype="object")
    aid = results["away_id"] if "away_id" in results.columns else pd.Series(None, index=results.index, dtype="object")
    home = pd.DataFrame({**common, "team_id": hid, "opp_id": aid, "team": results["home"], "opp": results["away"], "venue": "H",
                         "gf": results["hg"], "ga": results["ag"],
                         "gf_norm": results["hg"] / mu_h, "ga_norm": results["ag"] / mu_a,
                         "xg_for": results["hxg"], "xg_against": results["axg"],
                         "sot_for": results["hst"], "sot_against": results["ast"]})
    away = pd.DataFrame({**common, "team_id": aid, "opp_id": hid, "team": results["away"], "opp": results["home"], "venue": "A",
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
    venue_rate_o25: float = float("nan")
    venue_rate_btts: float = float("nan")
    venue_rate_o15: float = float("nan")
    venue_last5: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.n_eff >= CONFIG["MIN_EFF_MATCHES"]


def _valid_id(x) -> bool:
    return isinstance(x, str) and x.strip() != ""


def team_history(long: pd.DataFrame, country: str, team: str, team_id=None) -> pd.DataFrame:
    """A team's perspective rows: by Livescore id when known (any competition), else by country + name."""
    if long.empty:
        return long
    if _valid_id(team_id) and "team_id" in long.columns:
        rows = long[long["team_id"] == team_id]
        if not rows.empty:
            return rows
    return long[(long["country"] == country) & (long["team"] == team)]


def build_profile(long: pd.DataFrame, country: str, team: str, venue: str, now: datetime, team_id=None) -> TeamProfile:
    p = TeamProfile(name=team)
    if long.empty:
        return p
    rows = team_history(long, country, team, team_id).head(CONFIG["MAX_MATCHES_PER_TEAM"])
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
        vrows = rows[vmask]
        p.venue_rate_o15 = wmean(vrows["o15"], wv)
        p.venue_rate_o25 = wmean(vrows["o25"], wv)
        p.venue_rate_btts = wmean(vrows["btts"], wv)
        p.venue_last5 = [{"date": r.date, "venue": r.venue, "opp": r.opp, "gf": int(r.gf), "ga": int(r.ga),
                          "league": r.league} for r in vrows.head(5).itertuples()]
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


def head_to_head(results: pd.DataFrame, country: str, home: str, away: str, limit: int = 10,
                 home_id=None, away_id=None) -> list[dict]:
    if results.empty:
        return []
    if _valid_id(home_id) and _valid_id(away_id) and "home_id" in results.columns:
        m = results[((results["home_id"] == home_id) & (results["away_id"] == away_id)) |
                    ((results["home_id"] == away_id) & (results["away_id"] == home_id))]
    else:
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
    lam_h: float          # final expected goals (market-blended where odds exist)
    lam_a: float
    mod_h: float          # model-only expected goals
    mod_a: float
    mkt_h: float          # market-implied expected goals (nan without odds)
    mkt_a: float
    p_model: dict         # market -> model-only probability
    p_market_o25: float   # bookmaker-implied P(over 2.5)
    p_final: dict         # market -> final probability used for ranking (O15, O25, O35, BTTS)
    hist: dict            # market -> average historical hit-rate of both teams (information only)
    h2h: list
    div_avg: DivAvg
    extra: markets.ExtraMarkets = field(default_factory=markets.ExtraMarkets)
    sb: dict | None = None        # Sportybet prices (main markets) or None when not matched
    sb_event: dict | None = None  # Sportybet event meta (id, names)
    sb_full: dict | None = None   # full Sportybet market list (corners / cards), dossier matches only
    fair: dict = field(default_factory=dict)   # calibrated probabilities for priced selections
    trends: dict = field(default_factory=dict) # plain-language team / match / h2h trends (v4)

    @property
    def basis(self) -> str:
        return "market+model" if not math.isnan(self.mkt_h) else "model only"

    @property
    def data_ok(self) -> bool:
        return self.home.ok and self.away.ok

    @property
    def label(self) -> str:
        return f"{self.fx['home']} v {self.fx['away']}"


def analyse(fx: pd.Series, long: pd.DataFrame, results: pd.DataFrame,
            div_avgs: dict[str, DivAvg], now: datetime, h2h_pool: pd.DataFrame | None = None) -> MatchRow:
    g = div_avgs.get("__global__", DivAvg(1.45, 1.2, 0, float("nan"), float("nan")))
    da = div_avgs.get(fx["div"], g)
    hid, aid = fx.get("home_id"), fx.get("away_id")
    H = build_profile(long, fx["country"], fx["home"], "H", now, hid)
    A = build_profile(long, fx["country"], fx["away"], "A", now, aid)

    rho = CONFIG["DC_RHO"]
    mod_h = min(max(da.mu_h * H.att * A.dfc, 0.15), 4.5)
    mod_a = min(max(da.mu_a * A.att * H.dfc, 0.15), 4.5)
    p_model = probs_from_matrix(score_matrix(mod_h, mod_a, rho))

    oo, ou = fx["odds_over"], fx["odds_under"]
    if pd.notna(oo) and pd.notna(ou) and oo > 1 and ou > 1:
        p_mkt = (1 / oo) / (1 / oo + 1 / ou)
    else:
        p_mkt = float("nan")

    mk = market_lambdas(fx["odds_h"], fx["odds_d"], fx["odds_a"], oo, ou)
    if mk is not None:
        w = CONFIG["MARKET_XG_WEIGHT"]
        mkt_h, mkt_a = mk
        lam_h = (1 - w) * mod_h + w * mkt_h
        lam_a = (1 - w) * mod_a + w * mkt_a
    else:
        mkt_h = mkt_a = float("nan")
        lam_h, lam_a = mod_h, mod_a
    M = score_matrix(lam_h, lam_a, rho)
    p_final = probs_from_matrix(M)
    hist = {
        "O15": float(np.nanmean([H.rate_o15, A.rate_o15])) if H.n and A.n else float("nan"),
        "O25": float(np.nanmean([H.rate_o25, A.rate_o25])) if H.n and A.n else float("nan"),
        "BTTS": float(np.nanmean([H.rate_btts, A.rate_btts])) if H.n and A.n else float("nan"),
    }
    row = MatchRow(fx, H, A, lam_h, lam_a, mod_h, mod_a, mkt_h, mkt_a, p_model, p_mkt, p_final, hist,
                   head_to_head(h2h_pool if h2h_pool is not None else results, fx["country"], fx["home"], fx["away"],
                                home_id=hid, away_id=aid), da)
    # ---- extra markets (v3): 1X2 / DC from the score matrix + sharp market, team goals, corners, cards
    ex = row.extra
    oh, od, oa = sharp_1x2(fx)
    ex.x12 = markets.one_x_two(M, oh, od, oa)
    ex.tg = markets.team_goals(M)
    cm = MODELS.get("corners")
    if cm is not None and fx["source"] == "main":
        ex.corners = cm.expect(fx["country"], fx["home"], fx["away"], fx["div"])
        ex.corner_p = markets.count_lines(ex.corners, markets.CORNERS)
    km = MODELS.get("cards")
    if km is not None and fx["source"] == "main":
        ex.cards = km.expect(fx["country"], fx["home"], fx["away"], fx["div"], fx.get("referee", "") or "")
        ex.card_p = markets.count_lines(ex.cards, markets.CARDS)
    so, su = sharp_ou(fx)
    fair_o = markets.fair_two_way(so, su)
    ex.p_o25_fair = (1 - CONFIG["MARKET_XG_WEIGHT"]) * p_final["O25"] + CONFIG["MARKET_XG_WEIGHT"] * fair_o \
        if not math.isnan(fair_o) else float("nan")
    return row


MODELS: dict = {}   # corners / cards count models, built once per run in main()


def _ok(v) -> bool:
    return v is not None and not (isinstance(v, float) and math.isnan(v)) and v > 1


def sharp_1x2(fx: pd.Series):
    """Best available reference prices for the 1X2 fair probability: Betfair Exchange, else market average."""
    if all(_ok(fx.get(c)) for c in ("bfe_h", "bfe_d", "bfe_a")):
        return fx["bfe_h"], fx["bfe_d"], fx["bfe_a"]
    return fx.get("odds_h"), fx.get("odds_d"), fx.get("odds_a")


def sharp_ou(fx: pd.Series):
    if all(_ok(fx.get(c)) for c in ("bfe_over", "bfe_under")):
        return fx["bfe_over"], fx["bfe_under"]
    return fx.get("odds_over"), fx.get("odds_under")


def attach_prices(rows: list[MatchRow], sbmap: dict, todays: pd.DataFrame) -> None:
    """Attach Sportybet prices to rows and finish the calibrated probabilities used for legs / value.

    The feed's reference prices (Betfair Exchange / market average) can be a few days old, while Sportybet's
    price is live. So where both exist the fair probability is the average of the two market views (each
    blended 90/10 with the model); a big gap between them is flagged as "price moved" rather than sold as value.
    """
    w = CONFIG["MARKET_XG_WEIGHT"]
    for i, r in zip(todays.index, rows):
        ev = sbmap.get(i)
        if ev:
            r.sb_event = {k: ev[k] for k in ("id", "home", "away", "country", "tournament", "ko")}
            r.sb = ev["markets"]
        ex = r.extra
        M = score_matrix(r.lam_h, r.lam_a, CONFIG["DC_RHO"])
        sb = r.sb or {}
        # ---- 1X2 / double chance
        sb1x2 = sb.get("1X2")
        if sb1x2 and all(sb1x2):
            x_sb = markets.one_x_two(M, *sb1x2)
            if ex.x12.get("source") == "market+model":
                gap = max(abs(ex.x12["H"] - x_sb["H"]), abs(ex.x12["A"] - x_sb["A"]))
                ex.x12 = {k: 0.5 * ex.x12[k] + 0.5 * x_sb[k] for k in ("H", "D", "A", "1X", "12", "X2")}
                ex.x12["source"] = "market+Sportybet+model"
                ex.x12["gap"] = gap
            else:
                ex.x12 = x_sb
                ex.x12["source"] = "Sportybet+model"
        # ---- Over 2.5
        ou = sb.get("OU", {}).get(2.5) if sb else None
        fair_sb = markets.fair_two_way(ou[0], ou[1]) if ou and ou[0] and ou[1] else float("nan")
        p_sb = (1 - w) * r.p_final["O25"] + w * fair_sb if not math.isnan(fair_sb) else float("nan")
        if not math.isnan(ex.p_o25_fair) and not math.isnan(p_sb):
            ex.p_o25_fair = 0.5 * ex.p_o25_fair + 0.5 * p_sb
        elif math.isnan(ex.p_o25_fair):
            ex.p_o25_fair = p_sb if not math.isnan(p_sb) else r.p_final["O25"]
        # ---- fair probabilities of the shortlist markets (price check): model/market blend, half-anchored on Sportybet
        r.fair = {"O15": r.p_final["O15"], "O25": ex.p_o25_fair, "BTTS": r.p_final["BTTS"]}
        ou15 = sb.get("OU", {}).get(1.5) if sb else None
        if ou15 and ou15[0] and ou15[1]:
            r.fair["O15"] = 0.5 * r.p_final["O15"] + 0.5 * markets.fair_two_way(ou15[0], ou15[1])
        btts = sb.get("BTTS") if sb else None
        if btts and btts[0] and btts[1]:
            r.fair["BTTS"] = 0.5 * r.p_final["BTTS"] + 0.5 * markets.fair_two_way(btts[0], btts[1])


def avg_prices(fx: pd.Series) -> dict | None:
    """Fallback price set from the feed averages (used when Sportybet is unavailable)."""
    h, d, a = fx.get("odds_h"), fx.get("odds_d"), fx.get("odds_a")
    if not all(_ok(v) for v in (h, d, a)):
        return None
    dc = lambda o1, o2: 1 / (1 / o1 + 1 / o2)
    out = {"1X2": (h, d, a), "DC": {"1X": dc(h, d), "12": dc(h, a), "X2": dc(d, a)}}
    if _ok(fx.get("odds_over")) and _ok(fx.get("odds_under")):
        out["OU"] = {2.5: (fx["odds_over"], fx["odds_under"])}
    return out


def sb_price(r: MatchRow, mkt: str):
    """Sportybet price for a shortlist market (O15 / O25 / BTTS) or None."""
    if not r.sb:
        return None
    if mkt == "BTTS":
        return (r.sb.get("BTTS") or (None, None))[0]
    line = 1.5 if mkt == "O15" else 2.5
    return (r.sb.get("OU", {}).get(line) or (None, None))[0]


# ----------------------------------------------------------------------------- run schedule / parlays
def run_desc(label: str, tz: bool = False) -> str:
    """'run 07:00' / 'manual run 15:05' (+ timezone label)."""
    txt = f"manual run {label[7:]}" if str(label).startswith("manual") else f"run {label}"
    return f"{txt} {TZL}" if tz else txt


def run_schedule(now: datetime) -> tuple[str, datetime]:
    """(run label, window end). Runs close to a report hour (07/12/17) are the full-report runs and keep the
    plain 'HH:MM' label; the half-hourly refreshes in between are 'auto HH:MM'; dispatches are 'manual HH:MM'."""
    hours = CONFIG["RUN_HOURS"]
    todays = [now.replace(hour=h, minute=0, second=0, microsecond=0) for h in hours]
    event = os.getenv("GITHUB_EVENT_NAME", "")
    label = f"manual {now:%H:%M}" if event == "workflow_dispatch" or not event else f"auto {now:%H:%M}"
    # the first run within 90 min after a report hour that has not yet produced that report is the report run
    # (GitHub's cron is often 5-30 min late; a crashed run is retried by the next half-hourly one)
    done = _report_marks().get(now.strftime("%Y-%m-%d"), [])
    for t in todays:
        if -5 * 60 <= (now - t).total_seconds() <= 90 * 60 and f"{t:%H:%M}" not in done:
            label = f"{t:%H:%M}"
            break
    nxt = [t for t in todays if t > now + timedelta(minutes=20)]
    window_end = nxt[0] if nxt else (todays[0] + timedelta(days=1))
    return label, window_end


def is_report_run(label: str) -> bool:
    return not label.startswith(("auto", "manual"))


REPORT_MARKS_FILE = DATA_DIR / "report_marks.json"


def _report_marks() -> dict:
    try:
        return json.loads(REPORT_MARKS_FILE.read_text(encoding="utf-8")) if REPORT_MARKS_FILE.exists() else {}
    except Exception:
        return {}


def mark_report_run(now: datetime, label: str) -> None:
    """Remember that today's report for this hour went out (keeps the last 3 days)."""
    marks = _report_marks()
    day = now.strftime("%Y-%m-%d")
    marks.setdefault(day, [])
    if label not in marks[day]:
        marks[day].append(label)
    for k in sorted(marks)[:-3]:
        marks.pop(k, None)
    REPORT_MARKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MARKS_FILE.write_text(json.dumps(marks, indent=1), encoding="utf-8")


def build_run_parlays(rows: list[MatchRow], now: datetime, window_end: datetime, sb_ok: bool) -> dict:
    """Legs from priced matches kicking off before the next run; whole window if too thin."""
    start = now + timedelta(minutes=10)
    source = "Sportybet" if sb_ok else "avg market"

    def legs_for(rs):
        legs = []
        for r in rs:
            if not r.data_ok:
                continue
            prices = r.sb if sb_ok else avg_prices(r.fx)
            if not prices and sb_ok:
                continue
            legs += parlay_mod.candidate_legs(r.fx, r.extra.x12, r.extra.p_o25_fair, prices, source)
        return legs

    short = [r for r in rows if start <= r.fx["kickoff"] <= window_end]
    legs = legs_for(short)
    extended = False
    if len({l.key for l in legs}) < CONFIG["PARLAY_MIN_MATCHES"]:
        legs = legs_for([r for r in rows if r.fx["kickoff"] >= start])
        extended = True
    lo, hi = CONFIG["PARLAY_ODDS"]
    built = parlay_mod.build_parlays(legs, lo, hi, CONFIG["PARLAYS_PER_RUN"])
    return {"parlays": built, "legs": legs, "extended": extended, "source": source,
            "n_matches": len({l.key for l in legs})}


def select_picks(rows: list[MatchRow]) -> dict[str, list[MatchRow]]:
    picks: dict[str, list[MatchRow]] = {}
    for mkt, thr in CONFIG["THRESHOLDS"].items():
        # backtest: team hit-rate floors and model-vs-market filters added nothing once the
        # probabilities were calibrated, so the rule is simply "final probability >= threshold"
        cand = [r for r in rows if r.data_ok and r.p_final[mkt] >= thr["p"]]
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
            key = (r.fx["date"].strftime("%Y-%m-%d"), r.fx["home"], r.fx["away"], mkt)
            if key in existing:
                continue
            existing.add(key)
            odds = r.fx["odds_over"] if mkt == "O25" else float("nan")
            new.append({
                "match_date": key[0], "kickoff": r.fx["kickoff"].strftime("%Y-%m-%d %H:%M"),
                "country": r.fx["country"], "div": r.fx["div"], "league": r.fx["league"],
                "home": r.fx["home"], "away": r.fx["away"], "market": mkt,
                "p_model": f"{r.p_model[mkt]:.3f}",
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


def basis_str(r: MatchRow) -> str:
    return "📈 market+model" if r.basis == "market+model" else "🧮 model only"


def render_pick_table(rows: list[MatchRow], mkt: str) -> list[str]:
    L = []
    if not rows:
        L.append("_No match met the criteria today._")
        return L
    if mkt == "O25":
        L.append(f"| # | Kick-off ({TZL}) | Competition | Match | Final | Rating | Market (odds) | Model | Basis | Last-10 form | Exp. goals |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for i, r in enumerate(rows, 1):
            L.append(f"| {i} | {ko(r)} | {comp(r)} | **{r.label}** | **{pct(r.p_final['O25'])}** | {stars(r.p_final['O25'], mkt)} | "
                     f"{market_str(r)} | {pct(r.p_model['O25'])} | {basis_str(r)} | {form_str(r, mkt)} | "
                     f"{r.lam_h:.1f} – {r.lam_a:.1f} |")
    else:
        L.append(f"| # | Kick-off ({TZL}) | Competition | Match | Final | Rating | Model | Basis | Last-10 form | Exp. goals |")
        L.append("|---|---|---|---|---|---|---|---|---|---|")
        for i, r in enumerate(rows, 1):
            L.append(f"| {i} | {ko(r)} | {comp(r)} | **{r.label}** | **{pct(r.p_final[mkt])}** | "
                     f"{stars(r.p_final[mkt], mkt)} | {pct(r.p_model[mkt])} | {basis_str(r)} | {form_str(r, mkt)} | "
                     f"{r.lam_h:.1f} – {r.lam_a:.1f} |")
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
    L.append(f"* Final expected goals: **{r.lam_h:.2f} – {r.lam_a:.2f}** (total {r.lam_h + r.lam_a:.2f}, {r.basis}) · "
             f"P(O1.5) **{pct(r.p_final['O15'])}** · P(O2.5) **{pct(r.p_final['O25'])}** · P(O3.5) {pct(r.p_final['O35'])} · "
             f"P(BTTS) **{pct(r.p_final['BTTS'])}**")
    L.append(f"* Team-form model alone: {r.mod_h:.2f} – {r.mod_a:.2f} · P(O2.5) {pct(r.p_model['O25'])} · P(BTTS) {pct(r.p_model['BTTS'])}"
             + (f" · Market-implied: {r.mkt_h:.2f} – {r.mkt_a:.2f}" if not math.isnan(r.mkt_h) else ""))
    if not math.isnan(r.p_market_o25):
        L.append(f"* Market: Over 2.5 @ {r.fx['odds_over']:.2f} / Under 2.5 @ {r.fx['odds_under']:.2f} "
                 f"(implied O2.5 {pct(r.p_market_o25)}) · 1X2 {f2(r.fx['odds_h'])} / {f2(r.fx['odds_d'])} / {f2(r.fx['odds_a'])}")
    elif pd.notna(r.fx["odds_h"]):
        L.append(f"* Market 1X2: {f2(r.fx['odds_h'])} / {f2(r.fx['odds_d'])} / {f2(r.fx['odds_a'])} (no O/U odds published in feed)")
    L.append(f"* League context: avg {r.div_avg.mu_h:.2f} home + {r.div_avg.mu_a:.2f} away goals · "
             f"O2.5 in {pct(r.div_avg.o25_rate)} · BTTS in {pct(r.div_avg.btts_rate)} of matches")
    L += render_extra_lines(r)
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


def fmt_odds(o) -> str:
    return "–" if o is None or (isinstance(o, float) and math.isnan(o)) else f"{o:.2f}"


def sb_line_str(d: dict | None, lines=None) -> str:
    """'O8.5 1.45/2.60 · O9.5 1.85/1.90' from a Sportybet {line: (over, under)} dict."""
    if not d:
        return "–"
    parts = []
    for line in sorted(d):
        if lines and line not in lines:
            continue
        o, u = d[line]
        parts.append(f"O{line:g} {fmt_odds(o)} / U {fmt_odds(u)}")
    return " · ".join(parts) if parts else "–"


def render_extra_lines(r: MatchRow) -> list[str]:
    ex = r.extra
    L = []
    if ex.x12:
        x = ex.x12
        L.append(f"* **1X2** (fair, {x.get('source', 'model')}): home {pct(x['H'])} · draw {pct(x['D'])} · away {pct(x['A'])} → "
                 f"fair odds {1 / x['H']:.2f} / {1 / x['D']:.2f} / {1 / x['A']:.2f} · "
                 f"**Double chance** 1X {pct(x['1X'])} · 12 {pct(x['12'])} · X2 {pct(x['X2'])}")
    if ex.tg:
        t = ex.tg
        L.append(f"* **Team goals:** {r.fx['home']} to score {pct(t['H_o05'])} (2+ {pct(t['H_o15'])}) · "
                 f"{r.fx['away']} to score {pct(t['A_o05'])} (2+ {pct(t['A_o15'])})")
    if ex.corners is not None:
        c, cp = ex.corners, ex.corner_p
        tot = " · ".join(f"O{l:g} **{pct(p)}**" for l, p in cp["total"].items())
        L.append(f"* **Corners:** expected {c.eh:.1f} (home) + {c.ea:.1f} (away) = **{c.total:.1f}** · total {tot} · "
                 f"home " + " · ".join(f"O{l:g} {pct(p)}" for l, p in cp["home"].items()) + " · away " +
                 " · ".join(f"O{l:g} {pct(p)}" for l, p in cp["away"].items()) +
                 f" _(team averages: {r.fx['home']} {c.h_for:.1f} for / {c.h_against:.1f} against over {c.h_n} games, "
                 f"{r.fx['away']} {c.a_for:.1f} / {c.a_against:.1f} over {c.a_n})_")
    if ex.cards is not None:
        k, kp = ex.cards, ex.card_p
        tot = " · ".join(f"O{l:g} **{pct(p)}**" for l, p in kp["total"].items())
        ref = ""
        if k.ref_n > 0:
            ref = f" · referee {r.fx.get('referee', '')} factor {k.ref_factor:.2f} ({k.ref_n:.0f} weighted games)"
        L.append(f"* **Cards** (yellow + red): expected {k.eh:.1f} + {k.ea:.1f} = **{k.total:.1f}** · total {tot}{ref} "
                 f"_(team averages: {r.fx['home']} {k.h_for:.1f} received / {k.h_against:.1f} opponents booked, "
                 f"{r.fx['away']} {k.a_for:.1f} / {k.a_against:.1f})_")
    if r.sb:
        sb = r.sb
        parts = []
        if sb.get("1X2") and any(sb["1X2"]):
            parts.append("1X2 " + " / ".join(fmt_odds(o) for o in sb["1X2"]))
        if sb.get("DC"):
            parts.append("DC 1X/12/X2 " + " / ".join(fmt_odds(sb["DC"].get(k)) for k in ("1X", "12", "X2")))
        if sb.get("OU"):
            parts.append("goals " + sb_line_str(sb["OU"], (1.5, 2.5, 3.5)))
        if sb.get("BTTS"):
            parts.append(f"BTTS {fmt_odds(sb['BTTS'][0])} / {fmt_odds(sb['BTTS'][1])}")
        if sb.get("TGH"):
            parts.append(f"{r.fx['home']} goals " + sb_line_str(sb["TGH"], (0.5, 1.5)))
        if sb.get("TGA"):
            parts.append(f"{r.fx['away']} goals " + sb_line_str(sb["TGA"], (0.5, 1.5)))
        L.append("* **Sportybet:** " + " · ".join(parts))
        full = r.sb_full or {}
        parts = []
        if full.get("CORN"):
            parts.append("total corners " + sb_line_str(full["CORN"], (8.5, 9.5, 10.5, 11.5)))
        if full.get("CORNH"):
            parts.append("home corners " + sb_line_str(full["CORNH"], (3.5, 4.5, 5.5)))
        if full.get("CORNA"):
            parts.append("away corners " + sb_line_str(full["CORNA"], (3.5, 4.5, 5.5)))
        if full.get("CORN1H"):
            parts.append("1st-half corners " + sb_line_str(full["CORN1H"]) + " _(no model — market only)_")
        if full.get("CARDS"):
            parts.append("total cards " + sb_line_str(full["CARDS"], (3.5, 4.5, 5.5)))
        if parts:
            L.append("* **Sportybet corners / cards:** " + " · ".join(parts))
    return L


def leg_row(l: parlay_mod.Leg) -> str:
    flag = " ⚠️ price moved vs reference — check team news" if l.ev > 0.08 else ""
    return (f"| {l.kickoff[5:]} | **{l.match}** | {l.league} | **{l.label}** | **{l.odds:.2f}** | {l.fair_odds:.2f} | "
            f"{pct(l.p)} | {100 * l.ev:+.1f}%{flag} |")


def render_parlays(ctx: dict, pr: dict, ids: list[str], psum: dict) -> list[str]:
    lo, hi = CONFIG["PARLAY_ODDS"]
    L = [f"## 🎟️ Parlays — {run_desc(ctx['run'])} · combined odds {lo:.2f}–{hi:.2f}", ""]
    src = pr["source"]
    win = f"kick-offs before the next run ({ctx['window_end']:%a %H:%M} {TZL})"
    if pr["extended"]:
        win = f"whole 24 h window (fewer than {CONFIG['PARLAY_MIN_MATCHES']} priced matches before the next run)"
    L.append(f"_Prices: **{src}**{' — Sportybet was unreachable, average market prices used' if src != 'Sportybet' else ''}. "
             f"Window: {win}. {pr['n_matches']} priced matches, {len(pr['legs'])} candidate legs. "
             f"Legs are limited to 1X2, double chance and Over/Under 2.5 — markets with real prices. "
             f"Each parlay maximises expected return (calibrated probability × price) inside the odds band._")
    L.append("")
    if not pr["parlays"]:
        L.append("_No parlay could be built inside the odds band for this window._")
        L.append("")
        return L
    for i, pl in enumerate(pr["parlays"], 1):
        odds, p = parlay_mod.parlay_odds(pl), parlay_mod.parlay_p(pl)
        pid = ids[i - 1] if i - 1 < len(ids) else ""
        L.append(f"### Parlay {i} — {len(pl)} legs @ **{odds:.2f}** · win probability **{pct(p)}** · "
                 f"expected return {100 * (p * odds - 1):+.1f}% · id `{pid}`")
        L.append("")
        L.append("| Kick-off | Match | Competition | Selection | Price | Fair odds | Probability | Leg edge |")
        L.append("|---|---|---|---|---|---|---|---|")
        for l in pl:
            L.append(leg_row(l))
        L.append("")
    a, d30 = psum.get("all", {}), psum.get("30d", {})
    if a.get("n"):
        L.append(f"**Parlay record:** {a['won']}/{a['n']} won ({pct(a['rate'])}, expected {pct(a['exp_rate'])}) · "
                 f"flat-stake return {100 * a['roi']:+.1f}% · last 30 days {d30.get('won', 0)}/{d30.get('n', 0)} "
                 f"({pct(d30.get('rate', float('nan')))}, {100 * d30['roi']:+.1f}%)" if d30.get("n") else
                 f"**Parlay record:** {a['won']}/{a['n']} won ({pct(a['rate'])}, expected {pct(a['exp_rate'])}) · "
                 f"flat-stake return {100 * a['roi']:+.1f}%")
    else:
        L.append(f"**Parlay record:** no settled parlays yet ({psum.get('pending', 0)} pending).")
    L.append("")
    L.append(f"> ⚠️ Honest expectation: a parlay at ~{(lo + hi) / 2:.1f} needs to win about 1 in 3 to break even. "
             "In the 2023-26 backtest this exact construction won 30-33% of the time and returned −4% to −13% "
             "per unit at average prices — the bookmaker margin compounds across legs. Treat parlays as "
             "entertainment with a known cost, not as income. Full test: `backtest/PARLAY_EXPERIMENT.md`.")
    L.append("")
    return L


def render_safest(ctx: dict) -> list[str]:
    sf = ctx.get("safe") or {}
    if not sf:
        return []
    L = [f"## 🔒 Safest bets — {run_desc(ctx['run'])}", ""]
    L.append(f"_Goals, corners and cards selections whose probability is at least {pct(sf['min_p'])} on **both** views "
             f"(calibrated model and the de-margined Sportybet price) at a Sportybet price of {sf['min_odds']:.2f} or more, "
             f"ranked by probability. Graded automatically (`data/safe_bets.csv`)._")
    L.append("")
    botd = ctx.get("botd") or []
    if botd:
        L.append(f"### ⭐ Bets of the day — {ctx['now']:%A %d %B}")
        L.append("")
        L.append("| Kick-off | Match | Competition | Selection | Price | Probability | Status |")
        L.append("|---|---|---|---|---|---|---|")
        icon = {"hit": "✅ hit", "miss": "❌ miss", "pending": "⏳", "void": "void"}
        for b in botd:
            L.append(f"| {b['kickoff'][11:]} | **{b['home']} v {b['away']}** | {b['league']} | **{b['label']}** | "
                     f"**{b['odds']:.2f}** | {pct(b['p'])} | {icon.get(b['status'], b['status'])} |")
        L.append("")
    bets = sf.get("bets") or []
    L.append(f"### Safest single bets — top {min(len(bets), 25)} of {len(bets)}")
    L.append("")
    if bets:
        L.append("| Kick-off | Match | Competition | Selection | Price | Probability | Model | Sportybet |")
        L.append("|---|---|---|---|---|---|---|---|")
        for b in bets[:25]:
            L.append(f"| {b.kickoff[5:]} | {b.home} v {b.away} | {b.league} | **{b.label}** | **{b.odds:.2f}** | **{pct(b.p)}** | "
                     f"{pct(b.p_model)} | {pct(b.p_sb) if b.p_sb is not None else '–'} |")
    else:
        L.append("_Nothing priced met the rules in this window._")
    L.append("")
    ss = ctx.get("safe_summary") or {}
    ba = (ss.get("bets") or {}).get("all") or {}
    bd = (ss.get("botd") or {}).get("all") or {}
    if ba.get("n"):
        L.append(f"_Track record — safest bets: {ba.get('won', 0)}/{ba.get('n', 0)} hit ({pct(ba['rate'])}, expected {pct(ba['exp_rate'])})"
                 f"{'; bets of the day: ' + str(bd.get('won', 0)) + '/' + str(bd.get('n', 0)) + ' hit' if bd.get('n') else ''}._")
        L.append("")
    return L


def render_value_check(picks: dict, sb_ok: bool) -> list[str]:
    L = ["## 💰 Sportybet price check — shortlisted picks", ""]
    if not sb_ok:
        L.append("_Sportybet prices were not available for this run._")
        L.append("")
        return L
    L.append("_Fair odds = 1 / calibrated probability (90% sharp market, 10% model where prices exist). "
             "A positive edge means Sportybet pays more than the fair price; the backtest found positive edges "
             "of this kind on Over 2.5 returned about +3% at the best available price — small, but real. "
             "Negative edges mean the price is below fair value._")
    L.append("")
    L.append("| Market | Match | Kick-off | Probability | Fair odds | Sportybet | Edge |")
    L.append("|---|---|---|---|---|---|---|")
    n = 0
    for mkt, name in MARKETS.items():
        for r in picks.get(mkt, []):
            price = sb_price(r, mkt)
            p = r.fair.get(mkt, r.p_final[mkt])
            if price is None or p is None or math.isnan(p) or p <= 0:
                continue
            n += 1
            edge = p * price - 1
            flag = "✅ value" if edge > 0.02 else ("≈ fair" if edge > -0.03 else "❌ short")
            L.append(f"| {name} | **{r.label}** | {r.fx['kickoff']:%a %H:%M} | {pct(p)} | {1 / p:.2f} | **{price:.2f}** | "
                     f"{100 * edge:+.1f}% {flag} |")
    if n == 0:
        L.append("| – | _no shortlisted pick is priced at Sportybet yet_ | | | | | |")
    L.append("")
    return L


def render_other_markets(rows: list[MatchRow]) -> list[str]:
    L = ["## 🧾 Other markets — 1X2, double chance, team goals, corners, cards", ""]
    if not rows:
        return L + ["_No fixtures._", ""]
    L.append("_Probabilities are model + sharp-market blends (1X2, team goals) or the backtested count models "
             "(corners / cards, main leagues only). Sportybet column = 1X2 prices where the match was found._")
    L.append("")
    L.append(f"| Kick-off ({TZL}) | Match | Competition | Home / Draw / Away | 1X / X2 | Home to score / 2+ | "
             f"Away to score / 2+ | Corners exp. (O9.5 · O10.5) | Cards exp. (O3.5 · O4.5) | Sportybet 1X2 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: (r.fx["kickoff"], comp(r))):
        x, t, c, k = r.extra.x12, r.extra.tg, r.extra.corners, r.extra.cards
        cp, kp = r.extra.corner_p, r.extra.card_p
        corners = f"{c.total:.1f} ({pct(cp['total'][9.5])} · {pct(cp['total'][10.5])})" if c is not None else "–"
        cards = f"{k.total:.1f} ({pct(kp['total'][3.5])} · {pct(kp['total'][4.5])})" if k is not None else "–"
        sb = " / ".join(fmt_odds(o) for o in r.sb["1X2"]) if r.sb and r.sb.get("1X2") and any(r.sb["1X2"]) else "–"
        L.append(f"| {ko(r)} | **{r.label}** | {comp(r)} | {pct(x['H'])} / {pct(x['D'])} / {pct(x['A'])} | "
                 f"{pct(x['1X'])} / {pct(x['X2'])} | {pct(t['H_o05'])} / {pct(t['H_o15'])} | {pct(t['A_o05'])} / {pct(t['A_o15'])} | "
                 f"{corners} | {cards} | {sb} |")
    L.append("")
    return L


def render_parlay_history(psum: dict, rec: list[dict]) -> list[str]:
    L = ["### Parlay ledger", ""]
    a = psum.get("all", {})
    if not a.get("n") and not rec:
        pend = psum.get("pending", 0)
        L.append(f"_No settled parlays yet — {pend} pending (graded automatically once the results are in)._"
                 if pend else "_No parlays recorded yet._")
        L.append("")
        return L
    L.append("| Scope | Settled | Won | Hit rate | Expected | Avg odds | Flat-stake return |")
    L.append("|---|---|---|---|---|---|---|")
    for name, st in (("All time", psum.get("all", {})), ("Last 30 days", psum.get("30d", {}))):
        if st.get("n"):
            L.append(f"| {name} | {st['n']} | {st['won']} | {pct(st['rate'])} | {pct(st['exp_rate'])} | {f2(st['avg_odds'])} | {100 * st['roi']:+.1f}% |")
        else:
            L.append(f"| {name} | 0 | 0 | – | – | – | – |")
    for run, st in sorted(psum.get("by_run", {}).items()):
        if st.get("n"):
            L.append(f"| Run {run} | {st['n']} | {st['won']} | {pct(st['rate'])} | {pct(st['exp_rate'])} | {f2(st['avg_odds'])} | {100 * st['roi']:+.1f}% |")
    L.append("")
    if rec:
        L.append("| Id | Created | Run | Legs | Odds | Prob. | Status |")
        L.append("|---|---|---|---|---|---|---|")
        icon = {"won": "✅ won", "lost": "❌ lost", "pending": "⏳ pending", "void": "void"}
        for x in rec:
            legs = "; ".join(f"{l.match} — {l.label} @ {l.odds:.2f}" for l in x["legs"])
            L.append(f"| `{x['id']}` | {x['created']} | {x['run']} | {legs} | {x['odds']} | {pct(float(x['p']))} | {icon.get(x['status'], x['status'])} |")
        L.append("")
    return L


def render_report(ctx: dict, rows: list[MatchRow], picks: dict, summary: dict, notes: list[str]) -> str:
    now = ctx["now"]
    L = [f"# ⚽ PlayReport — {now:%A %d %B %Y}", ""]
    comps = {comp(r) for r in rows}
    L.append(f"**{run_desc(ctx.get('run', ''), True).capitalize()}** · scan window {ctx['start']:%a %d %b %H:%M} → {ctx['end']:%a %d %b %H:%M} · "
             f"**{len(rows)} fixtures** across **{len(comps)} competitions** · generated {now:%H:%M} {TZL} · "
             f"next run {ctx['window_end']:%a %H:%M}")
    L.append("")
    if notes:
        L.append("> " + "  \n> ".join(notes))
        L.append("")
    if ctx.get("digest"):
        L += ctx["digest"]
    L += render_safest(ctx)

    L.append("## 🎯 Shortlist")
    L.append("")
    for mkt, name in MARKETS.items():
        thr = CONFIG["THRESHOLDS"][mkt]
        L.append(f"### {name} — {len(picks.get(mkt, []))} pick(s)")
        L.append(f"_Rule: final probability ≥ {pct(thr['p'])} (⭐⭐ ≥ {pct(thr['tiers'][0])}, ⭐⭐⭐ ≥ {pct(thr['tiers'][1])}). "
                 f"Backtest 2025/26–26/27: {CONFIG['BACKTEST'][mkt]}._")
        L.append("")
        L += render_pick_table(picks.get(mkt, []), mkt)
        L.append("")

    cap = CONFIG["REPORT_MAX_ROWS"]
    ranked = sorted([r for r in rows if r.data_ok], key=lambda r: r.p_final["O25"], reverse=True)
    L.append(f"## 📊 Full scan — top {min(cap, len(ranked))} of {len(rows)} fixtures by Over 2.5 probability")
    L.append("")
    if ranked:
        L.append(f"| Kick-off ({TZL}) | Competition | Match | Exp. goals | O1.5 | O2.5 | BTTS | Market O2.5 (odds) | Model O2.5 | Basis | O2.5 last-10 form |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for r in ranked[:cap]:
            L.append(f"| {ko(r)} | {comp(r)} | {r.label} | {r.lam_h:.1f} – {r.lam_a:.1f} | {pct(r.p_final['O15'])} | "
                     f"**{pct(r.p_final['O25'])}** | {pct(r.p_final['BTTS'])} | {market_str(r)} | {pct(r.p_model['O25'])} | "
                     f"{basis_str(r)} | {form_str(r, 'O25')} |")
        if len(rows) > cap:
            L.append("")
            L.append(f"_{len(rows) - cap} more fixtures (including {sum(1 for r in rows if not r.data_ok)} with too little history) are in the PlayReport app._")
    else:
        L.append("_No fixtures found in the scan window._")
    L.append("")

    L += render_value_check(picks, bool(ctx.get("sb_ok")))
    focus_keys = {id(r) for m in picks.values() for r in m}
    for b in (ctx.get("safe") or {}).get("bets") or []:
        focus_keys.add(b.key)
    focus = [r for r in rows if id(r) in focus_keys or
             (r.fx["date"].strftime("%Y-%m-%d"), r.fx["country"], r.fx["home"], r.fx["away"]) in focus_keys]
    L += render_other_markets([r for r in focus if r.fx["source"] == "main"] or focus[:cap])

    if focus:
        L.append("## 🔍 Match details — shortlisted and safest-bet matches (click to expand)")
        L.append("")
        for r in sorted(focus, key=lambda r: (r.fx["kickoff"], comp(r))):
            L += render_details(r)

    L.append("## 📈 Trackers (auto-settled from results)")
    L.append("")
    L.append("### Shortlist tracker")
    L.append("")
    L += render_tracker(summary)
    L.append("")
    L.append("_Flat-stake return is for model evaluation only: 1 unit on every Over 2.5 pick at the average market odds._")
    L.append("")

    L.append("## ℹ️ Method")
    L.append("")
    L += [
        "* **Team-form model:** attack/defence strengths from goals scored and conceded over the last two seasons, "
        f"normalised by league averages, time-weighted (half-life {CONFIG['HALF_LIFE_DAYS']} days) and strongly "
        f"shrunk towards league average (K={CONFIG['SHRINK_K']:g} matches — goal form is noisy; the backtest showed "
        "weak shrinkage made the old model over-confident by 5-10 points).",
        "* **Market-implied expected goals:** where the feed publishes odds, the Over/Under 2.5 price fixes the expected "
        "total and the 1X2 prices fix the home/away split. The final expected goals are "
        f"{int(CONFIG['MARKET_XG_WEIGHT'] * 100)}% market / {int((1 - CONFIG['MARKET_XG_WEIGHT']) * 100)}% model "
        "(📈 market+model). Without odds the model is used alone (🧮 model only).",
        f"* Probabilities for every market come from a Dixon-Coles adjusted Poisson score matrix (ρ={CONFIG['DC_RHO']:g}).",
        "* **Backtest (52,000 matches, 2023-26, no look-ahead):** final probabilities are calibrated to within ±3 points; "
        "the model alone beats league averages but never beats the market, and when the model is more bullish than the "
        "market those matches under-deliver — so 'Model' above is information, not a value signal. "
        "Full results: `backtest/RESULTS.md`.",
        "* **Extra markets (v3):** 1X2 / double chance = score matrix blended 10/90 with the sharp market (Betfair "
        "Exchange, else market average), de-margined with the power method (removes the favourite-longshot bias). "
        "Corners and cards = team for/against rates, league-normalised and shrunk (K=40 / K=20), negative binomial "
        "totals; cards include a referee factor where the referee is published (UK leagues). Both are calibrated "
        "within ~2 points on the standard lines (`backtest/MARKETS_RESULTS.md`). Half-time corners have no free data "
        "source and are shown as Sportybet prices only, without a model.",
        "* **World coverage (v4):** every competition on Livescore.com that Sportybet prices is analysed with the same "
        "team-form model from Livescore's season results (goals markets only; corners and cards need the richer "
        "football-data feed of the 22 main European leagues). Sportybet's de-margined prices are the market view there.",
        "* **Safest bets** = goals, corners and cards selections at ≥70% on both the model and the de-margined Sportybet "
        "price, priced 1.30 or better; parlays and accumulators are no longer produced (the backtest showed they lose money).",
        "* **Sportybet prices** never enter the probability model except as the market view they represent.",
        f"* Data: football-data.co.uk, Livescore.com. All times are {TZL} ({CONFIG['TIMEZONE']}). ⚠️ marks teams with too little history "
        "— they are never shortlisted.",
        "* This is statistical information, not advice. Past hit-rates do not guarantee future results.",
    ]
    L.append("")
    return "\n".join(L)


def render_readme_block(ctx: dict, rows: list[MatchRow], picks: dict, summary: dict, report_rel: str) -> str:
    now = ctx["now"]
    L = [f"### Latest scan — {now:%A %d %B %Y} ({now:%H:%M} {TZL})", "",
         f"{len(rows)} fixtures scanned · window {ctx['start']:%a %H:%M} → {ctx['end']:%a %H:%M} {TZL} · "
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
                         f"{stars(r.p_final[mkt], mkt)} |")
            if len(sel) > 8:
                L.append(f"| … | _{len(sel) - 8} more in the full report_ | | | |")
        else:
            L.append("_None met the criteria._")
        L.append("")
    pr = ctx.get("parlays") or {}
    if pr:
        L.append(f"**Parlays ({run_desc(ctx.get('run', ''))}, {pr['source']})** — see [dossier]({report_rel.replace('.md', '-parlays.md')})")
        L.append("")
        for i, pl in enumerate(pr["parlays"], 1):
            legs = "; ".join(f"{l.match} — {l.label} @ {l.odds:.2f}" for l in pl)
            L.append(f"{i}. @ **{parlay_mod.parlay_odds(pl):.2f}** (P {pct(parlay_mod.parlay_p(pl))}): {legs}")
        if not pr["parlays"]:
            L.append("_none possible in this window_")
        L.append("")
    L.append("**Tracker**")
    L.append("")
    L += render_tracker(summary)
    L.append("")
    L += render_parlay_history(ctx.get("parlay_summary", {}), [])
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
            "xg_home_final": round(r.lam_h, 3), "xg_away_final": round(r.lam_a, 3),
            "xg_home_model": round(r.mod_h, 3), "xg_away_model": round(r.mod_a, 3),
            "xg_home_market": None if math.isnan(r.mkt_h) else round(r.mkt_h, 3),
            "xg_away_market": None if math.isnan(r.mkt_a) else round(r.mkt_a, 3),
            "basis": r.basis,
            "p_over15": round(r.p_final["O15"], 3), "p_over25": round(r.p_final["O25"], 3),
            "p_over35": round(r.p_final["O35"], 3), "p_btts": round(r.p_final["BTTS"], 3),
            "p_model_over15": round(r.p_model["O15"], 3), "p_model_over25": round(r.p_model["O25"], 3),
            "p_model_btts": round(r.p_model["BTTS"], 3),
            "odds_over25_avg": fx["odds_over"], "odds_under25_avg": fx["odds_under"],
            "odds_over25_b365": fx["b365_over"], "odds_under25_b365": fx["b365_under"],
            "p_market_over25": None if math.isnan(r.p_market_o25) else round(r.p_market_o25, 3),
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
            "p_home": r.extra.x12.get("H"), "p_draw": r.extra.x12.get("D"), "p_away": r.extra.x12.get("A"),
            "p_home_scores": r.extra.tg.get("H_o05"), "p_away_scores": r.extra.tg.get("A_o05"),
            "exp_corners_home": r.extra.corners.eh if r.extra.corners else None,
            "exp_corners_away": r.extra.corners.ea if r.extra.corners else None,
            "p_corners_over95": r.extra.corner_p["total"][9.5] if r.extra.corner_p else None,
            "exp_cards_home": r.extra.cards.eh if r.extra.cards else None,
            "exp_cards_away": r.extra.cards.ea if r.extra.cards else None,
            "p_cards_over45": r.extra.card_p["total"][4.5] if r.extra.card_p else None,
            "sportybet_home": r.sb["1X2"][0] if r.sb and r.sb.get("1X2") else None,
            "sportybet_draw": r.sb["1X2"][1] if r.sb and r.sb.get("1X2") else None,
            "sportybet_away": r.sb["1X2"][2] if r.sb and r.sb.get("1X2") else None,
            "sportybet_over25": sb_price(r, "O25"), "sportybet_btts": sb_price(r, "BTTS"),
        })
    pd.DataFrame(recs).round(3).to_csv(path, index=False)


def render_dossier(ctx: dict, pr: dict, ids: list[str], rows_by_key: dict, headlines: dict) -> str:
    """Parlay dossier: every parlay, then the full data sheet of every match involved (+ headlines)."""
    now = ctx["now"]
    L = [f"# 🎟️ Parlay dossier — {now:%A %d %B %Y}, {run_desc(ctx['run'], True)}", ""]
    lo, hi = CONFIG["PARLAY_ODDS"]
    L.append(f"_{len(pr['parlays'])} parlay(s) · combined odds {lo:.2f}–{hi:.2f} · prices: {pr['source']} · "
             f"generated {now:%H:%M} {TZL}. Full method and the honest backtest warning are in the main report._")
    L.append("")
    if not pr["parlays"]:
        L.append("_No parlay could be built for this window._")
        return "\n".join(L)
    L.append("## Summary")
    L.append("")
    for i, pl in enumerate(pr["parlays"], 1):
        odds, p = parlay_mod.parlay_odds(pl), parlay_mod.parlay_p(pl)
        pid = ids[i - 1] if i - 1 < len(ids) else ""
        L.append(f"### Parlay {i} — {len(pl)} legs @ **{odds:.2f}** · win probability **{pct(p)}** · "
                 f"expected return {100 * (p * odds - 1):+.1f}% · id `{pid}`")
        L.append("")
        L.append("| Kick-off | Match | Competition | Selection | Price | Fair odds | Probability | Leg edge |")
        L.append("|---|---|---|---|---|---|---|---|")
        for l in pl:
            L.append(leg_row(l))
        L.append("")
    L.append("## Match data sheets")
    L.append("")
    seen = set()
    for i, pl in enumerate(pr["parlays"], 1):
        for l in pl:
            if l.key in seen:
                continue
            seen.add(l.key)
            r = rows_by_key.get(l.key)
            if r is None:
                continue
            L.append(f"### {r.label} — {comp(r)}, {ko(r)} (parlay {i}: {l.label} @ {l.odds:.2f})")
            L.append("")
            L.append(f"* Final expected goals **{r.lam_h:.2f} – {r.lam_a:.2f}** ({r.basis}) · P(O1.5) {pct(r.p_final['O15'])} · "
                     f"P(O2.5) **{pct(r.p_final['O25'])}** · P(O3.5) {pct(r.p_final['O35'])} · P(BTTS) **{pct(r.p_final['BTTS'])}**"
                     + (f" · Sportybet O2.5 {fmt_odds(sb_price(r, 'O25'))} / BTTS {fmt_odds(sb_price(r, 'BTTS'))}" if r.sb else ""))
            L.append(f"* Team-form model alone: {r.mod_h:.2f} – {r.mod_a:.2f}"
                     + (f" · market-implied {r.mkt_h:.2f} – {r.mkt_a:.2f}" if not math.isnan(r.mkt_h) else "")
                     + f" · league avg {r.div_avg.mu_h:.2f} + {r.div_avg.mu_a:.2f} goals, O2.5 in {pct(r.div_avg.o25_rate)}")
            if pd.notna(r.fx.get("odds_h")):
                L.append(f"* Market average 1X2 {f2(r.fx['odds_h'])} / {f2(r.fx['odds_d'])} / {f2(r.fx['odds_a'])}"
                         + (f" · O/U 2.5 {f2(r.fx['odds_over'])} / {f2(r.fx['odds_under'])}" if pd.notna(r.fx.get("odds_over")) else "")
                         + (f" · Betfair Exchange 1X2 {f2(r.fx['bfe_h'])} / {f2(r.fx['bfe_d'])} / {f2(r.fx['bfe_a'])}" if pd.notna(r.fx.get("bfe_h")) else ""))
            L += render_extra_lines(r)
            L.append("")
            L += render_team_block(r.home, "Home")
            L += render_team_block(r.away, "Away")
            if r.h2h:
                parts = [f"{m['date']:%d %b %y}: {m['home']} {m['hg']}-{m['ag']} {m['away']}" for m in r.h2h]
                tot = [m["hg"] + m["ag"] for m in r.h2h]
                L.append(f"**Head-to-head** (last {len(r.h2h)}): avg {np.mean(tot):.1f} goals, O2.5 in {sum(t >= 3 for t in tot)}/{len(tot)}, "
                         f"BTTS in {sum(m['hg'] > 0 and m['ag'] > 0 for m in r.h2h)}/{len(tot)}  ")
                L.append("; ".join(parts))
                L.append("")
            for team in (r.fx["home"], r.fx["away"]):
                hs = headlines.get(team) or []
                L.append(f"**{team} — recent headlines** _(Google News, context only, not used by the model)_")
                L.append("")
                if hs:
                    for h in hs:
                        when = h["when"].astimezone(now.tzinfo).strftime("%d %b") if h.get("when") else ""
                        L.append(f"* {when} · {h['source']}: {h['title']}")
                else:
                    L.append("* _no recent headlines found_")
                L.append("")
    return "\n".join(L)


def weekly_digest(tracker: pd.DataFrame, ledger: pd.DataFrame, now: datetime) -> list[str]:
    """Monday digest: last 7 days + all time for the shortlists and parlays."""
    L = ["## 📅 Weekly digest", ""]
    cut = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    L.append("| Market | Last 7 days | Hit rate | All time | Hit rate | Backtest expectation |")
    L.append("|---|---|---|---|---|---|")
    for mkt, name in MARKETS.items():
        s = tracker[(tracker["market"] == mkt) & tracker["status"].isin(["hit", "miss"])] if not tracker.empty else tracker
        wk = s[s["match_date"] >= cut] if not s.empty else s
        h_all, h_wk = int((s["status"] == "hit").sum()) if not s.empty else 0, int((wk["status"] == "hit").sum()) if not wk.empty else 0
        L.append(f"| {name} | {h_wk}/{len(wk)} | {pct(h_wk / len(wk)) if len(wk) else '–'} | {h_all}/{len(s)} | "
                 f"{pct(h_all / len(s)) if len(s) else '–'} | {CONFIG['BACKTEST'][mkt].split(' of')[0]} |")
    ps = parlay_mod.summary(ledger, now)
    wk = ledger[(ledger["created"] >= cut)] if not ledger.empty else ledger
    wks = parlay_mod._stats(wk)
    a = ps["all"]
    L.append(f"| Parlays | {wks['won']}/{wks['n']} | {pct(wks['rate'])} | {a['won']}/{a['n']} | {pct(a['rate'])} | "
             f"30-33% wins, −4% to −13% return |")
    L.append("")
    if a["n"]:
        L.append(f"Parlay flat-stake return: last 7 days {100 * wks['roi']:+.1f}% · all time {100 * a['roi']:+.1f}% "
                 f"(avg odds {f2(a['avg_odds'])}, model expected {pct(a['exp_rate'])} wins vs actual {pct(a['rate'])}).")
        L.append("")
    return L


def digest_text(lines: list[str]) -> str:
    """Plain-text version of the digest for Telegram."""
    out = ["📅 <b>Weekly digest</b>"]
    for ln in lines:
        if ln.startswith("|") and not ln.startswith("|---"):
            cells = [c.strip().replace("**", "") for c in ln.strip("|").split("|")]
            if cells[0] == "Market":
                continue
            out.append(f"• {html.escape(cells[0])}: week {cells[1]} ({cells[2]}), all {cells[3]} ({cells[4]})")
        elif ln and not ln.startswith("#") and not ln.startswith("|"):
            out.append(html.escape(ln))
    return "\n".join(out)


def send_telegram_document(path: Path, caption: str) -> bool:
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat or not path.exists():
        return False
    try:
        with open(path, "rb") as fh:
            r = SESSION.post(f"https://api.telegram.org/bot{token}/sendDocument", data={"chat_id": chat, "caption": caption[:1000]},
                             files={"document": (path.name, fh, "application/pdf" if path.suffix == ".pdf" else "text/plain")}, timeout=60)
        if r.status_code != 200:
            log.warning("Telegram document error %s: %s", r.status_code, r.text[:200])
            return False
        return True
    except (requests.RequestException, OSError) as exc:
        log.warning("Telegram document failed: %s", exc)
        return False


def telegram_text(ctx: dict, rows: list[MatchRow], picks: dict, report_url: str | None) -> str:
    now = ctx["now"]
    cov = ctx.get("coverage") or {}
    L = [f"⚽ <b>PlayReport — {now:%a %d %b}, {run_desc(ctx.get('run', ''))}</b>",
         f"{len(rows)} fixtures · {cov.get('competitions', 0)} competitions · {cov.get('priced', 0)} priced by Sportybet · times in {TZL}"]
    botd = ctx.get("botd") or []
    if botd:
        L.append("")
        L.append(f"⭐ <b>Bets of the day</b>")
        icon = {"hit": "✅", "miss": "❌", "pending": "", "void": "⚪"}
        for b in botd:
            L.append(f"• {b['kickoff'][11:]} {html.escape(b['home'])} v {html.escape(b['away'])} — <b>{html.escape(b['label'])}</b> "
                     f"@ {b['odds']:.2f} · {pct(b['p'])} {icon.get(b['status'], '')}")
    sf = ctx.get("safe") or {}
    bets = sf.get("bets") or []
    L.append("")
    L.append(f"🔒 <b>Safest bets</b> (≥{pct(sf.get('min_p', 0.7))} on both views, price ≥ {sf.get('min_odds', 1.3):.2f}) — {len(bets)}")
    if not bets:
        L.append("nothing priced met the rules in this window")
    for b in bets[:12]:
        L.append(f"• {b.kickoff[5:]} {html.escape(b.home)} v {html.escape(b.away)} — <b>{html.escape(b.label)}</b> @ {b.odds:.2f} · {pct(b.p)}")
    if len(bets) > 12:
        L.append(f"… +{len(bets) - 12} more in the app")
    for mkt, name in MARKETS.items():
        sel = picks.get(mkt, [])
        L.append("")
        L.append(f"<b>{name}</b> ({len(sel)})")
        if not sel:
            L.append("none today")
        for r in sel[:6]:
            L.append(f"• {r.fx['kickoff']:%H:%M} {html.escape(r.label)} — {html.escape(r.fx['league'])} — "
                     f"<b>{pct(r.p_final[mkt])}</b> {stars(r.p_final[mkt], mkt)}")
        if len(sel) > 6:
            L.append(f"… +{len(sel) - 6} more")
    if report_url:
        L += ["", f'<a href="{report_url}">Full report</a>']
    return "\n".join(L)


def alert_text(new_bets: list, now: datetime) -> str:
    L = [f"🎯 <b>New safest bet{'s' if len(new_bets) > 1 else ''} found</b> · {now:%a %H:%M} {TZL}"]
    for b in new_bets[:10]:
        L.append(f"• {b.kickoff[5:]} {html.escape(b.home)} v {html.escape(b.away)} ({html.escape(b.league)}) — "
                 f"<b>{html.escape(b.label)}</b> @ {b.odds:.2f} · {pct(b.p)}")
    if len(new_bets) > 10:
        L.append(f"… +{len(new_bets) - 10} more in the app")
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
            else:
                log.info("Telegram: message sent (%d chars)", len(c))
        except requests.RequestException as exc:
            log.warning("Telegram failed: %s", exc)


# ----------------------------------------------------------------------------- main
def all_sels(r: MatchRow) -> list[dict]:
    """Every modelled selection of a match as plain dicts (probability views + Sportybet price), best first."""
    sels = sorted(safe_mod.selections(r), key=lambda s: (-s.p, -(s.odds or 0)))
    return [safe_mod.sel_dict(s, r.fx["home"], r.fx["away"]) for s in sels]


def top_sels(r: MatchRow) -> list[dict]:
    """The three best priced selections (for the day history)."""
    out = [d for d in all_sels(r) if d["odds"] and d["odds"] >= safe_mod.MIN_ODDS and not d["diff"]]
    return [{"sel": d["sel"], "label": d["label"], "p": d["p"], "odds": d["odds"]} for d in out[:3]]


def main() -> None:
    tz = ZoneInfo(CONFIG["TIMEZONE"])
    override = os.getenv("SCAN_NOW")  # e.g. "2026-09-26 07:00" for testing
    now = datetime.strptime(override, "%Y-%m-%d %H:%M").replace(tzinfo=tz) if override else datetime.now(tz)
    tz_off = int(now.utcoffset().total_seconds() // 3600)
    start = now - timedelta(minutes=5)
    end = now + timedelta(hours=CONFIG["WINDOW_HOURS"])
    run_label, window_end = run_schedule(now)
    report_run = is_report_run(run_label)
    ctx = {"now": now, "start": start, "end": end, "run": run_label, "window_end": window_end}
    log.info("Run %s (%s): scan window %s -> %s, state %s", run_label, "report" if report_run else "refresh", start, end, STATE)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    fixtures = load_fixtures(tz)
    todays = fixtures[(fixtures["kickoff"] >= start) & (fixtures["kickoff"] <= end)] if not fixtures.empty else fixtures
    log.info("football-data: %d upcoming fixtures in feed, %d inside the window", len(fixtures), len(todays))

    # ---- world spine (Livescore): every match in the window that the feeds above do not cover
    ls_events, ls_map, archive = [], {}, None
    if CONFIG["LIVESCORE"]:
        try:
            ls_events = worldfeed.fetch_window(start, end, tz_off)
            log.info("Livescore: %d events on the window days", len(ls_events))
        except Exception as exc:  # noqa: BLE001
            log.warning("Livescore window failed: %s", exc)
    if ls_events and not todays.empty:
        try:
            ls_map = livescore.match_fixtures(todays, now, tz_off, events=ls_events)
        except Exception as exc:  # noqa: BLE001
            log.warning("Livescore matching failed: %s", exc)
    if CONFIG["WORLD"] and ls_events:
        used = {v["eid"] for v in ls_map.values()}
        world_events = [e for e in worldfeed.upcoming(ls_events, start, end) if e["eid"] not in used]
        world_fx = worldfeed.fixtures_frame(world_events, tz)
        if not world_fx.empty:
            base = todays.copy()
            base["home_id"] = None
            base["away_id"] = None
            base["eid"] = None
            todays = pd.concat([base, world_fx], ignore_index=True).sort_values(["kickoff", "country", "league"]).reset_index(drop=True)
            # rebuild the fixture-index -> livescore map on the new index
            by_eid = {e["eid"]: e for e in ls_events}
            old_eids = {}
            for i, row in base.iterrows():
                if i in ls_map:
                    old_eids[(row["kickoff"], row["country"], row["home"], row["away"])] = ls_map[i]
            ls_map = {}
            for i, row in todays.iterrows():
                if row.get("eid") and row["eid"] in by_eid:
                    ls_map[i] = worldfeed.ls_entry(by_eid[row["eid"]])
                else:
                    ev = old_eids.get((row["kickoff"], row["country"], row["home"], row["away"]))
                    if ev:
                        ls_map[i] = ev
        log.info("World spine: %d Livescore fixtures added (%d matched to feed fixtures)", len(world_fx), len(used))
        try:
            archive = worldfeed.Archive(LS_DIR)
            archive.absorb_days(ls_events, now)
            archive.refresh(worldfeed.stage_priorities(todays), now, tz_off)
            archive.save()
        except Exception as exc:  # noqa: BLE001
            log.warning("Livescore archive failed: %s", exc)
    elif todays.empty:
        pass

    tracker = load_tracker()
    pending = tracker[tracker["status"] == "pending"] if not tracker.empty else tracker

    # which history files do we need? whole country systems, so promoted/relegated teams keep their history
    countries = set(todays["country"]) if not todays.empty else set()
    countries |= set(pending["country"]) if not pending.empty else set()
    main_divs = {d for d, (c, _) in MAIN_LEAGUES.items() if c in countries}
    extra_codes = {code for c, code in EXTRA_LEAGUES.items() if c in countries}

    seasons = season_codes(now)
    older = []
    y = now.year if now.month >= 7 else now.year - 1
    for k in range(2, CONFIG["H2H_SEASONS"]):
        older.append(f"{(y - k) % 100:02d}{(y - k + 1) % 100:02d}")
    since = datetime(now.year, now.month, now.day) - timedelta(days=CONFIG["MAX_HISTORY_DAYS"])
    main_all = load_main_results(main_divs, seasons + older, live_seasons=(seasons[0],))
    extra_all = load_extra_results(extra_codes, since - timedelta(days=365 * 3))
    world_all = archive.results_frame(since - timedelta(days=365 * 3)) if archive is not None else pd.DataFrame()
    pool = pd.concat([f for f in (main_all, extra_all, world_all) if f is not None and not f.empty] or [empty_results()],
                     ignore_index=True)
    pool = pool.dropna(subset=["date", "hg", "ag"]).sort_values("date", ascending=False).reset_index(drop=True)
    results = pool[pool["date"] >= since].reset_index(drop=True)
    log.info("History pool: %d matches for the model (%d incl. older seasons for head-to-head; %d from Livescore)",
             len(results), len(pool), 0 if world_all is None or world_all.empty else len(world_all))

    div_avgs = compute_div_avgs(results, now)
    long = make_long(results, div_avgs)
    MODELS["corners"] = markets.CountModel(results, "hc", "ac", now, markets.CORNERS)
    cards_df = results.assign(hcards=results["hy"].fillna(0) + results["hr"].fillna(0),
                              acards=results["ay"].fillna(0) + results["ar"].fillna(0))
    cards_df.loc[results["hy"].isna(), ["hcards", "acards"]] = np.nan
    MODELS["cards"] = markets.CountModel(cards_df, "hcards", "acards", now, markets.CARDS, use_ref=True)

    rows = [analyse(fx, long, results, div_avgs, now, pool) for _, fx in todays.iterrows()]

    # ---- Sportybet prices
    sbmap, sb_ok = {}, False
    if CONFIG["SPORTYBET"] and rows:
        events = sporty.fetch_upcoming(CONFIG["WINDOW_HOURS"] + 6)
        sb_ok = bool(events)
        sbmap = sporty.match_fixtures(todays, events) if events else {}
    attach_prices(rows, sbmap, todays)
    ctx["sb_ok"] = sb_ok
    # full market lists (corners / cards) for the main-league matches the count models cover
    n_full = 0
    if sb_ok:
        for r in sorted(rows, key=lambda r: r.fx["kickoff"]):
            if n_full >= CONFIG["FULL_MARKETS_MAX"]:
                break
            if r.fx["source"] == "main" and r.sb_event and r.sb_event.get("id") and (r.extra.corners or r.extra.cards):
                r.sb_full = sporty.fetch_event_markets(r.sb_event["id"])
                n_full += 1
    log.info("Sportybet: %d fixtures priced, %d full market lists", len(sbmap), n_full)
    picks = select_picks(rows)

    # ---- trends (team / match / head-to-head)
    try:
        lg_tr = trends_mod._long(pool)
        for r in rows:
            r.trends = trends_mod.for_fixture(lg_tr, r.fx, r.h2h)
    except Exception as exc:  # noqa: BLE001
        log.warning("Trends failed: %s", exc)

    # ---- day history with late scores
    days = None
    results_s = results
    try:
        days = history_mod.Days(DAYS_DIR, now)
        days.upsert(rows, comp, ls_map, top_sels)
        extra = days.fill_scores(results)
        if not extra.empty:
            results_s = pd.concat([results, extra], ignore_index=True)
            log.info("History: %d late score(s) from Livescore added for settlement", len(extra))
    except Exception as exc:  # noqa: BLE001
        log.warning("Day history failed: %s", exc)

    # ---- legacy ledgers (parlays / trebles are no longer produced; pending ones are still graded)
    ledger = parlay_mod.load_ledger(PARLAY_FILE)
    if not ledger.empty and (ledger["status"] == "pending").any():
        ledger = parlay_mod.settle(ledger, results_s, now)
        ledger.to_csv(PARLAY_FILE, index=False)
    pr = {"parlays": [], "legs": [], "source": "none", "extended": False}
    ctx.update({"parlays": pr, "parlay_ids": [], "parlay_summary": parlay_mod.summary(ledger, now), "parlay_recent": []})

    # ---- safest bets (goals / corners / cards, both views agree, price >= 1.30) + bets of the day
    safe_res = safe_mod.safest(rows, now, window_end, groups=safe_mod.SAFE_GROUPS, trebles=False)
    bets_df = safe_mod.load_csv(SAFE_BETS_FILE, safe_mod.SAFE_BET_COLS)
    accas_df = safe_mod.load_csv(SAFE_ACCAS_FILE, safe_mod.ACCA_COLS)
    bets_df = safe_mod.settle_bets(bets_df, results_s, now)
    if not accas_df.empty and (accas_df["status"] == "pending").any():
        accas_df = safe_mod.settle_accas(accas_df, results_s, now)
        accas_df.to_csv(SAFE_ACCAS_FILE, index=False)
    bets_df, new_bets = safe_mod.add_bets(bets_df, safe_res["bets"], now, run_label)
    bets_df = safe_mod.pick_bets_of_the_day(bets_df, now, CONFIG["BOTD_N"])
    bets_df.to_csv(SAFE_BETS_FILE, index=False)
    safe_res["ids"] = []
    ctx["safe"] = safe_res
    ctx["safe_summary"] = safe_mod.summary(bets_df, accas_df, now)
    ctx["botd"] = safe_mod.bets_of_the_day(bets_df, now)
    log.info("Safest: %d bets (%d new), bets of the day: %d", len(safe_res["bets"]), len(new_bets), len(ctx["botd"]))

    # ---- alerts for the app (new safest bets), kept in state
    alerts_file = DATA_DIR / "app" / "alerts.json"
    try:
        alerts = json.loads(alerts_file.read_text(encoding="utf-8")) if alerts_file.exists() else []
    except (OSError, ValueError):
        alerts = []
    for b in new_bets:
        alerts.append({"id": safe_mod.bet_id(b.key[0], b.home, b.away, b.sel), "ts": now.strftime("%Y-%m-%d %H:%M"),
                       "title": f"New safest bet · {b.label}", "kickoff": b.kickoff,
                       "text": f"{b.home} v {b.away} · {b.kickoff[5:]} · {b.odds:.2f} · {pct(b.p)}",
                       "fixture": appdata.fixture_id(b.key[0], b.key[1], b.home, b.away)})
    alerts = alerts[-50:]

    notes = []
    lowdata = sum(1 for r in rows if not r.data_ok)
    if lowdata:
        notes.append(f"{lowdata} fixture(s) flagged ⚠️ low data and excluded from shortlists.")
    if CONFIG["SPORTYBET"]:
        notes.append(f"Sportybet ({sporty.CC.upper()}): {len(sbmap)} of {len(rows)} fixtures priced." if sb_ok
                     else "Sportybet prices unavailable this run — average market prices shown instead.")
    coverage = {"fixtures": len(rows), "competitions": len({comp(r) for r in rows}), "priced": len(sbmap),
                "main": sum(1 for r in rows if r.fx["source"] == "main"), "extra": sum(1 for r in rows if r.fx["source"] == "extra"),
                "world": sum(1 for r in rows if r.fx["source"] == "world"), "data_ok": sum(1 for r in rows if r.data_ok)}
    ctx["coverage"] = coverage

    today_str = now.strftime("%Y-%m-%d")
    tracker = settle_tracker(tracker, results_s, now)
    tracker = add_picks(tracker, picks, now)
    tracker.to_csv(TRACKER_FILE, index=False)
    summary = tracker_summary(tracker, now)

    # ---- day history files + team pages for the app
    days_index = []
    if days is not None:
        try:
            days.annotate(tracker, ledger, accas_df, bets_df)
            days_index = days.summarise()
            log.info("History: %d day file(s) written", days.write())
        except Exception as exc:  # noqa: BLE001
            log.warning("Day history write failed: %s", exc)
    try:
        log.info("Team pages: %d division file(s)", len(teamstats.export(results, now, TEAMS_DIR)))
    except Exception as exc:  # noqa: BLE001
        log.warning("Team pages failed: %s", exc)

    digest_lines = []
    if now.weekday() == 0 and run_label == f"{CONFIG['RUN_HOURS'][0]:02d}:00":
        digest_lines = weekly_digest(tracker, ledger, now)
        ctx["digest"] = digest_lines

    report_md = render_report(ctx, rows, picks, summary, notes)
    (REPORTS_DIR / f"{today_str}.md").write_text(report_md, encoding="utf-8")
    (REPORTS_DIR / "latest.md").write_text(report_md, encoding="utf-8")
    rows_to_csv(rows, REPORTS_DIR / f"{today_str}.csv")
    # ---- structured export for the Android app
    try:
        appdata.export(APP_FILE, ctx=ctx, rows=rows, picks=picks, tracker_summary=summary, notes=notes, ls_map=ls_map,
                       helpers={"render_details": render_details, "stars": stars, "comp": comp, "sb_price": sb_price,
                                "selections": all_sels},
                       reports_dir=REPORTS_DIR, tz_label=TZL, thresholds=CONFIG["THRESHOLDS"],
                       backtest=CONFIG["BACKTEST"], repo=os.getenv("GITHUB_REPOSITORY", "perfectndumiso1-netizen/goals-scanner"),
                       days_index=days_index, safe_summary=ctx["safe_summary"], botd=ctx["botd"], alerts=alerts,
                       coverage=coverage, safe_groups=safe_mod.SAFE_GROUPS,
                       extra_badges=archive.badge_map() if archive is not None else None, report_run=report_run)
        log.info("App data: %s", APP_FILE)
    except Exception as exc:  # noqa: BLE001 - never lose the run because of the app export
        log.exception("App data export failed: %s", exc)
    if os.getenv("README_AUTO") == "1":
        update_readme(render_readme_block(ctx, rows, picks, summary, f"reports/{today_str}.md"))

    pdf_report = None
    if report_run and CONFIG["PDF"] and pdfgen is not None:
        stamp = f"{today_str}-{now:%H%M}"
        try:
            pdf_report = pdfgen.markdown_to_pdf(report_md, PDF_DIR / f"playreport-{stamp}.pdf", "PlayReport",
                                                f"{run_desc(run_label, True).capitalize()} · full report")
        except Exception as exc:  # noqa: BLE001 - never lose the run because of the PDF
            log.warning("PDF generation failed: %s", exc)
    # keep only the newest PDFs in state
    for old_pdf in sorted(PDF_DIR.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)[12:]:
        old_pdf.unlink(missing_ok=True)

    repo = os.getenv("GITHUB_REPOSITORY")
    server = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    report_url = f"{server}/{repo}/blob/data/reports/{today_str}.md" if repo else None
    if report_run:
        send_telegram(telegram_text(ctx, rows, picks, report_url))
        if pdf_report:
            send_telegram_document(pdf_report, f"📄 PlayReport — {now:%a %d %b}, {run_desc(run_label, True)} ({len(rows)} fixtures)")
        mark_report_run(now, run_label)
    elif new_bets:
        send_telegram(alert_text(new_bets, now))
    if digest_lines:
        send_telegram(digest_text(digest_lines))

    for mkt, name in MARKETS.items():
        log.info("%s: %d pick(s)", name, len(picks[mkt]))
    log.info("Done. Report: %s", REPORTS_DIR / f"{today_str}.md")


if __name__ == "__main__":
    main()
