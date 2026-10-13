"""Run-scoped, privacy-safe health counters for external feed adapters.

Only aggregate counts and coarse outcome labels are stored. URLs, response bodies,
credentials, and provider error text are deliberately excluded from publications.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

_OUTCOMES = {"success", "empty", "error", "cache", "stale"}
_sources: dict[str, dict] = {}
_run_id: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def begin_run(run_id: str | None = None) -> None:
    """Reset counters for one scanner invocation."""
    global _sources, _run_id
    _sources = {}
    _run_id = run_id


def record(source: str, outcome: str, detail: str | None = None) -> None:
    """Record one network or cache result using a small, non-sensitive detail label."""
    if outcome not in _OUTCOMES:
        raise ValueError(f"unsupported feed outcome: {outcome}")
    name = str(source).strip().lower().replace(" ", "_")
    rec = _sources.setdefault(name, {
        "requests": 0, "success": 0, "empty": 0, "errors": 0,
        "cache_hits": 0, "stale_fallbacks": 0,
    })
    if outcome in ("success", "empty", "error"):
        rec["requests"] += 1
    if outcome == "success":
        rec["success"] += 1
        rec["last_success"] = _now()
    elif outcome == "empty":
        rec["empty"] += 1
        rec["last_success"] = _now()
    elif outcome == "error":
        rec["errors"] += 1
        rec["last_error"] = _now()
    elif outcome == "cache":
        rec["cache_hits"] += 1
    elif outcome == "stale":
        rec["stale_fallbacks"] += 1
        rec["cache_hits"] += 1
    if detail:
        # Labels may not contain arbitrary provider text, query strings, or credentials.
        label = str(detail).lower()
        rec["last_detail"] = label[:40] if re.fullmatch(r"[a-z0-9_:-]{1,40}", label) else "invalid_detail"


def snapshot() -> dict:
    """Return a JSON-safe copy and a derived status for each source."""
    sources = {}
    for name, value in _sources.items():
        rec = dict(value)
        if rec["errors"]:
            rec["status"] = "degraded" if rec["success"] or rec["empty"] or rec["cache_hits"] else "failed"
        elif rec["requests"] == 0:
            rec["status"] = "cached" if rec["cache_hits"] else "not_called"
        elif rec["success"] == 0 and rec["empty"]:
            rec["status"] = "empty"
        else:
            rec["status"] = "healthy"
        sources[name] = rec
    return {"run_id": _run_id, "sources": sources}
