"""Player statistics built incrementally from match observations (strictly in date order).

PlayerStats.observe() is called once per finished match by the replay in tennis/history.py; features()
returns only what was observed before the moment it is called. Missing statistics stay None ("N/A"),
they are never imputed or zero-filled, and every figure carries its sample size and age.
"""
from __future__ import annotations

import json
import math
import re
from collections import deque
from datetime import date

from . import config as C

_TB_SET = re.compile(r"(\d+)-(\d+)\((\d+)\)")
HALF_LIFE_DAYS = 365.0
RECENT_KEEP = 40


def _days(a: str, b: str) -> int:
    try:
        return (date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days
    except Exception:                                  # noqa: BLE001
        return 0


def _safe_div(a, b):
    return None if not b else a / b


def tiebreaks_won(score: str | None) -> tuple[int, int]:
    """(tiebreak sets won by the match winner, by the loser) from a score string like '7-6(4) 6-7(3) 6-3'."""
    w = l = 0
    for m in _TB_SET.finditer(score if isinstance(score, str) else ""):
        a, b = int(m.group(1)), int(m.group(2))
        if (a, b) == (7, 6):
            w += 1
        elif (a, b) == (6, 7):
            l += 1
    return w, l


class _Player:
    __slots__ = ("recent", "sv_w", "sv_p", "rt_w", "rt_p", "first_in", "first_won", "second_won", "ace", "df", "svgms",
                 "bp_saved", "bp_faced", "bp_conv", "bp_created", "n_stat", "last_stat", "last", "opp_rt_w", "opp_sv_w",
                 "adj_p", "n")

    def __init__(self):
        self.recent = deque(maxlen=RECENT_KEEP)
        self.sv_w = self.sv_p = self.rt_w = self.rt_p = 0.0
        self.first_in = self.first_won = self.second_won = 0.0
        self.ace = self.df = self.svgms = self.bp_saved = self.bp_faced = self.bp_conv = self.bp_created = 0.0
        self.n_stat = 0.0
        self.last_stat = None
        self.last = None
        self.opp_rt_w = 0.0            # Σ (opponent return-points-won rate × our serve points), for opponent adjustment
        self.opp_sv_w = 0.0            # Σ (opponent serve-points-won rate × our return points)
        self.adj_p = 0.0
        self.n = 0

    def decay(self, day: str) -> None:
        if self.last_stat is None:
            return
        d = _days(day, self.last_stat)
        if d <= 0:
            return
        f = 0.5 ** (d / HALF_LIFE_DAYS)
        for k in ("sv_w", "sv_p", "rt_w", "rt_p", "first_in", "first_won", "second_won", "ace", "df", "svgms",
                  "bp_saved", "bp_faced", "bp_conv", "bp_created", "n_stat", "opp_rt_w", "opp_sv_w", "adj_p"):
            setattr(self, k, getattr(self, k) * f)


class PlayerStats:
    def __init__(self, baselines: dict | None = None):
        self.p: dict[str, _Player] = {}
        self.baselines = baselines or {}

    def get(self, pid: str) -> _Player:
        pl = self.p.get(pid)
        if pl is None:
            pl = self.p[pid] = _Player()
        return pl

    # -------------------------------------------------------------- observation
    def observe(self, m: dict) -> None:
        """m: date, surface, tour, level, w, l, w_games, l_games, w_sets, l_sets, tiebreaks, retired, score,
        w_svpt, w_1stIn, w_1stWon, w_2ndWon, w_ace, w_df, w_SvGms, w_bpSaved, w_bpFaced, l_* (None when unknown),
        exp_w = pre-match model probability of the winner (for form-vs-expectation), rating_w/rating_l."""
        day = m["date"]
        tb_w, tb_l = tiebreaks_won(m.get("score"))
        for side, opp in (("w", "l"), ("l", "w")):
            pid = m[side]
            pl = self.get(pid)
            won = side == "w"
            gf, ga = m.get(f"{side}_games"), m.get(f"{opp}_games")
            sf, sa = m.get(f"{side}_sets"), m.get(f"{opp}_sets")
            exp = m.get("exp_w")
            pl.recent.append((day, won, m.get("surface"), m.get(f"rating_{opp}"), gf, ga, sf, sa,
                              tb_w if won else tb_l, (tb_w + tb_l), bool(m.get("retired")), m.get("level"),
                              None if exp is None else (exp if won else 1 - exp), m.get(f"opp_name_{side}")))
            pl.last = day
            pl.n += 1
            svpt = m.get(f"{side}_svpt")
            osvpt = m.get(f"{opp}_svpt")
            if svpt and osvpt and svpt > 0 and osvpt > 0 and m.get(f"{side}_1stWon") is not None:
                pl.decay(day)
                sw = (m.get(f"{side}_1stWon") or 0) + (m.get(f"{side}_2ndWon") or 0)
                ow = (m.get(f"{opp}_1stWon") or 0) + (m.get(f"{opp}_2ndWon") or 0)
                pl.sv_w += sw
                pl.sv_p += svpt
                pl.rt_w += osvpt - ow
                pl.rt_p += osvpt
                pl.first_in += m.get(f"{side}_1stIn") or 0
                pl.first_won += m.get(f"{side}_1stWon") or 0
                pl.second_won += m.get(f"{side}_2ndWon") or 0
                pl.ace += m.get(f"{side}_ace") or 0
                pl.df += m.get(f"{side}_df") or 0
                pl.svgms += m.get(f"{side}_SvGms") or 0
                pl.bp_saved += m.get(f"{side}_bpSaved") or 0
                pl.bp_faced += m.get(f"{side}_bpFaced") or 0
                pl.bp_created += m.get(f"{opp}_bpFaced") or 0
                pl.bp_conv += (m.get(f"{opp}_bpFaced") or 0) - (m.get(f"{opp}_bpSaved") or 0)
                pl.n_stat += 1
                pl.last_stat = day
                # opponent strength for the serve/return adjustment (opponent's rates *before* this match)
                orate = self._rates(m[opp])
                base = self.baseline(m.get("tour"), m.get("surface"))
                if orate["rpw"] is not None and orate["n"] >= 3:
                    pl.opp_rt_w += orate["rpw"] * svpt
                    pl.adj_p += svpt
                else:
                    pl.opp_rt_w += (1 - base) * svpt
                    pl.adj_p += svpt
                if orate["spw"] is not None and orate["n"] >= 3:
                    pl.opp_sv_w += orate["spw"] * osvpt
                else:
                    pl.opp_sv_w += base * osvpt

    def _rates(self, pid: str) -> dict:
        pl = self.p.get(pid)
        if pl is None or pl.sv_p <= 0:
            return {"spw": None, "rpw": None, "n": 0}
        return {"spw": pl.sv_w / pl.sv_p, "rpw": pl.rt_w / pl.rt_p if pl.rt_p else None, "n": pl.n_stat}

    def baseline(self, tour: str | None, surface: str | None) -> float:
        key = f"{tour}|{surface}" if surface else f"{tour}|all"
        v = self.baselines.get(key) or self.baselines.get(f"{tour}|all")
        if v is None:
            v = C.DEFAULT_SERVE_BASELINE.get((tour, surface)) or (0.63 if tour == "atp" else 0.565)
        return v

    # -------------------------------------------------------------- features (as of now, i.e. everything observed so far)
    def features(self, pid: str, as_of: str, surface: str | None, tour: str | None) -> dict:
        pl = self.p.get(pid)
        if pl is None:
            return {"n": 0, "form": {}, "surface_form": {}, "serve": None, "ret": None, "traits": None, "profile": None,
                    "days_since_last": None, "note": "no match history in the data set"}
        rec = list(pl.recent)
        out: dict = {"n": pl.n, "days_since_last": _days(as_of, pl.last) if pl.last else None}
        out["form"] = {f"last{n}": _form(rec[-n:]) for n in C.FORM_WINDOWS}
        srec = [r for r in rec if r[2] == surface] if surface else []
        out["surface_form"] = {f"last{n}": _form(srec[-n:]) for n in C.FORM_WINDOWS} if surface else {}
        out["surface_form_n"] = len(srec)
        vs_exp = [r[1] - r[12] for r in rec[-10:] if r[12] is not None]
        out["form_vs_expectation"] = {"value": sum(vs_exp) / len(vs_exp), "n": len(vs_exp)} if vs_exp else {"value": None, "n": 0}
        # match profile
        full = [r for r in rec[-20:] if r[4] is not None and not r[10]]
        out["profile"] = {
            "n": len(full),
            "avg_total_games": _safe_div(sum(r[4] + r[5] for r in full), len(full)),
            "straight_sets_share": _safe_div(sum(1 for r in full if min(r[6] or 0, r[7] or 0) == 0), len(full)),
            "deciding_set_share": _safe_div(sum(1 for r in full if (r[6] or 0) + (r[7] or 0) in (3, 5) and abs((r[6] or 0) - (r[7] or 0)) == 1), len(full)),
            "tiebreaks_per_match": _safe_div(sum(r[9] for r in full), len(full)),
            "tiebreak_record": [sum(r[8] for r in full), sum(r[9] for r in full)],
        } if full else None
        # serve / return (decayed sums)
        if pl.sv_p > 0:
            age = _days(as_of, pl.last_stat) if pl.last_stat else None
            base = self.baseline(tour, surface)
            spw, rpw = pl.sv_w / pl.sv_p, (pl.rt_w / pl.rt_p if pl.rt_p else None)
            out["serve"] = {"n": round(pl.n_stat, 1), "as_of": pl.last_stat, "age_days": age, "stale": age is not None and age > C.SERVE_FRESH_DAYS,
                            "spw": spw, "first_in": _safe_div(pl.first_in, pl.sv_p), "first_won": _safe_div(pl.first_won, pl.first_in),
                            "second_won": _safe_div(pl.second_won, pl.sv_p - pl.first_in),
                            "hold": _safe_div(pl.svgms - (pl.bp_faced - pl.bp_saved), pl.svgms), "aces_per_match": _safe_div(pl.ace, pl.n_stat),
                            "df_per_match": _safe_div(pl.df, pl.n_stat), "bp_saved": _safe_div(pl.bp_saved, pl.bp_faced)}
            out["ret"] = {"n": round(pl.n_stat, 1), "rpw": rpw, "bp_converted": _safe_div(pl.bp_conv, pl.bp_created),
                          "bp_created_per_match": _safe_div(pl.bp_created, pl.n_stat)}
            # traits relative to the tour/surface baseline, opponent-adjusted and shrunk by sample size
            shrink = pl.n_stat / (pl.n_stat + C.SERVE_MIN_MATCHES)
            opp_rt = pl.opp_rt_w / pl.adj_p if pl.adj_p else (1 - base)
            opp_sv = pl.opp_sv_w / pl.rt_p if pl.rt_p else base
            serve_raw, ret_raw = spw - base, (rpw - (1 - base)) if rpw is not None else None
            serve_adj = spw - base + (opp_rt - (1 - base))          # faced strong returners → credit
            ret_adj = (rpw - (1 - base) + (opp_sv - base)) if rpw is not None else None
            out["traits"] = {"serve_raw": serve_raw, "serve_adj": serve_adj, "serve": serve_adj * shrink,
                             "return_raw": ret_raw, "return_adj": ret_adj, "return": (ret_adj or 0.0) * shrink if ret_adj is not None else None,
                             "shrink": shrink, "baseline": base, "opp_return_faced": opp_rt, "opp_serve_faced": opp_sv,
                             "low_confidence": pl.n_stat < C.SERVE_MIN_MATCHES or (age is not None and age > C.SERVE_FRESH_DAYS)}
        else:
            out["serve"] = None
            out["ret"] = None
            out["traits"] = None
        out["recent_matches"] = [{"date": r[0], "won": r[1], "surface": r[2], "opp_rating": None if r[3] is None else round(r[3]),
                                  "games": [r[4], r[5]], "sets": [r[6], r[7]], "retired": r[10], "level": r[11], "opponent": r[13]}
                                 for r in rec[-10:]][::-1]
        return out


def _form(rs: list) -> dict:
    if not rs:
        return {"n": 0, "wins": 0, "rate": None}
    w = sum(1 for r in rs if r[1])
    return {"n": len(rs), "wins": w, "rate": w / len(rs)}


def serve_baselines(base, since: str = "2015-01-01") -> dict:
    """Tour/surface serve-points-won share from matches with statistics (historical frequency, not a model)."""
    d = base[(base["date"] >= since) & base["w_svpt"].notna() & base["l_svpt"].notna() & (base["w_svpt"] > 0) & (base["l_svpt"] > 0)]
    won = d["w_1stWon"].fillna(0) + d["w_2ndWon"].fillna(0) + d["l_1stWon"].fillna(0) + d["l_2ndWon"].fillna(0)
    pts = d["w_svpt"] + d["l_svpt"]
    out = {}
    for (tour, surf), g in d.assign(won=won, pts=pts).groupby(["tour", "surface"]):
        if g["pts"].sum() > 20000:
            out[f"{tour}|{surf}"] = float(g["won"].sum() / g["pts"].sum())
    for tour, g in d.assign(won=won, pts=pts).groupby("tour"):
        out[f"{tour}|all"] = float(g["won"].sum() / g["pts"].sum())
    return out


def save_baselines(b: dict) -> None:
    C.HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    (C.HISTORY_DIR / "baselines.json").write_text(json.dumps(b, indent=1))


def load_baselines() -> dict | None:
    p = C.HISTORY_DIR / "baselines.json"
    return json.loads(p.read_text()) if p.exists() else None


def sample_label(n) -> str:
    return C.sample_label(int(n) if n else 0)
