"""Small reviewed derby map. Exact clubs/country, symmetric; not a popularity guess.

Reference: https://derby.ist/all and https://lowerblock.com/articles/the-biggest-rivalries-in-world-football/
Unknown pairs (including big non-local rivalries) get no derby claim.
"""
from player_photos import club_key

PAIRS = (
    ('South Africa', 'Orlando Pirates', 'Kaizer Chiefs', 'Soweto Derby'),
    ('England', 'Manchester United', 'Manchester City', 'Manchester Derby'),
    ('England', 'Arsenal', 'Tottenham', 'North London Derby'),
    ('England', 'Liverpool', 'Everton', 'Merseyside Derby'),
    ('Spain', 'Real Madrid', 'Atlético Madrid', 'Madrid Derby'),
    ('Italy', 'Milan', 'Inter', 'Milan Derby'),
    ('Italy', 'Roma', 'Lazio', 'Rome Derby'),
)


def label(home, away, country):
    home_key, away_key = club_key(home, country), club_key(away, country)
    if not home_key or not away_key or home_key == away_key:
        return None
    pair = frozenset((home_key, away_key))
    for region, left, right, name in PAIRS:
        if pair == frozenset((club_key(left, region), club_key(right, region))):
            return name
    return None
