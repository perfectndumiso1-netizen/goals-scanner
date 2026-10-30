"""Compact public score text. Provider provenance remains in the private planning metadata."""
import re
from .content import norm

FLAGS = dict(zip(
    ['england','scotland','wales','northernireland','egypt','thailand','unitedarabemirates','uae','oman',
     'tanzania','jordan','romania','southafrica','spain','italy','germany','france','japan','brazil',
     'argentina','portugal','netherlands','belgium','turkey','usa','unitedstates','mexico','saudiarabia'],
    ['🇬🇧','🇬🇧','🇬🇧','🇬🇧','🇪🇬','🇹🇭','🇦🇪','🇦🇪','🇴🇲','🇹🇿','🇯🇴','🇷🇴','🇿🇦','🇪🇸','🇮🇹','🇩🇪','🇫🇷',
     '🇯🇵','🇧🇷','🇦🇷','🇵🇹','🇳🇱','🇧🇪','🇹🇷','🇺🇸','🇺🇸','🇲🇽','🇸🇦']))
LABELS = {
    'corners':'🚩 Corners', 'yellow_cards':'🟨 Yellow', 'red_cards':'🟥 Red',
    'shots_on_target':'🎯 On target', 'total_shots':'🥅 Shots', 'possession':'📊 Possession',
    'saves':'🧤 Saves', 'fouls':'⚠️ Fouls', 'offsides':'🚫 Offsides',
}


def pair(value, maximum=200):
    return (isinstance(value,(list,tuple)) and len(value)==2 and
            all(type(n) is int and 0<=n<=maximum for n in value))


def stats_lines(match):
    stats=match.get('statistics')
    if not isinstance(stats,dict) or not match.get('statistics_at'):return []
    cells=[]
    for key,label in LABELS.items():
        values=stats.get(key)
        if key=='possession':
            if (not isinstance(values,(list,tuple)) or len(values)!=2 or
                any(type(n) not in (int,float) or not 0<=n<=100 for n in values) or abs(sum(values)-100)>1):continue
        elif not pair(values):continue
        suffix='%' if key=='possession' else ''
        cells.append(f'{label} {values[0]:g}{suffix}–{values[1]:g}{suffix}')
    return ['  '.join(cells[i:i+2]) for i in range(0,len(cells),2)]


def match_line(match):
    status=match['status']
    if status in ('NS','PST','CANC'):
        state={'NS':'Scheduled','PST':'Postponed','CANC':'Cancelled'}[status]
        return f"📅 {match['home']} v {match['away']} · {state}"
    if status in ('1H','2H','ET'):
        elapsed=match.get('elapsed')
        minute=f"{elapsed}′" if type(elapsed) is int and 0<=elapsed<=180 else {'1H':'1H','2H':'2H','ET':'ET'}[status]
        extra=match.get('added_time')
        if elapsed in (45,90,105,120) and type(extra) is int and 0<extra<=30:minute=f'{elapsed}+{extra}′'
        state=f'🔴 {minute}' + (' ET' if status=='ET' else '')
    else:
        state={'HT':'⏸ HT','BT':'⏸ ET break','FT':'🏁 FT','AET':'🏁 AET','PEN':'🏁 PEN',
               'P':'⚽ Penalties','ABD':'Abandoned','SUSP':'Suspended','INT':'Interrupted'}.get(status,status)
    text=f"{state} | {match['home']} {match['home_goals']}–{match['away_goals']} {match['away']}"
    if status=='PEN' and pair(match.get('penalties')):
        text+=f" (pens {match['penalties'][0]}–{match['penalties'][1]})"
    return text


def half_line(match):
    half=match.get('halftime')
    if not pair(half) or match['status'] in ('NS','1H','PST','CANC'):return None
    goals=[match.get('home_goals'),match.get('away_goals')]
    if not pair(goals) or any(h>g for h,g in zip(half,goals)):return None
    line=f'↳ 1st half: {half[0]}–{half[1]}'
    # Extra-time/shootout totals are never labelled second-half goals.
    full=goals if match['status'] in ('2H','FT') else match.get('fulltime')
    if match['status']!='HT' and pair(full) and all(h<=f<=g for h,f,g in zip(half,full,goals)):
        line+=f' | 2nd half: {full[0]-half[0]}–{full[1]-half[1]}'
    return line


def hashtags(matches):
    tags=[]
    seen=set()
    for match in matches:
        country=match.get('country',''); league=match.get('competition','')
        # Country-qualified tags avoid conflating the many different Premier/Division leagues.
        aliases={('england','premierleague'):'PremierLeague',('spain','laliga'):'LaLiga',
                 ('italy','seriea'):'SerieA',('germany','bundesliga'):'Bundesliga',
                 ('france','ligue1'):'Ligue1',('world','uefachampionsleague'):'ChampionsLeague'}
        words=league if norm(country)=='world' else country+' '+league
        tag=aliases.get((norm(country),norm(league))) or ''.join(w[:1].upper()+w[1:] for w in re.findall(r'[A-Za-z0-9]+',words))
        if not norm(league) or not tag or len(tag)>60 or tag.casefold() in seen:continue
        seen.add(tag.casefold());tags.append('#'+tag)
        if len(tags)==7:break
    # Relevant keywords, not a claim of verified search-volume rankings.
    for keyword in ('LiveScores','Football','FootballStats'):
        if keyword.casefold() not in seen:
            tags.append('#'+keyword);seen.add(keyword.casefold())
    return tags[:10]


def caption(matches):
    lines=['Live Matches SAST','']
    groups={}
    for match in matches:
        key=(match.get('country',''),match.get('competition',''))
        groups.setdefault(key,[]).append(match)
    for (country,competition),rows in groups.items():
        lines.append(f"{FLAGS.get(norm(country),'🌍')} {country} ◆ {competition}")
        for match in rows:
            lines.append(match_line(match))
            halves=half_line(match)
            if halves:lines.append(halves)
            lines.extend(stats_lines(match))
            lines.append('')
    lines.append(' '.join(hashtags(matches)))
    return '\n'.join(lines)
