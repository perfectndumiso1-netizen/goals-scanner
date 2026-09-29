"""Seed the Livescore stage archive with a list of competitions (whole season + earlier seasons).

Usage:
    python3 tools/seed_stages.py <state_dir> [stage-key ...]

Without stage keys it seeds scanner.CONFIG["SEED_STAGES"] (the major-league list). It uses the same
public Livescore feed and the same Archive code as the scanner — no new data source, no model change.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import worldfeed  # noqa: E402


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    state = Path(sys.argv[1]).resolve()
    archive = worldfeed.Archive(state / "data" / "ls")
    if len(sys.argv) > 2:
        keys = [k.strip() for k in sys.argv[2:] if k.strip()]
    else:
        import scanner
        keys = [k.strip() for k in str(scanner.CONFIG["SEED_STAGES"]).split(",") if k.strip()]
    now = datetime.now()
    prios = {k: 1 for k in keys}
    r = archive.refresh(prios, now, tz_offset_hours=2, budget_s=600.0)
    b = archive.backfill(prios, now, tz_offset_hours=2, seasons=2, budget_s=300.0, max_requests=400)
    n = archive.save()
    print(f"seeded {len(keys)} stages: refreshed {r['refreshed']}, backfill requests {b['requests']}, "
          f"earlier-season results {b['added']}, files written {n}")


if __name__ == "__main__":
    main()
