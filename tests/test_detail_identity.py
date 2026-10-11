"""User-reported bug (2026-10-11): tapping a match could show another match's stats.

Three layers of defence:
1. verify.check_publication rejects a detail file whose content belongs to a different fixture
   (a mis-keyed fx/<key>.json can never be promoted again).
2. core.loadDetail never serves a cached detail whose id differs from the requested match.
3. pages.match never renders a mismatched detail and falls back to the fixture row.
1 is testable here; 2 and 3 are guarded in the app harness.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from tests.test_verify_archive_fixtures import _build
import verify

NOW = datetime(2026, 9, 30, 12, 0)


def test_miskeyed_detail_blocks_publication(tmp_path):
    staging, live = _build(tmp_path)
    detail = json.loads((staging / "fx" / "k1.json").read_text(encoding="utf-8"))
    detail["id"] = "some-other-match"          # detail content belongs to another fixture
    detail["home"] = "Someone",                # tuple: also triggers the side check
    (staging / "fx" / "k1.json").write_text(json.dumps(detail), encoding="utf-8")
    errors, _ = verify.check_publication(staging, live, tmp_path / "no-ledger.csv", NOW, expect_fixtures=1)
    assert any("belongs to" in e for e in errors), errors


def test_matching_detail_still_passes(tmp_path):
    staging, live = _build(tmp_path)
    errors, _ = verify.check_publication(staging, live, tmp_path / "no-ledger.csv", NOW, expect_fixtures=1)
    assert not [e for e in errors if "belongs to" in e or "fixture says" in e], errors
