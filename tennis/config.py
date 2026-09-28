"""Tennis scanner configuration: paths, sources, coverage and model parameters.

Model parameters marked "validated" were chosen in tennis/backtest.py on 2010–2018 data and
evaluated on 2019–2026 (see tennis/BACKTEST_RESULTS.md). Nothing here is a bookmaker input.
"""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# All generated tennis files live under STATE (a clone of the `tennis-data` branch in CI).
STATE = Path(os.getenv("TENNIS_STATE_DIR", str(REPO)))
DATA = STATE / "data" / "tennis"
APP = STATE / "data" / "app" / "tennis"
REPORTS = STATE / "reports" / "tennis"
CACHE = Path(os.getenv("TENNIS_CACHE_DIR", "/tmp/tennis-cache"))   # raw downloads, never committed

MATCHES_DIR = DATA / "matches"          # Livescore results per day (YYYY-MM-DD.json)
PLAYERS_DIR = DATA / "players"          # identity bridge + player snapshots
TOURNAMENTS_DIR = DATA / "tournaments"  # surface resolution log
HISTORY_DIR = DATA / "history"          # processed historical base + per-day prediction files
TRACKER = DATA / "tracker.csv"
LATEST = DATA / "latest.json"

TZ_OFFSET_HOURS = 2                     # SAST (UTC+2) for display; all stored times are UTC

# ---------------------------------------------------------------- sources
SACKMANN_MIRROR = "https://raw.githubusercontent.com/Aneeshers/tennis-sackmann-archive/main/"
SACKMANN_YEARS = list(range(2005, 2027))
SACKMANN_LICENCE = "Historical match data compiled by Jeff Sackmann (tennisabstract.com), CC BY-NC-SA 4.0, via the Aneeshers archive mirror (June 2026 snapshot)."
BASE_END = "2026-06-07"                 # last date covered by the historical snapshot (Roland Garros 2026 included)
LIVESCORE = "https://prod-public-api.livescore.com/v1/api/app"
LIVESCORE_UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"
SPORTY_SPORT_ID = "sr%3Asport%3A5"      # tennis on Sportybet (Sportradar sport id 5)
SPORTY_MARKETS = {"186": "winner", "189": "total_games", "187": "game_handicap", "190": "p1_games", "191": "p2_games"}
BACKFILL_MAX_DAYS_PER_RUN = int(os.getenv("TENNIS_BACKFILL_DAYS", "45"))

# ---------------------------------------------------------------- coverage
# Livescore category names (Cnm) → (tour, level). Everything else (ITF, team events, exhibitions, doubles) is skipped.
CATEGORY_MAP = {
    "ATP 250": ("atp", "A"), "ATP 500": ("atp", "A"), "ATP 1000": ("atp", "M"), "ATP Masters 1000": ("atp", "M"),
    "Grand Slam": ("mixed", "G"), "ATP Finals": ("atp", "F"), "ATP Challenger": ("atp", "C"),
    "WTA 250": ("wta", "I"), "WTA 500": ("wta", "P"), "WTA 1000": ("wta", "PM"), "WTA Finals": ("wta", "F"),
    "WTA Challenger": ("wta", "C"), "WTA 125": ("wta", "C"), "WTA": ("wta", "I"), "ATP": ("atp", "A"),
}
GRAND_SLAM_TOKENS = ("australian open", "roland garros", "french open", "wimbledon", "us open")
SURFACES = ("Hard", "Clay", "Grass", "Carpet")

# ---------------------------------------------------------------- model (validated values are written by the backtest report)
ELO_INIT = 1500.0
# Rating parameters: chosen by log loss on 2012–2018 (training period), evaluated out of sample on 2019–2026.
# Full grid and results: tennis/BACKTEST_RESULTS.md (regenerate with `python3 -m tennis.backtest`).
ELO_K = 150.0            # K = ELO_K / (matches + ELO_OFFSET) ** ELO_SHAPE  (experience-based K schedule)
ELO_OFFSET = 5.0
ELO_SHAPE = 0.3
SURFACE_WEIGHT = 0.5     # blend of surface-specific and overall rating difference (validated: 0.0 / 0.25 / 0.5 / 0.75 / 1.0 tried)
ELO_SCALE = 500.0        # logistic scale of the rating difference (validated: 400 / 450 / 500; wider = better calibrated favourites)
FORM_SIGMA = {"atp": 0.08, "wta": 0.10}   # day-form spread of the serve-point difference in the game model (fitted on 2012–2018, evaluated 2019–2026; backtest §5)
MIN_MATCHES_RATED = 10   # below this a player's rating is labelled provisional
SERVE_FRESH_DAYS = 240   # serve/return traits older than this are flagged stale
SERVE_MIN_MATCHES = 8    # fewer serve-stat matches than this → LOW DATA CONFIDENCE on game markets
FORM_WINDOWS = (5, 10, 20)
SAMPLE_LABELS = ((1, 4, "Very small"), (5, 9, "Small"), (10, 19, "Moderate"), (20, 39, "Strong"), (40, 10**9, "Very strong"))

# Tour/surface serve-point baselines (share of points won by the server), computed from the historical
# base in tennis/stats.py::serve_baselines and cached; these defaults are only used before the base exists.
DEFAULT_SERVE_BASELINE = {("atp", "Hard"): 0.640, ("atp", "Clay"): 0.615, ("atp", "Grass"): 0.660,
                          ("wta", "Hard"): 0.570, ("wta", "Clay"): 0.560, ("wta", "Grass"): 0.585}

# ---------------------------------------------------------------- publication
MIN_ODDS = 1.30
EDGE_NOTE_PP = 5.0       # a selection is highlighted (not "safe") when model − implied ≥ this many points
GAME_EDGE_PP = 10.0      # game markets (totals / player games / handicap) need a larger gap: expected-total MAE ≈ 5 games
MAX_EDGE_PP = 20.0       # …and ≤ this: bigger gaps are far more often model blind spots than value → warning, not highlight
HIGHLIGHT_MIN_MATCHES = 30   # both players need this many rated matches before a disagreement is highlighted
LOOKAHEAD = timedelta(hours=36)
REPORT_HOURS_SAST = (8, 18)


def sample_label(n: int | None) -> str:
    if not n:
        return "No data"
    for lo, hi, lab in SAMPLE_LABELS:
        if lo <= n <= hi:
            return lab
    return "No data"


def ensure_dirs() -> None:
    for p in (MATCHES_DIR, PLAYERS_DIR, TOURNAMENTS_DIR, HISTORY_DIR, APP / "matches", APP / "players", APP / "days",
              APP / "tournaments", REPORTS, CACHE):
        p.mkdir(parents=True, exist_ok=True)
