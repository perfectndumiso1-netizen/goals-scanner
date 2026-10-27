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

import policy
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


def _anchored(det: dict) -> tuple[float, bool]:
    """How far the declared market anchor can legitimately move a published probability, and whether it does.

    Returns (allow_pp, ok). The anchor is declared in the detail file (`context.market_anchor`, written by
    `policy.market_anchor_record`). When it is declared, every published probability must be reproducible from the
    inputs the file also carries — the model number the anchor was applied to (`final_*`, or a `sels` row's second
    and third columns) and the de-vigged market it anchored to (`market_*` / `p_sb`) — through `policy.publish_p`.
    One number that does not come out of the formula, and the anchor explains nothing: the old zero-tolerance rule
    applies again. That keeps the gate meaningful instead of turning it off with a boolean.
    """
    ctx = det.get("context") or {}
    anchor = ctx.get("market_anchor") or {}
    if not anchor.get("enabled"):
        return 0.0, False
    allow = 0.0
    for s in det.get("sels") or []:
        if len(s) >= 4 and _num(s[1]) and _num(s[2]) and _num(s[3]):
            want = policy.publish_p(float(s[2]), float(s[3]))
            if want is None or abs(float(s[1]) - want) > 0.004:
                return 0.0, False
            allow = max(allow, abs(float(s[1]) - float(s[2])) * 100.0)
    p = det.get("p") or {}
    for key in ("O15", "O25", "O35", "BTTS"):
        pub, model = p.get(key), p.get(f"final_{key}")
        mkt = p.get(f"market_{key}")
        if not (_num(pub) and _num(model) and _num(mkt) and 0 < float(mkt) < 1):
            continue
        want = policy.publish_p(float(model), float(mkt))
        if want is None or abs(float(pub) - want) > 0.004:
            return 0.0, False
        if _num(p.get(f"model_{key}")):
            allow = max(allow, abs(float(pub) - float(p[f"model_{key}"])) * 100.0)
    return allow, True


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
    anchor_pp, anchor_ok = _anchored(det)
    if anchor_ok:
        # a declared, reproducible anchor explains exactly the gap it produced — nothing more
        allowed_pp = max(allowed_pp, anchor_pp + tol)
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
    manifest_p = staging / "run_manifest.json"
    if not manifest_p.exists():
        errors.append("run_manifest.json missing")
    else:
        try:
            manifest = json.loads(manifest_p.read_text(encoding="utf-8"))
            if manifest.get("schema_version") != d.get("version"):
                errors.append(f"run manifest schema version {manifest.get('schema_version')!r} does not match app version {d.get('version')!r}")
            if meta.get("run_id") and manifest.get("run_id") != meta.get("run_id"):
                errors.append("run manifest run_id does not match latest.json meta.run_id")
            for field in ("run_id", "model_version", "config_sha256", "generated_at", "feed_health", "counts"):
                if field not in manifest:
                    errors.append(f"run manifest missing {field}")
            digest = manifest.get("config_sha256")
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                errors.append("run manifest config_sha256 is not a lowercase SHA-256 hex digest")
            if not isinstance(manifest.get("feed_health"), dict) or not isinstance(manifest.get("counts"), dict):
                errors.append("run manifest feed_health and counts must be objects")
        except (OSError, ValueError, AttributeError) as exc:
            errors.append(f"run_manifest.json is not valid JSON: {exc}")
    fixtures = d.get("fixtures") or []
    if expect_fixtures and not fixtures:
        errors.append("no fixtures in the publication although the scan had rows")
    if not fixtures:
        live_latest = live / "latest.json"
        try:
            live_d = json.loads(live_latest.read_text(encoding="utf-8")) if live_latest.exists() else {}
            live_fx = live_d.get("fixtures") or []
            cut = now.strftime("%Y-%m-%d %H:%M")
            remaining = [f for f in live_fx if str((f or {}).get("kickoff") or "")[:16] >= cut]
            if remaining:
                errors.append(f"empty publication would wipe {len(remaining)} live fixture(s) still in the window")
        except (OSError, ValueError, TypeError):
            pass
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
        # 2026-10-27: the published O2.5 is now anchored to the price and capped (market + 3 pp, 90 %), so the two
        # numbers can meet at the cap. A real inversion is still a data fault; a few points of it are the anchor.
        if _prob(p.get("O15")) and _prob(p.get("O25")) and p["O25"] > p["O15"] + 1e-6:
            if p["O25"] > p["O15"] + 0.05:
                errors.append(f"P(O2.5) > P(O1.5) for {fid}")
            else:
                warns.append(f"P(O2.5) {p['O25']:.2f} sits above P(O1.5) {p['O15']:.2f} for {fid} (market anchor)")
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
        # identity: the detail must belong to THIS fixture (user-reported bug: a match page
        # showed another match's stats). A mis-keyed file must block the publication.
        fxid = f.get("id")
        if det.get("id") is not None and fxid is not None and str(det.get("id")) != str(fxid):
            errors.append(f"detail file {key}.json belongs to {det.get('id')!r}, not {fxid!r}")
        for side in ("home", "away"):
            if det.get(side) and f.get(side) and str(det.get(side)) != str(f.get(side)):
                errors.append(f"detail file {key}.json has {side}={det.get(side)!r}, fixture says {f.get(side)!r}")
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
            # Over 2.5 and BTTS START from 55% (policy.py, user rule 2026-10-17): the rule is per selection
            floor = policy.min_p(str(b.get("sel", "")), min_p)
            if not _num(b.get("p")) or b["p"] < floor - 1e-6:
                errors.append(f"safest bet below the probability rule: {b.get('label')} {b.get('p')}")
            # a live (carried-over) bet is frozen from the previous publication and may pre-date the policy,
            # so only this run's own bets are held to it
            if not policy.allowed(str(b.get("sel", ""))):
                errors.append(f"selection the market policy dropped in safest bets: {b.get('sel')}")
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
