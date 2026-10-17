# model diet (user rules 2026-10-11, widened 2026-10-17): the curated list + every league the archive has enough data on.
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import coverage
import scanner

ALLOWED = [
    ("England", "Premier League"), ("England", "Championship"),
    ("Spain", "La Liga"), ("Spain", "LaLiga"), ("Spain", "LaLiga 2"), ("Spain", "Segunda División"),
    ("Italy", "Serie A"), ("Italy", "Serie B"),
    ("Germany", "Bundesliga"), ("Germany", "2. Bundesliga"),
    ("France", "Ligue 1"), ("France", "Ligue 2"),
    ("Netherlands", "Eredivisie"),
    ("Belgium", "Pro League"), ("Belgium", "Jupiler Pro League"),
    ("Portugal", "Primeira Liga"), ("Scotland", "Premiership"),
    ("Turkiye", "Süper Lig"), ("Turkey", "Super Lig"),
    ("Denmark", "Superliga"), ("Denmark", "Superligaen"),
    ("Switzerland", "Super League"), ("Greece", "Super League"),
    ("Poland", "Ekstraklasa"), ("Austria", "Bundesliga"),
    ("Sweden", "Allsvenskan"), ("Norway", "Eliteserien"),
    ("Croatia", "HNL"), ("Serbia", "Super Liga"), ("Ukraine", "Premier League"),
    ("Brazil", "Serie A"), ("Argentina", "Liga Profesional: Clausura"),
    ("USA", "MLS"), ("USA", "Major League Soccer"), ("Mexico", "Liga MX: Apertura"),
    ("South Africa", "Premiership"), ("Nigeria", "NPFL"),
    ("Egypt", "Premier League"), ("Morocco", "Botola Pro"),
    # UEFA club competitions are IN (user reversal 2026-10-12). Real Livescore shape: the competition
    # IS the country (Ccd "champions-league"), the league (Scd) is "League Stage" / knockout names.
    ("Champions League", "League Stage"), ("Europa League", "League Stage"), ("Conference League", "League Stage"),
    ("UEFA", "Champions League"), ("Europe", "UEFA Europa League"),   # secondary shapes stay covered
]

BLOCKED = [
    # explicit user exclusions
    ("Japan", "J1 League"), ("Japan", "J2 League"), ("Australia", "A-League Men"),
    ("England", "Women's Super League"), ("Sweden", "Damallsvenskan"),
    ("England", "Premier League 2"), ("Italy", "Primavera 1"),
    ("Club Friendlies", "Club Friendly Games"),
    # cups / knockouts / internationals
    ("England", "FA Cup"), ("Italy", "Coppa Italia"), ("Germany", "DFB Pokal"),
    ("France", "Coupe de France"), ("Spain", "Copa del Rey"), ("England", "Carabao Cup"),
    # UEFA club competitions themselves are allowed now — but their qualifiers / play-off rounds stay out
    ("Champions League", "Qualification"), ("Champions League", "2nd Qualifying Round"),
    ("Europa League", "Play-offs"), ("Conference League", "Qualification Play-offs"),
    ("South America", "Copa Libertadores"), ("Europe", "Nations League"),
    ("International", "World Cup Qualifiers"), ("Denmark", "Superliga: Playoffs"),
    # lower tiers and minor competitions: not on the curated list, so they only come in when the ARCHIVE has
    # enough data on them (see the data-rich tests below) — with no archive they stay out, as before
    ("Argentina", "Primera Nacional"), ("Italy", "Serie D: Group A"),
    ("Spain", "Segunda División RFEF: Group 3"), ("Greece", "Super League 2"),
    ("Sweden", "Superettan"), ("Belgium", "Challenger Pro League"),
    ("Germany", "Regionalliga West"), ("Germany", "Oberliga: Westfalen"),
    ("Croatia", "2. HNL"), ("USA", "MLS Next Pro"), ("United States", "USL League One"),
    ("Kenya", "Premier League"), ("Ghana", "Premier League"), ("China", "Super League"),
    ("Saudi Arabia", "Saudi Professional League"), ("Finland", "Ykkösliiga"),
    ("San Marino", "Campionato Sammarinese"), ("Andorra", "1st Division"),
]


def test_diet_allows_exactly_the_data_rich_list():
    for c, l in ALLOWED:
        assert scanner.league_allowed(c, l), f"should analyse {c} — {l}"


@pytest.fixture(autouse=True)
def _no_archive(monkeypatch):
    """Unit tests of the curated list must not depend on whatever archive a previous test loaded."""
    monkeypatch.setattr(scanner, "DATA_RICH", {})


def test_diet_blocks_junk_and_everything_unlisted():
    for c, l in BLOCKED:
        assert not scanner.league_allowed(c, l), f"should not analyse {c} — {l}"


def test_diet_is_on_and_depth_gate_defaults_to_eight():
    assert scanner.CONFIG["MODEL_DIET"] is True
    assert scanner.CONFIG["MIN_TEAM_MATCHES"] == 8


def test_seed_stages_carry_no_banned_competitions():
    # 2026-10-17: only Japan and Australia stay explicitly banned (user rule 2026-10-11); the rest of the
    # old list is now decided by the archive rule, not by name
    banned = ("japan", "australia")
    for s in scanner.CONFIG["SEED_STAGES"].split(","):
        s = s.strip().lower()
        assert not any(b in s for b in banned), f"seed stage off the diet: {s}"


def test_rules_payload_explains_the_diet():
    src = open("shortlist.py", encoding="utf-8").read()
    assert '"diet":' in src


# =============================================================== 2026-10-17: "every league we have enough data on"
NOW = datetime(2026, 10, 17, 9, 30)


def _fact(country, league, teams=18, median=40.0, stats=1.0, status="ACTIVE", eligible=True, age_days=3):
    return {"country": country, "competition": league, "teams": teams, "median_per_team": median, "status": status,
            "eligible": eligible, "stats_quality": {"pct": stats}, "last_result": NOW - timedelta(days=age_days)}


def _rich(*facts):
    return scanner.data_rich_from_facts(list(facts), NOW)


def test_the_chinese_super_league_has_enough_data_and_comes_in(monkeypatch):
    rich = _rich(_fact("China", "Super League", teams=18, median=51, stats=1.0))
    assert scanner._diet_key("China", "Super League") in rich
    monkeypatch.setattr(scanner, "DATA_RICH", rich)
    assert scanner.league_allowed("China", "Super League")
    assert not scanner.league_allowed("China", "FA Cup")          # the cup stays out even though the country is in


def test_data_rich_needs_a_real_table_depth_recency_and_eligibility():
    assert _rich(_fact("X", "Top Division", teams=6)) == {}                       # too few clubs for a league table
    assert _rich(_fact("X", "Top Division", teams=60)) == {}                      # a pooled competition, not a table
    assert _rich(_fact("X", "Top Division", median=9)) == {}                      # thin history per club
    assert _rich(_fact("X", "Top Division", eligible=False)) == {}                # the registry's own flag
    assert _rich(_fact("X", "Top Division", status="UPCOMING")) == {}
    assert _rich(_fact("X", "Top Division", status="DATA_ERROR", eligible=False)) == {}
    assert _rich(_fact("X", "Top Division", age_days=500)) == {}                  # outside the model's 400-day window
    assert len(_rich(_fact("X", "Top Division", status="FINISHED", age_days=60))) == 1   # off-season is fine


def test_no_statistics_is_ok_for_a_national_league_but_not_for_a_regional_or_amateur_tier():
    rich = _rich(_fact("Ghana", "Premier League", stats=0.0), _fact("Tunisia", "Ligue I", stats=0.0),
                 _fact("Germany", "Oberliga: Bremen", stats=0.0), _fact("Italy", "Serie D: Group C", stats=0.0),
                 _fact("Norway", "3. Division: Group 5", stats=0.0), _fact("Spain", "Segunda Division RFEF: Group 1", stats=0.03),
                 _fact("Mexico", "Liga Premier: Serie B", stats=0.0), _fact("Republic of Korea", "K3 League", stats=0.0),
                 _fact("Denmark", "Danmarksserien: Group 2", stats=0.0))
    assert set(rich) == {scanner._diet_key("Ghana", "Premier League"), scanner._diet_key("Tunisia", "Ligue I")}


def test_a_stats_rich_lower_tier_comes_in_because_the_archive_supports_it():
    rich = _rich(_fact("England", "League 1", teams=37, median=60, stats=1.0),
                 _fact("Italy", "Serie C: Group A", teams=29, median=55, stats=0.9))
    assert len(rich) == 2


def test_the_hard_blocks_beat_the_archive_rule():
    facts = [_fact("Japan", "J1 League"), _fact("Australia", "A-League Men"), _fact("Germany", "Frauen-Bundesliga"),
             _fact("Spain", "Liga F"), _fact("England", "Premier League 2"), _fact("England", "FA Cup"),
             _fact("England", "Baller League UK", stats=0.0), _fact("International Friendlies", "Friendlies 2024", teams=30),
             _fact("Europe", "Champions League: Qualification"), _fact("Denmark", "Superliga: Playoffs")]
    assert _rich(*facts) == {}


def test_country_spellings_line_up_between_feeds(monkeypatch):
    monkeypatch.setattr(scanner, "DATA_RICH", _rich(_fact("Turkiye", "1st Lig", teams=20), _fact("Republic of Korea", "K-League 1", teams=12)))
    assert scanner.league_allowed("Turkey", "1st Lig") and scanner.league_allowed("South Korea", "K-League 1")
    assert scanner._diet_key("Türkiye", "Süper Lig") == scanner._diet_key("Turkiye", "Super Lig")   # accents are folded


def test_england_step_four_no_longer_slips_through_the_premier_league_pattern():
    assert scanner.league_allowed("England", "Premier League") and scanner.league_allowed("England", "Championship")
    assert not scanner.league_allowed("England", "Northern Premier League")
    assert not scanner.league_allowed("England", "Premier League 2")


def test_japan_and_australia_stay_blocked_even_when_they_have_enough_data(monkeypatch):
    monkeypatch.setattr(scanner, "DATA_RICH", {scanner._diet_key("Japan", "J1 League"): "x", scanner._diet_key("Australia", "A-League Men"): "x"})
    assert not scanner.league_allowed("Japan", "J1 League") and not scanner.league_allowed("Australia", "A-League Men")


def test_archive_only_leagues_are_analysed_a_fortnight_ahead_curated_and_main_divisions_always(monkeypatch):
    monkeypatch.setattr(scanner, "DATA_RICH", {scanner._diet_key("China", "Super League"): "x"})
    near, far = NOW + timedelta(days=5), NOW + timedelta(days=40)
    assert scanner.fixture_allowed("China", "Super League", near, NOW)
    assert not scanner.fixture_allowed("China", "Super League", far, NOW)          # the far end of the 60-day window costs scan time
    assert scanner.fixture_allowed("England", "Premier League", far, NOW)          # curated: full horizon
    assert scanner.fixture_allowed("England", "League One", far, NOW, div_code="E2")   # a football-data main division is always in
    assert not scanner.fixture_allowed("England", "FA Cup", near, NOW, div_code="E2")  # ...unless blocked
    assert not scanner.fixture_allowed("Narnia", "Top Flight", near, NOW)


def test_diet_off_switch_and_extra_days_lever_exist():
    assert scanner.CONFIG["DIET_EXTRA_DAYS"] == 14 and scanner.CONFIG["MODEL_DIET"] is True


# ---------------------------------------------------------------- coverage.stage_facts reads the archive
def _write_stage(dir_: Path, key, country, league, n_teams, rounds, stats_every=1):
    import json
    teams = [f"T{i}" for i in range(n_teams)]
    events, stats, i = {}, {}, 0
    for r in range(rounds):
        for a in range(n_teams // 2):
            d = (NOW - timedelta(days=3 + 7 * (rounds - r))).strftime("%Y%m%d1500")
            events[str(i)] = [d, "h", teams[a], "a", teams[a + n_teams // 2], 2, 1, None, None]
            if i % stats_every == 0:
                stats[str(i)] = {"shots": [10, 8]}
            i += 1
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / f"{key.replace('/', '__')}.json").write_text(json.dumps(
        {"key": key, "country": country, "league": league, "fetched": "2026-10-16 12:00",
         "events": events, "stats": stats, "stats_probe": {}, "backfill": {}}), encoding="utf-8")


def test_stage_facts_feed_the_diet_end_to_end(tmp_path, monkeypatch):
    st = tmp_path / "stages"
    _write_stage(st, "china/super-league", "China", "Super League", n_teams=16, rounds=20)            # 20 matches/club, stats on all
    _write_stage(st, "ghana/premier-league", "Ghana", "Premier League", n_teams=16, rounds=20, stats_every=10**6)  # no stats at all
    _write_stage(st, "germany/oberliga-bremen", "Germany", "Oberliga: Bremen", n_teams=16, rounds=20, stats_every=10**6)
    _write_stage(st, "x/thin", "X", "Top Division", n_teams=16, rounds=4)                             # 4 matches/club: too thin
    facts = {f["competition"]: f for f in coverage.stage_facts(st, NOW)}
    assert facts["Super League"]["median_per_team"] == 20.0 and facts["Super League"]["last_result"] is not None
    n = scanner.refresh_data_rich(st, NOW)
    assert n == 2
    assert scanner.league_allowed("China", "Super League") and scanner.league_allowed("Ghana", "Premier League")
    assert not scanner.league_allowed("Germany", "Oberliga: Bremen") and not scanner.league_allowed("X", "Top Division")


def test_refresh_never_raises_without_an_archive(tmp_path):
    assert scanner.refresh_data_rich(tmp_path / "nothing-here", NOW) == 0
    assert scanner.DATA_RICH == {}


def test_refresh_works_with_the_timezone_aware_clock_main_uses(tmp_path):
    """Regression: main() passes a tz-aware `now`; the first version raised, the diet silently fell back to the
    curated list, and no new league would ever have appeared in production."""
    from zoneinfo import ZoneInfo
    st = tmp_path / "stages"
    _write_stage(st, "china/super-league", "China", "Super League", n_teams=16, rounds=20)
    aware = NOW.replace(tzinfo=ZoneInfo("Africa/Johannesburg"))
    assert coverage.stage_facts(st, aware)
    assert scanner.refresh_data_rich(st, aware) == 1
    assert scanner.fixture_allowed("China", "Super League", aware + timedelta(days=3), aware)
