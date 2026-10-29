"""Evidence-first editorial builders: no LLM service, model estimates or invented facts."""
from __future__ import annotations
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

SAST = ZoneInfo('Africa/Johannesburg')
SOURCE = 'PlayReport fixture archive (Livescore / football-data.co.uk)'


def local(value):
    value = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return value.replace(tzinfo=SAST) if value.tzinfo is None else value.astimezone(SAST)


def norm(value):
    import unicodedata
    value = unicodedata.normalize('NFKD', str(value)).casefold()
    return re.sub(r'[^a-z0-9]', '', ''.join(c for c in value if not unicodedata.combining(c)))


def load(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default


def candidate(kind, key, topic, caption, **kwargs):
    return dict(kind=kind, key=key, topic=topic, caption=caption,
                caption_hash=hashlib.sha256(caption.encode()).hexdigest(), **kwargs)


def sample(rows, now, venue=None):
    """Exactly five distinct scored competitive records, never reinterpret rate/xG columns as results."""
    if not isinstance(rows, list) or len(rows) < 5:
        return None
    seen, matches = set(), []
    for row in rows:
        try:
            date = local(row['date'])
            gf, ga = row['gf'], row['ga']
            if not isinstance(row['league'],str) or not isinstance(row['opp'],str):return None
            league, opponent = row['league'].strip(), row['opp'].strip()
            if isinstance(gf, bool) or isinstance(ga, bool) or int(gf) != float(gf) or int(ga) != float(ga) or min(int(gf), int(ga)) < 0:
                return None
            if not league or not opponent or re.search(r'friendl(?:y|ies)|testimonial|exhibition', league, re.I):
                return None
            if date.date() >= now.date() or now - date > timedelta(days=240):
                return None  # date-only results from today cannot be verified as completed before this post.
            if row.get('venue') not in ('H', 'A') or (venue and row['venue'] != venue):
                return None
            key = (date.date(), norm(opponent), row['venue'])
            if key in seen:
                return None
            seen.add(key)
            matches.append(dict(date=date.date().isoformat(), gf=int(gf), ga=int(ga), league=league,
                                opponent=opponent, venue=row['venue']))
        except (KeyError, ValueError, TypeError, OverflowError):
            return None
    matches.sort(key=lambda r: r['date'], reverse=True)
    matches = matches[:5]
    if now - local(matches[0]['date']) > timedelta(days=60):
        return None
    form = ''.join('W' if r['gf'] > r['ga'] else 'L' if r['gf'] < r['ga'] else 'D' for r in matches)
    leagues = sorted({r['league'] for r in matches})
    return dict(n=5, form=form, scored=sum(r['gf'] for r in matches), conceded=sum(r['ga'] for r in matches),
                scored_in=sum(r['gf'] > 0 for r in matches), conceded_in=sum(r['ga'] > 0 for r in matches),
                wins=form.count('W'), start=matches[-1]['date'], end=matches[0]['date'],
                scope=leagues[0] if len(leagues) == 1 else 'mixed competitive competitions', matches=matches)


def h2h_rows(detail, now):
    found = {}
    pair = {norm(detail.get('home')), norm(detail.get('away'))}
    for row in detail.get('h2h') or []:
        try:
            date = local(row['date'])
            hg, ag = row['hg'], row['ag']
            if not row.get('league') or re.search(r'friendl(?:y|ies)|testimonial|exhibition',row['league'],re.I):
                continue
            if {norm(row['home']), norm(row['away'])} != pair or date.date() >= now.date() or now-date > timedelta(days=1100):
                continue
            if isinstance(hg, bool) or isinstance(ag, bool) or int(hg) != float(hg) or int(ag) != float(ag) or min(int(hg), int(ag)) < 0:
                continue
            key = (date.date(), norm(row['home']), norm(row['away']))
            found[key] = dict(date=date.date().isoformat(), hg=int(hg), ag=int(ag), home=row['home'], away=row['away'])
        except (KeyError, ValueError, TypeError):
            continue
    return sorted(found.values(), key=lambda r: r['date'], reverse=True)[:5]


def verified_fixtures(root, now, config):
    """Read-only view of the scanner publication; stale/unverifiable source means no factual post."""
    root = Path(root)
    payload = load(root/'latest.json', {})
    try:
        generated = local(payload['meta']['generated'])
        if not timedelta(0) <= now-generated <= timedelta(hours=config['max_source_age_hours']):
            return []
    except (KeyError, ValueError, TypeError):
        return []
    out = []
    for fixture in payload.get('fixtures', []):
        try:
            kickoff = local(fixture['kickoff'])
            if not now < kickoff < now+timedelta(days=7) or fixture.get('time_known') is not True:
                continue
            if any(not isinstance(fixture.get(k),str) or not fixture[k].strip() for k in ('id','home','away','country','competition')) or norm(fixture['home'])==norm(fixture['away']):
                continue
            key = fixture.get('d')
            if not re.fullmatch(r'[a-f0-9]{12}', str(key)):
                continue
            detail = load(root/'fx'/f'{key}.json', {})
            enabled=config.get('editorial_competitions',[])
            if enabled and not any(norm(fixture.get('country'))==norm(c['country']) and norm(fixture.get('league')) in {norm(n) for n in c['names']} for c in enabled):
                continue
            if detail.get('id') != fixture.get('id') or local(detail['kickoff']) != kickoff:
                continue
            if any(norm(detail.get(s)) != norm(fixture.get(s)) for s in ('home','away')):
                continue
            if local(detail['generated']).date() != now.date() or not timedelta(0)<=now-local(detail['generated'])<=timedelta(hours=config['max_source_age_hours']):
                continue
            teams = detail.get('teams') or {}
            home = sample((teams.get('home') or {}).get('last5'), now)
            away = sample((teams.get('away') or {}).get('last5'), now)
            if not home or not away:
                continue
            hv = sample((teams.get('home') or {}).get('venue_last5'), now, 'H')
            av = sample((teams.get('away') or {}).get('venue_last5'), now, 'A')
            angle = max(home['scored_in'], away['scored_in'], home['conceded_in'], away['conceded_in'])
            out.append(dict(fixture=fixture, home=home, away=away, hv=hv, av=av,
                            h2h=h2h_rows(detail, now), interest=angle, generated=generated.isoformat()))
        except (KeyError, ValueError, TypeError):
            continue
    return sorted(out, key=lambda x: (-x['interest'], x['fixture']['kickoff'], x['fixture']['id']))


def story(item):
    f, h, a = item['fixture'], item['home'], item['away']
    angles = []
    for side, stats in ((f['home'], h), (f['away'], a)):
        if stats['scored_in'] >= 4:
            angles.append(f"{side} scored in {stats['scored_in']} of those five games.")
        elif stats['conceded_in'] >= 4:
            angles.append(f"{side} conceded in {stats['conceded_in']} of those five games.")
    return angles[:2]


def sample_line(name, stats):
    return (f"{name}: {stats['form']} (latest first), {stats['scored']} scored / {stats['conceded']} conceded. "
            f"Last five recorded competitive games, {stats['start']}–{stats['end']} · {stats['scope']}.")


def match_card(items, now):
    for item in items:
        if not item['hv'] or not item['av'] or not story(item):
            continue
        f = item['fixture']; ko = local(f['kickoff'])
        angles = story(item)
        lines = [angles[0].replace('of those five games','of their last five recorded competitive games'),'',
                 f"{f['home']} vs {f['away']}",f"{f['competition']} · {ko:%a %d %b, %H:%M} SAST"]
        if len(angles)>1:lines+=['',angles[1].replace('of those five games','of their last five recorded competitive games')]
        meetings=item['h2h']
        if len(meetings)>=3:
            total=sum(m['hg']+m['ag'] for m in meetings)
            lines+=['',f"Their last {len(meetings)} recorded competitive meetings produced {total} goals ({meetings[-1]['date']}–{meetings[0]['date']})."]
        lines+=['','Who do you fancy here?']
        rows = [f"{f[s]}: {item[s]['form']} | GF {item[s]['scored']} / GA {item[s]['conceded']}" for s in ('home','away')]
        rows += [f"Home sample: {item['hv']['scored']} GF / {item['hv']['conceded']} GA",
                 f"Away sample: {item['av']['scored']} GF / {item['av']['conceded']} GA"]
        return candidate('card', f"card:{f['id']}", f"fixture:{f['id']}", '\n'.join(lines),
            graphic=dict(title='MATCH IN NUMBERS', subtitle=f"{f['home']} vs {f['away']}",
                         context=f"{f['competition']} | {ko:%d %b %H:%M} SAST", rows=rows,
                         notes=['Five recorded competitive games per sample. Latest result first.',
                             f"Recent home: {item['home']['start']}–{item['home']['end']} · {item['home']['scope']}",
                             f"Recent away: {item['away']['start']}–{item['away']['end']} · {item['away']['scope']}",
                             f"At home: {item['hv']['start']}–{item['hv']['end']} · {item['hv']['scope']}",
                             f"Away: {item['av']['start']}–{item['av']['end']} · {item['av']['scope']}"]),
            fixture_ids=[f['id']], evidence=item,source=SOURCE)
    return None


def community(items, book, now, history):
    topics = [p.get('topic') for p in history if p.get('kind') == 'community']
    day = now.date().isoformat()
    rotation = ['discussion','form','preview','review','fact','debate','development']
    recent_modes = [p.get('mode') for p in history if p.get('kind') == 'community'][-2:]
    start = now.date().toordinal() % len(rotation)
    modes = rotation[start:]+rotation[:start]
    for mode in modes:
        if mode in recent_modes:
            continue
        if mode == 'review':
            yesterday = (now.date()-timedelta(days=1)).isoformat()
            rows = [r for r in book if r.get('match_date') == yesterday and r.get('kind') == 'advisor']
            keys = [(r.get('country'),r.get('home'),r.get('away'),r.get('sel')) for r in rows]
            if not rows or len(keys) != len(set(keys)):
                continue
            wins = sum(r.get('status')=='hit' for r in rows); losses=sum(r.get('status')=='miss' for r in rows)
            if not wins+losses:
                continue
            pending=sum(r.get('status') not in ('hit','miss','void') for r in rows); void=sum(r.get('status')=='void' for r in rows)
            caption=(f"How yesterday’s picks finished.\n{yesterday}: {wins} won, {losses} lost; {pending} pending and {void} void. "
                f"{100*wins/(wins+losses):.1f}% across {wins+losses} settled selections, not matches.\n"
                "That’s the original shortlist, not a list rebuilt after the results. Pending and void picks aren’t in that percentage.\n"
                "Back to the numbers before the next round.\n18+ · Past results don’t guarantee the next result.")
            return candidate('community',f'community:{day}',f'review:{yesterday}',caption,mode=mode,source='frozen Advisor ledger',
                graphic=dict(title='YESTERDAY’S PICKS',subtitle=yesterday,context='The original selections, wins and losses included',
                    rows=[f'{wins} won · {losses} lost',f'{pending} pending · {void} void',f'{100*wins/(wins+losses):.1f}% from {wins+losses} settled picks'],
                    notes=['Pending and void picks are excluded from the hit rate.','18+ · Past results don’t guarantee the next result.']))
        for item in items:
            f=item['fixture']; topic=f"{mode}:{f['id']}"
            if topic in topics or not story(item):
                continue
            ko=local(f['kickoff'])
            questions={
                'discussion':'Who would you back to get the better of this one?',
                'form':'Would you trust the attack or the defence here?',
                'preview':'What’s your read on this one?',
                'fact':'A useful detail before kick-off. Does it change your view?',
                'debate':'Does the recent form tell the whole story here?',
                'development':'Which side looks more likely to turn things around?'}
            opening=story(item)[0].replace('of those five games','of their last five recorded competitive games')
            caption='\n'.join([opening,'',f"{f['home']} vs {f['away']} · {f['competition']}",
                f"{ko:%a %d %b, %H:%M} SAST",'',questions[mode]])
            return candidate('community',f'community:{day}',topic,caption,mode=mode,fixture_ids=[f['id']],evidence=item,source=SOURCE,
                graphic=dict(title='BEFORE KICK-OFF',subtitle=f"{f['home']} vs {f['away']}",
                    context=f"{f['competition']} · {ko:%d %b %H:%M} SAST",
                    rows=[f"{f[side]}: {item[side]['form']} | {item[side]['scored']} scored · {item[side]['conceded']} conceded" for side in ('home','away')],
                    notes=story(item)+['Five recorded competitive games each. Form reads newest first.',
                        f"Home: {item['home']['start']}–{item['home']['end']} · {item['home']['scope']}",f"Away: {item['away']['start']}–{item['away']['end']} · {item['away']['scope']}"]))
    return None


def weekly(items, root, now):
    fixtures = {}
    for offset in range(8):
        day=(now.date()+timedelta(days=offset)).isoformat()
        data=load(Path(root)/'days'/f'{day}.json',{})
        try:
            if not timedelta(0) <= now-local(data['updated']) <= timedelta(hours=24):
                continue
        except (ValueError, TypeError, KeyError):
            continue
        for f in data.get('fixtures',[]):
            try:
                if any(not isinstance(f.get(k),str) or not f[k].strip() for k in ('id','home','away','country','competition')) or f.get('time_known') is False:
                    continue
                if now < local(f['kickoff']) < now+timedelta(days=7) and not f.get('score'):
                    fixtures[f['id']]=f
            except (KeyError,ValueError,TypeError):
                continue
    for item in items:
        fixtures[item['fixture']['id']]=item['fixture']
    # The archive can contain a rescheduled fixture under two different day IDs.
    # Do not choose a date arbitrarily or describe that as a demanding fixture list.
    by_pair={}
    for fx in fixtures.values():
        pair=(fx.get('country'),norm(fx.get('competition','')),frozenset((norm(fx.get('home')),norm(fx.get('away')))))
        by_pair.setdefault(pair,set()).add(fx['kickoff'])
    uncertain_teams={(country,team) for (country,_competition,pair),kickoffs in by_pair.items() if len(kickoffs)>1 for team in pair}
    teams={}
    for item in items:
        f=item['fixture']
        for side in ('home','away'):
            s=item[side]
            if max(s['scored_in'],s['conceded_in']) < 4:
                continue
            key=(f['country'],norm(f[side]))
            if key in uncertain_teams:
                continue
            upcoming=[fx for fx in fixtures.values() if fx.get('country')==f['country'] and norm(f[side]) in (norm(fx.get('home')),norm(fx.get('away')))]
            upcoming.sort(key=lambda fx:fx['kickoff'])
            teams[key]=dict(name=f[side],competition=f['competition'],stats=s,fixtures=upcoming,
                            interest=max(s['scored_in'],s['conceded_in'])+min(len(upcoming),3))
    chosen=sorted(teams.values(),key=lambda t:(-t['interest'],t['name']))[:5]
    if len(chosen)<3:
        return None
    week=now.strftime('%G-W%V')
    lines=['A few teams worth keeping an eye on',f"Next seven days: {now:%d %b}–{now+timedelta(days=7):%d %b %Y}", '']
    sections=[]
    for team in chosen:
        s=team['stats']
        angle=f"Scored in {s['scored_in']}/5" if s['scored_in']>=4 else f"Conceded in {s['conceded_in']}/5"
        lines += [f"{team['name']} · {team['competition']}",sample_line(team['name'],s),
                  f"{angle}. Here’s what’s next for them:"]
        for fx in team['fixtures']:
            ko=local(fx['kickoff'])
            lines.append(f"{ko:%a %d %b %H:%M} SAST: {fx['home']} vs {fx['away']} · {fx['competition']}")
        lines.append('')
        first=team['fixtures'][0];ko=local(first['kickoff'])
        sections.append(f"{team['name']} | {s['form']} | {angle}\nNext: {ko:%d %b %H:%M} SAST · {first['home']} vs {first['away']}")
    lines += ['Anyone else on your watchlist this week?', 'Kick-off times can change.']
    return candidate('weekly',f'weekly:{week}',f'weekly:{week}','\n'.join(lines),
        graphic=dict(title='TEAMS TO WATCH THIS WEEK',subtitle=f"{now:%d %b} — {now+timedelta(days=7):%d %b %Y}",
                     context='Next seven days · kickoff times SAST',rows=sections,
                     notes=['Each form sample is 5 recorded competitive matches; dates and competitions in caption.']),teams=chosen,
        fixture_ids=sorted({f['id'] for t in chosen for f in t['fixtures']}),source=SOURCE)
