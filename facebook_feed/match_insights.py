"""Verified venue form and recent H2H. Factual editorial only; no odds/model input."""
from datetime import timedelta
from . import editorial as e
from .provider import ProviderError


def history(api, book, target, season):
    key = f"{target['league_id']}:{season}"
    if key not in book['histories']:
        passes = []
        for _ in range(2):
            rows = [e.fixture(r) for r in api.catalog({'leagueId': target['league_id'], 'season': season})]
            if any(m is None or (m['league_id'], m['season'], m['league']) !=
                   (target['league_id'], season, target['league']) for m in rows):
                raise ProviderError('History league/season mismatch')
            # Live/future rows can legitimately move between reads. Only
            # completed records are evidence; compare them in canonical ID order.
            passes.append(sorted((m for m in rows if m['status'] in e.FINAL), key=lambda m:m['id']))
        # Do not cache an inconsistent history as usable evidence.
        if passes[0] != passes[1]:
            raise ProviderError('Repeat-catalog sample conflict; statistics withheld')
        book['histories'][key] = {'passes': passes, 'checked_at': api.at}
    saved = book['histories'][key]['passes']
    if len(saved) != 2 or saved[0] != saved[1]:
        raise ProviderError('Repeat-catalog sample conflict; statistics withheld')
    return saved[0]


def completed(rows, target, now, days):
    cutoff = min(now, e.aware(target['kickoff']))
    return sorted((m for m in rows if m['status'] in e.FINAL and
                   e.aware(m['kickoff']) < cutoff and now-e.aware(m['kickoff']) <= timedelta(days=days)),
                  key=lambda m: (m['kickoff'], m['id']), reverse=True)


def team_record(api, book, rows, target, side, now):
    tid = target[side+'_id']; result = []
    for index, m in enumerate(rows):
        if m['score'] is None or m['status'] != 'Finished':
            raise ProviderError('Recent regulation-time result unavailable; no four-picture package')
        if index == 0:
            m = e.checked_detail(api, book, m, now)
        home = m['home_id'] == tid
        if m['home' if home else 'away'] != target[side]:
            raise ProviderError('Historical team name/identity conflict')
        gf, ga = m['score'] if home else reversed(m['score'])
        result.append({'id': m['id'], 'date': m['kickoff'], 'gf': gf, 'ga': ga,
                       'opponent': m['away' if home else 'home'], 'venue': 'H' if home else 'A'})
    return result


def extra_evidence(api, book, target, now):
    # Only two complete league seasons; no undocumented H2H/odds endpoints.
    current = history(api, book, target, target['season'])
    seasons = [target['season']]
    # Reuse current-season evidence when it already fills all four cards. Never
    # spend scarce quota (or require older-season access) merely to pad H2H.
    eligible = completed(current, target, now, 365)
    venue_complete = all(sum(m[side+'_id']==target[side+'_id'] for m in eligible)>=5
                         for side in ('home','away'))
    has_meeting = any({m['home_id'],m['away_id']}=={target['home_id'],target['away_id']}
                      for m in completed(current,target,now,730))
    previous = []
    if not venue_complete or not has_meeting:
        previous = history(api, book, target, target['season']-1)
        seasons.append(target['season']-1)
    rows = current + previous
    if len({m['id'] for m in rows}) != len(rows):
        raise ProviderError('Duplicate match across seasons; no four-picture package')
    recent = completed(rows, target, now, 365)
    venue = {}
    for side in ('home', 'away'):
        selected = [m for m in recent if m[side+'_id'] == target[side+'_id']][:5]
        if len(selected) != 5:
            raise ProviderError('Five recent home/away results unavailable; no four-picture package')
        venue[side] = team_record(api, book, selected, target, side, now)
    meetings = [m for m in completed(rows, target, now, 730)
                if {m['home_id'], m['away_id']} == {target['home_id'], target['away_id']}][:5]
    if not meetings:
        raise ProviderError('Recent head-to-head results unavailable; no four-picture package')
    h2h = []
    for index, m in enumerate(meetings):
        if m['score'] is None or m['status'] != 'Finished':
            raise ProviderError('Head-to-head regulation-time score unavailable')
        if index == 0:
            m = e.checked_detail(api, book, m, now)
        for side in ('home', 'away'):
            tid = target[side+'_id']
            if m['home' if m['home_id'] == tid else 'away'] != target[side]:
                raise ProviderError('Head-to-head team identity conflict')
        h2h.append({'id': m['id'], 'date': m['kickoff'], 'home': m['home'], 'away': m['away'],
                    'home_id': m['home_id'], 'away_id': m['away_id'], 'score': m['score']})
    return {'venue_form': venue, 'h2h': h2h, 'seasons': seasons}


def form(rows):
    wins = sum(r['gf'] > r['ga'] for r in rows); draws = sum(r['gf'] == r['ga'] for r in rows)
    return {'wins': wins, 'draws': draws, 'losses': len(rows)-wins-draws,
            'points': 3*wins+draws, 'scored': sum(r['gf'] for r in rows),
            'conceded': sum(r['ga'] for r in rows)}


def priority(target, book, now):
    """Rank only already repeat-verified history; never spend quota surveying odds.

    Complete evidence first, then the clearest five-match points/goal-difference
    contrast. Unknowns tie on kickoff/ID, never league prestige. Not a forecast.
    """
    records = []
    for season in (target['season'], (target['season'] or 0)-1):
        item = book['histories'].get(f"{target['league_id']}:{season}", {})
        passes = item.get('passes', [])
        if len(passes) == 2 and passes[0] == passes[1]:
            records.extend(passes[0])
    if not records:
        return (0, 0, 0)
    current = [m for m in completed(records, target, now, 180) if m['season']==target['season']]
    overall = [[m for m in current if target[side+'_id'] in (m['home_id'],m['away_id'])][:5]
               for side in ('home','away')]
    if any(len(g)!=5 for g in overall) or any(m['status']!='Finished' or m['score'] is None for m in sum(overall,[])):
        return (0, 0, 0)
    recent = completed(records, target, now, 365)
    groups = [[m for m in recent if m[side+'_id'] == target[side+'_id']][:5] for side in ('home', 'away')]
    meetings = [m for m in completed(records, target, now, 730)
                if {m['home_id'], m['away_id']} == {target['home_id'], target['away_id']}]
    if any(len(g) != 5 for g in groups) or not meetings:
        return (0, 0, 0)
    if any(m['status'] != 'Finished' or m['score'] is None for m in sum(groups, []) + meetings[:5]):
        return (0, 0, 0)
    stats = []
    for side, group in zip(('home', 'away'), groups):
        scores = [m['score'] if side == 'home' else list(reversed(m['score'])) for m in group]
        stats.append(form([{'gf': gf, 'ga': ga} for gf, ga in scores]))
    a, b = stats
    return (1, abs(a['points']-b['points']), abs((a['scored']-a['conceded'])-(b['scored']-b['conceded'])))


def record(stats):
    parts=[f"{stats['wins']} win"+('s' if stats['wins']!=1 else '')] if stats['wins'] else []
    if stats['draws']:parts.append(f"{stats['draws']} draw"+('s' if stats['draws']!=1 else ''))
    if stats['losses']:parts.append(f"{stats['losses']} "+('loss' if stats['losses']==1 else 'losses'))
    return ', '.join(parts[:-1])+' and '+parts[-1] if len(parts)>1 else parts[0]


def caption(m, home, away, extra=None):
    head = f"{m['home']} vs {m['away']} | {e.LEAGUES[m['league']][0]}\nKickoff: {e.aware(m['kickoff']):%d %b %Y, %H:%M} SAST"
    a, b = form(home['matches']), form(away['matches'])
    summary = (f"{m['home']} come into this with {record(a)} in their last five league matches, "
               f"scoring {a['scored']} and conceding {a['conceded']}. {m['away']} have {record(b)}, "
               f"with {b['scored']} goals for and {b['conceded']} against over their last five.")
    gap = a['points']-b['points']
    if abs(gap) >= 3:
        stronger, weaker = (m['home'], m['away']) if gap > 0 else (m['away'], m['home'])
        edge = f"{stronger} look stronger on recent league form; {weaker} have been the weaker side over those five games."
    else:
        edge = 'Recent league form is closely matched, so neither side has a clear overall form advantage.'
    if extra:
        h, v = (form(extra['venue_form'][side]) for side in ('home', 'away'))
        venue_gap=h['points']-v['points']
        if abs(venue_gap)>=3:
            venue_stronger,venue_weaker=(m['home'],m['away']) if venue_gap>0 else (m['away'],m['home'])
            if abs(gap)<3:
                edge=(f"Overall league form is close, but {venue_stronger} look stronger on the home/away records; "
                      f"{venue_weaker} have the weaker figures in that split.")
            elif gap*venue_gap<0:
                edge+=f" However, the home/away records favour {venue_stronger}, so the two form pictures point in different directions."
            else:
                edge+=' The home/away records back up that form advantage.'
        edge += (f" At home, {m['home']} have won {h['wins']} of their last five league games ({h['scored']} scored, {h['conceded']} conceded). "
                 f"Away from home, {m['away']} have won {v['wins']} of five ({v['scored']} scored, {v['conceded']} conceded).")
    goals = [sum(r['gf']+r['ga'] >= 2 for r in s['matches']) for s in (home, away)]
    trend = f"Two or more goals were scored in {goals[0]} of {m['home']}'s last five league games and {goals[1]} of {m['away']}'s."
    if extra:
        meetings = extra['h2h']; latest = meetings[0]
        period = 'the last two league seasons' if len(extra['seasons'])==2 else 'the current league season'
        trend += (f" Their latest league meeting finished {latest['home']} {latest['score'][0]}–{latest['score'][1]} {latest['away']} "
                  f"on {e.aware(latest['date']):%d %b %Y}; the H2H picture shows {len(meetings)} recent meeting{'s' if len(meetings)!=1 else ''} from {period}.")
    return head + '\n\n' + '\n\n'.join('• '+part for part in (summary, edge, trend)) + \
        '\n\nWhich market looks strongest to you in this match?\n\n' + e.hashtags(m['league'], (m['home'], m['away']))
