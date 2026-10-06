"""Persistent store for research records (data/research/records.json).

Shape: {"version": 1, "meta": {...}, "records": {fid: <record dict>}}.  One file (not thousands) because the
records are small and the state branch is force-pushed; writes are atomic and pruned to a rolling window so the
file cannot grow without bound.  Fails soft: a corrupt store is rebuilt rather than fatal.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("research.store")
VERSION = 1


class Store:
    def __init__(self, path: Path, keep_days: int = 7, max_records: int = 2000, max_mb: float = 8.0):
        self.path = Path(path)
        self.keep_days = max(1, int(keep_days))
        self.max_records = max(100, int(max_records))
        self.max_bytes = max(0.5, float(max_mb)) * 1e6
        self.dropped: dict = {}
        self.records: dict[str, dict] = {}
        self.meta: dict = {}
        self._dirty = False
        self.load()

    # -- io
    def load(self) -> None:
        self.records, self.meta = {}, {}
        if not self.path.exists():
            return
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(d, dict) and isinstance(d.get("records"), dict):
                self.records = d["records"]
                self.meta = d.get("meta") or {}
        except (OSError, ValueError) as exc:  # noqa: BLE001
            log.warning("Research store unreadable (%s) — starting a fresh one", exc)
            self.records, self.meta = {}, {"recovered_from_error": str(exc)[:200]}

    def save(self, now: datetime | None = None) -> int:
        if now is not None:
            self.prune(now)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": VERSION, "meta": {**self.meta, "saved": (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
                                                "n": len(self.records)},
                   "records": self.records}
        tmp = Path(tempfile.mkstemp(dir=str(self.path.parent), prefix=".records-", suffix=".tmp")[1])
        try:
            tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            os.replace(tmp, self.path)
        finally:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
        self._dirty = False
        return len(self.records)

    def compact(self, now: datetime, after_days: float = 2.0) -> int:
        """Trim the heavy payloads of settled records.

        The evidence that matters for evaluation (each fact's text, source, both timestamps and confidence) is
        kept; what is dropped is the bulk — the line-up name lists and structured `value` payloads used to *apply*
        a rule, which are only needed while the fixture is live. Without this a week of records is tens of MB and
        the state branch pays for it on every half-hourly push.
        """
        cutoff = (now - timedelta(days=float(after_days))).strftime("%Y-%m-%d %H:%M")
        trimmed = 0
        for rec in self.records.values():
            if str(rec.get("kickoff") or "") >= cutoff:
                continue
            for f in rec.get("facts") or []:
                if f.get("value"):
                    f["value"] = {}
                    trimmed += 1
            if len(rec.get("facts") or []) > 10:
                rec["facts"] = rec["facts"][:10]
            rec["notes"] = (rec.get("notes") or [])[:2]
            self._dirty = True
        return trimmed

    def prune(self, now: datetime) -> int:
        """Age, then cap by count, then cap by size — oldest first at every step.

        The state branch is force-pushed every 30 minutes, so the store is kept deliberately small: a week of
        records, at most `max_records`, and never more than `max_mb`. Nothing here touches the ledgers
        (`tracker.csv` / `safe_bets.csv`), which is where the published base-vs-final numbers actually live.
        """
        self.compact(now)
        cutoff = (now - timedelta(days=self.keep_days)).strftime("%Y-%m-%d %H:%M")
        before = len(self.records)
        self.records = {k: v for k, v in self.records.items() if str(v.get("kickoff") or "") >= cutoff}
        self.dropped = {"old": before - len(self.records)}
        if len(self.records) > self.max_records:
            newest = sorted(self.records.items(), key=lambda kv: str(kv[1].get("kickoff") or ""), reverse=True)
            self.dropped["over_count"] = len(self.records) - self.max_records
            self.records = dict(newest[: self.max_records])
        if self.max_bytes > 0:
            sizes = {k: len(json.dumps(v)) for k, v in self.records.items()}
            total = sum(sizes.values())
            if total > self.max_bytes:
                oldest = sorted(self.records, key=lambda k: str(self.records[k].get("kickoff") or ""))
                n0 = len(oldest)
                while oldest and total > self.max_bytes:
                    k = oldest.pop(0)
                    total -= sizes[k]
                    del self.records[k]
                self.dropped["over_size"] = n0 - len(oldest)
        return sum(self.dropped.values())

    # -- access
    def get(self, fid: str) -> dict | None:
        return self.records.get(fid)

    def put(self, record: dict) -> None:
        self.records[str(record["fid"])] = record
        self._dirty = True

    def size_bytes(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def limits(self) -> dict:
        """Which limits are biting — surfaced in the run log so the trade-off is never invisible."""
        return {"keep_days": self.keep_days, "max_records": self.max_records,
                "max_mb": round(self.max_bytes / 1e6, 1), "dropped": self.dropped or {}}

    def summary(self) -> dict:
        """Small block for the run log / app meta: how much research is being carried."""
        n = len(self.records)
        q: dict[str, int] = {}
        facts = 0
        for r in self.records.values():
            q[str(r.get("quality"))] = q.get(str(r.get("quality")), 0) + 1
            facts += len(r.get("facts") or [])
        return {"records": n, "facts": facts, "quality": q, "bytes": self.size_bytes(),
                "file": self.path.name}
