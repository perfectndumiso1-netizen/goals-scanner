"""Data checks before a publication is promoted to the app (and before the ledgers are trusted).

`check_publication()` inspects the staged export (latest.json, meta.json, alerts.json, per-match files) and the
ledger, and returns (errors, warnings). Any error blocks the promotion: the app keeps the previous publication and
the run reports the problem on Telegram / in the log instead of publishing something broken.
"""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime
from pathlib import Path

import safe

MAX_LATEST_MB = 4.0
STATUSES = {"pending", "hit", "miss", "void"}


def _archive_ids(staging: Path) -> set:
    """Fixture ids present in the day archive (the 60-day history files).

    High-probability selections and shortlist picks can legitimately point at matches outside the
    published app window (they are analysed early, up to 60 days ahead); the app renders them from
    the bet objects themselves and the Days tab carries their detail.
    """
    out = set()
    days_dir = staging.parent / "days"
    if days_dir.is_dir():
        for p in days_dir.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for f in d.get("fixtures") or []:
                if f.get("id"):
                    out.add(f["id"])
    return out


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not (isinstance(x, float) and math.isnan(x))


def _prob(x) -> bool:
    return _num(x) and -1e-9 <= x <= 1 + 1e-9


def context_budget(det: dict) -> tuple[float, float, float, float, bool]:
    """How far a detail file may depart from the statistical model, and how far it does.

    Returns (allowed_pp, worst_pp, allowed_xg, worst_xg, declared):
      * nothing is allowed unless the detail file carries a context block that declares the adjustment and its
        size (`context.totals.adjust_enabled`, `max_pp`, `lam_pct_h/a`) — so a silent blend (bookmaker odds
        creeping into a published probability) remains a hard error, which is what this check is for;
      * when it is declared, the allowance is exactly the adjustment the record names, plus rounding tolerance,
        never a blanket permission.
    """
    det = det or {}
    ctx = det.get("context") or {}
    tot = ctx.get("totals") or {}
    declared = bool(tot.get("adjust_enabled"))
    tol = 0.2
    allowed_pp = float(tot.get("max_pp") or 0.0) + tol if declared else 0.0
    worst_pp = 0.0
    for s in det.get("sels") or []:
        if len(s) >= 3 and _num(s[1]) and _num(s[2]):
            worst_pp = max(worst_pp, abs(float(s[1]) - float(s[2])) * 100.0)
    p = det.get("p") or {}
    if _num(p.get("model_O25")) and _num(p.get("O25")):
        worst_pp = max(worst_pp, abs(float(p["O25"]) - float(p["model_O25"])) * 100.0)
    if _num(p.get("model_BTTS")) and _num(p.get("BTTS")):
        worst_pp = max(worst_pp, abs(float(p["BTTS"]) - float(p["model_BTTS"])) * 100.0)
    xg = det.get("xg") or {}
    allowed_xg = worst_xg = 0.0
    if _num(xg.get("home")) and _num(xg.get("model_home")):
        worst_xg = abs(float(xg["home"]) - float(xg["model_home"]))
        if declared:
            lam = max(abs(float(tot.get("lam_pct_h") or 0.0)), abs(float(tot.get("lam_pct_a") or 0.0)))
            allowed_xg = abs(float(xg["model_home"])) * lam / 100.0 + 0.02
    return allowed_pp, worst_pp, allowed_xg, worst_xg, declared


def check_publication(staging: Path, live: Path, ledger: Path, now: datetime, expect_fixtures: int) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warns: list[str] = []
    latest_p = staging / "latest.json"
    if not latest_p.exists():
        return ["latest.json missing"], warns
    if latest_p.stat().st_size > MAX_LATEST_MB * 1e6:
        errors.append(f"latest.json too large ({latest_p.stat().st_size / 1e6:.1f} MB)")
    try:
        d = json.loads(latest_p.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"latest.json is not valid JSON: {exc}"], warns
    if d.get("version") != 3:
        errors.append(f"unexpected format version {d.get('version')}")
    meta = d.get("meta") or {}
    if meta.get("generated") != now.strftime("%Y-%m-%d %H:%M"):
        errors.append(f"meta.generated {meta.get('generated')!r} != run time")
    fixtures = d.get("fixtures") or []
    if expect_fixtures and not fixtures:
        errors.append("no fixtures in the publication although the scan had rows")
    ids = set()
    n_detail_missing = 0
    for f in fixtures:
        fid = f.get("id")
        if not fid or fid in ids:
            errors.append(f"duplicate or empty fixture id {fid!r}")
            continue
        ids.add(fid)
        try:
            datetime.strptime(f.get("kickoff", ""), "%Y-%m-%d %H:%M")
        except ValueError:
            errors.append(f"bad kickoff {f.get('kickoff')!r} for {fid}")
        p = f.get("p") or {}
        for k in ("O15", "O25", "BTTS"):
            if p.get(k) is not None and not _prob(p[k]):
                errors.append(f"probability {k}={p[k]!r} out of range for {fid}")
        if _prob(p.get("O15")) and _prob(p.get("O25")) and p["O25"] > p["O15"] + 1e-6:
            errors.append(f"P(O2.5) > P(O1.5) for {fid}")
        x12 = f.get("x12") or []
        if len(x12) == 3 and all(_num(v) for v in x12) and abs(sum(x12) - 1) > 0.05:
            warns.append(f"1X2 probabilities sum to {sum(x12):.2f} for {fid}")
        xg = f.get("xg") or []
        if len(xg) == 2 and all(_num(v) for v in xg) and (min(xg) < 0 or max(xg) > 6):
            warns.append(f"odd expected goals {xg} for {fid}")
        key = f.get("d")
        if key and not (staging / "fx" / f"{key}.json").exists() and not (live / "fx" / f"{key}.json").exists():
            n_detail_missing += 1
        for side in ("home", "away"):
            if not f.get(side):
                errors.append(f"missing {side} team for {fid}")
    if n_detail_missing:
        (errors if n_detail_missing > 3 else warns).append(f"{n_detail_missing} fixture(s) without a detail file")
    # ---- data-first engine: the detail files must carry the evidence layer and no market-contaminated probability
    n_checked = n_noq = n_blend = 0
    blend_examples: list[str] = []
    for f in fixtures:
        key = f.get("d")
        fp = staging / "fx" / f"{key}.json"
        if not key or not fp.exists() or f.get("frozen"):
            continue
        try:
            det = json.loads(fp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        n_checked += 1
        q = det.get("quality") or {}
        if q.get("overall") not in ("High", "Medium", "Low"):
            n_noq += 1
        # The published probability may differ from the statistical model ONLY through a bounded, declared
        # context adjustment (the research layer's record). Anything else — a delta with no record behind it,
        # or a delta larger than the adjustment it declares — is the market-contamination error this check
        # exists for, and it still blocks the publication.
        allowed_pp, worst_pp, allowed_xg, worst_xg, declared = context_budget(det)
        if worst_pp > allowed_pp + 1e-9 or worst_xg > allowed_xg + 1e-9:
            n_blend += 1
            if len(blend_examples) < 5:
                blend_examples.append(f"{key}: {worst_pp:.2f} pp / {worst_xg:.2f} xG off the model (allowed "
                                      f"{allowed_pp:.2f} pp / {allowed_xg:.2f} xG; declared: {declared})")
    if n_checked and n_noq:
        (errors if n_noq > 3 else warns).append(f"{n_noq} of {n_checked} detail files without a data-quality assessment")
    if n_blend:
        errors.append(f"{n_blend} detail file(s) where a published probability / xG differs from the statistical model "
                      "without a declared, bounded context adjustment (market contamination): "
                      + "; ".join(blend_examples))
    sf = d.get("safe") or {}
    min_p = float(sf.get("min_p") or 0.7)
    known = ids | _archive_ids(staging)
    for b in sf.get("bets") or []:
        if b.get("fixture") not in known:
            errors.append(f"safest bet on unknown fixture {b.get('fixture')}")
        if not b.get("live"):
            if not _num(b.get("p")) or b["p"] < min_p - 1e-6:
                errors.append(f"safest bet below the probability rule: {b.get('label')} {b.get('p')}")
        if safe.OVERS_ONLY and safe.is_under(str(b.get("sel", ""))):
            errors.append(f"under selection in safest bets: {b.get('sel')}")
    seen_match = set()
    for b in (sf.get("bets") or []):
        if b.get("live"):
            continue
        m = (b.get("home"), b.get("away"))
        if m in seen_match:
            warns.append(f"more than one market on {m[0]} v {m[1]} in safest bets")
        seen_match.add(m)
    today = sf.get("today") or {}
    section_keys = {g[0] for g in safe.BOTD_GROUPS}
    card_matches = {}
    for b in today.get("bets") or []:
        if b.get("status") not in STATUSES:
            errors.append(f"bad status {b.get('status')!r} on day-card bet {b.get('id')}")
        if b.get("section") not in section_keys:
            errors.append(f"unknown day-card section {b.get('section')!r}")
        m = (b.get("home"), b.get("away"))
        if m in card_matches and card_matches[m] != b.get("sel"):
            warns.append(f"two markets on {m[0]} v {m[1]} in the day card")
        card_matches[m] = b.get("sel")
    # the daily acca builds: the contract is what makes them honest, so it is enforced on every publication
    ac = d.get("accas") or {}
    tried = set()
    for i, b in enumerate(ac.get("bets") or []):
        legs = b.get("legs") or []
        n = b.get("n_legs") or len(legs)
        if not legs:
            errors.append(f"acca {b.get('id')} published with no legs")
            continue
        if n < 2 or n > 3:
            errors.append(f"acca {b.get('id')} has {n} legs (the plan is 2-3: fewer legs is the cheapest way to the price)")
        if not _num(b.get("odds")) or abs(float(b["odds"]) - float(ac.get("target") or 3)) > 0.06:
            errors.append(f"acca {b.get('id')} priced {b.get('odds')} against a {ac.get('target')} target")
        if not _num(b.get("p")) or not _num(b.get("p_market")):
            errors.append(f"acca {b.get('id')} is missing its model or market probability")
        elif float(b["p"]) > 1 or float(b["p_market"]) > 1:
            errors.append(f"acca {b.get('id')} has a probability above 1")
        matches = set()
        for leg in legs:
            if leg.get("fixture") not in known:
                errors.append(f"acca {b.get('id')} leg on unknown fixture {leg.get('fixture')}")
            m = (leg.get("country"), leg.get("home"), leg.get("away"))
            if m in matches:
                errors.append(f"acca {b.get('id')} takes two markets from one match ({m[1]} v {m[2]})")
            matches.add(m)
            if m in tried:
                errors.append(f"acca {b.get('id')} shares a match with an earlier build ({m[1]} v {m[2]})")
            tried.add(m)
            e = leg.get("edge_pp")
            lo, hi = (ac.get("edge_pp") or [2.0, 12.0])
            if not _num(e) or float(e) < float(lo) - 0.05 or float(e) > float(hi) + 0.05:
                errors.append(f"acca {b.get('id')} leg {leg.get('label')} carries a {e} pp edge, outside the "
                              f"{lo}-{hi} pp gate (below it is paying the vig, above it is a data fault)")
    if ac.get("bets") and not ac.get("ids"):
        errors.append("acca builds published without their ledger ids (settlement would lose them)")
    for mkt, lst in (d.get("picks") or {}).items():
        for pk in lst:
            if pk.get("fixture") not in known:
                errors.append(f"{mkt} pick on unknown fixture {pk.get('fixture')}")
    for name in ("meta.json", "alerts.json", "badges.json"):
        p = staging / name
        if not p.exists():
            errors.append(f"{name} missing")
            continue
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except ValueError as exc:
            errors.append(f"{name} is not valid JSON: {exc}")
    # ledger invariants
    if ledger.exists():
        try:
            with ledger.open(encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh))
            seen = set()
            for r in rows:
                k = (r.get("match_date"), r.get("home"), r.get("away"), r.get("sel"))
                if k in seen:
                    errors.append(f"duplicate ledger row {k}")
                seen.add(k)
                if r.get("status") not in STATUSES:
                    errors.append(f"bad ledger status {r.get('status')!r} for {k}")
                try:
                    pv = float(r.get("p") or "nan")
                    if not (0 <= pv <= 1):
                        errors.append(f"ledger probability out of range for {k}")
                except ValueError:
                    errors.append(f"ledger probability not numeric for {k}")
                if r.get("status") in ("hit", "miss") and not (r.get("score") or "").strip():
                    warns.append(f"settled ledger row without a score: {k}")
        except (OSError, csv.Error) as exc:
            errors.append(f"ledger unreadable: {exc}")
    return errors, warns
