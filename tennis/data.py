"""Tennis data access: historical base (Sackmann archive mirror), Livescore tennis fixtures/results,
Sportybet tennis prices, the player-identity bridge and tournament→surface resolution.

Rules: nothing is estimated or zero-filled here. A missing value stays None / NaN. Every stored
record carries its source.
"""
from __future__ import annotations

import gzip
import io
import json
import logging
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import config as C

log = logging.getLogger("tennis.data")
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": C.LIVESCORE_UA, "Accept": "application/json"})

ROUND_ORDER = {"Q1": 0, "Q2": 1, "Q3": 2, "RR": 3, "R128": 4, "R64": 5, "R32": 6, "R16": 7, "QF": 8, "SF": 9, "BR": 10, "F": 11}
STAT_COLS = ["ace", "df", "svpt", "1stIn", "1stWon", "2ndWon", "SvGms", "bpSaved", "bpFaced"]
BASE_COLS = ["tour", "level", "tourney_id", "tourney_name", "surface", "best_of", "round", "date", "match_num",
             "w_id", "w_name", "w_ioc", "w_rank", "l_id", "l_name", "l_ioc", "l_rank", "score", "minutes"] + \
            [f"w_{c}" for c in STAT_COLS] + [f"l_{c}" for c in STAT_COLS] + \
            ["w_games", "l_games", "w_sets", "l_sets", "tiebreaks", "retired", "src"]


# ------------------------------------------------------------------ names & identity
def norm_name(s: str | None) -> str:
    """'Félix Auger-Aliassime' → 'felix auger aliassime'; 'Mannarino, Adrian' → 'adrian mannarino'."""
    if not s:
        return ""
    s = str(s)
    if "," in s:
        last, first = s.split(",", 1)
        s = f"{first} {last}"
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[\-']", " ", s.lower())
    s = re.sub(r"[^a-z ]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def name_tokens(s: str) -> tuple[str, ...]:
    return tuple(norm_name(s).split())


def names_match(a: str, b: str) -> float:
    """0..1 similarity between two player names: 1 exact token set; 0.9 same last name + same first initial
    (covers 'A. Zverev' vs 'Alexander Zverev'); 0.8 same last two tokens (double surnames); else 0."""
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return 0.0
    if set(ta) == set(tb):
        return 1.0
    if ta[-1] == tb[-1] and ta[0][0] == tb[0][0]:
        return 0.9
    if len(ta) >= 2 and len(tb) >= 2 and ta[-2:] == tb[-2:]:
        return 0.8
    if len(ta) >= 2 and len(tb) >= 2 and ta[-1] == tb[-1] and (ta[-2] == tb[0] or tb[-2] == ta[0]):
        return 0.75
    return 0.0


# ------------------------------------------------------------------ score parsing
_SET_RE = re.compile(r"^(\d+)-(\d+)(?:\((\d+)\))?$")


def parse_score(score: str | None) -> dict:
    """'6-4 5-7 7-6(4)' → games/sets/tiebreaks/retired. Walkovers and unparsable scores → all None."""
    out = {"w_games": None, "l_games": None, "w_sets": None, "l_sets": None, "tiebreaks": None, "retired": False, "walkover": False}
    if not score or not isinstance(score, str):
        return out
    s = score.strip()
    if "W/O" in s.upper() or "WALKOVER" in s.upper() or s.upper() in ("DEF", "DEF."):
        out["walkover"] = True
        return out
    toks = s.replace("[", "").replace("]", "").split()
    wg = lg = ws = ls = tb = 0
    ok = False
    for t in toks:
        u = t.upper()
        if u in ("RET", "RET.", "ABD", "ABN", "DEF", "UNP"):
            out["retired"] = True
            continue
        m = _SET_RE.match(t)
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        if a > 30 or b > 30:          # 10-point match tiebreak written as a set e.g. 10-8: count as one game each way
            a, b = (1, 0) if a > b else (0, 1)
        ok = True
        wg += a
        lg += b
        if m.group(3) is not None or (a, b) in ((7, 6), (6, 7)):
            tb += 1
        if a > b:
            ws += 1
        elif b > a:
            ls += 1
    if not ok:
        return out
    out.update(w_games=wg, l_games=lg, w_sets=ws, l_sets=ls, tiebreaks=tb)
    return out


# ------------------------------------------------------------------ historical base
def _mirror_file(rel: str) -> Path | None:
    C.CACHE.mkdir(parents=True, exist_ok=True)
    p = C.CACHE / rel.replace("/", "_")
    if p.exists() and p.stat().st_size > 0:
        return p
    for attempt in range(3):
        try:
            r = SESSION.get(C.SACKMANN_MIRROR + rel, timeout=120)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            p.write_bytes(r.content)
            return p
        except Exception as exc:                       # noqa: BLE001
            log.warning("download %s failed (%s), attempt %d", rel, exc, attempt + 1)
            time.sleep(2 + 3 * attempt)
    return None


def _read_sackmann(path: Path, tour: str) -> pd.DataFrame:
    d = pd.read_csv(path, low_memory=False)
    keep = pd.DataFrame({
        "tour": tour, "level": d["tourney_level"].astype(str), "tourney_id": d["tourney_id"].astype(str),
        "tourney_name": d["tourney_name"].astype(str), "surface": d["surface"].where(d["surface"].isin(C.SURFACES), None),
        "best_of": pd.to_numeric(d["best_of"], errors="coerce"), "round": d["round"].astype(str),
        "date": pd.to_datetime(d["tourney_date"].astype(str), format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d"),
        "match_num": pd.to_numeric(d["match_num"], errors="coerce"),
        "w_id": d["winner_id"].astype(str), "w_name": d["winner_name"].astype(str), "w_ioc": d["winner_ioc"],
        "w_rank": pd.to_numeric(d["winner_rank"], errors="coerce"),
        "l_id": d["loser_id"].astype(str), "l_name": d["loser_name"].astype(str), "l_ioc": d["loser_ioc"],
        "l_rank": pd.to_numeric(d["loser_rank"], errors="coerce"), "score": d["score"].astype(str),
        "minutes": pd.to_numeric(d["minutes"], errors="coerce"),
    })
    for c in STAT_COLS:
        keep[f"w_{c}"] = pd.to_numeric(d.get(f"w_{c}"), errors="coerce")
        keep[f"l_{c}"] = pd.to_numeric(d.get(f"l_{c}"), errors="coerce")
    parsed = pd.DataFrame([parse_score(s) for s in keep["score"]])
    for c in ("w_games", "l_games", "w_sets", "l_sets", "tiebreaks", "retired"):
        keep[c] = parsed[c].values
    keep = keep[~parsed["walkover"].values]
    keep["src"] = "sackmann"
    return keep[BASE_COLS]


def build_base(years=None, force: bool = False) -> pd.DataFrame:
    """Download the archive files (cached) and write the unified base to HISTORY_DIR/base.csv.gz."""
    out = C.HISTORY_DIR / "base.csv.gz"
    if out.exists() and not force:
        return load_base()
    years = years or C.SACKMANN_YEARS
    parts = []
    for y in years:
        for rel, tour in ((f"atp/atp_matches_{y}.csv", "atp"), (f"atp/atp_matches_qual_chall_{y}.csv", "atp"),
                          (f"wta/wta_matches_{y}.csv", "wta")):
            p = _mirror_file(rel)
            if p is None:
                log.warning("archive file missing: %s", rel)
                continue
            try:
                parts.append(_read_sackmann(p, tour))
            except Exception as exc:                   # noqa: BLE001
                log.warning("cannot parse %s: %s", rel, exc)
    if not parts:
        raise RuntimeError("no historical tennis data could be loaded")
    base = pd.concat(parts, ignore_index=True)
    base = base[base["date"].notna() & (base["w_id"] != "nan") & (base["l_id"] != "nan")]
    # the ATP qual/chall files repeat main-draw qualifying of tour events that also sit in the main file: drop exact duplicates
    base = base.drop_duplicates(subset=["tour", "tourney_id", "w_id", "l_id", "round"], keep="first")
    base["round_order"] = base["round"].map(ROUND_ORDER).fillna(3).astype(int)
    base = base.sort_values(["date", "round_order", "tourney_id", "match_num"]).drop(columns="round_order").reset_index(drop=True)
    C.HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        base.to_csv(fh, index=False)
    # player table
    pl = pd.concat([base[["w_id", "w_name", "w_ioc", "tour"]].rename(columns={"w_id": "pid", "w_name": "name", "w_ioc": "ioc"}),
                    base[["l_id", "l_name", "l_ioc", "tour"]].rename(columns={"l_id": "pid", "l_name": "name", "l_ioc": "ioc"})])
    pl = pl.drop_duplicates("pid", keep="last")
    C.PLAYERS_DIR.mkdir(parents=True, exist_ok=True)
    pl.to_csv(C.PLAYERS_DIR / "players.csv", index=False)
    log.info("historical base: %d matches, %d players (%s → %s)", len(base), len(pl), base["date"].min(), base["date"].max())
    return base


def load_base() -> pd.DataFrame:
    out = C.HISTORY_DIR / "base.csv.gz"
    if not out.exists():
        return build_base()
    with gzip.open(out, "rt", encoding="utf-8") as fh:
        base = pd.read_csv(fh, low_memory=False, dtype={"w_id": str, "l_id": str, "tourney_id": str})
    return base


def load_players() -> pd.DataFrame:
    p = C.PLAYERS_DIR / "players.csv"
    if not p.exists():
        build_base()
    return pd.read_csv(p, dtype={"pid": str})


class PlayerIndex:
    """Bridges Livescore/Sportybet player names to historical player ids. Unmatched players get a new id
    ('ls<livescore id>') and start with no history — no one else's data is ever attached to them."""

    def __init__(self, players: pd.DataFrame):
        self.by_key: dict[str, list[dict]] = {}
        self.by_last: dict[str, list[dict]] = {}
        self.info: dict[str, dict] = {}
        for r in players.itertuples(index=False):
            rec = {"pid": str(r.pid), "name": r.name, "ioc": r.ioc if isinstance(r.ioc, str) else None, "tour": r.tour}
            self.info[rec["pid"]] = rec
            toks = name_tokens(r.name)
            if not toks:
                continue
            self.by_key.setdefault(" ".join(sorted(toks)), []).append(rec)
            self.by_last.setdefault(toks[-1], []).append(rec)
        p = C.PLAYERS_DIR / "identity.json"
        self.identity: dict[str, dict] = json.loads(p.read_text()) if p.exists() else {}

    def resolve(self, name: str, ioc: str | None = None, tour: str | None = None, ls_id: str | None = None) -> dict:
        """→ {'pid', 'name', 'how': 'exact'|'fuzzy'|'new', 'score'}; ls_id results are remembered in identity.json."""
        if ls_id and ls_id in self.identity:
            return self.identity[ls_id]
        toks = name_tokens(name)
        cands = list(self.by_key.get(" ".join(sorted(toks)), []))
        how, score = "exact", 1.0
        if not cands and toks:
            cands = [c for c in self.by_last.get(toks[-1], []) if names_match(name, c["name"]) >= 0.75]
            how, score = "fuzzy", max((names_match(name, c["name"]) for c in cands), default=0.0)
            cands = [c for c in cands if names_match(name, c["name"]) >= score - 1e-9]
        if ioc and len(cands) > 1:
            cands = [c for c in cands if c["ioc"] in (None, ioc)] or cands
        if tour and len(cands) > 1:
            cands = [c for c in cands if c["tour"] == tour] or cands
        if len(cands) == 1 and (how == "exact" or ioc is None or cands[0]["ioc"] in (None, ioc)):
            res = {"pid": cands[0]["pid"], "name": cands[0]["name"], "how": how, "score": round(score, 2)}
        else:
            # ambiguous or unknown → new identity (never guess between two people)
            res = {"pid": f"ls{ls_id}" if ls_id else f"new:{norm_name(name)}", "name": name, "how": "new",
                   "score": 0.0, "ambiguous": len(cands) > 1}
        if ls_id:
            self.identity[ls_id] = res
        return res

    def save(self) -> None:
        C.PLAYERS_DIR.mkdir(parents=True, exist_ok=True)
        (C.PLAYERS_DIR / "identity.json").write_text(json.dumps(self.identity, ensure_ascii=False, sort_keys=True))


# ------------------------------------------------------------------ surface resolution
_STOP = {"open", "atp", "wta", "ch", "challenger", "masters", "cup", "qualification", "qualifying", "international",
         "internationals", "championships", "championship", "classic", "the", "of", "de", "del", "tennis", "and",
         "men", "women", "singles", "mens", "womens", "presented", "by", "tour", "finals", "1000", "500", "250", "125"}


def tourney_key(name: str) -> tuple[str, ...]:
    s = norm_name(re.sub(r"\(.*?\)", " ", str(name)).split(":")[0].split(",")[0])
    return tuple(t for t in s.split() if t not in _STOP and not t.isdigit())


class SurfaceResolver:
    """Tournament → surface from the historical base (name tokens + calendar month) plus explicit overrides.
    Unknown tournaments stay N/A; nothing is guessed from the country or the season."""
    OVERRIDES = {  # Livescore naming that differs from the historical tournament names
        "china": "Hard", "japan tokyo": "Hard", "japan": "Hard", "korea seoul": "Hard", "korea": "Hard", "shanghai": "Hard",
        "paris": "Hard", "vienna": "Hard", "basel": "Hard", "stockholm": "Hard", "antwerp": "Hard", "almaty": "Hard",
        "brussels": "Hard", "wuhan": "Hard", "ningbo": "Hard", "hong kong": "Hard", "guangzhou": "Hard", "jiujiang": "Hard",
        "chennai": "Hard", "osaka": "Hard", "tokyo": "Hard", "hangzhou": "Hard", "chengdu": "Hard", "singapore": "Hard",
        "riyadh": "Hard", "turin": "Hard", "us": "Hard", "australian": "Hard", "roland garros": "Clay", "french": "Clay",
        "wimbledon": "Grass", "queens club": "Grass", "halle": "Grass", "eastbourne": "Grass", "mallorca": "Grass",
        "bad homburg": "Grass", "berlin": "Grass", "nottingham": "Grass", "s hertogenbosch": "Grass", "stuttgart": "Grass",
        "monte carlo": "Clay", "madrid": "Clay", "rome": "Clay", "italian": "Clay", "hamburg": "Clay", "gstaad": "Clay",
        "kitzbuhel": "Clay", "bastad": "Clay", "umag": "Clay", "estoril": "Clay", "barcelona": "Clay", "munich": "Clay",
        "bucharest": "Clay", "geneva": "Clay", "lyon": "Clay", "marrakech": "Clay", "houston": "Clay", "rio de janeiro": "Clay",
        "buenos aires": "Clay", "santiago": "Clay", "cordoba": "Clay", "indian wells": "Hard", "miami": "Hard",
        "cincinnati": "Hard", "canadian": "Hard", "canada": "Hard", "toronto": "Hard", "montreal": "Hard",
        "washington": "Hard", "winston salem": "Hard", "atlanta": "Hard", "los cabos": "Hard", "acapulco": "Hard",
        "dallas": "Hard", "delray beach": "Hard", "rotterdam": "Hard", "marseille": "Hard", "doha": "Hard", "dubai": "Hard",
        "montpellier": "Hard", "adelaide": "Hard", "brisbane": "Hard", "auckland": "Hard", "hobart": "Hard", "metz": "Hard",
        "athens": "Hard", "belgrade": "Hard", "sofia": "Hard", "san diego": "Hard", "cleveland": "Hard", "monterrey": "Hard",
        "merida": "Hard", "austin": "Hard", "linz": "Hard", "abu dhabi": "Hard", "charleston": "Clay", "strasbourg": "Clay",
        "rabat": "Clay", "prague": "Clay", "palermo": "Clay", "iasi": "Clay", "budapest": "Clay", "warsaw": "Clay",
        "lausanne": "Clay", "cluj napoca": "Hard", "tenerife": "Hard", "guadalajara": "Hard",
    }

    def __init__(self, base: pd.DataFrame | None):
        self.table: dict[tuple[str, ...], dict[int, dict[str, int]]] = {}
        if base is not None and len(base):
            g = base.dropna(subset=["surface"]).groupby(["tourney_name", base["date"].str.slice(5, 7)])["surface"] \
                .agg(lambda s: s.value_counts().to_dict()).reset_index()
            for r in g.itertuples(index=False):
                key = tourney_key(r.tourney_name)
                if key:
                    self.table.setdefault(key, {}).setdefault(int(r[1]), {})
                    for surf, n in r.surface.items():
                        self.table[key][int(r[1])][surf] = self.table[key][int(r[1])].get(surf, 0) + n
        self.log: list[dict] = []

    def resolve(self, stage_name: str, month: int) -> dict:
        key = tourney_key(stage_name)
        joined = " ".join(key)
        for k, surf in self.OVERRIDES.items():
            if joined == k or joined.startswith(k + " ") or joined.endswith(" " + k):
                return {"surface": surf, "how": "override", "name": stage_name}
        best, best_score = None, 0.0
        for tk, months in self.table.items():
            inter = len(set(tk) & set(key))
            if not inter:
                continue
            jac = inter / len(set(tk) | set(key))
            if jac < 0.5:
                continue
            for m in (month, month - 1, month + 1):
                mm = ((m - 1) % 12) + 1
                if mm in months:
                    counts = months[mm]
                    surf = max(counts, key=counts.get)
                    score = jac + (0.1 if mm == month else 0.0) + min(sum(counts.values()), 50) / 1000
                    if score > best_score:
                        best, best_score = {"surface": surf, "how": "history", "name": stage_name, "matched": " ".join(tk),
                                            "confidence": round(jac, 2)}, score
        if best:
            return best
        return {"surface": None, "how": "unresolved", "name": stage_name}


# ------------------------------------------------------------------ Livescore tennis
def _ls_get(path: str) -> dict | None:
    for attempt in range(3):
        try:
            r = SESSION.get(f"{C.LIVESCORE}/{path}", timeout=25)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (404, 410):
                return None
        except Exception as exc:                       # noqa: BLE001
            log.warning("livescore %s: %s", path, exc)
        time.sleep(1 + attempt)
    return None


def _esd(v) -> str | None:
    try:
        return datetime.strptime(str(int(v)), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc).strftime("%Y-%m-%d %H:%M")
    except Exception:                                  # noqa: BLE001
        return None


def classify_stage(stage: dict) -> dict | None:
    """Livescore stage → tour/level/tournament or None when outside coverage (ITF, doubles, team events…)."""
    cat = (stage.get("Cnm") or "").strip()
    snm = (stage.get("Snm") or "").strip()
    low = f"{cat} {snm}".lower()
    if any(x in low for x in ("doubles", "davis cup", "billie jean", "laver cup", "united cup", "team tournaments",
                              "hopman", "exhibition", "itf", "juniors", "wheelchair", "legends")):
        return None
    tl = C.CATEGORY_MAP.get(cat)
    if tl is None:
        return None
    tour, level = tl
    if any(t in low for t in C.GRAND_SLAM_TOKENS):
        level = "G"
    if tour == "mixed":
        tour = "wta" if "women" in low or "wta" in low else "atp"
    qual = "qualif" in low
    return {"tour": tour, "level": level, "tournament": snm, "category": cat, "qualifying": qual,
            "stage_id": str(stage.get("Sid") or "")}


def parse_event(ev: dict, stage: dict) -> dict | None:
    """One Livescore tennis event → normalised match record (singles only)."""
    t1, t2 = ev.get("T1") or [], ev.get("T2") or []
    if len(t1) != 1 or len(t2) != 1:
        return None
    sets, tb = [], []
    for i in range(1, 6):
        a, b = ev.get(f"Tr1S{i}"), ev.get(f"Tr2S{i}")
        if a in (None, "") or b in (None, ""):
            break
        try:
            sets.append([int(a), int(b)])
        except ValueError:
            break
        ta, tb_ = ev.get(f"Tr1S{i}T"), ev.get(f"Tr2S{i}T")
        tb.append([int(ta), int(tb_)] if ta not in (None, "") and tb_ not in (None, "") else None)
    status = str(ev.get("Eps") or "")
    s1, s2 = ev.get("Tr1"), ev.get("Tr2")
    try:
        sets_won = [int(s1), int(s2)] if s1 not in (None, "") and s2 not in (None, "") else None
    except ValueError:
        sets_won = None
    finished = status in ("FT", "Ret.", "Ret", "AET", "W.O.", "WO", "Def.") or status.lower().startswith("ret")
    cancelled = status in ("Canc.", "Postp.", "Abn.", "Canc", "Postp")
    winner = None
    if finished and sets_won and sets_won[0] != sets_won[1]:
        winner = 1 if sets_won[0] > sets_won[1] else 2
    elif finished and ev.get("Ewt") in (1, 2):
        winner = int(ev["Ewt"])
    return {
        "ls_id": str(ev.get("Eid")), "start": _esd(ev.get("Esd")), "status": status, "finished": finished,
        "cancelled": cancelled, "retired": status.lower().startswith("ret") or status in ("W.O.", "WO", "Def."),
        "p1": {"ls_id": str(t1[0].get("ID")), "name": t1[0].get("Nm"), "ioc": t1[0].get("CoId")},
        "p2": {"ls_id": str(t2[0].get("ID")), "name": t2[0].get("Nm"), "ioc": t2[0].get("CoId")},
        "sets": sets, "tiebreak_points": tb, "sets_won": sets_won, "winner": winner,
        "tour": stage["tour"], "level": stage["level"], "tournament": stage["tournament"], "category": stage["category"],
        "qualifying": stage["qualifying"], "stage_id": stage["stage_id"], "src": "livescore",
    }


def fetch_ls_day(day: date) -> list[dict]:
    """All covered singles events of one day (UTC times)."""
    j = _ls_get(f"date/tennis/{day.strftime('%Y%m%d')}/0?MD=1")
    if not j:
        return []
    out = []
    for st in j.get("Stages") or []:
        cls = classify_stage(st)
        if cls is None:
            continue
        for ev in st.get("Events") or []:
            rec = parse_event(ev, cls)
            if rec:
                rec["day"] = day.isoformat()
                out.append(rec)
    return out


def day_file(day: date | str) -> Path:
    return C.MATCHES_DIR / f"{day if isinstance(day, str) else day.isoformat()}.json"


def store_day(day: date, events: list[dict]) -> None:
    C.MATCHES_DIR.mkdir(parents=True, exist_ok=True)
    day_file(day).write_text(json.dumps({"day": day.isoformat(), "fetched": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                                         "src": "livescore", "events": events}, ensure_ascii=False))


def load_day(day: date | str) -> dict | None:
    p = day_file(day)
    return json.loads(p.read_text()) if p.exists() else None


def backfill_results(today: date, max_days: int | None = None) -> dict:
    """Fetch and store Livescore day files from the end of the historical base up to yesterday.
    A day is re-fetched while it still holds unfinished matches (up to 3 days back)."""
    max_days = max_days or C.BACKFILL_MAX_DAYS_PER_RUN
    start = date.fromisoformat(C.BASE_END) + timedelta(days=1)
    fetched, d = 0, start
    while d < today and fetched < max_days:
        existing = load_day(d)
        stale = existing is not None and (today - d).days <= 3 and any(not e["finished"] and not e["cancelled"] for e in existing["events"])
        if existing is None or stale:
            store_day(d, fetch_ls_day(d))
            fetched += 1
        d += timedelta(days=1)
    return {"from": start.isoformat(), "to": (today - timedelta(days=1)).isoformat(), "fetched": fetched,
            "complete": d >= today}


def load_results(since: str | None = None) -> list[dict]:
    """Finished singles matches stored from Livescore, oldest first, de-duplicated by event id."""
    out, seen = [], set()
    for p in sorted(C.MATCHES_DIR.glob("*.json")):
        if since and p.stem < since:
            continue
        j = json.loads(p.read_text())
        for e in j["events"]:
            if e["finished"] and e["winner"] and e["ls_id"] not in seen:
                seen.add(e["ls_id"])
                out.append(e)
    return out


# ------------------------------------------------------------------ Sportybet tennis prices (comparison layer only)
# Sportybet sits behind AWS WAF bot control: Python's HTTP/1.1 client gets a JavaScript challenge (HTTP 202)
# from cloud IPs such as GitHub's runners while curl over HTTP/2 is served normally, so curl is tried first.
# (Same approach as the football scanner; re-implemented here so tennis has no runtime dependency on it.)
SPORTY_BASE = "https://www.sportybet.com/api/za/factsCenter"
SPORTY_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
_CURL = shutil.which("curl")


def _sporty_get(url: str) -> dict | None:
    body, code = None, 0
    try:
        if _CURL:
            out = subprocess.run([_CURL, "-s", "--http2", "-m", "20", "-A", SPORTY_UA, "-H", "Accept: application/json",
                                  "-H", "Accept-Language: en", "-w", "\n%{http_code}", url],
                                 capture_output=True, text=True, timeout=30).stdout
            body, _, code_s = out.rpartition("\n")
            code = int(code_s or 0)
        if not _CURL or code != 200:
            r = SESSION.get(url, timeout=20, headers={"User-Agent": SPORTY_UA, "Accept": "application/json"})
            body, code = r.text, r.status_code
        if code != 200:
            log.warning("Sportybet HTTP %s for %s", code, url[:120])
            return None
        d = json.loads(body)
        if d.get("bizCode") not in (10000, None):
            log.warning("Sportybet bizCode %s: %s", d.get("bizCode"), str(d.get("message"))[:100])
            return None
        return d.get("data") or {}
    except (requests.RequestException, ValueError, subprocess.SubprocessError, OSError) as exc:
        log.warning("Sportybet request failed: %s", exc)
        return None


def fetch_sporty_tennis(hours_ahead: float = 48) -> list[dict]:
    """Upcoming Sportybet tennis events with Winner / Total games / Game handicap / Player games prices."""
    horizon = time.time() + hours_ahead * 3600
    events: list[dict] = []
    mk = "%2C".join(C.SPORTY_MARKETS)
    for page in range(1, 12):
        data = _sporty_get(f"{SPORTY_BASE}/pcUpcomingEvents?sportId={C.SPORTY_SPORT_ID}&marketId={mk}&pageSize=100&pageNum={page}&option=1")
        if not data:
            break
        n = 0
        for t in data.get("tournaments") or []:
            for e in t.get("events") or []:
                n += 1
                ko = e.get("estimateStartTime")
                if not ko or ko / 1000 > horizon:
                    continue
                events.append({"id": e.get("eventId"), "start": datetime.fromtimestamp(ko / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M"),
                               "tournament": t.get("name", ""), "category": t.get("categoryName", ""),
                               "p1": e.get("homeTeamName", ""), "p2": e.get("awayTeamName", ""),
                               "markets": parse_sporty_markets(e.get("markets") or [])})
        if n == 0:
            break
    log.info("Sportybet tennis: %d events within %.0f h", len(events), hours_ahead)
    return events


def _num(x):
    try:
        v = float(x)
        return v if np.isfinite(v) and v > 1.0 else None
    except (TypeError, ValueError):
        return None


def parse_sporty_markets(markets: list) -> dict:
    """→ {'winner': {'p1','p2'}, 'total_games': {line: {'over','under'}}, 'game_handicap': {hcp: {'p1','p2'}},
         'p1_games': {line: {...}}, 'p2_games': {line: {...}}}. Only sensible prices (>1.0) are kept."""
    out: dict = {}
    for m in markets:
        kind = C.SPORTY_MARKETS.get(str(m.get("id")))
        if not kind or m.get("status") not in (None, 0):
            continue
        outs = {(o.get("desc") or "").lower(): _num(o.get("odds")) for o in m.get("outcomes") or [] if o.get("isActive", 1)}
        spec = str(m.get("specifier") or "")
        if kind == "winner":
            if outs.get("home") and outs.get("away"):
                out["winner"] = {"p1": outs["home"], "p2": outs["away"]}
        elif kind in ("total_games", "p1_games", "p2_games"):
            mm = re.search(r"total=([\d.]+)", spec)
            over = next((v for k, v in outs.items() if k.startswith("over")), None)
            under = next((v for k, v in outs.items() if k.startswith("under")), None)
            if mm and over and under:
                out.setdefault(kind, {})[float(mm.group(1))] = {"over": over, "under": under}
        elif kind == "game_handicap":
            mm = re.search(r"hcp=(-?[\d.]+)", spec)
            if mm and outs.get("home") and outs.get("away"):
                out.setdefault(kind, {})[float(mm.group(1))] = {"p1": outs["home"], "p2": outs["away"]}
    return out


def match_prices(fixtures: list[dict], events: list[dict], tol_hours: float = 6.0) -> dict[str, dict]:
    """Fixture id → Sportybet event, matched on both player names (order-insensitive) and start time."""
    out: dict[str, dict] = {}
    for f in fixtures:
        t0 = datetime.strptime(f["start"], "%Y-%m-%d %H:%M") if f.get("start") else None
        best, best_s = None, 0.0
        for e in events:
            s_direct = min(names_match(f["p1"]["name"], e["p1"]), names_match(f["p2"]["name"], e["p2"]))
            s_swap = min(names_match(f["p1"]["name"], e["p2"]), names_match(f["p2"]["name"], e["p1"]))
            s = max(s_direct, s_swap)
            if s < 0.75:
                continue
            if t0:
                t1 = datetime.strptime(e["start"], "%Y-%m-%d %H:%M")
                if abs((t1 - t0).total_seconds()) > tol_hours * 3600:
                    continue
            if s > best_s:
                best, best_s = dict(e, swapped=s_swap > s_direct, name_score=s), s
        if best:
            out[f["ls_id"]] = best
    return out
