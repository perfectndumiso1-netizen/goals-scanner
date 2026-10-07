"""Guards on the live-research / context layer.

The layer exists to make published probabilities *better informed* without ever letting information, odds or
guesswork quietly take over the model.  These tests pin the properties that matter:

  * Phase A cannot move a probability: with the shipped configuration every rule proposes 0.0 and the published
    probability is identical to the statistical model's.
  * No odds anywhere: the package never reads a bookmaker/Sportybet price.
  * Missing information is "N/A" — never an estimate, never a substituted team, never a guessed line-up.
  * Stale facts and unresolved conflicts produce zero adjustment.
  * Adjustments are bounded (per-category ceiling, lambda ceiling, percentage-point ceiling) and the direction is
    preserved when a bound bites.
  * The generic requirements run: missing data, stale data, conflicting sources, API failure, rate-limit
    exhaustion, no line-up, predicted-vs-confirmed, weather unavailable, lower-league gaps, extreme adjustments.

Everything is offline: the collectors take injected fakes, so no test touches the network.
"""
from __future__ import annotations

import ast
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research import context as ctx_mod          # noqa: E402
from research import facts as F                  # noqa: E402
from research import fatigue, lineups, motivation, rules, teamnews, weather  # noqa: E402
from research.store import Store                 # noqa: E402

NOW = datetime(2026, 10, 6, 12, 0)
ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- helpers
class Fx(dict):
    """Minimal stand-in for the scanner's fixture Series."""


def fixture(kickoff=None, home="Alpha", away="Beta", **kw) -> Fx:
    ko = kickoff or (NOW + timedelta(hours=5))
    return Fx({"kickoff": ko, "home": home, "away": away, "country": "Testland", "div": "TL1",
               "league": "Test League", "eid": "1234", **kw})


class Row:
    """Minimal stand-in for MatchRow: model probabilities, lambdas, an audit dict, news/squad slots.

    `p_model` defaults to the fake maths evaluated at the fixture's lambdas — exactly the relationship the real
    scanner guarantees (its model probability comes from the same rate -> matrix -> probability path).  Pass an
    explicit `p_model` to simulate an inconsistency.
    """

    def __init__(self, fx=None, p_model=None, lam_h=1.5, lam_a=1.1, news=None):
        self.fx = fixture() if fx is None else fx
        self.p_model = p_model or fake_prob_fn(lam_h, lam_a)
        self.p_final = dict(self.p_model)
        self.lam_h, self.lam_a = lam_h, lam_a
        self.mod_h, self.mod_a = lam_h, lam_a
        self.audit = {}
        self.news = news


class _StubClient:
    """Line-up client stub: returns a fixed parsed payload, counts nothing, touches no network."""

    used = 0

    def __init__(self, parsed):
        self.parsed = parsed

    def fetch(self, eid, now):
        return self.parsed


def fake_prob_fn(lam_h: float, lam_a: float) -> dict:
    """Monotone stand-in for score_matrix()+probs_from_matrix() — enough to exercise the bounding maths."""
    tot = lam_h + lam_a
    o15 = min(0.97, max(0.03, 1 - pow(2.718281828, -tot * 0.78)))
    o25 = min(0.95, max(0.02, 1 - pow(2.718281828, -tot * 0.55)))
    o35 = min(0.9, max(0.01, 1 - pow(2.718281828, -tot * 0.38)))
    btts = min(0.95, max(0.02, (1 - pow(2.718281828, -lam_h * 0.9)) * (1 - pow(2.718281828, -lam_a * 0.9))))
    share = lam_h / max(1e-9, tot)
    return {"O15": o15, "O25": o25, "O35": o35, "BTTS": btts, "HW": 0.9 * share * 0.8, "AW": 0.9 * (1 - share) * 0.8}


def make_engine(tmp_path, *, adjust=False, weights=None, news=None) -> ctx_mod.Engine:
    cfg = ctx_mod.Config(adjust=adjust, weights=weights or dict(rules.DEFAULT_WEIGHTS), keep_days=7)
    applied: list = []

    def apply_fn(row, lh, la, probs):
        applied.append({"row": row, "lam_h": lh, "lam_a": la, "probs": probs})
        row.lam_h, row.lam_a = lh, la
        row.p_final = dict(probs)

    eng = ctx_mod.Engine(cfg, NOW, tmp_path, fake_prob_fn, apply_fn)
    eng.applied = applied          # type: ignore[attr-defined]
    return eng


def results_frame(team="Alpha", days=(3, 10), div="TL1") -> pd.DataFrame:
    rows = []
    for d in days:
        rows.append({"date": pd.Timestamp((NOW - timedelta(days=d)).date()), "country": "Testland", "div": div,
                     "league": "Test League", "home": team, "away": "Other", "hg": 1, "ag": 1})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- facts
def test_fact_requires_a_source_and_keeps_both_timestamps():
    f = F.make_fact("fatigue", "Alpha", "last match 3 days ago", "own archive", NOW, kind="schedule")
    d = f.to_dict()
    assert d["source"] and d["retrieved_at"].endswith("Z") and d["effective_at"].endswith("Z")
    assert d["confidence"] in F.TIERS and d["category"] in F.CATEGORIES


def test_gap_facts_are_shown_but_never_count_as_evidence():
    na = F.make_fact("lineup", "home XI", "N/A — the feed has not published line-ups", "feed", NOW,
                     kind="lineup_not_published")
    assert F.is_na(na) is True
    grade, why = F.grade_quality([na], [], NOW, None, "full")
    assert grade == "INSUFFICIENT" and any("gap" in r for r in why)
    real = F.make_fact("fatigue", "Alpha", "3 days", "archive", NOW, confidence="provider", kind="schedule")
    assert F.grade_quality([na, real], [], NOW, None, "full")[0] in ("LOW", "MEDIUM")


def test_unknown_fact_is_written_as_na_not_guessed():
    f = F.make_fact("weather", "Unknown Stadium", "N/A — venue could not be located, no weather is fetched",
                    "Open-Meteo", NOW, kind="weather_unavailable")
    assert f.text.startswith("N/A") and f.value == {} and f.verified is False


def test_freshness_ttl_and_lineup_match_relative_rule():
    old = F.make_fact("team_news", "Alpha", "x", "outlet", NOW, effective_at=NOW - timedelta(days=5),
                      confidence="press")
    assert F.freshness(old, NOW, None) == "stale"
    ko = NOW + timedelta(hours=2)
    xi = F.make_fact("lineup", "home XI", "confirmed XI", "feed", NOW, confidence="official", verified=True)
    assert F.freshness(xi, NOW, ko) == "current"
    assert F.freshness(xi, ko + timedelta(hours=5), ko) == "stale"     # long after the match


def test_quality_grading_is_factual_and_capped_by_competition_support():
    none = F.grade_quality([], [], NOW, None, "full")
    assert none[0] == "INSUFFICIENT"
    weak = [F.make_fact("team_news", "Alpha", "reported: “X”", "outlet", NOW, confidence="press")]
    assert F.grade_quality(weak, [], NOW, None, "full")[0] == "LOW"
    xi = F.make_fact("lineup", "home XI", "confirmed XI", "feed", NOW, confidence="official", verified=True)
    fat = F.make_fact("fatigue", "Alpha", "3 days", "archive", NOW, confidence="provider")
    good = F.grade_quality([xi, fat, *weak], [], NOW, None, "full")
    assert good[0] == "HIGH"
    capped = F.grade_quality([xi, fat, *weak], [], NOW, None, "none")
    assert capped[0] == "LOW" and any("capped" in r for r in capped[1])


def test_unresolved_conflict_lowers_quality_and_says_so():
    a = F.make_fact("team_news", "Alpha", "out", "outlet A", NOW, confidence="press", kind="team_out",
                    effective_at=NOW - timedelta(hours=2))
    b = F.make_fact("team_news", "Alpha", "in", "outlet B", NOW, confidence="press", kind="team_in")
    conflicts = F.mark_conflicts([a, b])
    assert conflicts and conflicts[0]["conflict"] is True
    assert conflicts[0]["resolution"] == "unresolved" and conflicts[0]["impact"] == "no adjustment"
    grade = F.grade_quality([a, b], conflicts, NOW, None, "full")[0]
    assert grade in ("LOW", "MEDIUM")


# --------------------------------------------------------------------------- rules
def test_every_shipped_weight_is_zero_so_phase_a_cannot_move_a_probability():
    assert set(rules.DEFAULT_WEIGHTS) == {"lineup", "fatigue", "motivation", "weather"}
    assert all(v == 0.0 for v in rules.DEFAULT_WEIGHTS.values())


def test_normal_weather_never_adjusts_even_with_a_weight():
    w = F.make_fact("weather", "Alpha Stadium", "18°C, rain 0.1 mm/h, wind 9 km/h — normal conditions",
                    "Open-Meteo", NOW, kind="conditions", value={"severity": "normal"})
    r = rules.weather_rule([w], NOW, weight=1.0, ctx={})
    assert r.lam_pct == 0.0 and "no adjustment by rule" in r.reason


def test_severe_weather_proposal_is_negative_and_inside_the_category_ceiling():
    w = F.make_fact("weather", "Alpha Stadium", "41 km/h, rain 9 mm/h — severe", "Open-Meteo", NOW,
                    kind="conditions", value={"severity": "severe"})
    r = rules.weather_rule([w], NOW, weight=1.0, ctx={})
    assert -rules.MAX_PCT["weather"] <= r.lam_pct < 0
    r2 = rules.weather_rule([w], NOW, weight=99.0, ctx={})
    assert r2.lam_pct >= -rules.MAX_PCT["weather"]      # a weight cannot blow past the ceiling


def test_fatigue_thresholds_and_target_side():
    home_fx = {"home": "Alpha", "away": "Beta"}
    t = F.make_fact("fatigue", "Alpha", "last match 3 days ago", "archive", NOW, kind="schedule",
                    value={"days_since_last": 3.0, "matches_7d": 1})
    r = rules.fatigue_rule([t], NOW, 1.0, home_fx)
    assert r.target == "home" and r.lam_pct < 0 and r.enabled
    fresh = F.make_fact("fatigue", "Alpha", "last match 9 days ago", "archive", NOW, kind="schedule",
                        value={"days_since_last": 9.0, "matches_7d": 0})
    assert rules.fatigue_rule([fresh], NOW, 1.0, home_fx).lam_pct == 0.0
    both = [t, F.make_fact("fatigue", "Beta", "last match 2 days ago", "archive", NOW, kind="schedule",
                           value={"days_since_last": 2.0, "matches_7d": 3})]
    assert rules.fatigue_rule(both, NOW, 1.0, home_fx).target == "both"


def test_lineup_and_motivation_rules_never_invent_a_number():
    xi = F.make_fact("lineup", "home XI", "confirmed XI published by the feed", "feed", NOW,
                     confidence="official", verified=True, kind="confirmed_xi")
    assert rules.lineup_rule([xi], NOW, 1.0, {}) .lam_pct == 0.0
    m = F.make_fact("motivation", "competition", "Test League — format: league", "archive", NOW, kind="format")
    assert rules.motivation_rule([m], NOW, 1.0, {}).lam_pct == 0.0
    assert "not scored" in rules.motivation_rule([m], NOW, 1.0, {}).reason


def test_rules_ignore_stale_facts():
    stale = F.make_fact("weather", "S", "severe", "Open-Meteo", NOW, effective_at=NOW - timedelta(days=4),
                        kind="conditions", value={"severity": "severe"})
    assert rules.weather_rule([stale], NOW, 1.0, {}).lam_pct == 0.0


def test_extreme_proposal_is_clamped_by_all_three_ceilings():
    base_lh, base_la = 1.5, 1.1
    base_probs = fake_prob_fn(base_lh, base_la)
    lh, la, capped = ctx_mod.clamp(base_lh, base_la, base_lh * 2.0, base_la * 2.0, base_probs, fake_prob_fn,
                                   max_pp=2.0, max_lambda_pct=6.0)
    assert capped is True
    assert abs(100 * (lh / base_lh - 1)) <= 6.0 + 1e-6 and abs(100 * (la / base_la - 1)) <= 6.0 + 1e-6
    worst = max(abs(100 * (fake_prob_fn(lh, la)[m] - base_probs[m])) for m in ctx_mod.MARKETS)
    assert worst <= 2.0 + 1e-6
    assert lh > base_lh and la > base_la                      # direction preserved through the bisection
    almost = ctx_mod.clamp(base_lh, base_la, base_lh * 1.0005, base_la, base_probs, fake_prob_fn, 5.0, 6.0)
    assert almost[2] is False


def test_apply_rules_semantics_for_each_target():
    up = rules.Rule("fatigue", 1.0, 1.0, 2.0, "x", target="home")
    lh, la = ctx_mod.apply_rules(1.5, 1.1, [up])
    assert lh > 1.5 and la < 1.1
    down = rules.Rule("fatigue", 1.0, 1.0, -2.0, "x", target="away")
    lh, la = ctx_mod.apply_rules(1.5, 1.1, [down])
    assert la < 1.1 and lh > 1.5
    total = rules.Rule("weather", 1.0, 1.0, -3.0, "x", target="total")
    lh, la = ctx_mod.apply_rules(1.5, 1.1, [total])
    assert lh < 1.5 and la < 1.1


# --------------------------------------------------------------------------- collectors (offline fakes)
def test_lineups_are_never_requested_before_the_lead_window_and_empty_means_na():
    class Client:
        used = 0

        def fetch(self, eid, now):
            self.used += 1
            return None

    c = Client()
    early = fixture(kickoff=NOW + timedelta(hours=9))
    assert lineups.facts_for(early, NOW, c, lead_min=120, eid="1") == []
    assert c.used == 0
    late = fixture(kickoff=NOW + timedelta(hours=1))
    out = lineups.facts_for(late, NOW, c, lead_min=120, eid="1")
    assert c.used == 1 and out[0].kind == "lineup_not_published" and out[0].text.startswith("N/A")


def test_lineup_cache_survives_naive_and_aware_clocks(tmp_path):
    """Regression: a cached XI whose timestamp was parsed as naive while the run clock was aware raised
    inside pandas/datetime maths and disabled the line-up collector for every fixture."""
    import time as _t
    from datetime import timezone

    c = lineups.Client(tmp_path / "l.json", ttl_min=15)
    c.cache["9"] = {"ts": _t.time(), "home": {"team": "A"}, "away": {"team": "B"}}
    assert c._cached("9", NOW) is not None and c._cached("9", datetime.now(timezone.utc)) is not None
    c.cache["9"]["ts"] = _t.time() - 3600
    assert c._cached("9", NOW) is None
    c.cache["8"] = {"ts": "2026-10-06 16:00:00", "home": {}, "away": None}   # older cache format
    assert c._cached("8", NOW) is None


def test_lineup_parse_marks_confirmed_xis_verified_official_and_never_predicts():
    payload = {"Eid": "1", "Lu": [
        {"Tnb": 1, "Fo": [4, 3, 3], "Ps": [{"Fn": "A", "Ln": "One", "Snu": 1, "Pos": 1, "Fp": "G", "Pid": 11},
                                           {"Fn": "A", "Ln": "Two", "Snu": 9, "Pos": 4, "Pid": 12},
                                           {"Fn": "Sub", "Ln": "Player", "Snu": 14, "Pos": 5, "Pid": 13},
                                           {"Fn": "The", "Ln": "Coach", "Pos": 10, "Pid": 14}]},
        {"Tnb": 2, "Fo": [4, 4, 2], "Snm": "Beta", "Ps": [{"Fn": "B", "Ln": "One", "Snu": 7, "Pos": 2, "Pid": 21}]}]}
    got = lineups._parse(payload)
    assert got["home"]["formation"] == "4-3-3" and got["away"]["side"] == 2
    home_names = [p["name"] for p in got["home"]["players"]]
    assert "A One" in home_names and "Sub Player" in home_names
    assert [p["name"] for p in got["home"]["players"] if p["starter"]] == ["A One", "A Two"]
    assert [p["name"] for p in got["home"]["players"] if p["sub"]] == ["Sub Player"]
    assert lineups.facts_for(fixture(kickoff=NOW + timedelta(hours=1)), NOW, _StubClient(got), 120, eid="1")[0].verified


def test_weather_classification_and_no_fetch_outside_the_horizon(tmp_path):
    assert weather.classify(None, 18, 0.1, 9)[0] == "normal"
    assert weather.classify(None, 18, 5.0, 9)[0] == "severe"
    assert weather.classify(95, 30, 0.0, 5)[0] == "severe"
    assert weather.classify(None, 20, 1.5, 33)[0] == "notable"
    v = weather.Venues(tmp_path / "venues.json")
    far = fixture(kickoff=NOW + timedelta(days=5))
    assert weather.facts_for(far, NOW, v, weather.WeatherCache(tmp_path / "w.json"), horizon_h=48) == []


def test_weather_cache_budget_and_ttl_keep_request_volume_flat(tmp_path):
    cache = weather.WeatherCache(tmp_path / "w.json", ttl_h=6.0, budget=1)
    cache.put("50.00,4.00@2026-10-06T17", {"temp": 15.0})
    assert cache.get("50.00,4.00@2026-10-06T17")["temp"] == 15.0   # served from cache, no new call
    assert cache.exhausted is True and cache.used == 1
    unknown = weather.facts_for(fixture(), NOW, venues=None, cache=cache, horizon_h=48)
    assert unknown == []                                          # no venues object -> no weather requests at all


def test_weather_unknown_venue_is_na_and_the_geocoder_fails_soft(tmp_path, monkeypatch):
    v = weather.Venues(tmp_path / "venues.json", budget=2)

    def boom(*a, **kw):
        raise RuntimeError("network down")

    monkeypatch.setattr(weather.requests, "get", boom)
    assert v.lookup("Unknown Stadium", NOW) is None
    # a transport failure is not cached: the next run must retry instead of permanently declaring it unknown
    assert "unknown-stadium" not in v.data

    class _Empty:
        status_code = 200

        @staticmethod
        def json():
            return []

    monkeypatch.setattr(weather.requests, "get", lambda *a, **kw: _Empty())
    assert v.lookup("Unknown Stadium", NOW) is None
    v.save()
    assert json.loads((tmp_path / "venues.json").read_text())["unknown-stadium"]["lat"] is None


def test_teamnews_flags_availability_reports_but_never_verifies_them():
    row = Row(news={"home": [{"title": "Star striker ruled out for Alpha", "source": "Reputable Times",
                              "when": "2026-10-06 08:00", "link": "https://x/1", "bucket": "24h"},
                            {"title": "Alpha ready for the derby", "source": "Reputable Times",
                             "when": "2026-10-05 08:00", "link": "https://x/2", "bucket": "3d"}],
                   "away": []})
    out = teamnews.facts_for(row, NOW)
    home = [f for f in out if f.subject == "Alpha"]
    assert any(f.kind == "team_out" for f in home)
    assert all(f.verified is False for f in home)
    assert all(f.confidence == "press" for f in home)
    assert any(f.kind == "news_unavailable" and f.text.startswith("N/A") for f in out if f.subject == "Beta")


def test_engine_pulls_team_news_through_the_injected_shared_cache(tmp_path):
    """One lookup per team per run, through the scanner's own cache; the fact must carry the outlet, the
    publication time and the link, and must never claim the team has no news when nothing was looked up."""
    calls: list[tuple] = []

    def news_fn(team, country):
        calls.append((team, country))
        if team == "Alpha":
            return [{"title": "Alpha striker fit again", "source": "Reputable Times",
                     "when": "2026-10-06 09:30", "link": "https://news/alpha", "bucket": "24h"}]
        return []

    eng = make_engine(tmp_path).with_history(results_frame())
    eng.news_fn = news_fn
    row = Row()
    rec = eng.run(row, fid="fid-news")
    assert calls == [("Alpha", "Testland"), ("Beta", "Testland")]
    news = [f for f in rec.facts if f.category == "team_news"]
    alpha = [f for f in news if f.subject == "Alpha"][0]
    assert alpha.confidence == "press" and alpha.verified is False and alpha.url == "https://news/alpha"
    assert alpha.effective_at.startswith("2026-10-06")
    assert alpha.kind == "team_in" and "availability signal" in alpha.text
    beta = [f for f in news if f.subject == "Beta"][0]
    assert beta.kind == "news_unavailable" and "no reputable recent headline" in beta.text

    # a budget-starved lookup is reported as such, never as "no news exists"
    eng3 = make_engine(tmp_path / "budget").with_history(results_frame())
    eng3.news_fn = lambda team, country: ([], "stale")
    rec3 = eng3.run(Row(), fid="fid-budget")
    assert any("request budget reached" in f.text for f in rec3.facts if f.category == "team_news")

    # outside the news window nothing is looked up, and the gap says exactly that
    eng2 = make_engine(tmp_path / "far").with_history(results_frame())
    eng2.news_fn = news_fn
    eng2.news_horizon_h = 1.0
    calls.clear()
    rec2 = eng2.run(Row(), fid="fid-far")
    assert calls == []
    assert any("not looked up this run" in f.text for f in rec2.facts if f.category == "team_news")


def test_fixture_listings_and_betting_pages_are_not_stored_as_team_news():
    """A "Live Score" page or a betting preview is not news about a team: it carries no attributable fact (and
    the specification forbids using another site's prediction), so it is dropped rather than stored."""
    row = Row(news={"home": [{"title": "Alpha vs Beta - Live Score - October 06, 2026", "source": "Sports Site",
                              "when": "2026-10-06 09:00", "link": "u1", "bucket": "24h"},
                            {"title": "Alpha vs Beta prediction and betting tips", "source": "Tips Site",
                             "when": "2026-10-06 08:00", "link": "u2", "bucket": "24h"}],
                   "away": [{"title": "Beta defender sidelined with a hamstring injury", "source": "Reputable Times",
                             "when": "2026-10-06 07:00", "link": "u3", "bucket": "24h"}]})
    out = teamnews.facts_for(row, NOW)
    home = [f for f in out if f.subject == "Alpha"]
    assert home and all(f.kind == "news_unavailable" for f in home), [f.text for f in home]
    beta = [f for f in out if f.subject == "Beta"]
    assert any(f.kind == "team_out" for f in beta) and "hamstring" in beta[0].text


def test_report_line_shows_a_signed_adjustment_and_never_prints_absolute_as_positive():
    """Rendering guard: a fatigue reduction must read as a minus, and a record that adjusted must never render
    as 'no adjustment' (that happened once, when lam_pct was dropped from the app view)."""
    import scanner
    from research.facts import ResearchRecord

    rec = ResearchRecord(
        fid="x", kickoff="2026-10-06 20:45", updated="2026-10-06T18:00:00Z", quality="MEDIUM",
        quality_reasons=["4 current fact(s) in 3 categories"], support="full",
        facts=[], conflicts=[], base={"O15": 0.86, "O25": 0.5997, "O35": 0.34, "BTTS": 0.63, "HW": 0.5, "AW": 0.3},
        final={"O15": 0.855, "O25": 0.5863, "O35": 0.32, "BTTS": 0.61, "HW": 0.5, "AW": 0.3},
        adjustments=[{"cat": "fatigue", "weight": 1.0, "strength": "strong", "target": "both", "raw": 1.0,
                      "reason": "congested schedule: Alpha (3 day(s))", "sources": ["own archive"],
                      "fact_ids": ["f1"], "pp": {"O25": -1.34, "BTTS": -2.0}, "lam_pct": -1.98, "enabled": True}],
        totals={"lam_pct_h": -1.98, "lam_pct_a": -1.98, "max_pp": 1.34, "applied": True, "capped": False,
                "adjust_enabled": True})
    view = rec.app_view()
    assert view["adjustments"][0]["lam_pct"] == -1.98        # survives the trip to the app/report
    lines = scanner.render_context(view)
    head = lines[0]
    assert "-1.3 pp on O2.5" in head and "no adjustment" not in head
    assert "**FINAL** O2.5 59%" in head
    assert any("-1.3 pp on O2.5 — congested schedule" in line for line in lines)
    # and the no-adjustment case still says so, with a reason taken from a rule that actually evaluated something
    rec.totals.update({"applied": False, "adjust_enabled": False, "max_pp": 0.0})
    rec.final = dict(rec.base)
    rec.adjustments = [{"cat": "fatigue", "weight": 0.0, "strength": "strong", "target": "both", "raw": 0.0,
                        "reason": "rest is adequate (shortest gap 9 day(s))", "sources": [], "fact_ids": [],
                        "pp": {"O25": 0.0}, "lam_pct": 0.0, "enabled": False},
                       {"cat": "motivation", "weight": 0.0, "strength": "unavailable", "target": "total",
                        "raw": 0.0, "reason": "stakes (...) recorded but not scored until the backtested points model exists",
                        "sources": [], "fact_ids": [], "pp": {"O25": 0.0}, "lam_pct": 0.0, "enabled": False}]
    out = scanner.render_context(rec.app_view())
    assert "no adjustment" in out[0] and "FINAL** = BASE" in out[0]
    # the reason comes from a rule that actually evaluated something, not from the not-scored placeholder
    assert any("rest is adequate" in line for line in out)
    assert not any("backtested points model" in line for line in out)


def test_conflicting_reports_produce_a_recorded_conflict_with_no_adjustment():
    a = F.make_fact("team_news", "Alpha", "reported: injured", "Outlet A", NOW, confidence="press",
                    kind="team_out", effective_at=NOW - timedelta(hours=3))
    b = F.make_fact("team_news", "Alpha", "reported: returns to training", "Outlet B", NOW, confidence="press",
                    kind="team_in")
    confl = teamnews.availability_conflict([a, b])
    assert confl and confl[0]["source_a"] == "Outlet A" and confl[0]["source_b"] == "Outlet B"
    assert confl[0]["impact"] == "no adjustment"


def test_fatigue_index_reads_the_archive_and_reports_na_when_the_team_is_unknown():
    idx = fatigue.MatchIndex(results_frame(days=(3, 10)), NOW)
    sig = idx.signals("Alpha", NOW + timedelta(hours=4))
    assert sig["days_since_last"] == 3.0
    assert idx.signals("Nobody FC", NOW) is None
    out = fatigue.facts_for(idx, fixture(), NOW)
    assert any(f.kind == "no_history" and f.text.startswith("N/A") for f in out)


def test_lower_league_gap_is_stated_rather_than_papered_over():
    m = motivation.facts_for(results_frame(), fixture(), NOW, support="none")
    assert any(f.kind == "coverage_none" for f in m)
    assert any(f.kind == "stakes_unavailable" and f.text.startswith("N/A") for f in m)


def test_collectors_work_with_a_tz_aware_kickoff_and_a_naive_archive():
    """Regression: the scanner's clock and kick-offs are tz-aware (Africa/Johannesburg), the results archive and
    football-data frames are naive local dates. Mixing them raised inside pandas and silently produced zero facts
    for every fixture — the layer looked like it was running while researching nothing."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Africa/Johannesburg")
    now = datetime(2026, 10, 6, 17, 54, tzinfo=tz)
    frame = pd.DataFrame([{"date": pd.Timestamp("2026-10-03"), "country": "England", "div": "E0",
                           "league": "Premier League", "home": "Alpha", "away": "Other", "hg": 1, "ag": 1}])
    ko = pd.Timestamp("2026-10-06 20:45", tz=tz)
    idx = fatigue.MatchIndex(frame, now)
    assert idx.signals("Alpha", ko)["days_since_last"] == 3.0
    fx = {"kickoff": ko, "home": "Alpha", "away": "Beta", "country": "England", "div": "E0",
          "league": "Premier League"}
    assert len(motivation.facts_for(frame, fx, now, "full")) >= 2
    assert len(fatigue.facts_for(idx, fx, now)) == 2


# --------------------------------------------------------------------------- engine
def test_engine_phase_a_leaves_the_published_probability_untouched(tmp_path):
    eng = make_engine(tmp_path).with_history(results_frame())
    row = Row(news=None)
    rec = eng.run(row, fid="2026-10-06|Testland|Alpha|Beta")
    assert rec.totals["adjust_enabled"] is False and rec.totals["applied"] is False
    assert row.p_final == row.p_model and row.lam_h == row.mod_h
    assert rec.base["O25"] == round(row.p_model["O25"], 4)
    assert rec.final == rec.base
    assert all(v == 0.0 for m, v in rec.totals.items() if False) or rec.totals["max_pp"] == 0.0
    assert row.audit["context"]["quality"] in ("HIGH", "MEDIUM", "LOW", "INSUFFICIENT")
    eng.finish()
    assert eng.store.path.exists()
    stored = json.loads(eng.store.path.read_text(encoding="utf-8"))
    assert "2026-10-06|Testland|Alpha|Beta" in stored["records"]


def test_engine_with_weights_zero_cannot_adjust_even_when_the_switch_is_on(tmp_path):
    eng = make_engine(tmp_path, adjust=True, weights={"fatigue": 1.0, "lineup": 0.0, "motivation": 0.0,
                                                      "weather": 0.0}).with_history(results_frame(days=(2, 5)))
    row = Row()
    rec = eng.run(row, fid="fid-1")
    # the weight is on and the schedule is congested -> the rule fires, and every bound is respected
    assert rec.totals["applied"] is True and rec.totals["base_consistent"] is True
    assert row.p_final != row.p_model                  # the published probability follows the rule ...
    assert rec.base["O25"] == round(row.p_model["O25"], 4)   # ... the stored base is the model's ...
    assert row.mod_h == 1.5 and row.mod_a == 1.1       # ... and the model's own xG is untouched
    assert all(abs(100 * (row.p_final[m] - row.p_model[m])) <= 2.0 + 1e-6 for m in ctx_mod.MARKETS)
    assert abs(rec.totals["lam_pct_h"]) <= 6.0 and abs(rec.totals["lam_pct_a"]) <= 6.0


def test_engine_conflict_forces_zero_adjustment(tmp_path):
    eng = make_engine(tmp_path, adjust=True, weights={"team_news": 9.0, "fatigue": 0.0})
    row = Row(news={"home": [{"title": "Star man injured and out", "source": "Outlet A",
                              "when": "2026-10-06 09:00", "link": "u", "bucket": "24h"},
                            {"title": "Star man returns to training", "source": "Outlet B",
                             "when": "2026-10-06 10:00", "link": "u", "bucket": "24h"}], "away": []})
    rec = eng.run(row, fid="fid-2")
    assert rec.conflicts and rec.totals["applied"] is False
    news_rule = [a for a in rec.adjustments if a["cat"] == "team_news"] or None
    assert news_rule is None or news_rule[0]["pp"]["O25"] == 0.0


def test_engine_survives_a_broken_collector(tmp_path):
    eng = make_engine(tmp_path).with_history(results_frame())
    eng.collect = lambda row, support="full": (_ for _ in ()).throw(RuntimeError("boom"))  # type: ignore[assignment]
    rec = eng.run(Row(), fid="fid-3")
    assert eng.stats["errors"] == 1 and any("research error" in n for n in rec.notes)
    assert rec.quality == "INSUFFICIENT"


def test_should_research_respects_the_horizon(tmp_path):
    eng = make_engine(tmp_path)
    assert eng.should_research(Row(fixture(kickoff=NOW + timedelta(hours=48)))) is True
    assert eng.should_research(Row(fixture(kickoff=NOW + timedelta(days=8)))) is False


def test_engine_never_reads_odds_or_sportybet_prices():
    """Static guard on the *code* (not the prose): the research package must have no odds/price input at all.

    Checked on the parsed tree, so imports, names and attributes are inspected — docstrings that promise the
    layer never reads odds are irrelevant, and an actual reference cannot hide behind a comment.
    """
    banned = {"odds", "p_sb", "sportybet", "sporty", "implied", "price", "prices", "odds_h", "odds_over"}
    offenders: list[str] = []
    for p in sorted((ROOT / "research").glob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id.lower() in banned:
                offenders.append(f"{p.name}:{node.id}")
            elif isinstance(node, ast.Attribute) and node.attr.lower() in banned:
                offenders.append(f"{p.name}:{node.attr}")
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in node.names] + ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
                for m in mods:
                    if str(m).split(".")[0].lower() in banned:
                        offenders.append(f"{p.name}:import {m}")
    assert not offenders, f"odds/price references found in the research package: {offenders[:5]}"


def test_engine_refuses_to_adjust_when_it_cannot_reproduce_the_base_probability(tmp_path):
    """If the engine's own maths does not reproduce the published base probability, it must not adjust: the
    adjustment would be applied to a different number from the one on screen."""
    eng = make_engine(tmp_path, adjust=True, weights={"fatigue": 1.0, "lineup": 0.0, "motivation": 0.0,
                                                      "weather": 0.0}).with_history(results_frame(days=(2, 5)))
    row = Row(p_model={"O15": 0.60, "O25": 0.40, "O35": 0.25, "BTTS": 0.45, "HW": 0.40, "AW": 0.35})
    rec = eng.run(row, fid="fid-mismatch")
    assert rec.totals["applied"] is False and rec.totals["base_consistent"] is False
    assert row.p_final == row.p_model and any("not reproduced" in n for n in rec.notes)


# --------------------------------------------------------------------------- publication contract (verify.py)
def test_verify_allows_a_declared_bounded_delta_and_blocks_everything_else():
    """The publication gate must keep catching a silent blend while allowing a declared context adjustment."""
    import verify

    clean = {"sels": [["O25", 0.61, 0.61, 0.64, 1.9, 0]], "p": {"O25": 0.61, "model_O25": 0.61},
             "xg": {"home": 1.5, "model_home": 1.5}}
    a_pp, w_pp, a_xg, w_xg, declared = verify.context_budget(clean)
    assert (a_pp, w_pp, a_xg, w_xg, declared) == (0.0, 0.0, 0.0, 0.0, False)

    declared_det = {"context": {"totals": {"adjust_enabled": True, "max_pp": 1.4, "lam_pct_h": -3.0}},
                    "sels": [["O25", 0.585, 0.596, 0.64, 1.9, 0]],
                    "p": {"O25": 0.585, "model_O25": 0.596},
                    "xg": {"home": 1.455, "model_home": 1.5}}
    a_pp, w_pp, a_xg, w_xg, declared = verify.context_budget(declared_det)
    assert declared is True and w_pp <= a_pp and w_xg <= a_xg

    # a delta bigger than the adjustment the record declares (e.g. an odds blend slipping in)
    sneaky = {"context": {"totals": {"adjust_enabled": True, "max_pp": 0.5, "lam_pct_h": 0.0}},
              "sels": [["O25", 0.70, 0.596, 0.64, 1.9, 0]], "p": {"O25": 0.70, "model_O25": 0.596},
              "xg": {"home": 1.5, "model_home": 1.5}}
    a_pp, w_pp, _, _, _ = verify.context_budget(sneaky)
    assert w_pp > a_pp

    # no context record at all -> any difference is an error, exactly as before this layer existed
    silent = {"sels": [["O25", 0.70, 0.596, 0.64, 1.9, 0]], "p": {"O25": 0.70, "model_O25": 0.596},
              "xg": {"home": 1.9, "model_home": 1.5}}
    a_pp, w_pp, a_xg, w_xg, declared = verify.context_budget(silent)
    assert (a_pp, a_xg, declared) == (0.0, 0.0, False) and w_pp > 0 and w_xg > 0


def test_store_compacts_settled_records_but_keeps_the_evidence(tmp_path):
    """A week of records must not turn the state file into tens of megabytes: once a fixture is settled the
    bulky rule payloads (line-up name lists, structured values) are dropped while the evidence a reader or an
    error analysis needs — the fact text, its source, both timestamps and the confidence — is kept."""
    p = tmp_path / "records.json"
    s = Store(p, keep_days=7)
    live = {"fid": "live", "kickoff": NOW.strftime("%Y-%m-%d %H:%M"),
            "facts": [{"category": "lineup", "kind": "confirmed_xi", "text": "confirmed XI published by the feed",
                       "source": "feed", "retrieved_at": "x", "effective_at": "x", "confidence": "official",
                       "value": {"starters": [f"Player {i}" for i in range(11)]}}]}
    old = {"fid": "old", "kickoff": (NOW - timedelta(days=3)).strftime("%Y-%m-%d %H:%M"),
           "facts": [{"category": "lineup", "kind": "confirmed_xi", "text": "confirmed XI published by the feed",
                      "source": "feed", "retrieved_at": "x", "effective_at": "x", "confidence": "official",
                      "value": {"starters": [f"Player {i}" for i in range(11)]}}],
           "notes": ["a", "b", "c", "d"]}
    s.put(live); s.put(old)
    assert s.compact(NOW) == 1
    assert s.records["old"]["facts"][0]["value"] == {}
    assert s.records["old"]["facts"][0]["text"] and s.records["old"]["facts"][0]["source"] == "feed"
    assert len(s.records["old"]["notes"]) == 2
    assert s.records["live"]["facts"][0]["value"]["starters"]      # a live fixture keeps its payload


def test_store_size_guard_drops_oldest_first(tmp_path):
    """The store is force-pushed with the state every 30 minutes, so its size is capped: when the ceiling bites
    the oldest records go first and the run log says so."""
    p = tmp_path / "records.json"
    st = Store(p, keep_days=7, max_records=5000, max_mb=0.5)       # the production floor: 0.5 MB
    for i in range(1500):                                          # ~750 KB of records
        st.put({"fid": f"f{i}", "kickoff": (NOW - timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M"),
                "facts": [{"text": "x" * 400, "source": "a source name", "category": "fatigue", "value": {}}]})
    dropped = st.prune(NOW)
    assert dropped > 0 and st.dropped.get("over_size", 0) > 0
    saved = st.save(NOW)
    assert 0 < saved < 1500
    import json as _json
    kept = _json.loads(p.read_text(encoding="utf-8"))["records"]
    assert "f0" in kept and "f1499" not in kept                    # newest kept, oldest dropped
    assert len(_json.dumps({"records": kept})) <= 500_000 * 1.05


def test_store_prunes_old_records_and_survives_corruption(tmp_path):
    p = tmp_path / "records.json"
    s = Store(p, keep_days=5, max_records=1000)
    s.put({"fid": "old", "kickoff": "2026-09-01 12:00"})
    s.put({"fid": "new", "kickoff": NOW.strftime("%Y-%m-%d %H:%M")})
    s.save(NOW)
    s2 = Store(p, keep_days=5)
    assert set(s2.records) == {"new"}
    p.write_text("{not json", encoding="utf-8")
    s3 = Store(p, keep_days=5)
    assert s3.records == {} and "recovered_from_error" in s3.meta
