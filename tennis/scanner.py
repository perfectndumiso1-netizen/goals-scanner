"""Tennis scanner — daily orchestrator.

fetch → validate → statistics → model → markets → JSON → reports → tracker → Telegram.
Run: TENNIS_STATE_DIR=<clone of tennis-data branch> python3 -m tennis.scanner
Env: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID (optional), TENNIS_REPORT=1 to force the Telegram report.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

from . import config as C
from . import data as D
from . import history as H
from . import markets as MK
from . import model as M
from . import notify as N
from . import quality as Q
from . import report as REP
from . import stats as S

log = logging.getLogger("tennis.scanner")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(second=0, microsecond=0)


def _r(x, d=3):
    return None if x is None else round(x, d)


def explain(pred: dict, dist: dict | None, dom_parts: dict | None, fx: dict) -> dict:
    a, b = fx["p1"]["name"], fx["p2"]["name"]
    steps = [f"Overall rating {a} {pred['rating_a']:.0f} vs {b} {pred['rating_b']:.0f} → difference {pred['diff_overall']:+.0f}"]
    if pred["diff_surface"] is not None:
        steps.append(f"{pred['surface']} rating {pred['surface_rating_a']:.0f} vs {pred['surface_rating_b']:.0f} → difference {pred['diff_surface']:+.0f}; "
                     f"blend {1-C.SURFACE_WEIGHT:.2f}×overall + {C.SURFACE_WEIGHT:.2f}×surface = {pred['diff_blended']:+.0f}")
    else:
        steps.append("Surface unknown → overall rating difference used alone")
    steps.append(f"Rating probability 1/(1+10^(−{pred['diff_blended']:.0f}/{C.ELO_SCALE:g})) = {pred['p_ref']*100:.1f}% (best-of-3 reference)")
    steps.append(f"Set probability {pred['p_set']*100:.1f}% → best-of-{pred['best_of']} match probability {pred['p_match']*100:.1f}%")
    if dist and dom_parts:
        steps.append(f"Games: serve-point baseline {dom_parts['baseline']*100:.1f}% ({fx['tour'].upper()} {pred['surface'] or 'all'}), "
                     f"serve traits {dom_parts['serve_a']*100:+.1f} / {dom_parts['serve_b']*100:+.1f} pp, return traits {dom_parts['return_a']*100:+.1f} / {dom_parts['return_b']*100:+.1f} pp "
                     f"→ serve dominance {dom_parts['dominance']:.3f}; day-form spread σ = {dom_parts['sigma']:.2f} (validated); split pinned to the match probability: {a} wins {dist['pa']*100:.1f}% of service points on an average day, {b} {dist['pb']*100:.1f}% "
                     f"→ expected total {dist['expected_total']:.1f} games")
    return {"steps": steps, "inputs": {"rating_a": _r(pred["rating_a"], 1), "rating_b": _r(pred["rating_b"], 1),
                                       "surface_rating_a": _r(pred["surface_rating_a"], 1), "surface_rating_b": _r(pred["surface_rating_b"], 1),
                                       "n_a": pred["n_a"], "n_b": pred["n_b"], "ns_a": pred["ns_a"], "ns_b": pred["ns_b"],
                                       "surface_weight": C.SURFACE_WEIGHT, "k_schedule": f"{C.ELO_K:g}/(n+{C.ELO_OFFSET:g})^{C.ELO_SHAPE:g}",
                                       "dominance": dom_parts}}


def warnings_for(pred: dict, quality: dict, fa: dict, fb: dict, rows: list[dict], surface_info: dict) -> list[str]:
    w = []
    if min(pred["n_a"], pred["n_b"]) < C.MIN_MATCHES_RATED:
        w.append(f"Provisional rating: only {min(pred['n_a'], pred['n_b'])} earlier matches for one player — probability carries wide uncertainty")
    if pred["p_match"] >= 0.85 or pred["p_match"] <= 0.15:
        w.append("Strong favourite: the model's probability is high, but the fair price is short — small edges here are within model error")
    if not surface_info.get("surface"):
        w.append("Surface unknown — surface form not used")
    for f, nm in ((fa, "player A"), (fb, "player B")):
        s = f.get("serve") or {}
        if s.get("stale"):
            w.append(f"Serve/return statistics for {nm} are {s.get('age_days')} days old (archive) — game markets flagged LOW DATA CONFIDENCE")
        fv = f.get("form_vs_expectation") or {}
        if fv.get("value") is not None and fv.get("n", 0) >= 6 and abs(fv["value"]) >= 0.25:
            w.append(f"Recent results of {nm} differ from what ratings expected ({fv['value']*100:+.0f} pp over {fv['n']} matches) — form signal, not yet in the rating")
    for r in rows:
        if r["market"] == "winner" and r["edge_pp"] is not None and abs(r["edge_pp"]) >= 15:
            w.append(f"Large model/market gap on the winner market ({r['edge_pp']:+.0f} pp) — check for injury/withdrawal news; the model has no such information")
            break
    if quality["overall"] == "Low":
        w.append("Low data quality — treat every number on this match as indicative only")
    return w


def analyse(fx: dict, R: M.Ratings, PS: S.PlayerStats, index: D.PlayerIndex, resolver: D.SurfaceResolver,
            odds: dict | None, backfill: dict | None, h2h_fn=None) -> dict:
    ia = index.resolve(fx["p1"]["name"], fx["p1"].get("ioc"), fx["tour"], fx["p1"]["ls_id"])
    ib = index.resolve(fx["p2"]["name"], fx["p2"].get("ioc"), fx["tour"], fx["p2"]["ls_id"])
    month = int((fx["start"] or fx["day"])[5:7])
    sinfo = resolver.resolve(fx["tournament"], month)
    surface = sinfo["surface"]
    best_of = 5 if (fx["level"] == "G" and fx["tour"] == "atp") else 3
    pred = R.predict(ia["pid"], ib["pid"], surface, best_of)
    as_of = (fx["start"] or fx["day"])[:10]
    fa, fb = PS.features(ia["pid"], as_of, surface, fx["tour"]), PS.features(ib["pid"], as_of, surface, fx["tour"])
    ta, tb = fa.get("traits") or {}, fb.get("traits") or {}
    base_sv = PS.baseline(fx["tour"], surface)
    dom_parts = {"baseline": base_sv, "serve_a": ta.get("serve") or 0.0, "serve_b": tb.get("serve") or 0.0,
                 "return_a": ta.get("return") or 0.0, "return_b": tb.get("return") or 0.0}
    dom_parts["dominance"] = 2 * base_sv + dom_parts["serve_a"] + dom_parts["serve_b"] - dom_parts["return_a"] - dom_parts["return_b"]
    dom_parts["sigma"] = C.FORM_SIGMA.get(fx["tour"], 0.0)
    low_conf = (not ta) or (not tb) or bool(ta.get("low_confidence")) or bool(tb.get("low_confidence")) or min(pred["n_a"], pred["n_b"]) < C.MIN_MATCHES_RATED
    dist = None
    try:
        dist = M.match_distribution_mixture(pred["p_match"], dom_parts["dominance"], best_of, fx["level"] == "G", dom_parts["sigma"])
    except Exception as exc:                            # noqa: BLE001
        log.warning("game model failed for %s: %s", fx["ls_id"], exc)
    rows = MK.build(fx, pred, dist, odds, low_conf)
    quality = Q.assess(fx, pred, fa, fb, sinfo, ia, ib, odds, backfill)
    hl = MK.highlights(rows, quality["score"], min(pred["n_a"], pred["n_b"]))
    sel = MK.select(rows, quality["score"], min(pred["n_a"], pred["n_b"]))
    h2h = []
    if h2h_fn and ia.get("how") != "new" and ib.get("how") != "new":
        try:
            names = {str(ia["pid"]): fx["p1"]["name"], str(ib["pid"]): fx["p2"]["name"]}
            h2h = [dict(x, winner_name=names.get(str(x["winner"]), x["winner"])) for x in h2h_fn(ia["pid"], ib["pid"])]
        except Exception as exc:                        # noqa: BLE001
            log.warning("h2h failed for %s: %s", fx["ls_id"], exc)
    start_sast = (datetime.strptime(fx["start"], "%Y-%m-%d %H:%M") + timedelta(hours=C.TZ_OFFSET_HOURS)) if fx.get("start") else None
    return {
        "id": fx["ls_id"], "start": fx["start"], "day": fx["day"], "day_sast": start_sast.strftime("%Y-%m-%d") if start_sast else fx["day"],
        "tour": fx["tour"], "level": fx["level"], "category": fx["category"],
        "tournament": fx["tournament"], "qualifying": fx.get("qualifying", False), "surface": surface, "surface_info": sinfo, "best_of": best_of,
        "status": fx["status"],
        "p1": {"name": fx["p1"]["name"], "ioc": fx["p1"].get("ioc"), "pid": ia["pid"], "identity": ia, "rating": _r(pred["rating_a"], 0),
               "surface_rating": _r(pred["surface_rating_a"], 0), "n": pred["n_a"], "n_surface": pred["ns_a"], "features": fa},
        "p2": {"name": fx["p2"]["name"], "ioc": fx["p2"].get("ioc"), "pid": ib["pid"], "identity": ib, "rating": _r(pred["rating_b"], 0),
               "surface_rating": _r(pred["surface_rating_b"], 0), "n": pred["n_b"], "n_surface": pred["ns_b"], "features": fb},
        "p": {"a": _r(pred["p_match"], 4), "b": _r(1 - pred["p_match"], 4), "set": _r(pred["p_set"], 4), "reference_bo3": _r(pred["p_ref"], 4)},
        "set_scores": {k: _r(v, 4) for k, v in (dist["set_scores"] if dist else pred["set_scores"]).items()},
        "games": None if dist is None else {"expected_total": _r(dist["expected_total"], 2), "pa": dist["pa"], "pb": dist["pb"],
                                            "total_pmf": {str(k): _r(v, 5) for k, v in sorted(dist["total_games"].items())},
                                            "games_a_pmf": {str(k): _r(v, 5) for k, v in sorted(dist["games_a"].items())},
                                            "games_b_pmf": {str(k): _r(v, 5) for k, v in sorted(dist["games_b"].items())},
                                            "handicap_pmf": {str(k): _r(v, 5) for k, v in sorted(dist["handicap"].items())},
                                            "low_confidence": low_conf},
        "markets": rows, "highlights": hl, "selection": sel["preferred"], "strong": sel["strong"], "selection_note": sel["why_none"],
        "h2h": h2h, "h2h_record": [sum(1 for x in h2h if str(x["winner"]) == str(ia["pid"])), sum(1 for x in h2h if str(x["winner"]) == str(ib["pid"]))],
        "odds": {"source": "Sportybet ZA", "event": odds.get("id"), "start": odds.get("start"), "markets": odds.get("markets")} if odds else None,
        "quality": quality, "explain": explain(pred, dist, dom_parts, fx),
        "warnings": warnings_for(pred, quality, fa, fb, rows, sinfo),
    }


def dedupe_fixtures(fixtures: list[dict]) -> list[dict]:
    """Same two players on the same day = one match (Livescore occasionally lists a match under two stages)."""
    seen, uniq = set(), []
    for f in fixtures:
        key = (f["day"], tuple(sorted((D.norm_name(f["p1"]["name"]), D.norm_name(f["p2"]["name"])))))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(f)
    return uniq


SEL_KEYS = ("market", "label", "selection", "line", "model_p", "fair_odds", "book_odds", "implied_fair", "edge_pp", "kind", "strong", "family", "why", "confidence", "flag")


def compact(row: dict | None) -> dict | None:
    return None if row is None else {k: row[k] for k in SEL_KEYS if k in row}


def slim(m: dict) -> dict:
    """Index entry for latest.json / day files (small)."""
    win = [r for r in m["markets"] if r["market"] == "winner"]
    pl = lambda p: {"name": p["name"], "ioc": p["ioc"], "rating": p["rating"], "n": p["n"], "last_rank": (p.get("features") or {}).get("last_rank"),
                    "form10": ((p.get("features") or {}).get("form") or {}).get("last10")}
    return {"id": m["id"], "start": m["start"], "day_sast": m["day_sast"], "tour": m["tour"], "category": m["category"], "tournament": m["tournament"],
            "qualifying": m["qualifying"], "surface": m["surface"], "best_of": m["best_of"], "p1": pl(m["p1"]), "p2": pl(m["p2"]),
            "p": m["p"], "expected_total": (m["games"] or {}).get("expected_total"),
            "odds": {"a": win[0]["book_odds"], "b": win[1]["book_odds"], "implied_a": win[0]["implied_fair"], "edge_a": win[0]["edge_pp"]} if win and win[0]["book_odds"] else None,
            "quality": {"score": m["quality"]["score"], "overall": m["quality"]["overall"]},
            "selection": compact(m.get("selection")), "strong": [compact(x) for x in m.get("strong") or []], "selection_note": m.get("selection_note"),
            "h2h_record": m.get("h2h_record"),
            "highlights": len(m["highlights"]), "warnings": len(m["warnings"]), "low_confidence_games": bool((m["games"] or {}).get("low_confidence", True))}


def main() -> int:
    t0 = time.time()
    C.ensure_dirs()
    now = utcnow()
    today = now.date()
    log.info("Tennis scanner start %s UTC (state %s)", now.strftime("%Y-%m-%d %H:%M"), C.STATE)
    base = D.load_base()
    bl = S.load_baselines()
    if not bl:
        bl = S.serve_baselines(base)
        S.save_baselines(bl)
    index = D.PlayerIndex(D.load_players())
    resolver = D.SurfaceResolver(base)
    # 1. results (Livescore) since the archive snapshot, bounded per run
    backfill = D.backfill_results(today)
    log.info("Livescore results backfill: %s", backfill)
    # 2. today's and tomorrow's fixtures (today's file is stored so that results are captured later)
    fixtures: list[dict] = []
    for d in (today, today + timedelta(days=1)):
        evs = D.fetch_ls_day(d)
        if d == today:
            D.store_day(d, evs)
        fixtures += evs
    results = D.load_results()
    ls_recs = H.livescore_records(results, index, resolver)
    # 3. ratings & statistics: archive then Livescore results, strictly chronological
    R, PS = M.Ratings(), S.PlayerStats(bl)
    n1 = H.replay(H.base_records(base), R, PS)
    n2 = H.replay(ls_recs, R, PS)
    log.info("replayed %d archive + %d Livescore matches; %d rated players", n1, n2, len(R.r))
    horizon = now + C.LOOKAHEAD
    upcoming = [f for f in fixtures if not f["finished"] and not f["cancelled"] and f["start"]
                and now - timedelta(hours=1) <= datetime.strptime(f["start"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc) <= horizon]
    upcoming = dedupe_fixtures(upcoming)
    # 4. prices (comparison layer)
    prices = {}
    try:
        events = D.fetch_sporty_tennis(hours_ahead=C.LOOKAHEAD.total_seconds() / 3600 + 6)
        prices = D.match_prices(upcoming, events)
    except Exception as exc:                            # noqa: BLE001
        log.warning("Sportybet tennis prices unavailable: %s", exc)
    # 5. analysis
    matches = []
    for fx in upcoming:
        try:
            matches.append(analyse(fx, R, PS, index, resolver, prices.get(fx["ls_id"]), backfill, h2h_fn=lambda a, b: H.h2h(base, ls_recs, a, b)))
        except Exception as exc:                        # noqa: BLE001
            log.exception("analysis failed for %s v %s: %s", fx["p1"]["name"], fx["p2"]["name"], exc)
    index.save()
    highlights = []
    for m in matches:
        for h in m["highlights"]:
            highlights.append(dict(h, match=f"{m['p1']['name']} v {m['p2']['name']}", start=m["start"], tournament=m["tournament"],
                                   quality=m["quality"]["score"], match_id=m["id"]))
    highlights.sort(key=lambda h: -h["edge_pp"])
    # 6. tracker: day selection (preferred market) + strong markets + highlights + the rating favourite of every priced match; settle stored results
    day = (now + timedelta(hours=C.TZ_OFFSET_HOURS)).strftime("%Y-%m-%d")
    rows = []
    for m in matches:
        if not m["odds"]:
            continue
        fav = "player_a" if m["p"]["a"] >= 0.5 else "player_b"
        r = next((x for x in m["markets"] if x["market"] == "winner" and x["selection"] == fav), None)
        cands = ([dict(x, kind="strong") for x in m["strong"]] + ([dict(m["selection"], kind="day")] if m["selection"] else [])
                 + [dict(x, kind="highlight") for x in m["highlights"]] + ([dict(r, kind="favourite")] if r and r["book_odds"] else []))
        for x in cands:
            rows.append({"date": m["day_sast"], "tournament": m["tournament"], "round": "Q" if m["qualifying"] else "", "surface": m["surface"] or "N/A",
                         "player_a": m["p1"]["name"], "player_b": m["p2"]["name"], "market": x["market"], "selection": x["selection"], "line": x["line"] if x["line"] is not None else "",
                         "model_probability": x["model_p"], "fair_odds": x["fair_odds"], "bookmaker_odds": x["book_odds"], "implied": x["implied_fair"],
                         "edge_pp": x["edge_pp"], "match_id": m["id"], "data_quality": m["quality"]["score"], "kind": x["kind"]})
    added = H.record_selections(rows)
    results_by_id = {e["ls_id"]: e for e in results}
    for f in fixtures:                                   # today's finished matches are in `fixtures`, not yet in results
        if f["finished"]:
            results_by_id.setdefault(f["ls_id"], f)
    settled = H.settle(results_by_id)
    tsum = H.tracker_summary()
    log.info("tracker: %d new selections, %d settled now, %s", added, settled, tsum)
    # 7. JSON (app-facing + raw)
    meta = {"generated": now.strftime("%Y-%m-%d %H:%M UTC"), "generated_sast": (now + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"),
            "sport": "tennis", "version": "0.1", "coverage": "ATP, WTA, ATP/WTA Challengers (singles)", "lookahead_hours": int(C.LOOKAHEAD.total_seconds() // 3600),
            "archive_end": C.BASE_END, "backfill": backfill, "livescore_results": len(results), "rated_players": len(R.r),
            "priced": sum(1 for m in matches if m["odds"]), "licence": C.SACKMANN_LICENCE,
            "model": {"type": "Elo (overall + surface) → set probability → best-of-3/5; Markov chain for games", "k": C.ELO_K, "offset": C.ELO_OFFSET,
                      "shape": C.ELO_SHAPE, "surface_weight": C.SURFACE_WEIGHT, "scale": C.ELO_SCALE, "form_sigma": C.FORM_SIGMA, "validated": "tennis/BACKTEST_RESULTS.md"},
            "note": "Model probabilities use match results only. Bookmaker prices are a separate comparison layer."}
    slims = [slim(m) for m in sorted(matches, key=lambda x: x["start"])]
    def _tag(x, m):
        return dict(x, match=f"{m['p1']['name']} v {m['p2']['name']}", start=m["start"], day_sast=m["day_sast"], tournament=m["tournament"],
                    category=m["category"], surface=m["surface"], quality=m["quality"]["score"], match_id=m["id"])
    selections = sorted([_tag(m["selection"], m) for m in slims if m["selection"]], key=lambda x: -x["model_p"])
    strong = sorted([_tag(x, m) for m in slims for x in m["strong"]], key=lambda x: -x["model_p"])
    # "Selections of the day" blocks, in display order; a block shows up to 7 (most probable first) and only
    # selections that already met the rules — never padded, a block with none is omitted. Game-handicap picks are
    # not a daily block; they stay on the match pages, the Bets tab and in `selections`.
    sections = []
    for fam in ("Match winner", "Player games", "Total games"):
        items = [x for x in selections if x.get("family") == fam][:7]
        if items:
            sections.append({"title": fam, "selections": items})
    app_latest = {"meta": meta, "matches": slims, "selections": selections, "sections": sections, "strong": strong,
                  "highlights": highlights[:40], "tracker": tsum,
                  "rules": {"day": f"preferred market per match: highest model probability ≥ {C.DAY_MIN_P*100:.0f}% among Sportybet-priced markets (odds never filter), data quality ≥ 60, both players ≥ {C.HIGHLIGHT_MIN_MATCHES} rated matches",
                            "strong": f"model ≥ {C.STRONG_MIN_P*100:.0f}% (same eligibility)",
                            "highlight": f"model − market implied between {C.EDGE_NOTE_PP:.0f} and {C.MAX_EDGE_PP:.0f} pp ({C.GAME_EDGE_PP:.0f} pp for game markets), one per match"}}
    (C.APP / "latest.json").write_text(json.dumps(app_latest, ensure_ascii=False))
    C.LATEST.write_text(json.dumps({"meta": meta, "matches": matches, "highlights": highlights, "tracker": tsum}, ensure_ascii=False))
    for m in matches:
        (C.APP / "matches" / f"{m['id']}.json").write_text(json.dumps(m, ensure_ascii=False))
    # keep only recent per-match files
    cutoff = (today - timedelta(days=7)).isoformat()
    for p in (C.APP / "matches").glob("*.json"):
        try:
            if json.loads(p.read_text()).get("day", "9999") < cutoff:
                p.unlink()
        except Exception:                                # noqa: BLE001
            pass
    touched = H.update_day_files(slims, results_by_id, day)
    log.info("day files updated: %s", ", ".join(touched))
    H.write_day_file(day, {"day": day, "generated": meta["generated"], "matches": matches})
    # players: top 100 ratings per tour (transparency)
    pl_names = {**{r["p1"]["pid"]: r["p1"]["name"] for r in matches}, **{r["p2"]["pid"]: r["p2"]["name"] for r in matches}}
    names = D.load_players().set_index("pid")["name"].to_dict()
    top = sorted(((pid, r) for pid, r in R.r.items() if R.n.get(pid, 0) >= C.MIN_MATCHES_RATED), key=lambda x: -x[1])[:200]
    (C.APP / "players" / "ratings.json").write_text(json.dumps({"generated": meta["generated"], "players": [
        {"pid": pid, "name": names.get(pid) or pl_names.get(pid) or pid, "rating": round(r), "matches": R.n.get(pid, 0), "last": R.last.get(pid)} for pid, r in top]}))
    (C.APP / "tournaments" / "surfaces.json").write_text(json.dumps({"generated": meta["generated"], "resolved": [
        dict(m["surface_info"], tour=m["tour"], category=m["category"]) for m in {m["tournament"]: m for m in matches}.values()]}, ensure_ascii=False))
    # 8. reports
    md = REP.markdown(day, matches, highlights, tsum, meta, selections=selections, strong=strong, sections=sections)
    (C.REPORTS / f"{day}.md").write_text(md, encoding="utf-8")
    (C.REPORTS / "latest.md").write_text(md, encoding="utf-8")
    REP.write_csv(C.REPORTS / f"{day}.csv", matches)
    pdf = REP.write_pdf(md, C.REPORTS / f"{day}.pdf", day)
    # 9. Telegram (report hours SAST, once per hour slot, or forced)
    hour_sast = (now + timedelta(hours=C.TZ_OFFSET_HOURS)).hour
    stamp = C.DATA / "last_report.txt"
    due = next((h for h in C.REPORT_HOURS_SAST if h <= hour_sast <= h + 1), None)   # GitHub cron may start a run late
    slot = f"{day} {due}"
    if os.getenv("TENNIS_REPORT") == "1" or (due is not None and (not stamp.exists() or stamp.read_text().strip() != slot)):
        text = telegram_text(day, matches, highlights, meta, sections=sections, strong=strong, tracker=tsum)
        if N.send_text(text):
            stamp.write_text(slot)
        if pdf:
            N.send_document(pdf, f"Tennis report {day} (PDF)")
        N.send_document(C.REPORTS / f"{day}.csv", f"Tennis markets {day} (CSV)")
    log.info("done: %d matches, %d priced, %d highlights, %.0f s", len(matches), meta["priced"], len(highlights), time.time() - t0)
    return 0


def telegram_text(day: str, matches: list[dict], highlights: list[dict], meta: dict, sections: list | None = None, strong: list | None = None,
                  tracker: dict | None = None) -> str:
    L = [f"{N.TAG} — {day}", f"{len(matches)} singles matches in the next {meta['lookahead_hours']} h · {meta['priced']} priced by Sportybet", ""]
    n_sel = sum(len(sec["selections"]) for sec in (sections or []))
    if n_sel:
        L.append(f"Selections of the day ({n_sel} matches, one preferred market each, ranked by model probability):")
        for sec in sections or []:
            L.append(f"— {sec['title']} —")
            for x in sec["selections"][:8]:
                L.append(f"• {REP.sast(x['start'])} {x['match']} — {x['label']}: model {x['model_p']*100:.0f}% (fair {x['fair_odds']:.2f}) · Sportybet {x['book_odds']:.2f} "
                         f"(implied {x['implied_fair']*100:.0f}%) · DQ {x['quality']}%{' · STRONG' if x.get('strong') else ''}")
        L.append("")
    else:
        L += ["No match clears the selection rules today (model ≥ 60%, data quality ≥ 60%).", ""]
    if strong:
        L.append(f"Strong markets (model ≥ 70% and market ≥ 50%): {len(strong)} across {len({x['match_id'] for x in strong})} matches — full list in the app.")
        L.append("")
    if highlights:
        L.append("Model above market (disagreements, not tips):")
        for h in highlights[:12]:
            L.append(f"• {REP.sast(h['start'])} {h['match']} — {h['label']}: model {h['model_p']*100:.0f}% (fair {h['fair_odds']:.2f}) vs {h['book_odds']:.2f} "
                     f"(implied {h['implied_fair']*100:.0f}%), edge {h['edge_pp']:+.1f} pp, data quality {h['quality']}%")
    else:
        L.append("No model/market disagreement clears the thresholds today.")
    L += ["", "Strongest model favourites:"]
    for m in sorted(matches, key=lambda m: -max(m["p"]["a"], m["p"]["b"]))[:8]:
        fav = m["p1"] if m["p"]["a"] >= 0.5 else m["p2"]
        pf = max(m["p"]["a"], m["p"]["b"])
        L.append(f"• {REP.sast(m['start'])} {fav['name']} {pf*100:.0f}% (fair {1/pf:.2f}) · {m['tournament']} · DQ {m['quality']['score']}%")
    t = tracker or {}
    if t.get("settled"):
        d = (t.get("by_kind") or {}).get("day") or {}
        L += ["", f"Record so far: {t['won']}/{t['settled']} tracked selections won" + (f" · day selections {d['won']}/{d['settled']} (avg model {d['avg_model_p']*100:.0f}%)" if d.get("settled") else "")]
    L += ["", "Model = results-only Elo (surface & format aware); prices are a comparison layer. Data quality ≠ probability. A 70% selection loses 3 times in 10. Full tables in the PDF/CSV and in the app."]
    return "\n".join(L)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    sys.exit(main())
