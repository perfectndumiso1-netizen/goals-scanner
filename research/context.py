"""The engine: collect facts for a fixture, score them with rules, and (only if enabled) adjust the goal rates.

Flow for one fixture (`Engine.run`):

    1. COLLECT   facts from the collectors (fatigue, motivation, line-ups, team news, weather)
    2. FRESHNESS each fact is marked current or stale (stale facts are shown, never used)
    3. CONFLICT  contradictory availability reports are recorded, and zero their category
    4. RULES     every rule runs and reports a proposal (0 with the shipped weights)
    5. BOUND     proposals are capped per category, then in total (`max_lambda_pct`, then `max_adj_pp`)
    6. APPLY     the *existing* score-matrix maths is re-run on the adjusted rates -> final probabilities
    7. RECORD    base vs final, the reasons, the sources, the quality grade and the conflicts are stored

What it will never do: read bookmaker / Sportybet prices (there is no odds field anywhere in this package), touch
`p_model` (the base probability stays exactly as the statistical model produced it), or adjust on weak, stale or
contradictory evidence.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from . import facts as F
from . import fatigue, lineups, motivation, rules, teamnews, weather
from .store import Store

log = logging.getLogger("research.context")

MARKETS = ("O15", "O25", "O35", "BTTS", "HW", "AW")


@dataclass
class Config:
    """Env-driven, like the rest of the scanner.  Defaults are deliberately inert: collect, never adjust."""
    enabled: bool = True
    adjust: bool = False                 # master switch for touching lambda at all
    max_adj_pp: float = 2.0              # hard ceiling on any published market, in percentage points
    max_lambda_pct: float = 6.0          # hard ceiling on the combined lambda move, in %
    weights: dict = field(default_factory=lambda: dict(rules.DEFAULT_WEIGHTS))
    horizon_h: float = 72.0              # fixtures further out are not researched (staged design)
    lineup_lead_min: float = 120.0       # when to start asking the feed for XIs
    weather_horizon_h: float = 48.0
    budget_s: float = 60.0
    ttl_h: float = 6.0
    keep_days: int = 7
    max_records: int = 2000
    max_mb: float = 8.0
    budget_lineups: int = 60
    budget_geocodes: int = 8
    budget_weather: int = 60
    store_file: str = "records.json"
    venues_file: str = "venues.json"
    lineups_file: str = "lineups_cache.json"
    weather_file: str = "weather_cache.json"


def apply_rules(lam_h: float, lam_a: float, scored: list[rules.Rule]) -> tuple[float, float]:
    """One definition of what a proposal *means*, applied to the goal rates.

    home  : the home side is the one affected — its rate falls (or rises), and the opponent's moves half as far
            the other way, because a tired team also concedes more;
    away  : mirror image;
    both  : both sides' rates move together (a condition shared by the two teams);
    total : both rates move the same way (weather affects the match, not one team).
    """
    for r in scored:
        if not r.lam_pct:
            continue
        x = r.lam_pct / 100.0
        if r.target == "home":
            lam_h *= 1 + x
            lam_a *= 1 - x / 2
        elif r.target == "away":
            lam_a *= 1 + x
            lam_h *= 1 - x / 2
        else:                                   # both | total
            lam_h *= 1 + x
            lam_a *= 1 + x
    return max(0.05, lam_h), max(0.05, lam_a)


def pp_delta(base: dict, other: dict) -> dict:
    """Per-market difference in percentage points (base -> other), rounded for display."""
    return {m: round(100.0 * (float(other.get(m, 0.0)) - float(base.get(m, 0.0))), 3) for m in MARKETS
            if base.get(m) is not None}


def clamp(base_lh: float, base_la: float, lam_h: float, lam_a: float, base_probs: dict, prob_fn,
          max_pp: float, max_lambda_pct: float) -> tuple[float, float, bool]:
    """Scale the proposed lambda move down until (a) it is inside the lambda ceiling and (b) every published
    market is inside the percentage-point ceiling.  Deterministic bisection on one scale factor — the direction
    and the relative size of the adjustment are preserved."""
    dh = lam_h / base_lh - 1.0
    da = lam_a / base_la - 1.0
    cap = max_lambda_pct / 100.0
    worst = max(abs(dh), abs(da))
    if worst > cap > 0:
        k = cap / worst
        dh, da = dh * k, da * k
    if abs(dh) < 1e-12 and abs(da) < 1e-12:
        return base_lh, base_la, False

    def attempt(k: float) -> tuple[dict, float]:
        pr = prob_fn(base_lh * (1 + dh * k), base_la * (1 + da * k))
        w = max((abs(100.0 * (float(pr.get(m, 0.0)) - float(base_probs[m]))) for m in MARKETS
                 if base_probs.get(m) is not None), default=0.0)
        return pr, w

    if attempt(1.0)[1] <= max_pp:
        return base_lh * (1 + dh), base_la * (1 + da), False
    lo, hi = 0.0, 1.0
    for _ in range(26):
        mid = (lo + hi) / 2.0
        if attempt(mid)[1] > max_pp:
            hi = mid
        else:
            lo = mid
    return base_lh * (1 + dh * lo), base_la * (1 + da * lo), True


class Engine:
    """Per-run research engine: holds the collectors' caches and the record store; one instance per scan."""

    def __init__(self, cfg: Config, now: datetime, research_dir: Path, prob_fn, apply_fn, *,
                 news_fn=None, news_horizon_h: float = 24.0):
        self.cfg = cfg
        # one clock for the whole layer, always timezone-aware: naive input (tests, odd callers) is read as the
        # scanner's own wall clock, exactly like facts.iso() does, so nothing inside ever compares naive to aware
        self.now = F.as_aware(now, now) or now
        self.dir = Path(research_dir)
        self.prob_fn = prob_fn                 # scanner's own score_matrix()+probs_from_matrix(), injected
        self.apply_fn = apply_fn               # scanner hook: re-run its maths on adjusted rates
        self.dir.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.dir / cfg.store_file, keep_days=cfg.keep_days, max_records=cfg.max_records,
                           max_mb=cfg.max_mb)
        # news_fn(team, country) -> list[headline dicts]; the scanner injects it and it goes through the *same*
        # cache object and request budget the app's News tab uses, so a team is fetched once per run at most.
        self.news_fn = news_fn
        self.news_horizon_h = float(news_horizon_h)
        self.venues = weather.Venues(self.dir / cfg.venues_file, budget=cfg.budget_geocodes)
        self.lineup_client = lineups.Client(self.dir / cfg.lineups_file, budget=cfg.budget_lineups)
        self.weather_cache = weather.WeatherCache(self.dir / cfg.weather_file, ttl_h=cfg.ttl_h,
                                                  budget=cfg.budget_weather)
        self.results = None
        self.index: fatigue.MatchIndex | None = None
        self.stats = {"researched": 0, "facts": 0, "adjusted": 0, "skipped": 0, "errors": 0, "quality": {}}

    # -- inputs
    def with_history(self, results) -> "Engine":
        """Fatigue/motivation read the results frame the scanner already has in memory — no external calls."""
        self.results = results
        self.index = fatigue.MatchIndex(results, self.now) if results is not None else None
        return self

    # -- collection
    def _fx_view(self, row):
        """A read-only copy of the fixture whose kick-off is timezone-aware (the row itself is never mutated)."""
        fx, ko = row.fx, F.as_aware(row.fx.get("kickoff"), self.now)
        if ko is None or ko is fx.get("kickoff"):
            return fx
        view = dict(fx)
        view["kickoff"] = ko
        return view

    def collect(self, row, support: str = "full", fx=None) -> list[F.Fact]:
        fx, now = (fx if fx is not None else self._fx_view(row)), self.now
        out: list[F.Fact] = []
        if self.index is not None:
            out += fatigue.facts_for(self.index, fx, now)
        if self.results is not None:
            out += motivation.facts_for(self.results, fx, now, support)
        out += lineups.facts_for(fx, now, self.lineup_client, self.cfg.lineup_lead_min,
                                 eid=(fx.get("eid") or None),
                                 match_started=bool(F.as_aware(fx["kickoff"], now) <= now))
        in_news_window = (F.as_aware(fx["kickoff"], now) - now) <= timedelta(hours=self.news_horizon_h)
        fetched, statuses = None, {}
        if self.news_fn is not None and in_news_window:
            country = str(fx.get("country") or "")
            fetched = {}
            for side in ("home", "away"):
                team = str(fx[side])
                try:
                    res = self.news_fn(team, country)
                    items, status = res if isinstance(res, tuple) else (res, "fetched")
                    fetched[side] = items or []
                    statuses[side] = status
                except Exception as exc:  # noqa: BLE001 - news is context only
                    log.debug("news lookup failed for %s: %s", team, exc)
                    fetched[side] = []
        out += teamnews.facts_for(row, now, fetched=fetched, statuses=statuses,
                                  looked_up=bool(self.news_fn is not None and in_news_window))
        out += weather.facts_for(fx, now, self.venues, self.weather_cache,
                                 horizon_h=self.cfg.weather_horizon_h)
        for f in out:
            f.status = F.freshness(f, now, fx["kickoff"] if f.category == "lineup" else None)
        if out:
            out[0].value = {**out[0].value, "competition_support": support}
        return out

    # -- the whole flow for one fixture
    def run(self, row, fid: str, support: str = "full", stage: str = "collect") -> F.ResearchRecord:
        now = self.now
        fx = self._fx_view(row)
        rec = F.ResearchRecord(fid=fid, kickoff=fx["kickoff"].strftime("%Y-%m-%d %H:%M"),
                               updated=now.strftime("%Y-%m-%dT%H:%M:%SZ"), stage=stage, support=support)
        try:
            facts = self.collect(row, support, fx=fx)
            conflicts = [*F.mark_conflicts(facts), *teamnews.availability_conflict(facts)]
            blocked = {"team_news"} if any(not str(c.get("resolution", "")).startswith("resolved")
                                           for c in conflicts) else set()
            weights = {k: (0.0 if (not self.cfg.adjust or k in blocked) else float(v))
                       for k, v in (self.cfg.weights or {}).items()}
            scored = rules.run_all(facts, now, weights, {"home": str(fx["home"]), "away": str(fx["away"]),
                                                         "kickoff": fx["kickoff"]})

            base_probs = {m: float(row.p_model[m]) for m in MARKETS if m in row.p_model}
            base_lh, base_la = float(row.lam_h), float(row.lam_a)
            # The engine reproduces the model probability from the model's own rates with the model's own maths.
            # It must match the published base probability, otherwise the layer refuses to touch anything (a
            # mismatch would mean we are adjusting a *different* number from the one on screen).
            model_probs = {m: float(self.prob_fn(base_lh, base_la).get(m, 0.0)) for m in base_probs}
            mismatch = max((abs(model_probs[m] - base_probs[m]) for m in base_probs), default=0.0)
            consistent = mismatch <= 0.01
            lam_h, lam_a, capped, applied = base_lh, base_la, False, False
            final = dict(base_probs)
            if not consistent:
                log.warning("Research: recomputed base differs from the published model probability by %.4f — "
                            "no adjustment for this fixture", mismatch)
            if consistent and self.cfg.adjust and any(r.lam_pct for r in scored):
                lam_h, lam_a = apply_rules(base_lh, base_la, scored)
                lam_h, lam_a, capped = clamp(base_lh, base_la, lam_h, lam_a, model_probs, self.prob_fn,
                                             self.cfg.max_adj_pp, self.cfg.max_lambda_pct)
                if abs(lam_h - base_lh) > 1e-9 or abs(lam_a - base_la) > 1e-9:
                    pr = self.prob_fn(lam_h, lam_a)
                    final = {m: float(pr.get(m, base_probs[m])) for m in base_probs}
                    applied = True

            adj_rows = []
            for r in scored:
                d = {"cat": r.cat, "weight": r.weight, "strength": r.strength, "target": r.target,
                     "reason": r.reason, "sources": r.sources[:4], "fact_ids": r.fact_ids[:6],
                     "raw": round(float(r.raw), 3), "enabled": bool(r.enabled)}
                if r.lam_pct:
                    lh1, la1 = apply_rules(base_lh, base_la, [r])
                    d["pp"] = pp_delta(model_probs, self.prob_fn(lh1, la1))
                    d["lam_pct"] = round(r.lam_pct, 3)
                else:
                    d["pp"] = {m: 0.0 for m in base_probs}
                    d["lam_pct"] = 0.0
                adj_rows.append(d)

            quality, why = F.grade_quality(facts, conflicts, now, fx["kickoff"], support)
            rec.facts, rec.conflicts, rec.adjustments = facts, conflicts, adj_rows
            rec.quality, rec.quality_reasons = quality, why
            rec.base = {m: round(float(base_probs[m]), 4) for m in base_probs}
            rec.final = {m: round(float(final[m]), 4) for m in base_probs}
            delta = pp_delta(base_probs, final) if applied else {m: 0.0 for m in base_probs}
            rec.totals = {"lam_pct_h": round(100.0 * (lam_h / base_lh - 1.0), 3),
                          "base_consistent": bool(consistent),
                          "lam_pct_a": round(100.0 * (lam_a / base_la - 1.0), 3),
                          "max_pp": round(max((abs(v) for v in delta.values()), default=0.0), 3),
                          "applied": applied, "capped": capped, "adjust_enabled": bool(self.cfg.adjust)}
            rec.notes = ([f"base probability not reproduced by the engine (delta {mismatch:.4f} pp) — "
                          "adjustment disabled"] if not consistent else []) + [
                         f"{len(facts)} fact(s), {sum(1 for f in facts if f.status == 'current')} current",
                         f"line-up requests this run: {self.lineup_client.used}",
                         f"new venues geocoded: {self.venues.used}"]
            if capped:
                rec.notes.append(f"adjustment capped by the {self.cfg.max_adj_pp:.1f} pp ceiling")

            if applied:
                self.apply_fn(row, lam_h, lam_a, final)     # scanner re-runs its own maths with these rates
                self.stats["adjusted"] += 1
            row.audit["context"] = rec.app_view()
            self.store.put(rec.to_dict())
            self.stats["researched"] += 1
            self.stats["facts"] += len(facts)
            self.stats["quality"][quality] = self.stats["quality"].get(quality, 0) + 1
        except Exception as exc:  # noqa: BLE001 - research must never break a scan
            self.stats["errors"] += 1
            log.warning("Research failed for %s: %s", rec.kickoff, exc)
            log.debug("research failure detail", exc_info=True)
            rec.notes.append(f"research error: {exc}")
        return rec

    # -- run level
    def should_research(self, row) -> bool:
        ko = F.as_aware(row.fx["kickoff"], self.now)
        if ko is None:
            return False
        return (self.now - timedelta(hours=6)) <= ko <= (self.now + timedelta(hours=self.cfg.horizon_h))

    def finish(self) -> dict:
        """Persist caches + the store; returns the summary block for the run log / app meta."""
        try:
            self.lineup_client.save()
            self.venues.save()
            self.weather_cache.save()
            self.stats["store_records"] = self.store.save(self.now)
            self.stats["lineup_requests"] = self.lineup_client.used
            self.stats["geocode_requests"] = self.venues.used
            self.stats["weather_calls"] = self.weather_cache.used
            self.stats["store_bytes"] = self.store.size_bytes()
            if self.store.dropped:
                log.info("Research store: dropped %s (limits %s)", self.store.dropped, self.store.limits())
            log.info("Research: %d fixture(s), %d fact(s), %d adjustment(s), quality %s · line-up requests %d, "
                     "new venues %d, store %d record(s) / %.0f KB",
                     self.stats["researched"], self.stats["facts"], self.stats["adjusted"], self.stats["quality"],
                     self.lineup_client.used, self.venues.used, self.stats["store_records"],
                     self.stats["store_bytes"] / 1024.0)
        except Exception as exc:  # noqa: BLE001
            log.warning("Research store save failed: %s", exc)
        return self.stats
