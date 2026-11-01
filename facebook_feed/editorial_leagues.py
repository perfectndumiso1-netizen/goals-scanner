"""Editorial-only competition scope. Never changes the live roster or betting models."""
from .highlightly_watchlist import LEAGUES as LIVE_LEAGUES, normal

LEAGUES = dict(LIVE_LEAGUES, **{
    'eredivisie': ('Eredivisie', 'Netherlands', ('Eredivisie',)),
    'portugal': ('Primeira Liga', 'Portugal', ('Primeira Liga', 'Liga Portugal', 'Liga Portugal Betclic')),
    'belgium': ('Belgian Pro League', 'Belgium', ('Pro League', 'First Division A', 'Jupiler Pro League')),
    'turkey': ('Super Lig', 'Turkey', ('Super Lig', 'Süper Lig', 'Superliga')),
    'scotland': ('Scottish Premiership', 'Scotland', ('Premiership', 'Scottish Premiership')),
    'austria': ('Austrian Bundesliga', 'Austria', ('Bundesliga',)),
    'switzerland': ('Swiss Super League', 'Switzerland', ('Super League',)),
    'denmark': ('Danish Superliga', 'Denmark', ('Superliga', 'Superligaen')),
    'norway': ('Eliteserien', 'Norway', ('Eliteserien',)),
    'sweden': ('Allsvenskan', 'Sweden', ('Allsvenskan',)),
    'poland': ('Ekstraklasa', 'Poland', ('Ekstraklasa',)),
    'czechia': ('Czech First League', 'Czech Republic', ('First League', 'Czech Liga', '1. Liga')),
    'greece': ('Greek Super League', 'Greece', ('Super League', 'Super League 1')),
    'japan': ('J1 League', 'Japan', ('J1 League', 'J.League', 'J. League Div.1')),
    'korea': ('K League 1', 'South Korea', ('K League 1',)),
    'brazil': ('Brazil Serie A', 'Brazil', ('Serie A', 'Brasileiro Serie A', 'Brasileirão Série A')),
    'argentina': ('Argentine Primera Division', 'Argentina', ('Liga Profesional', 'Primera Division', 'Liga Profesional Argentina')),
    'usa': ('MLS', 'USA', ('Major League Soccer', 'MLS')),
    'mexico': ('Liga MX', 'Mexico', ('Liga MX',)),
})


def league_key(name, country):
    country = {'turkiye':'Turkey','unitedstates':'USA','unitedstatesofamerica':'USA','czechia':'Czech Republic','korearepublic':'South Korea'}.get(normal(country),country)
    return next((key for key, (_, nation, aliases) in LEAGUES.items()
                 if normal(country) == normal(nation) and normal(name) in {normal(a) for a in aliases}), None)
