"""Recent-form eligibility for team-to-score recommendations; model probabilities stay unchanged."""
from datetime import datetime, timedelta
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import appdata  # noqa: E402
import policy  # noqa: E402
import safe  # noqa: E402
import shortlist  # noqa: E402
from safe import Sel  # noqa: E402

NOW = datetime(2026, 10, 15, 10, 0)


@pytest.fixture
def team_family_on(monkeypatch):
    """The team-goal form gate is still tested with the family switched back on (MODEL_MARKETS=team)."""
    monkeypatch.setattr(policy, "ALLOW", frozenset(("team",)))


def profile(name, gf, ga=None, venue_gf=None):
    ga = list(ga if ga is not None else [0] * len(gf))
    venue_gf = list(venue_gf if venue_gf is not None else gf[:3])
    return NS(
        name=name, n=20, gf=1.2, ga=1.1, venue_n=5, venue_gf=1.1, venue_ga=1.0,
        last5=[{"gf": g, "ga": a} for g, a in zip(gf, ga)],
        venue_last5=[{"gf": g, "ga": 1} for g in venue_gf],
    )


def match_row(home=None, away=None):
    kickoff = NOW + timedelta(hours=5)
    fx = pd.Series({"date": pd.Timestamp(kickoff.date()), "kickoff": pd.Timestamp(kickoff),
                    "country": "England", "league": "League", "div": "E0",
                    "home": "Home FC", "away": "Away FC"})
    audit = {"quality": {"overall": "High", "score": 0.85},
             "confidence": {"TG": "High", "O15": "High", "O25": "High", "O35": "High",
                            "BTTS": "High", "X12": "High"},
             "warnings": [], "context": {"conflicts": []}}
    return NS(fx=fx, audit=audit, data_ok=True, sb={"test": True}, sb_asof=None,
              hist={"O25": 0.7}, mod_h=1.6, mod_a=1.2, h2h=[],
              home=home or profile("Home FC", [1, 1, 1, 0, 0], [1, 0, 1, 1, 0], [1, 1, 0]),
              away=away or profile("Away FC", [1, 1, 0, 0, 0], [1, 1, 1, 0, 0], [1, 0, 0]))


def test_the_team_goal_family_is_off_by_default():
    """2026-10-27 model review: team goals (-6.4 %, home team to score -10.1 %) are no longer offered at all."""
    assert not policy.allowed("HO05") and not policy.allowed("AO05") and not policy.allowed("HO15")


def test_weak_attack_is_rejected_even_when_opponent_concedes_frequently(team_family_on):
    r = match_row(
        home=profile("Home FC", [1, 0, 0, 0, 0], [1, 1, 0, 1, 0], [1, 0, 0]),
        away=profile("Away FC", [1, 1, 0, 1, 0], [1, 1, 1, 1, 1], [1, 0, 0]),
    )
    record = shortlist.evaluate(r, Sel("HO05", 0.82, 0.80, 1.50))
    assert record["status"] == "rejected"
    assert any("team scored in 1/5" in reason for reason in record["reasons"])
    assert record["p_model"] == 0.82                     # the raw model number survives in the record
    assert record["p"] == 0.805                          # what is published is the anchored blend (0.82 / 0.80)


def test_qualifying_team_pick_explains_overall_venue_and_opponent_form(team_family_on):
    r = match_row(home=profile("Home FC", [1, 1, 1, 1, 0], [1, 0, 1, 1, 0], [1, 1, 0]))
    record = shortlist.evaluate(r, Sel("HO05", 0.827, 0.80, 1.50))
    assert record["status"] == "primary", record["reasons"]
    article = shortlist.match_article(r, record)
    evidence = article["paras"][0]
    assert "4/5 recent matches" in evidence
    assert "2/3 at home" in evidence
    assert "Away FC conceded in 3/5" in evidence


def test_away_team_to_score_uses_away_attack_and_home_opponent_defence():
    r = match_row(
        home=profile("Home FC", [0, 0, 0, 0, 0], [1, 1, 1, 0, 0], [0, 0, 0]),
        away=profile("Away FC", [1, 1, 1, 1, 0], [1, 0, 1, 0, 1], [1, 1, 0]),
    )
    assert safe.team_goal_form_ok(r, "AO05")
    assert not safe.team_goal_form_ok(r, "HO05")


def test_missing_same_venue_or_opponent_history_fails_closed():
    r = match_row(home=profile("Home FC", [1, 1, 1, 1, 0], [1, 0, 1, 1, 0], [1, 1, 0]))
    r.home.venue_last5 = [{"gf": 1, "ga": 0}, {"gf": 1, "ga": 1}]
    ok, reason = safe.team_goal_form_status(r, "HO05")
    assert not ok and "only 2/3 recent home matches" in reason


def test_safe_and_bets_of_the_day_boards_do_not_bypass_the_form_gate(monkeypatch):
    r = match_row(home=profile("Home FC", [1, 0, 0, 0, 0], [1, 1, 0, 1, 0], [1, 0, 0]))
    monkeypatch.setattr(safe, "selections", lambda _row: [Sel("HO05", 0.82, 0.80, 1.50)])
    assert safe.safest([r], NOW, NOW + timedelta(days=1))["bets"] == []
    assert safe.botd_candidates([r], NOW) == []


def test_app_export_filter_hides_failed_recommendation_but_keeps_other_markets():
    r = match_row(home=profile("Home FC", [1, 0, 0, 0, 0], [1, 1, 0, 1, 0], [1, 0, 0]))
    selections = [{"sel": "HO05"}, {"sel": "O15"}, {"sel": "BTTS"}]
    visible = appdata._recommended_selections(r, selections, safe.team_goal_form_ok)
    assert [s["sel"] for s in visible] == ["O15", "BTTS"]
