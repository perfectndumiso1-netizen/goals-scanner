"""Per-match data-quality assessment for tennis. The score is a share of satisfied checks — it is NOT a
win probability and must never be used as one."""
from __future__ import annotations

from . import config as C

WEIGHTS = {"fixture": 2, "players": 2, "tournament": 1, "surface": 1, "format": 1, "ratings": 2, "recent_form": 1,
           "surface_sample": 1, "serve_data": 1, "return_data": 1, "opponent_strength": 1, "source_consistency": 1, "freshness": 1}


def _item(check: str, status: str, detail: str) -> dict:
    return {"check": check, "status": status, "detail": detail}


def assess(fx: dict, pred: dict, feats_a: dict, feats_b: dict, surface_info: dict, ident_a: dict, ident_b: dict,
           odds: dict | None, backfill: dict | None) -> dict:
    """status ∈ PASS / PARTIAL / STALE / N/A / FAIL. Score counts PASS = 1, PARTIAL/STALE = 0.5, N/A/FAIL = 0
    over all applicable weights."""
    items: list[dict] = []
    # fixture
    ok = bool(fx.get("start")) and bool(fx["p1"].get("name")) and bool(fx["p2"].get("name")) and bool(fx.get("tournament"))
    items.append(_item("fixture", "PASS" if ok else "FAIL", f"{fx.get('tournament')} · {fx.get('start')} UTC" if ok else "missing start time, player or tournament"))
    # players
    hows = (ident_a.get("how"), ident_b.get("how"))
    if all(h == "exact" for h in hows):
        items.append(_item("players", "PASS", "both players matched to the historical record by exact name"))
    elif "new" in hows:
        who = [n for n, h in ((fx["p1"]["name"], hows[0]), (fx["p2"]["name"], hows[1])) if h == "new"]
        items.append(_item("players", "PARTIAL", f"no historical record for {', '.join(who)} (new identity, no data borrowed)"))
    else:
        items.append(_item("players", "PARTIAL", "matched by surname + initial (fuzzy) — verify identity"))
    # tournament / category
    items.append(_item("tournament", "PASS", f"{fx.get('category')} · {'qualifying' if fx.get('qualifying') else 'main draw'}"))
    # surface
    s = surface_info.get("surface")
    if s and surface_info.get("how") == "override":
        items.append(_item("surface", "PASS", f"{s} (known tournament)"))
    elif s:
        items.append(_item("surface", "PASS" if (surface_info.get("confidence") or 0) >= 0.99 else "PARTIAL", f"{s} (from tournament history, match confidence {surface_info.get('confidence')})"))
    else:
        items.append(_item("surface", "N/A", "surface unknown for this tournament — surface component switched off"))
    # format
    items.append(_item("format", "PASS", f"best of {pred['best_of']}"))
    # ratings
    na, nb = pred["n_a"], pred["n_b"]
    if min(na, nb) >= C.MIN_MATCHES_RATED:
        items.append(_item("ratings", "PASS", f"ratings built from {na} and {nb} earlier matches ({C.sample_label(na)} / {C.sample_label(nb)})"))
    elif min(na, nb) > 0:
        items.append(_item("ratings", "PARTIAL", f"provisional rating: only {min(na, nb)} earlier matches for one player"))
    else:
        items.append(_item("ratings", "N/A", "one player has no earlier match in the data — rating is the default start value"))
    # recent form (activity)
    d = [feats_a.get("days_since_last"), feats_b.get("days_since_last")]
    f10 = [feats_a.get("form", {}).get("last10", {}).get("n", 0), feats_b.get("form", {}).get("last10", {}).get("n", 0)]
    if min(f10) >= 5 and all(x is not None and x <= 120 for x in d):
        items.append(_item("recent_form", "PASS", f"{f10[0]} and {f10[1]} recent matches; last played {d[0]} / {d[1]} days ago"))
    elif min(f10) >= 1:
        items.append(_item("recent_form", "STALE" if any(x is None or x > 120 for x in d) else "PARTIAL", f"{f10[0]} / {f10[1]} recent matches; last played {d[0]} / {d[1]} days ago"))
    else:
        items.append(_item("recent_form", "N/A", "no recent matches in the data for at least one player"))
    # surface sample
    ns = [pred.get("ns_a", 0), pred.get("ns_b", 0)]
    if not s:
        items.append(_item("surface_sample", "N/A", "no surface"))
    elif min(ns) >= 10:
        items.append(_item("surface_sample", "PASS", f"{ns[0]} and {ns[1]} earlier matches on {s}"))
    elif min(ns) > 0:
        items.append(_item("surface_sample", "PARTIAL", f"only {min(ns)} earlier matches on {s} for one player ({C.sample_label(min(ns))})"))
    else:
        items.append(_item("surface_sample", "N/A", f"no earlier matches on {s} for one player"))
    # serve / return
    for key, label in (("serve", "serve_data"), ("ret", "return_data")):
        sa, sb = feats_a.get(key), feats_b.get(key)
        if not sa or not sb:
            items.append(_item(label, "N/A", "no serve/return statistics in the data for at least one player (Livescore publishes none; archive only)"))
            continue
        n = min(sa.get("n", 0), sb.get("n", 0))
        stale = (feats_a.get("serve") or {}).get("stale") or (feats_b.get("serve") or {}).get("stale")
        age = max((feats_a.get("serve") or {}).get("age_days") or 0, (feats_b.get("serve") or {}).get("age_days") or 0)
        if n >= C.SERVE_MIN_MATCHES and not stale:
            items.append(_item(label, "PASS", f"{n:.0f}+ matches with statistics each, newest {age} days old"))
        elif n >= 1:
            items.append(_item(label, "STALE" if stale else "PARTIAL", f"{n:.0f} matches with statistics (effective, time-decayed); newest {age} days old"))
        else:
            items.append(_item(label, "N/A", "no statistics"))
    # opponent strength
    items.append(_item("opponent_strength", "PASS" if min(na, nb) >= C.MIN_MATCHES_RATED else "PARTIAL",
                       "opponents' ratings known for both players' recent results" if min(na, nb) >= C.MIN_MATCHES_RATED else "thin rating history for one player"))
    # source consistency (fixture vs prices)
    if odds is None:
        items.append(_item("source_consistency", "N/A", "no Sportybet price found for this match (no comparison, no effect on the model)"))
    else:
        items.append(_item("source_consistency", "PASS" if odds.get("name_score", 0) >= 0.9 else "PARTIAL", f"player names agree across Livescore and Sportybet (score {odds.get('name_score')})"))
    # freshness
    if backfill and backfill.get("complete"):
        items.append(_item("freshness", "PASS", f"results incorporated up to {backfill.get('to')}"))
    else:
        items.append(_item("freshness", "PARTIAL", f"results still being backfilled ({backfill.get('to') if backfill else 'unknown'})"))
    # score
    num = den = 0.0
    for it in items:
        w = WEIGHTS.get(it["check"], 1)
        den += w
        num += w * {"PASS": 1.0, "PARTIAL": 0.5, "STALE": 0.5}.get(it["status"], 0.0)
    score = round(100 * num / den) if den else 0
    overall = "High" if score >= 80 else "Medium" if score >= 60 else "Low"
    missing = [it["check"] for it in items if it["status"] in ("N/A", "FAIL")]
    return {"score": score, "overall": overall, "items": items, "missing": missing,
            "note": "Data quality describes how complete and current the inputs are. It is not a win probability."}
