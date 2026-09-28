"""Tennis reports: Markdown (+ PDF through the generic pdfgen) and CSV. Statistical language only —
no 'safe', 'banker', 'lock' or 'guaranteed'."""
from __future__ import annotations

import csv
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config as C

log = logging.getLogger("tennis.report")
FORBIDDEN = ("safe bet", "banker", "guaranteed", "lock", "sure win", "100% safe")


def sast(utc_str: str | None) -> str:
    if not utc_str:
        return "?"
    t = datetime.strptime(utc_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc) + timedelta(hours=C.TZ_OFFSET_HOURS)
    return t.strftime("%a %d %b %H:%M")


def pct(p) -> str:
    return "N/A" if p is None else f"{p*100:.0f}%"


def odd(o) -> str:
    return "—" if o is None else f"{o:.2f}"


def markdown(day: str, matches: list[dict], highlights: list[dict], tracker: dict, meta: dict) -> str:
    L = [f"# 🎾 TENNIS SCANNER — {day}", "",
         f"Generated {meta['generated']} · {len(matches)} singles matches in the next {int(C.LOOKAHEAD.total_seconds()//3600)} h "
         f"(ATP, WTA, Challengers; ITF, doubles and team events excluded) · {meta.get('priced', 0)} with Sportybet prices.",
         "", "**How to read:** MODEL % is the *data-only* probability from match results (Elo, surface-aware, format-aware; bookmaker prices are never an input). "
         "FAIR = 1 / model probability. SPORTYBET is the bookmaker price, IMPLIED its margin-free probability, EDGE = model − implied in points. "
         "DATA QUALITY is a completeness score, not a probability. Nothing here is a guarantee; a 70% probability loses three times in ten.", ""]
    # ordered by kick-off
    L += ["## Matches", "", "| Start (SAST) | Tournament | Match | Model | Fair | Sportybet | Implied | Edge | Data quality |", "|---|---|---|---|---|---|---|---|---|"]
    for m in sorted(matches, key=lambda x: x["start"] or ""):
        w = m["markets"][0] if m["markets"] else None
        fav = m["p1"] if m["p"]["a"] >= 0.5 else m["p2"]
        pf = max(m["p"]["a"], 1 - m["p"]["a"])
        row = next((r for r in m["markets"] if r["market"] == "winner" and r["selection"] == ("player_a" if m["p"]["a"] >= 0.5 else "player_b")), w)
        L.append(f"| {sast(m['start'])} | {m['tour'].upper()} {m['tournament']}{' (Q)' if m.get('qualifying') else ''} · {m['surface'] or 'surface N/A'} · bo{m['best_of']} "
                 f"| **{m['p1']['name']}** v **{m['p2']['name']}** → {fav['name']} | {pct(pf)} | {odd(1/pf if pf else None)} | {odd(row['book_odds'] if row else None)} "
                 f"| {pct(row['implied_fair'] if row else None)} | {'' if not row or row['edge_pp'] is None else f'{row['edge_pp']:+.1f} pp'} | {m['quality']['score']}% {m['quality']['overall']} |")
    L += [""]
    if highlights:
        L += ["## Model above market (disagreements worth a look — not recommendations)", "",
              "| Start | Match | Selection | Model | Fair | Sportybet | Implied | Edge | Data quality | Confidence |", "|---|---|---|---|---|---|---|---|---|---|"]
        for h in highlights:
            L.append(f"| {sast(h['start'])} | {h['match']} | {h['label']} | {pct(h['model_p'])} | {odd(h['fair_odds'])} | {odd(h['book_odds'])} | {pct(h['implied_fair'])} | {h['edge_pp']:+.1f} pp | {h['quality']}% | {h['confidence']} |")
        L += ["", "A disagreement means the model and the bookmaker weigh the evidence differently. The tracker records every one of these so the claim can be checked against results.", ""]
    else:
        L += ["## Model above market", "", "No selection clears the thresholds today (model ≥ 55%, edge ≥ 5 pp, price ≥ 1.30, data quality ≥ 60%, no low-confidence game data).", ""]
    if tracker.get("settled"):
        L += ["## Tracker so far", "", f"{tracker['settled']} settled selections, {tracker['won']} won.", ""]
        for k, v in tracker.get("by_market", {}).items():
            L.append(f"* {k}: {v['n']} settled, hit rate {v['hit_rate']*100:.0f}% vs average model probability {v['avg_model_p']*100:.0f}%")
        L.append("")
    L += ["## Notes", "",
          f"* Ratings: Elo from match results, overall + surface blend (weight {C.SURFACE_WEIGHT}), K = {C.ELO_K:g}/(matches+{C.ELO_OFFSET:g})^{C.ELO_SHAPE:g}; best-of-5 derived from the set probability. Validated in tennis/BACKTEST_RESULTS.md.",
          "* Game markets use a serve-point Markov chain pinned to the match probability; serve/return traits come from the archive (through June 2026) and are flagged stale as they age.",
          f"* Results since the archive come from Livescore ({meta.get('backfill', {}).get('to', '?')} incorporated). Livescore publishes no tennis statistics, so serve/return data is N/A for new matches.",
          f"* {C.SACKMANN_LICENCE}", "* Statistical information, not betting advice. 18+."]
    text = "\n".join(L)
    low = text.lower()
    for f in FORBIDDEN:
        if f in low:
            log.warning("forbidden wording in report: %s", f)
    return text


def write_csv(path: Path, matches: list[dict]) -> Path:
    fields = ["start_utc", "tour", "category", "tournament", "surface", "best_of", "player_a", "player_b", "market", "selection", "line",
              "model_probability", "fair_odds", "bookmaker_odds", "implied_fair", "edge_pp", "ev", "low_confidence", "data_quality", "match_id"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for m in matches:
            for r in m["markets"]:
                w.writerow({"start_utc": m["start"], "tour": m["tour"], "category": m["category"], "tournament": m["tournament"], "surface": m["surface"] or "N/A",
                            "best_of": m["best_of"], "player_a": m["p1"]["name"], "player_b": m["p2"]["name"], "market": r["market"], "selection": r["selection"],
                            "line": "" if r["line"] is None else r["line"], "model_probability": r["model_p"], "fair_odds": r["fair_odds"] or "",
                            "bookmaker_odds": r["book_odds"] or "", "implied_fair": r["implied_fair"] if r["implied_fair"] is not None else "",
                            "edge_pp": r["edge_pp"] if r["edge_pp"] is not None else "", "ev": r["ev"] if r["ev"] is not None else "",
                            "low_confidence": int(bool(r["low_confidence"])), "data_quality": m["quality"]["score"], "match_id": m["id"]})
    return path


def write_pdf(md: str, path: Path, day: str) -> Path | None:
    sys.path.insert(0, str(C.REPO))
    try:
        from pdfgen import markdown_to_pdf                  # generic Markdown → PDF (shared infrastructure, read-only)
        return markdown_to_pdf(md, path, title=f"Tennis Scanner {day}", subtitle="PlayReport · model vs market, data quality")
    except Exception as exc:                                # noqa: BLE001
        log.warning("PDF not generated: %s", exc)
        return None
