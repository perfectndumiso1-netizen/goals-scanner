from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import feed_health
import publication
import scanner
import sporty
import verify
import worldfeed


def test_football_data_csv_contract_offline():
    fixture = Path(__file__).parent / "fixtures" / "football-data-sample.csv"
    frame = scanner.read_csv(fixture.read_bytes())
    assert frame is not None and len(frame) == 1
    assert frame.loc[0, "HomeTeam"] == "Arsenal"
    assert scanner.parse_dates(frame["Date"]).iloc[0].strftime("%Y-%m-%d") == "2026-10-13"


def test_offline_feed_to_validated_publication(monkeypatch, tmp_path):
    fixtures = Path(__file__).parent / "fixtures"
    stage_payload = json.loads((fixtures / "livescore-day.json").read_text(encoding="utf-8"))
    market_payload = json.loads((fixtures / "sportybet-markets.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(worldfeed.livescore, "_get", lambda *args, **kwargs: stage_payload)
    feed_health.begin_run("offline-smoke")
    events = worldfeed.fetch_day(datetime(2026, 10, 13))
    markets = sporty._parse_markets(market_payload)
    feed_health.record("livescore", "success", "fixture_provider")
    feed_health.record("sportybet", "success", "fixture_provider")
    assert len(events) == 1 and events[0]["home"] == "Arsenal" and events[0]["away"] == "Chelsea"
    assert markets["OU"][2.5] == (1.95, 1.9)

    live = tmp_path / "app"
    staging = live / "_staging"
    now = datetime(2026, 10, 13, 20, 0)
    digest = "a" * 64

    def build():
        latest = {"version": 3, "meta": {"generated": now.strftime("%Y-%m-%d %H:%M"), "run_id": "offline-smoke"},
                  "fixtures": [], "safe": {"min_p": 0.7, "bets": [], "today": {"bets": []}},
                  "picks": {}, "accas": {}}
        (staging / "latest.json").write_text(json.dumps(latest), encoding="utf-8")
        for name in ("meta.json", "alerts.json", "badges.json"):
            (staging / name).write_text("{}", encoding="utf-8")
        manifest = {"schema_version": 3, "run_id": "offline-smoke", "model_version": "test-model",
                    "config_sha256": digest, "generated_at": now.isoformat(),
                    "feed_health": feed_health.snapshot(), "counts": {}}
        (staging / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def validate():
        return verify.check_publication(staging, live, tmp_path / "no-ledger.csv", now, expect_fixtures=0)

    def promote():
        live.mkdir(parents=True, exist_ok=True)
        for item in staging.iterdir():
            destination = live / item.name
            if item.is_dir():
                shutil.copytree(item, destination, dirs_exist_ok=True)
            else:
                shutil.copy2(item, destination)

    result = publication.publish(staging, build, validate, promote)
    assert result.published and not result.errors
    assert json.loads((live / "run_manifest.json").read_text(encoding="utf-8"))["run_id"] == "offline-smoke"
