"""Small operational checks for feed degradation and sudden coverage changes."""
from __future__ import annotations

import json
from pathlib import Path


def feed_alerts(snapshot: dict) -> list[dict]:
    alerts = []
    for source, rec in (snapshot.get("sources") or {}).items():
        status = rec.get("status")
        if status in ("failed", "degraded"):
            alerts.append({"code": f"feed_{source}_{status}", "severity": "warning",
                           "message": f"{source.replace('_', ' ')} feed is {status} "
                                      f"({rec.get('errors', 0)} error(s), {rec.get('success', 0)} success(es))."})
    return alerts


def _counts(meta: dict) -> dict:
    return {**(meta.get("coverage") or {}),
            "shortlist_primary": (meta.get("counts_shortlist") or {}).get("primary", 0)}


def coverage_alerts(previous_meta: dict | None, current_coverage: dict,
                    current_shortlist: dict | None = None) -> list[dict]:
    """Warn only on large drops from a prior successful publication; never changes picks."""
    if not previous_meta:
        return []
    previous = _counts(previous_meta)
    current = {**current_coverage,
               "shortlist_primary": (current_shortlist or {}).get("counts", {}).get("primary", 0)}
    minimums = {"fixtures": 20, "priced": 10, "data_ok": 20, "shortlist_primary": 10}
    alerts = []
    for key, floor in minimums.items():
        before = previous.get(key)
        after = current.get(key)
        if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
            continue
        if before >= floor and (after == 0 or after < before * 0.5):
            alerts.append({"code": f"coverage_drop_{key}", "severity": "warning",
                           "message": f"{key.replace('_', ' ')} coverage dropped from {int(before)} to {int(after)} "
                                      "since the last successful publication."})
    return alerts


def load_meta(path: Path) -> dict | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None
