"""Tennis markets: match winner, total games, player games, game handicap.

Model probability, fair odds, bookmaker odds, implied probability and edge are kept as separate fields.
Prices never change a probability; they only add the comparison columns.
"""
from __future__ import annotations

from . import config as C
from . import model as M

MARKET_LABELS = {"winner": "Match winner", "total_games": "Total games", "p1_games": "Player games", "p2_games": "Player games",
                 "game_handicap": "Game handicap"}


def implied(odds_a: float | None, odds_b: float | None) -> tuple[float | None, float | None, float | None]:
    """Raw implied probabilities and the bookmaker margin (overround) of a two-way price."""
    if not odds_a or not odds_b:
        return None, None, None
    ia, ib = 1 / odds_a, 1 / odds_b
    return ia, ib, ia + ib - 1


def _row(market: str, selection: str, line, p: float, book: float | None, other: float | None, low_conf: bool, label: str) -> dict:
    ia, ib, margin = implied(book, other)
    fair = 1 / p if p > 0 else None
    row = {"market": market, "label": label, "selection": selection, "line": line, "model_p": round(p, 4),
           "fair_odds": round(fair, 2) if fair else None, "book_odds": book, "implied": round(ia, 4) if ia else None,
           "implied_fair": round(ia / (ia + ib), 4) if ia and ib else None, "margin": round(margin, 4) if margin is not None else None,
           "edge_pp": round((p - ia / (ia + ib)) * 100, 1) if ia and ib else None, "ev": round(p * book - 1, 4) if book else None,
           "low_confidence": low_conf}
    return row


def build(fx: dict, pred: dict, dist: dict | None, odds: dict | None, low_conf_games: bool) -> list[dict]:
    """All market rows for one match. `dist` (Markov distribution) may be None when no game model is available."""
    a, b = fx["p1"]["name"], fx["p2"]["name"]
    sw = bool(odds and odds.get("swapped"))
    mk = (odds or {}).get("markets") or {}

    def side(m: dict | None, key1: str, key2: str):
        if not m:
            return None, None
        return (m.get(key2), m.get(key1)) if sw else (m.get(key1), m.get(key2))

    rows: list[dict] = []
    p = pred["p_match"]
    o1, o2 = side(mk.get("winner"), "p1", "p2")
    rows.append(_row("winner", "player_a", None, p, o1, o2, False, f"{a} to win"))
    rows.append(_row("winner", "player_b", None, 1 - p, o2, o1, False, f"{b} to win"))
    if dist is None:
        return rows
    # total games
    lines = sorted(mk.get("total_games", {}).keys()) or [_median(dist["total_games"]) + 0.5]
    for ln in lines:
        po = M.over_prob(dist["total_games"], ln)
        oo = mk.get("total_games", {}).get(ln, {})
        rows.append(_row("total_games", "over", ln, po, oo.get("over"), oo.get("under"), low_conf_games, f"Over {ln} games"))
        rows.append(_row("total_games", "under", ln, 1 - po, oo.get("under"), oo.get("over"), low_conf_games, f"Under {ln} games"))
    # player games
    for key, pmf_key, name in (("p1_games", "games_a", a), ("p2_games", "games_b", b)):
        src_key = key if not sw else ("p2_games" if key == "p1_games" else "p1_games")
        plines = sorted(mk.get(src_key, {}).keys()) or [_median(dist[pmf_key]) + 0.5]
        for ln in plines:
            po = M.over_prob(dist[pmf_key], ln)
            oo = mk.get(src_key, {}).get(ln, {})
            rows.append(_row(key, "over", ln, po, oo.get("over"), oo.get("under"), low_conf_games, f"{name} over {ln} games"))
            rows.append(_row(key, "under", ln, 1 - po, oo.get("under"), oo.get("over"), low_conf_games, f"{name} under {ln} games"))
    # game handicap (line is from player A's perspective; Sportybet's hcp is from the home side)
    hl = mk.get("game_handicap", {})
    hlines = sorted(hl.keys()) if hl else [_median_hcp(dist["handicap"])]
    for ln in hlines:
        ln_a = -ln if sw else ln
        pa_cov, pb_cov, push = M.handicap_probs(dist["handicap"], ln_a)
        oa, ob = side(hl.get(ln), "p1", "p2")
        if push > 0:
            pa_cov, pb_cov = pa_cov / (1 - push), pb_cov / (1 - push)
        rows.append(_row("game_handicap", "player_a", ln_a, pa_cov, oa, ob, low_conf_games, f"{a} {ln_a:+g} games"))
        rows.append(_row("game_handicap", "player_b", -ln_a, pb_cov, ob, oa, low_conf_games, f"{b} {-ln_a:+g} games"))
    return rows


def _median(pmf: dict[int, float]) -> int:
    acc = 0.0
    for k in sorted(pmf):
        acc += pmf[k]
        if acc >= 0.5:
            return k
    return max(pmf)


def _median_hcp(pmf: dict[int, float]) -> float:
    m = _median(pmf)
    return -(m - 0.5) if m > 0 else -(m + 0.5)


def highlights(rows: list[dict], quality_score: int, min_matches: int = 10**9) -> list[dict]:
    """Rows where the model is clearly above the bookmaker's fair implied probability. This is a
    model/market disagreement flag with its evidence — not a 'safe bet' label.
    Publication rules (conservative until the tracker has evidence): price ≥ MIN_ODDS, model ≥ 55%,
    edge ≥ EDGE_NOTE_PP for the winner market and ≥ GAME_EDGE_PP for game markets (the game model's
    expected total has a mean absolute error of ~5 games in the backtest, so small gaps there are noise),
    edge ≤ MAX_EDGE_PP (larger gaps usually mean information the model lacks — injuries, withdrawals,
    results outside the covered events — and are reported as warnings instead), data quality ≥ 60,
    both players with ≥ HIGHLIGHT_MIN_MATCHES rated matches, no low-confidence game data.
    At most ONE highlight per match: the largest qualifying edge (no stacking of correlated lines)."""
    out = []
    for r in rows:
        if r["book_odds"] is None or r["edge_pp"] is None or r["book_odds"] < C.MIN_ODDS:
            continue
        need = C.EDGE_NOTE_PP if r["market"] == "winner" else C.GAME_EDGE_PP
        if r["model_p"] < 0.55 or r["edge_pp"] < need or r["edge_pp"] > C.MAX_EDGE_PP or quality_score < 60:
            continue
        if r["low_confidence"] or min_matches < C.HIGHLIGHT_MIN_MATCHES:
            continue
        out.append(dict(r, flag="Model above market", confidence="Medium" if quality_score < 80 else "High"))
    out.sort(key=lambda r: -r["edge_pp"])
    return out[:1]
