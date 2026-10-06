"""Rule-based context scoring: facts in, a small *lambda* effect out.  No odds, no free-form judgement.

Every rule returns a `Rule` object:
  * `lam_pct`   the signed % change this rule proposes for the affected goal rate(s), *after* its weight;
  * `weight`    the configured weight (0.0 = disabled: the rule still reports what it saw, and proposes 0);
  * `reason`    one plain sentence a reader can check against the facts;
  * `fact_ids`  the facts the rule used, so the app can show the evidence behind any number;
  * `strength`  strong | weak | unavailable — a `weak` rule can never be scaled up by configuration.

Design rules encoded here:
  * normal weather => 0 (explicitly, by rule);
  * stale facts are ignored by every rule;
  * conflicts zero the category that owns them (handled in `context.py`);
  * every category has a hard ceiling (`MAX_PCT`) that a configured weight cannot exceed;
  * weights are the Phase-B gate: with the shipped defaults (all 0.0) every rule proposes exactly 0.0, which is
    what makes Phase A structurally incapable of changing a published probability.

How a proposal is applied to the goal rates is defined once, in `context.apply_rules()`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .facts import Fact, freshness

log = logging.getLogger("research.rules")

# Hard per-category ceilings (percentage points of the affected goal rate).  A weight can never exceed these.
MAX_PCT = {"lineup": 3.0, "fatigue": 3.0, "motivation": 2.0, "weather": 2.0}
DEFAULT_WEIGHTS = {"lineup": 0.0, "fatigue": 0.0, "motivation": 0.0, "weather": 0.0}


@dataclass
class Rule:
    cat: str
    weight: float
    raw: float                      # unscaled severity, 0..1
    lam_pct: float                  # signed % effect on the targeted goal rate(s), after weight + ceiling
    reason: str
    fact_ids: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    strength: str = "unavailable"   # strong | weak | unavailable
    target: str = "total"           # home | away | both | total
    enabled: bool = False

    def to_dict(self) -> dict:
        return {"cat": self.cat, "weight": round(float(self.weight), 4), "raw": round(float(self.raw), 4),
                "lam_pct": round(float(self.lam_pct), 4), "reason": self.reason, "fact_ids": self.fact_ids,
                "sources": self.sources, "strength": self.strength, "target": self.target,
                "enabled": bool(self.enabled)}


def _cap(cat: str, pct: float) -> float:
    lim = MAX_PCT.get(cat, 0.0)
    return max(-lim, min(lim, pct))


def _current(facts: list[Fact], category: str, now, kickoff=None) -> list[Fact]:
    return [f for f in facts if f.category == category and f.status == "current"
            and freshness(f, now, kickoff) == "current"]


def _side_of(subject: str, ctx: dict) -> str:
    s = str(subject).strip().lower()
    if s and s == str(ctx.get("home", "")).strip().lower():
        return "home"
    if s and s == str(ctx.get("away", "")).strip().lower():
        return "away"
    return ""


# --------------------------------------------------------------------------- rules
def fatigue_rule(facts: list[Fact], now, weight: float, ctx: dict) -> Rule:
    """Short rest (<= 4 days) or a congested week lowers a tired side's goal rate; the opponent's rate edges up
    because a tired team also concedes more.  When both sides are congested the effect is a lower total."""
    sig = [f for f in _current(facts, "fatigue", now, ctx.get("kickoff")) if f.kind == "schedule" and f.value]
    if not sig:
        return Rule("fatigue", weight, 0.0, 0.0, "no scheduling information — fatigue not assessed")
    sev: dict[str, tuple[float, Fact]] = {}
    for f in sig:
        days = float(f.value.get("days_since_last", 99))
        m7 = float(f.value.get("matches_7d", 0))
        raw = 1.0 if days <= 2 else 0.66 if days <= 3 else 0.33 if days <= 4 else 0.0
        if m7 >= 3:
            raw = min(1.0, raw + 0.34)
        side = _side_of(f.subject, ctx)
        if raw > 0 and side:
            sev[side] = (raw, f)
    if not sev:
        d = min((float(f.value.get("days_since_last", 99)) for f in sig), default=99)
        return Rule("fatigue", weight, 0.0, 0.0, f"rest is adequate (shortest gap {d:.0f} day(s))",
                    [f.id for f in sig], sorted({f.source for f in sig}), strength="strong")
    sides = sorted(sev)
    raw = max(r for r, _ in sev.values())
    target = "both" if len(sides) == 2 else sides[0]
    pct = _cap("fatigue", -MAX_PCT["fatigue"] * raw * float(weight))
    who = " and ".join(f"{sev[s][1].subject} ({float(sev[s][1].value.get('days_since_last', 0)):.0f} day(s))"
                       for s in sides)
    return Rule("fatigue", weight, raw, pct, f"congested schedule: {who}", [sev[s][1].id for s in sides],
                sorted({sev[s][1].source for s in sides}), strength="strong", target=target, enabled=weight > 0)


def motivation_rule(facts: list[Fact], now, weight: float, ctx: dict) -> Rule:
    """Stakes are NOT scored in Phase A: the points-based stakes model must be backtested first, so the rule says
    exactly that instead of pretending to know who is 'motivated'."""
    have = _current(facts, "motivation", now, ctx.get("kickoff"))
    if not have:
        return Rule("motivation", weight, 0.0, 0.0, "no competition-context information")
    return Rule("motivation", weight, 0.0, 0.0,
                "stakes (title / relegation / qualification / rotation) recorded but not scored until the "
                "backtested points model exists", [f.id for f in have], sorted({f.source for f in have}),
                strength="unavailable")


def weather_rule(facts: list[Fact], now, weight: float, ctx: dict) -> Rule:
    """Only genuinely severe conditions can adjust, and only downwards.  Normal weather is zero by rule — the
    layer therefore never 'explains' a result with the weather either."""
    w = [f for f in _current(facts, "weather", now, ctx.get("kickoff")) if f.kind == "conditions" and f.value]
    if not w:
        return Rule("weather", weight, 0.0, 0.0, "no weather information (N/A)")
    f = w[0]
    sev = str(f.value.get("severity") or "normal")
    head = f.text.split("—")[0].strip().rstrip(",")
    if sev == "normal":
        return Rule("weather", weight, 0.0, 0.0, f"normal weather ({head}) — no adjustment by rule", [f.id],
                    [f.source], strength="strong")
    raw = 0.7 if sev == "notable" else 1.0
    pct = _cap("weather", -MAX_PCT["weather"] * raw * float(weight))
    return Rule("weather", weight, raw, pct, f"severe weather: {head}", [f.id], [f.source],
                strength="strong" if sev == "severe" else "weak", target="total", enabled=weight > 0)


def lineup_rule(facts: list[Fact], now, weight: float, ctx: dict) -> Rule:
    """Confirmed XIs are recorded as high-quality facts.  Turning a published XI into a per-player goal impact
    needs a player-level baseline (Phase B); until then this rule never proposes a number."""
    xis = [f for f in _current(facts, "lineup", now, ctx.get("kickoff")) if f.kind == "confirmed_xi"]
    if not xis:
        return Rule("lineup", weight, 0.0, 0.0, "no confirmed line-up published yet")
    sides = [str(f.subject).split()[0] for f in xis]
    return Rule("lineup", weight, 0.0, 0.0,
                f"confirmed line-up recorded ({', '.join(sides)}) — player-level impact not enabled until the "
                "Phase-B player baseline exists", [f.id for f in xis], sorted({f.source for f in xis}),
                strength="strong")


RULES = {"lineup": lineup_rule, "fatigue": fatigue_rule, "motivation": motivation_rule, "weather": weather_rule}


def run_all(facts: list[Fact], now, weights: dict[str, float], ctx: dict | None = None) -> list[Rule]:
    """Every rule runs — including the ones that find nothing and the ones that propose 0 — so that
    'no adjustment' is always explainable and never looks like missing code."""
    ctx = ctx or {}
    out: list[Rule] = []
    for cat, fn in RULES.items():
        try:
            out.append(fn(facts, now, float(weights.get(cat, 0.0)), ctx))
        except Exception as exc:  # noqa: BLE001 - a rule must never break a scan
            log.warning("Rule %s failed: %s", cat, exc)
            out.append(Rule(cat, float(weights.get(cat, 0.0)), 0.0, 0.0, f"rule error ({exc})"))
    return out
