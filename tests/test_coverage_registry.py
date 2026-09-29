"""Tests for the worldwide coverage upgrade (Request 6): the coverage registry, the
data-driven league/team trend engine, the news cache and per-competition isolation.

All tests are offline (synthetic stage files, fake fetch functions) — the model itself is
frozen and is verified separately by the backtest hash identity (see RESULTS.md)."""
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

import coverage
import leagues
import news
import teamstats
from appdata import fixture_id


def _stage(key, country, league, matches, stats=None, probe=None, backfill=None, fetched="2026-09-29 18:00"):
    """Build a stage dict in the worldfeed format: events {eid: [esd, hid, home, aid, away, hg, ag, hth, hta]}."""
    events = {}
    for i, (d, h, a, hg, ag) in enumerate(matches):
        events[str(1000 + i)] = [d, "h", h, "a", a, hg, ag, None, None]
    return {"key": key, "country": country, "league": league, "fetched": fetched,
            "events": events, "stats": stats or {}, "stats_probe": probe or {}, "backfill": backfill or {}}


def _write(stages_dir: Path, d: dict, name: str | None = None):
    stages_dir.mkdir(parents=True, exist_ok=True)
    (stages_dir / (name or d["key"].replace("/", "__") + ".json")).write_text(json.dumps(d), encoding="utf-8")


NOW = datetime(2026, 9, 29, 18, 30)

# ---------------------------------------------------------------- registry: statuses


def test_active_and_eligible(tmp_path):
    teams = [f"T{i}" for i in range(10)]
    matches = []
    for r in range(5):  # 5 rounds -> every team has 5 archived matches
        for i in range(5):
            matches.append((f"202609{10 + r}1500", teams[i], teams[5 + i], 1, 0))
    out = tmp_path / "out"
    _write(tmp_path / "stages", _stage("c/l", "Country", "League", matches))
    s = coverage.build(tmp_path / "stages", out, NOW)
    e = [c for c in s["competitions"] if c["provider"] == "livescore"][0]
    assert e["status"] == "ACTIVE"
    assert e["eligible"] is True
    assert e["season"] == "2026-27"
    assert e["historical_matches"] == 25
    assert (out / "status.json").exists() and (out / "STATUS.md").exists()


def test_thin_sample_not_eligible(tmp_path):
    matches = [(f"202609{20 + i}1500", "A", "B", 1, 1) for i in range(3)] + \
              [(f"202609{23 + i}1500", "C", "D", 0, 2) for i in range(3)]
    _write(tmp_path / "stages", _stage("c/l", "Country", "League", matches))
    s = coverage.build(tmp_path / "stages", tmp_path / "out", NOW)
    e = [c for c in s["competitions"] if c["provider"] == "livescore"][0]
    assert e["status"] == "ACTIVE"
    assert e["eligible"] is False  # 2-3 matches per team < 5
    assert e["teams"] == 4 and e["historical_matches"] == 6


def test_upcoming_no_results(tmp_path):
    matches = [(f"2026100{1 + i}1800", f"A{i}", f"B{i}", None, None) for i in range(3)]
    _write(tmp_path / "stages", _stage("c/l", "Country", "League", matches))
    s = coverage.build(tmp_path / "stages", tmp_path / "out", NOW, window={"c/l": 3})
    e = [c for c in s["competitions"] if c["provider"] == "livescore"][0]
    assert e["status"] == "UPCOMING"
    assert e["eligible"] is False
    assert e["season"] is None


def test_data_error_on_failed_backfill(tmp_path):
    _write(tmp_path / "stages", _stage("c/l", "Country", "League", [], backfill={"2025-2026": -1, "2024-2025": -1}))
    s = coverage.build(tmp_path / "stages", tmp_path / "out", NOW)
    e = [c for c in s["competitions"] if c["provider"] == "livescore"][0]
    assert e["status"] == "DATA_ERROR"
    assert e["eligible"] is False
    assert "fetch" in e["reason"]


def test_stats_quality_and_dead_provider(tmp_path):
    matches = [(f"202609{10 + i}1500", f"A{i % 4}", f"B{i % 4}", 1, 0) for i in range(12)]
    # half the most recent matches carry statistics
    events = {str(1000 + i): None for i in range(12)}
    stats = {str(1000 + i): [3, 4, 1, 0, 0, 0, 5, 4, 40, 50, 8, 7] for i in range(0, 12, 2)}
    _write(tmp_path / "stages", _stage("c/l", "Country", "League", matches, stats=stats))
    s = coverage.build(tmp_path / "stages", tmp_path / "out", NOW)
    e = [c for c in s["competitions"] if c["provider"] == "livescore"][0]
    assert e["stats_quality"]["pct"] == 0.5
    assert e["stats_quality"]["provider_publishes"] is True
    # provider dead: 8+ probes, 0 hits -> "publishes none"
    _write(tmp_path / "stages", _stage("c/l2", "Country", "League 2", matches, probe={"tried": 9, "hit": 0}), name="x.json")
    s = coverage.build(tmp_path / "stages", tmp_path / "out", NOW)
    e2 = [c for c in s["competitions"] if c["provider_id"] == "c/l2"][0]
    assert e2["stats_quality"]["provider_publishes"] is False


def test_season_label_june_july_boundary(tmp_path):
    # most recent result in May -> previous July-based season
    matches = [("202605151500", "A", "B", 1, 0)] * 6
    _write(tmp_path / "stages", _stage("c/l", "Country", "League", matches))
    s = coverage.build(tmp_path / "stages", tmp_path / "out", NOW)
    e = [c for c in s["competitions"] if c["provider"] == "livescore"][0]
    assert e["season"] == "2025-26"


# ---------------------------------------------------------------- trend engine: N/A, never zero


def _rows(n, gf=1, ga=0):
    return pd.DataFrame({"res": ["W"] * n, "pts": [3] * n, "gf": [gf] * n, "ga": [ga] * n,
                         "date": pd.to_datetime([f"2026-09-{d:02d}" for d in range(1, n + 1)]),
                         "venue": ["H"] * n, "opp": ["X"] * n, "league": "L"})


def test_team_trend_window_never_zero_fills():
    assert teamstats._trend_window(pd.DataFrame(), 5) is None            # no matches -> N/A
    assert teamstats._trend_window(_rows(2), 5) is None                  # 2 < 3 -> N/A
    w = teamstats._trend_window(_rows(5, gf=2, ga=0), 5)
    assert w["n"] == 5 and w["o15"] == 1.0 and w["o25"] == 0.0 and w["cs"] == 1.0
    assert w["scored_in_n"] == 5 and w["conceded_in_n"] == 0


def test_league_trends_windows_and_na():
    evts = [{"eid": str(i), "ko": datetime(2026, 9, i + 1, 15, 0), "home": f"A{i % 6}", "away": f"B{i % 6}",
             "hg": 1, "ag": 1, "finished": True} for i in range(7)]
    t = leagues.league_trends(evts, datetime(2026, 7, 1), {})
    assert t["season"]["n"] == 7 and t["season"]["o25"] == 0.0 and t["season"]["btts"] == 1.0
    assert t["last5"] is not None and t["last5"]["n"] == 5
    assert t["previous_season"] is None            # no matches before the season start -> N/A
    assert t["season"]["avg_corners"] is None      # no stats published -> N/A, not 0
    assert t["change_last10_vs_season"]["avg_goals"] == 0.0
    # thinner than the minimum window size -> every window is N/A, never zero-filled
    t2 = leagues.league_trends(evts[:3], datetime(2026, 7, 1), {})
    assert t2["last5"] is None and t2["season"] is None and t2["previous_season"] is None


def test_league_trends_with_stats():
    evts = [{"eid": str(i), "ko": datetime(2026, 9, i + 1, 15, 0), "home": f"A{i % 6}", "away": f"B{i % 6}",
             "hg": 2, "ag": 1, "finished": True} for i in range(6)]
    stats = {str(i): [5, 4, 2, 1, 0, 0, 4, 3, 45, 50, 3, 2] for i in range(6)}
    t = leagues.league_trends(evts, datetime(2026, 7, 1), stats)
    assert t["season"]["avg_corners"] == 9.0 and t["season"]["corners_n"] == 6
    assert t["season"]["avg_cards"] == 3.0  # hy+ay+hr+ar = 2+1+0+0


# ---------------------------------------------------------------- news cache (offline)


def test_news_cache_ttl_and_budget(tmp_path):
    cache = news.Cache(tmp_path / "c.json", ttl_hours=6)
    calls = []

    def fetch(tag):
        def _f():
            calls.append(tag)
            return [{"title": f"t-{tag}", "source": "S", "link": "https://x", "published": "2026-09-29T08:00:00Z"}]
        return _f

    items, st = cache.items("k1", fetch("a"), [2])
    assert st == "fetched" and items[0]["bucket"] in ("24h", "3d", "7d")
    items, st = cache.items("k1", fetch("b"), [2])
    assert st == "cached" and calls == ["a"]                       # second call served from cache
    items, st = cache.items("k2", fetch("c"), [0])
    assert st == "stale" and items == [] and calls == ["a"]        # over budget: no fetch, nothing stored
    cache.save()
    cache2 = news.Cache(tmp_path / "c.json", ttl_hours=6)
    items, st = cache2.items("k1", fetch("d"), [0])
    assert st == "cached" and items[0]["title"] == "t-a"           # persisted on disk


def test_news_cache_failed_fetch_keeps_stale(tmp_path):
    cache = news.Cache(tmp_path / "c.json", ttl_hours=6)
    cache.data["k"] = {"ts": 0, "items": [{"title": "old"}]}       # stale entry
    # a failed fetch keeps the previous (stale) entries instead of caching an outage as "no news"
    items, st = cache.items("k", lambda: (_ for _ in ()).throw(RuntimeError()), [5])
    assert st == "stale" and items == [{"title": "old"}]
    # the next run retries and succeeds
    items, st = cache.items("k", lambda: [{"title": "new", "source": "S", "link": "u", "published": "2026-09-29T08:00:00Z"}], [5])
    assert st == "fetched" and items[0]["title"] == "new"
    # over budget: the stored (now fresh) entry is served
    items, st = cache.items("k", lambda: (_ for _ in ()).throw(RuntimeError()), [0])
    assert st == "cached"


def test_fixture_headlines_query_shape():
    import inspect
    src = inspect.getsource(news.fixture_headlines)
    assert 'core_name(home)' in src and 'core_name(away)' in src   # both team names in the query


# ---------------------------------------------------------------- per-competition isolation


def test_corrupt_stage_does_not_kill_build(tmp_path):
    (tmp_path / "stages").mkdir()
    _write(tmp_path / "stages", _stage("c/good1", "C", "Good 1", [("202609101500", "A", "B", 1, 0)] * 6))
    _write(tmp_path / "stages", _stage("c/good2", "C", "Good 2", [("202609111500", "C", "D", 2, 0)] * 6), name="z.json")
    (tmp_path / "stages" / "broken.json").write_text("{not json", encoding="utf-8")
    n = leagues.build(tmp_path / "stages", NOW, tmp_path / "out")
    assert n == 2
    idx = json.loads((tmp_path / "out" / "index.json").read_text())
    assert idx["count"] == 2


def test_leagues_build_keeps_status_registry(tmp_path):
    (tmp_path / "stages").mkdir()
    _write(tmp_path / "stages", _stage("c/good", "C", "Good", [("202609101500", "A", "B", 1, 0)] * 6))
    out = tmp_path / "out"
    coverage.build(tmp_path / "stages", out, NOW)
    n = leagues.build(tmp_path / "stages", NOW, out)
    assert n == 1
    assert (out / "status.json").exists()        # the registry survives the detail-file prune
    d = json.loads((out / "c__good.json").read_text())
    assert d["teams_div"] == "LS:c/good"          # stable team-page key for the Teams tab
    assert d["status"] == "ACTIVE" and d["eligible"] is True
    assert d["trends"]["season"]["n"] == 6


def test_add_news_patches_only_active_leagues(tmp_path):
    (tmp_path / "stages").mkdir()
    _write(tmp_path / "stages", _stage("c/a", "C", "A", [("202609101500", "A1", "A2", 1, 0)] * 6))
    out = tmp_path / "out"
    leagues.build(tmp_path / "stages", NOW, out, tz_hours=2)
    # no upcoming fixtures -> nothing is patched
    n = leagues.add_news(out, league_fn=lambda lg, c="": ["h"], team_fn=lambda t: ["h"])
    assert n == 0 and "news" not in json.loads((out / "c__a.json").read_text())
    # with a next fixture -> patched
    idx = json.loads((out / "index.json").read_text())
    idx["leagues"][0]["next"] = "2026-09-30 17:00"
    (out / "index.json").write_text(json.dumps(idx))
    n = leagues.add_news(out, league_fn=lambda lg, c="": [{"title": "lg", "source": "S", "link": "u", "when": "w"}],
                         team_fn=lambda t: [{"title": "t", "source": "S", "link": "u", "when": "w"}])
    assert n == 1
    d = json.loads((out / "c__a.json").read_text())
    assert d["news"]["league"] and set(d["news"]["teams"]) == {"A1", "A2"}


# ---------------------------------------------------------------- stable ID chain


def test_fixture_id_chain():
    fid = fixture_id("2026-09-30", "South Africa", "Orlando Pirates", "Mamelodi Sundowns")
    assert fid == fixture_id("2026-09-30", "South Africa", "Orlando Pirates", "Mamelodi Sundowns")
    assert fid != fixture_id("2026-09-30", "South Africa", "Orlando Pirates", "AmaZulu FC")
    assert "|" in fid
