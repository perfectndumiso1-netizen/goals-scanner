"""Fact records: the atomic unit of the research layer.

A `Fact` is something we *know* about a fixture, with provenance.  It never contains an opinion about what the
probability should be — that belongs to `rules.py`.  Nothing in this module reads odds.

Fields
------
category      availability | lineup | team_news | motivation | fatigue | weather
subject       who/what the fact is about (team name, "home XI", venue, the fixture)
text          a short, plain-language statement (what a reader sees)
source        the publication/feed the fact came from — always set
url           link to the source item when one exists
retrieved_at  ISO-8601 UTC — when *we* fetched it
effective_at  ISO-8601 UTC — when the information itself is dated (news date, forecast hour); "" = unknown
confidence    high | medium | low   (see SOURCE_TIERS)
verified      True only for first-party information (feed-published XI, official club/league statement)
status        current | stale | conflict | dropped
kind          machine tag for rule matching (e.g. "confirmed_xi", "days_since_last")
value         structured payload for the rules (numbers only — never prose interpretation)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# Source quality tiers (used for confidence and for resolving conflicts).
TIERS = {
    "official": 3,      # club / league / competition organiser / the feed that publishes the official XI
    "provider": 2,      # reputable structured provider (fixture feed, league data, weather service)
    "press": 1,         # reputable sports journalism
    "community": 0,     # anything else — recorded, never used for an adjustment
}

# How long a fact of each category stays *current*.  Beyond the TTL it is shown as stale and can never adjust.
TTL_H = {
    "lineup": 6.0,      # plus a match-relative check: valid until ~3 h after kick-off
    "team_news": 72.0,  # matches news.Cache's 24h/3d/7d buckets
    "weather": 6.0,
    "fatigue": 24.0,
    "motivation": 24.0,
    "availability": 72.0,
}
CATEGORIES = tuple(TTL_H)

# Facts that record a *gap* rather than information ("N/A — the feed has not published line-ups").  They are
# shown, they explain why an adjustment is zero, and they must never count as evidence for the research grade.
NA_KINDS = {"no_history", "stakes_unavailable", "coverage_none", "news_unavailable", "lineup_not_published",
            "lineup_partial", "lineup_unavailable", "weather_unavailable"}


def is_na(fact: "Fact") -> bool:
    """True for a gap, not a fact about the match."""
    return fact.kind in NA_KINDS or fact.text.startswith("N/A")


def iso(dt: datetime | None) -> str:
    """ISO-8601 UTC string, or "" when the time is unknown."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


@dataclass
class Fact:
    category: str
    subject: str
    text: str
    source: str
    url: str = ""
    retrieved_at: str = ""
    effective_at: str = ""
    confidence: str = "provider"
    verified: bool = False
    status: str = "current"
    kind: str = ""
    value: dict = field(default_factory=dict)
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = "f" + uuid.uuid4().hex[:10]
        if self.category not in CATEGORIES:
            raise ValueError(f"unknown fact category {self.category!r}")

    # -- convenience
    @property
    def tier(self) -> int:
        return TIERS.get(self.confidence, 0)

    def to_dict(self) -> dict:
        return {"id": self.id, "category": self.category, "subject": self.subject, "text": self.text,
                "source": self.source, "url": self.url, "retrieved_at": self.retrieved_at,
                "effective_at": self.effective_at, "confidence": self.confidence, "verified": bool(self.verified),
                "status": self.status, "kind": self.kind, "value": self.value}

    @classmethod
    def from_dict(cls, d: dict) -> "Fact":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def make_fact(category: str, subject: str, text: str, source: str, now: datetime, *, url: str = "",
              effective_at: datetime | None = None, confidence: str = "provider", verified: bool = False,
              kind: str = "", value: dict | None = None) -> Fact:
    """Build a fact with the retrieval timestamp stamped from `now` (the run clock, for reproducibility)."""
    return Fact(category=category, subject=subject, text=text, source=source, url=url,
                retrieved_at=iso(now), effective_at=iso(effective_at) or iso(now), confidence=confidence,
                verified=verified, kind=kind, value=value or {})


def as_aware(dt: datetime | None, like: datetime | None = None) -> datetime | None:
    """Return `dt` as a timezone-aware datetime.

    Naive datetimes in this codebase are the scanner's own wall clock (Africa/Johannesburg in production, a
    fixed test clock in the tests), so a naive kick-off takes the zone of the run clock — never UTC by accident.
    Mixing naive and aware datetimes is the one bug class that silently disables a whole collector, so every
    collector gets its times from here.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt
    zone = like.tzinfo if (like is not None and like.tzinfo is not None) else timezone.utc
    return dt.replace(tzinfo=zone)


def _as_utc(dt: datetime | None) -> datetime | None:
    """Treat a naive clock the same way `iso()` does (as UTC), so naive and aware scans behave identically."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def freshness(fact: Fact, now: datetime, kickoff: datetime | None = None) -> str:
    """current | stale — the *information age* of a fact, per category.

    Line-ups are special: they are published close to kick-off, so the check is match-relative (valid until
    3 h after kick-off) and the retrieval time only has to be plausible.
    """
    ttl = TTL_H.get(fact.category, 24.0)
    ref = parse_iso(fact.effective_at) or parse_iso(fact.retrieved_at)
    now = _as_utc(now)
    if ref is None or now is None:
        return "stale"
    if fact.category == "lineup":
        if kickoff is None:
            return "current" if now - ref <= timedelta(hours=ttl) else "stale"
        return "current" if now <= _as_utc(kickoff) + timedelta(hours=3) else "stale"
    return "current" if now - ref <= timedelta(hours=ttl) else "stale"


def mark_conflicts(facts: list[Fact]) -> list[dict]:
    """Detect same-subject availability claims that point in opposite directions.

    Returns a list of conflict records (never resolves them silently).  Resolution rule — used only when a
    *strictly higher-tier and strictly more recent* fact exists — is applied by `context.py`, which records
    `source_a / source_b / conflict / resolution / impact` exactly as the specification requires.
    """
    conflicts: list[dict] = []
    by_subject: dict[str, list[Fact]] = {}
    for f in facts:
        if f.category in ("team_news", "availability", "lineup") and f.kind in ("player_out", "player_in", "team_out", "team_in"):
            by_subject.setdefault(f.subject, []).append(f)
    for subject, group in by_subject.items():
        outs = [f for f in group if f.kind.endswith("_out")]
        ins = [f for f in group if f.kind.endswith("_in")]
        if outs and ins and len({f.source for f in group}) >= 2:
            a = max(outs, key=lambda f: (f.tier, f.effective_at))
            b = max(ins, key=lambda f: (f.tier, f.effective_at))
            resolution, keep = "unresolved", None
            if a.tier != b.tier:
                hi, lo = (a, b) if a.tier > b.tier else (b, a)
                t_hi = parse_iso(hi.effective_at) or datetime.min.replace(tzinfo=timezone.utc)
                t_lo = parse_iso(lo.effective_at) or datetime.min.replace(tzinfo=timezone.utc)
                if t_hi > t_lo:
                    resolution, keep = f"resolved in favour of {hi.source} (higher source tier, more recent)", hi
            conflicts.append({"subject": subject, "source_a": a.source, "source_b": b.source, "conflict": True,
                              "resolution": resolution, "impact": "no adjustment",
                              "text_a": a.text, "text_b": b.text, "keep": keep.id if keep else ""})
    return conflicts


def grade_quality(facts: list[Fact], conflicts: list[dict], now: datetime, kickoff: datetime | None,
                  support: str = "full") -> tuple[str, list[str]]:
    """Research quality of a fixture's information set: HIGH | MEDIUM | LOW | INSUFFICIENT.

    Ingredients are factual (what we hold, how fresh, how well sourced) — never how well the facts *agree with
    the model* and never a probability.  `support` carries the competition's structural coverage
    ("full" | "partial" | "none") so that competitions that publish nothing can never grade HIGH.
    """
    reasons: list[str] = []
    current = [f for f in facts if f.status == "current" and freshness(f, now, kickoff) == "current"
               and not is_na(f)]
    gaps = [f for f in facts if is_na(f)]
    stale = [f for f in facts if f not in current and not is_na(f)]
    if not current:
        reasons.append(f"no current information ({len(gaps)} gap(s) recorded as N/A"
                       + (f", {len(stale)} stale fact(s)" if stale else "") + ")")
        return "INSUFFICIENT", reasons
    cats = {f.category for f in current}
    first_party = [f for f in current if f.verified and f.tier >= TIERS["official"]]
    good = [f for f in current if f.tier >= TIERS["provider"]]
    reasons.append(f"{len(current)} current fact(s) in {len(cats)} categor{'y' if len(cats) == 1 else 'ies'}")
    if first_party:
        reasons.append(f"first-party source: {first_party[0].source}")
    if support == "none":
        reasons.append("competition publishes no statistics/line-ups — capped at LOW")
    if support == "partial":
        reasons.append("patchy coverage for this competition")

    grade = "LOW"
    if len(cats) >= 3 and first_party and support == "full":
        grade = "HIGH"
    elif len(cats) >= 2 and len(good) >= 2 and support != "none":
        grade = "MEDIUM"
    if conflicts:
        if all(c.get("resolution", "unresolved").startswith("unresolved") for c in conflicts):
            grade = {"HIGH": "MEDIUM", "MEDIUM": "LOW", "LOW": "LOW"}[grade]
            reasons.append(f"{len(conflicts)} unresolved conflict(s) — quality lowered, adjustment 0")
    if stale:
        reasons.append(f"{len(stale)} stale fact(s) ignored")
    if gaps:
        reasons.append(f"{len(gaps)} gap(s) recorded as N/A, not used as evidence")
    return grade, reasons


@dataclass
class ResearchRecord:
    """Everything the research layer knows and did for one fixture.  This is what is stored and displayed."""
    fid: str
    kickoff: str = ""
    updated: str = ""
    stage: str = "collect"                 # collect | prematch
    quality: str = "INSUFFICIENT"
    quality_reasons: list[str] = field(default_factory=list)
    support: str = "full"                  # competition structural coverage for research purposes
    facts: list[Fact] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    base: dict | None = None               # base (statistical) probabilities, the published foundation
    final: dict | None = None              # final probabilities (== base unless an adjustment was applied)
    adjustments: list[dict] = field(default_factory=list)   # per-category rule outcomes (incl. zeros)
    totals: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"fid": self.fid, "kickoff": self.kickoff, "updated": self.updated, "stage": self.stage,
                "quality": self.quality, "quality_reasons": self.quality_reasons, "support": self.support,
                "facts": [f.to_dict() for f in self.facts], "conflicts": self.conflicts,
                "base": self.base, "final": self.final, "adjustments": self.adjustments, "totals": self.totals,
                "notes": self.notes}

    def app_view(self, limit: int = 12) -> dict:
        """The compact block the app / report show.  Deliberately small: base vs final, the reasons, the quality."""
        def _f(x):
            return None if x is None else round(float(x), 4)

        return {
            "quality": self.quality,
            "quality_reasons": self.quality_reasons[:4],
            "support": self.support,
            "base": {k: _f(v) for k, v in (self.base or {}).items()},
            "final": {k: _f(v) for k, v in (self.final or {}).items()},
            # lam_pct must survive the trip to the app/report: it is how a reader tells a rule that proposed
            # nothing from one that proposed a bounded number (rendering "no adjustment" over a real
            # adjustment was a bug once already).
            "adjustments": [{"cat": a["cat"], "pp": a.get("pp"), "lam_pct": a.get("lam_pct", 0.0),
                             "reason": a.get("reason"), "sources": a.get("sources", []),
                             "weight": a.get("weight", 0.0), "strength": a.get("strength"),
                             "target": a.get("target"), "enabled": a.get("enabled", False)}
                            for a in self.adjustments],
            "totals": self.totals,
            "conflicts": [{"subject": c["subject"], "source_a": c["source_a"], "source_b": c["source_b"],
                           "resolution": c["resolution"], "impact": c["impact"]} for c in self.conflicts],
            "facts": [{"category": f.category, "subject": f.subject, "text": f.text, "source": f.source,
                       "url": f.url, "retrieved_at": f.retrieved_at, "effective_at": f.effective_at,
                       "confidence": f.confidence, "verified": f.verified, "stale": f.status == "stale"}
                      for f in self.facts[:limit]],
            "n_facts": len(self.facts),
            "updated": self.updated,
        }
