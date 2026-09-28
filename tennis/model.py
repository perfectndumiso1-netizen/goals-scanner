"""Tennis probability engine.

1. Ability: Elo ratings (overall + per surface) with an experience-based K schedule, updated only from
   match results in chronological order. Prediction = logistic of the blended rating difference.
2. Format: the rating difference maps to a *set* win probability; best-of-3 and best-of-5 match
   probabilities and set-score distributions follow from the set probability (independent sets).
3. Games: a Markov chain from serve-point win probabilities → game → set (tiebreak at 6-6) → match,
   giving total games, player games, game handicap and set scores. The two serve probabilities are
   pinned so that the chain reproduces the Elo match probability; their sum (serve dominance) comes from
   tour/surface baselines and, when available, the players' own serve/return traits.

No bookmaker information enters any function in this module.
"""
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np

from . import config as C


# ------------------------------------------------------------------ format mathematics
def match_from_set(p_set: float, best_of: int) -> float:
    """P(win match) from P(win a set), sets independent. bo3: p²(3−2p); bo5: p³(10−15p+6p²)."""
    p = min(max(p_set, 0.0), 1.0)
    if best_of == 5:
        return p ** 3 * (10 - 15 * p + 6 * p * p)
    return p * p * (3 - 2 * p)


def set_from_match(p_match: float, best_of: int = 3) -> float:
    """Inverse of match_from_set by bisection (monotone increasing)."""
    lo, hi = 0.0, 1.0
    target = min(max(p_match, 1e-9), 1 - 1e-9)
    for _ in range(60):
        mid = (lo + hi) / 2
        if match_from_set(mid, best_of) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def set_scores(p_set: float, best_of: int) -> dict[str, float]:
    """Probability of each final set score, independent sets."""
    p, q = p_set, 1 - p_set
    if best_of == 5:
        return {"3-0": p ** 3, "3-1": 3 * p ** 3 * q, "3-2": 6 * p ** 3 * q * q,
                "0-3": q ** 3, "1-3": 3 * q ** 3 * p, "2-3": 6 * q ** 3 * p * p}
    return {"2-0": p * p, "2-1": 2 * p * p * q, "0-2": q * q, "1-2": 2 * q * q * p}


# ------------------------------------------------------------------ Elo ratings
class Ratings:
    """Overall and surface Elo. update() must be called in chronological order; predict() before update()
    for the same match guarantees that no result leaks into its own prediction."""

    def __init__(self, k: float = C.ELO_K, offset: float = C.ELO_OFFSET, shape: float = C.ELO_SHAPE,
                 surface_weight: float = C.SURFACE_WEIGHT, format_adjust: bool = True, scale: float = C.ELO_SCALE):
        self.k, self.offset, self.shape, self.w, self.format_adjust = k, offset, shape, surface_weight, format_adjust
        self.scale = scale
        self.r: dict[str, float] = {}
        self.rs: dict[tuple[str, str], float] = {}
        self.n: dict[str, int] = {}
        self.ns: dict[tuple[str, str], int] = {}
        self.last: dict[str, str] = {}

    def k_for(self, n: int) -> float:
        return self.k / (n + self.offset) ** self.shape

    def logistic(self, diff: float) -> float:
        return 1.0 / (1.0 + 10 ** (-diff / self.scale))

    def diff(self, a: str, b: str, surface: str | None) -> tuple[float, float | None, float]:
        d_o = self.r.get(a, C.ELO_INIT) - self.r.get(b, C.ELO_INIT)
        d_s = None
        if surface:
            d_s = self.rs.get((a, surface), C.ELO_INIT) - self.rs.get((b, surface), C.ELO_INIT)
        blended = d_o if d_s is None else (1 - self.w) * d_o + self.w * d_s
        return d_o, d_s, blended

    def predict(self, a: str, b: str, surface: str | None, best_of: int = 3) -> dict:
        d_o, d_s, d = self.diff(a, b, surface)
        p_ref = self.logistic(d)                       # rating probability (best-of-3 reference)
        p_set = set_from_match(p_ref, 3)
        p_match = match_from_set(p_set, best_of) if (self.format_adjust and best_of == 5) else p_ref
        return {"p_match": p_match, "p_set": p_set if self.format_adjust or best_of == 3 else set_from_match(p_match, best_of),
                "p_ref": p_ref, "diff_overall": d_o, "diff_surface": d_s, "diff_blended": d,
                "rating_a": self.r.get(a, C.ELO_INIT), "rating_b": self.r.get(b, C.ELO_INIT),
                "surface_rating_a": self.rs.get((a, surface), C.ELO_INIT) if surface else None,
                "surface_rating_b": self.rs.get((b, surface), C.ELO_INIT) if surface else None,
                "n_a": self.n.get(a, 0), "n_b": self.n.get(b, 0),
                "ns_a": self.ns.get((a, surface), 0) if surface else 0, "ns_b": self.ns.get((b, surface), 0) if surface else 0,
                "set_scores": set_scores(p_set, best_of), "best_of": best_of, "surface": surface}

    def update(self, winner: str, loser: str, surface: str | None, day: str, best_of: int = 3) -> None:
        # overall system: own expectation
        e = self.logistic(self.r.get(winner, C.ELO_INIT) - self.r.get(loser, C.ELO_INIT))
        if self.format_adjust and best_of == 5:
            e = match_from_set(set_from_match(e, 3), 5)
        kw, kl = self.k_for(self.n.get(winner, 0)), self.k_for(self.n.get(loser, 0))
        self.r[winner] = self.r.get(winner, C.ELO_INIT) + kw * (1 - e)
        self.r[loser] = self.r.get(loser, C.ELO_INIT) - kl * (1 - e)
        self.n[winner] = self.n.get(winner, 0) + 1
        self.n[loser] = self.n.get(loser, 0) + 1
        self.last[winner] = day
        self.last[loser] = day
        if surface:
            kw_, kl_ = (winner, surface), (loser, surface)
            es = self.logistic(self.rs.get(kw_, C.ELO_INIT) - self.rs.get(kl_, C.ELO_INIT))
            if self.format_adjust and best_of == 5:
                es = match_from_set(set_from_match(es, 3), 5)
            ks_w, ks_l = self.k_for(self.ns.get(kw_, 0)), self.k_for(self.ns.get(kl_, 0))
            self.rs[kw_] = self.rs.get(kw_, C.ELO_INIT) + ks_w * (1 - es)
            self.rs[kl_] = self.rs.get(kl_, C.ELO_INIT) - ks_l * (1 - es)
            self.ns[kw_] = self.ns.get(kw_, 0) + 1
            self.ns[kl_] = self.ns.get(kl_, 0) + 1


# ------------------------------------------------------------------ Markov chain: points → games → sets → match
def p_game(p: float) -> float:
    """P(server wins a game) from P(server wins a point)."""
    p = min(max(p, 1e-6), 1 - 1e-6)
    q = 1 - p
    deuce = p * p / (1 - 2 * p * q)
    return p ** 4 * (1 + 4 * q + 10 * q * q) + 20 * p ** 3 * q ** 3 * deuce


@lru_cache(maxsize=4096)
def p_tiebreak(pa: float, pb: float, target: int = 7) -> float:
    """P(A wins a tiebreak to `target` points, win by 2). A serves point 1, then two points each.
    pa / pb = probability that A / B wins a point on own serve."""
    qa, qb = 1 - pa, 1 - pb
    memo: dict[tuple[int, int], float] = {}

    def server(idx: int) -> int:                        # 0-based point index → 0 (A serves) / 1 (B serves)
        return 0 if idx == 0 else (1 if ((idx - 1) // 2) % 2 == 0 else 0)

    def win(a: int, b: int) -> float:
        if a >= target and a - b >= 2:
            return 1.0
        if b >= target and b - a >= 2:
            return 0.0
        if a >= target - 1 and b >= target - 1 and a == b:
            # deuce-like: pairs of points, one on each serve
            pa_pair, pb_pair = pa * qb, qa * pb
            return pa_pair / (pa_pair + pb_pair)
        key = (a, b)
        if key in memo:
            return memo[key]
        s = server(a + b)
        pw = pa if s == 0 else qb                       # probability A wins this point
        v = pw * win(a + 1, b) + (1 - pw) * win(a, b + 1)
        memo[key] = v
        return v

    return win(0, 0)


@lru_cache(maxsize=4096)
def set_distribution(pa: float, pb: float, first_server: int, final_tb_target: int = 7) -> dict:
    """Distribution over set outcomes {(winner, games_a, games_b, next_first_server): prob}.
    Tiebreak at 6-6 (to `final_tb_target` points)."""
    ga_hold, gb_hold = p_game(pa), p_game(pb)
    out: dict[tuple[int, int, int, int], float] = {}
    stack = [((0, 0, first_server), 1.0)]
    while stack:
        (a, b, s), pr = stack.pop()
        if pr < 1e-12:
            continue
        if (a >= 6 or b >= 6) and abs(a - b) >= 2 and max(a, b) <= 7:
            key = (0 if a > b else 1, a, b, s)         # s already flipped to the next server after the last game
            out[key] = out.get(key, 0.0) + pr
            continue
        if a == 6 and b == 6:
            pt = p_tiebreak(pa, pb, final_tb_target) if s == 0 else 1 - p_tiebreak(pb, pa, final_tb_target)
            nxt = 1 - s                                  # the receiver of the tiebreak's first point serves first next set
            for w, prob in ((0, pt), (1, 1 - pt)):
                key = (w, 7 if w == 0 else 6, 6 if w == 0 else 7, nxt)
                out[key] = out.get(key, 0.0) + pr * prob
            continue
        p_a_wins_game = ga_hold if s == 0 else 1 - gb_hold
        stack.append(((a + 1, b, 1 - s), pr * p_a_wins_game))
        stack.append(((a, b + 1, 1 - s), pr * (1 - p_a_wins_game)))
    return out


def match_distribution(pa: float, pb: float, best_of: int = 3, slam_final_set: bool = False) -> dict:
    """Full match distribution from serve-point probabilities.
    Returns p_match, set score probabilities, total-games pmf, player-games pmfs, handicap pmf (games A − B)."""
    need = 3 if best_of == 5 else 2
    # state: (sets_a, sets_b, games_a, games_b, server) → prob
    states: dict[tuple[int, int, int, int, int], float] = {(0, 0, 0, 0, 0): 0.5, (0, 0, 0, 0, 1): 0.5}
    finals: dict[tuple[int, int, int, int], float] = {}
    while states:
        nxt: dict[tuple[int, int, int, int, int], float] = {}
        for (sa, sb, ga, gb, s), pr in states.items():
            final_set = (sa == need - 1 and sb == need - 1)
            tb_target = 10 if (slam_final_set and final_set) else 7
            for (w, xa, xb, ns), q in set_distribution(pa, pb, s, tb_target).items():
                p2 = pr * q
                if p2 < 1e-12:
                    continue
                sa2, sb2 = sa + (w == 0), sb + (w == 1)
                if sa2 == need or sb2 == need:
                    key = (sa2, sb2, ga + xa, gb + xb)
                    finals[key] = finals.get(key, 0.0) + p2
                else:
                    k2 = (sa2, sb2, ga + xa, gb + xb, ns)
                    nxt[k2] = nxt.get(k2, 0.0) + p2
        states = nxt
    p_match = sum(p for (sa, sb, _, _), p in finals.items() if sa > sb)
    sets: dict[str, float] = {}
    total: dict[int, float] = {}
    games_a: dict[int, float] = {}
    games_b: dict[int, float] = {}
    hcp: dict[int, float] = {}
    for (sa, sb, ga, gb), p in finals.items():
        sets[f"{sa}-{sb}"] = sets.get(f"{sa}-{sb}", 0.0) + p
        total[ga + gb] = total.get(ga + gb, 0.0) + p
        games_a[ga] = games_a.get(ga, 0.0) + p
        games_b[gb] = games_b.get(gb, 0.0) + p
        hcp[ga - gb] = hcp.get(ga - gb, 0.0) + p
    exp_total = sum(k * v for k, v in total.items())
    return {"p_match": p_match, "set_scores": sets, "total_games": total, "games_a": games_a, "games_b": games_b,
            "handicap": hcp, "expected_total": exp_total, "pa": pa, "pb": pb}


def solve_serve_split(p_match_target: float, dominance: float, best_of: int = 3, slam_final_set: bool = False) -> tuple[float, float]:
    """Find (pa, pb) with pa + pb = dominance whose Markov match probability equals the target."""
    lo, hi = -0.25, 0.25
    for _ in range(40):
        mid = (lo + hi) / 2
        pa, pb = dominance / 2 + mid, dominance / 2 - mid
        pa, pb = min(max(pa, 0.3), 0.9), min(max(pb, 0.3), 0.9)
        pm = match_distribution(round(pa, 4), round(pb, 4), best_of, slam_final_set)["p_match"]
        if pm < p_match_target:
            lo = mid
        else:
            hi = mid
        if hi - lo < 2e-4:
            break
    mid = (lo + hi) / 2
    return round(min(max(dominance / 2 + mid, 0.3), 0.9), 4), round(min(max(dominance / 2 - mid, 0.3), 0.9), 4)


# Gauss-Hermite nodes/weights (5 points) for a Normal spread of the day-specific serve-point difference
_GH_X, _GH_W = np.polynomial.hermite_e.hermegauss(5)
_GH_W = _GH_W / _GH_W.sum()


def match_distribution_mixture(p_match_target: float, dominance: float, best_of: int = 3, slam_final_set: bool = False,
                               sigma: float = 0.0) -> dict:
    """Game-level distribution with *day-form spread*: the serve-point difference between the players on the day is
    Normal(d0, sigma) rather than a fixed number (real matches are more lopsided than an independent-points chain
    with fixed probabilities predicts — this is the documented, validated overdispersion, see BACKTEST_RESULTS §5).
    d0 is solved so that the mixture's match probability equals the rating probability; pmfs are mixture averages.
    sigma = 0 reproduces the plain pinned chain."""
    nodes = [(0.0, 1.0)] if sigma <= 0 else list(zip(_GH_X, _GH_W))

    def evaluate(d0: float) -> tuple[float, list[tuple[float, dict]]]:
        parts = []
        pm = 0.0
        for x, w in nodes:
            d = d0 + sigma * x
            pa = min(max(dominance / 2 + d / 2, 0.3), 0.9)
            pb = min(max(dominance / 2 - d / 2, 0.3), 0.9)
            r = match_distribution(round(pa, 4), round(pb, 4), best_of, slam_final_set)
            parts.append((w, r))
            pm += w * r["p_match"]
        return pm, parts

    lo, hi = -0.5, 0.5
    parts = None
    for _ in range(40):
        mid = (lo + hi) / 2
        pm, parts = evaluate(mid)
        if pm < p_match_target:
            lo = mid
        else:
            hi = mid
        if hi - lo < 5e-4:
            break
    d0 = (lo + hi) / 2
    pm, parts = evaluate(d0)
    out = {"p_match": pm, "set_scores": {}, "total_games": {}, "games_a": {}, "games_b": {}, "handicap": {}}
    for w, r in parts:
        for key in ("set_scores", "total_games", "games_a", "games_b", "handicap"):
            for k, v in r[key].items():
                out[key][k] = out[key].get(k, 0.0) + w * v
    out["expected_total"] = sum(k * v for k, v in out["total_games"].items())
    out["pa"], out["pb"] = round(dominance / 2 + d0 / 2, 4), round(dominance / 2 - d0 / 2, 4)
    out["sigma"], out["d0"] = sigma, round(d0, 4)
    return out


def over_prob(pmf: dict[int, float], line: float) -> float:
    return sum(p for k, p in pmf.items() if k > line)


def handicap_probs(hcp_pmf: dict[int, float], line: float) -> tuple[float, float, float]:
    """(P(A covers), P(B covers), P(push)) for 'A + line' (line negative when A gives games)."""
    win = sum(p for k, p in hcp_pmf.items() if k + line > 0)
    push = sum(p for k, p in hcp_pmf.items() if abs(k + line) < 1e-9)
    return win, 1 - win - push, push
