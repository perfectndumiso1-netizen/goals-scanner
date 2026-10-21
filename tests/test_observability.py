from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
import feed_health
import monitoring
import publication
import appdata
import scanner
import verify


def test_feed_health_is_aggregate_and_does_not_publish_untrusted_detail():
    feed_health.begin_run("test-run")
    feed_health.record("football_data", "success")
    feed_health.record("football_data", "error", "token=never-log-this")
    feed_health.record("sportybet", "stale", "verified_price_cache")
    snapshot = feed_health.snapshot()
    assert snapshot["run_id"] == "test-run"
    assert snapshot["sources"]["football_data"]["status"] == "degraded"
    assert snapshot["sources"]["football_data"]["requests"] == 2
    assert snapshot["sources"]["sportybet"]["status"] == "cached"
    assert snapshot["sources"]["sportybet"]["stale_fallbacks"] == 1
    assert "never-log-this" not in json.dumps(snapshot)
    assert "token=" not in json.dumps(snapshot)


def test_coverage_alerts_ignore_small_baselines_but_flag_large_drops():
    previous = {"coverage": {"fixtures": 50, "priced": 30, "data_ok": 40},
                "counts_shortlist": {"primary": 12}}
    current = {"fixtures": 30, "priced": 20, "data_ok": 18}
    alerts = monitoring.coverage_alerts(previous, current, {"counts": {"primary": 0}})
    codes = {a["code"] for a in alerts}
    assert codes == {"coverage_drop_data_ok", "coverage_drop_shortlist_primary"}
    assert monitoring.coverage_alerts(None, current, {}) == []


def _valid_manifest():
    return {"schema_version": 3, "run_id": "offline-smoke", "model_version": "test-model",
            "config_sha256": "a" * 64, "generated_at": "2026-10-13T20:00:00+00:00",
            "feed_health": {"sources": {}}, "counts": {}}


def test_publication_promotes_only_after_successful_validation(tmp_path):
    staging = tmp_path / "app" / "_staging"
    promoted = []

    def build():
        (staging / "latest.json").write_text("{}", encoding="utf-8")

    result = publication.publish(staging, build, lambda: ([], ["test warning"]), lambda: promoted.append(True))
    assert result.published and result.warnings == ("test warning",)
    assert promoted == [True]
    assert not staging.exists()


def test_publication_refuses_invalid_export_and_cleans_staging(tmp_path):
    staging = tmp_path / "app" / "_staging"
    promoted = []
    result = publication.publish(staging, lambda: (staging / "bad.json").write_text("{}"),
                                 lambda: (["invalid"], []), lambda: promoted.append(True))
    assert not result.published and result.errors == ("invalid",)
    assert not promoted and not staging.exists()


def test_run_manifest_is_required_and_schema_checked(tmp_path):
    staging = tmp_path / "app" / "_staging"
    live = tmp_path / "app"
    staging.mkdir(parents=True)
    (staging / "latest.json").write_text(json.dumps({"version": 3,
        "meta": {"generated": "2026-10-13 20:00", "run_id": "offline-smoke"}, "fixtures": [],
        "safe": {"min_p": 0.7, "bets": [], "today": {"bets": []}}, "picks": {}, "accas": {}}), encoding="utf-8")
    for name in ("meta.json", "alerts.json", "badges.json"):
        (staging / name).write_text("{}", encoding="utf-8")
    errors, _ = verify.check_publication(staging, live, tmp_path / "no-ledger.csv",
                                         datetime(2026, 10, 13, 20, 0), expect_fixtures=0)
    assert "run_manifest.json missing" in errors
    manifest = _valid_manifest()
    manifest["schema_version"] = 99
    (staging / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    errors, _ = verify.check_publication(staging, live, tmp_path / "no-ledger.csv",
                                         datetime(2026, 10, 13, 20, 0), expect_fixtures=0)
    assert any("schema version" in e for e in errors)
    manifest["schema_version"] = 3
    manifest["run_id"] = "some-other-run"
    (staging / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    errors, _ = verify.check_publication(staging, live, tmp_path / "no-ledger.csv",
                                         datetime(2026, 10, 13, 20, 0), expect_fixtures=0)
    assert any("run_id" in e for e in errors)


def test_appdata_export_writes_provenance_and_feed_manifest(tmp_path):
    now = datetime(2026, 10, 13, 20, 0)
    feed_health.begin_run("export-test")
    feed_health.record("football_data", "success", "fixture_provider")
    stage = tmp_path / "app" / "_staging"
    reports = tmp_path / "reports"
    reports.mkdir()
    ctx = {"now": now, "start": now, "end": now, "app_start": now, "app_end": now,
           "window_end": now, "run": "20:00", "run_id": "export-test", "revision": "deadbeef",
           "model_version": "test-model", "config_sha256": "b" * 64, "feed_health": feed_health.snapshot(),
           "health_alerts": []}
    helpers = {"render_details": lambda *args: "", "stars": lambda *args: "",
               "comp": lambda *args: "", "sb_price": lambda *args: None, "selections": lambda *args: []}
    appdata.export(stage / "latest.json", ctx=ctx, rows=[], all_rows=[], picks={}, tracker_summary={},
                   notes=[], ls_map={}, helpers=helpers, reports_dir=reports, tz_label="UTC",
                   thresholds={}, backtest={}, repo=None, coverage={"fixtures": 0, "priced": 0},
                   safe_summary={}, botd=[], botd_groups=[], alerts=[], live_dir=tmp_path / "live")
    latest = json.loads((stage / "latest.json").read_text(encoding="utf-8"))
    manifest = json.loads((stage / "run_manifest.json").read_text(encoding="utf-8"))
    assert latest["meta"]["schema_version"] == manifest["schema_version"] == 3
    assert latest["meta"]["run_id"] == manifest["run_id"] == "export-test"
    assert manifest["feed_health"]["sources"]["football_data"]["success"] == 1
    assert manifest["counts"]["all_coverage_fixtures"] == 0
    # the home page's strong-markets section is published with its own bars (2026-10-21)
    assert latest["strong_markets"]["min_p"] == 0.75 and latest["strong_markets"]["min_odds"] == 1.16
    assert latest["strong_markets"]["bets"] == []
    assert "accas" not in latest                     # accumulators are removed from the app payload


def test_promote_publication_rolls_back_when_replacement_fails(monkeypatch, tmp_path):
    live = tmp_path / "app"
    staging = tmp_path / "_staging"
    live.mkdir()
    staging.mkdir()
    (live / "fx").mkdir()
    (staging / "fx").mkdir()
    names = ("latest.json", "meta.json", "alerts.json", "badges.json", "run_manifest.json")
    for name in names:
        (live / name).write_text(f"old-{name}", encoding="utf-8")
        (staging / name).write_text(f"new-{name}", encoding="utf-8")
    (live / "fx" / "detail.json").write_text('{"date":"2026-10-13"}', encoding="utf-8")
    (staging / "fx" / "detail.json").write_text('{"date":"2026-10-13","new":true}', encoding="utf-8")
    real_replace = scanner.os.replace

    def fail_on_meta(src, dst):
        if Path(dst) == live / "meta.json":
            raise OSError("simulated replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(scanner.os, "replace", fail_on_meta)
    with pytest.raises(OSError, match="simulated replace failure"):
        scanner.promote_publication(staging, live, datetime(2026, 10, 13, 20, 0))
    for name in names:
        assert (live / name).read_text(encoding="utf-8") == f"old-{name}"
    assert (live / "fx" / "detail.json").read_text(encoding="utf-8") == '{"date":"2026-10-13"}'
    assert not list(tmp_path.glob(".publication-backup-*"))
