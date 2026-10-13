# model diet (user rule 2026-10-11): only data-rich leagues are analysed.
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
    # UEFA club competitions are IN (user reversal 2026-10-12): Champions / Europa / Conference League
    ("UEFA", "Champions League"), ("UEFA", "UEFA Champions League"),
    ("Europe", "Europa League"), ("UEFA", "UEFA Europa League"),
    ("UEFA", "Conference League"), ("Europe", "UEFA Europa Conference League"),
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
    ("UEFA", "Champions League Qualification"), ("Europe", "Europa League Qualification"),
    ("UEFA", "UEFA Champions League, Play-off round"), ("Europe", "Conference League Play-offs"),
    ("South America", "Copa Libertadores"), ("Europe", "Nations League"),
    ("International", "World Cup Qualifiers"), ("Denmark", "Superliga: Playoffs"),
    # lower tiers and minor competitions (not on the allowlist)
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


def test_diet_blocks_junk_and_everything_unlisted():
    for c, l in BLOCKED:
        assert not scanner.league_allowed(c, l), f"should not analyse {c} — {l}"


def test_diet_is_on_and_depth_gate_defaults_to_eight():
    assert scanner.CONFIG["MODEL_DIET"] is True
    assert scanner.CONFIG["MIN_TEAM_MATCHES"] == 8


def test_seed_stages_carry_no_banned_competitions():
    banned = ("japan", "australia", "iran", "saudi", "qatar", "indonesia", "ghana",
              "tanzania", "botswana", "israel", "ireland", "wales", "romania", "chile",
              "colombia", "uruguay", "paraguay", "peru", "ecuador", "venezuela", "algeria")
    for s in scanner.CONFIG["SEED_STAGES"].split(","):
        s = s.strip().lower()
        assert not any(b in s for b in banned), f"seed stage off the diet: {s}"


def test_rules_payload_explains_the_diet():
    src = open("shortlist.py", encoding="utf-8").read()
    assert '"diet":' in src
