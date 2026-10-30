"""Evidence-first editorial builders: no LLM service, model estimates or invented facts."""
from __future__ import annotations
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

SAST = ZoneInfo('Africa/Johannesburg')
SOURCE = 'Mr 2 Odds fixture archive (Livescore / football-data.co.uk)'


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
            angles.append(f"{side} scored in {stats['scored_in']}/5 of that sample.")
        elif stats['conceded_in'] >= 4:
            angles.append(f"{side} conceded in {stats['conceded_in']}/5 of that sample.")
    return angles[:2]


def sample_line(name, stats):
    return (f"{name}: {stats['form']} (newest first), {stats['scored']} scored / {stats['conceded']} conceded. "
            f"Last 5 recorded competitive matches: {stats['start']}–{stats['end']} · {stats['scope']}.")


def match_card(items, now):
    for item in items:
        if not item['hv'] or not item['av'] or not story(item):
            continue
        f = item['fixture']; ko = local(f['kickoff'])
        lines = ['MR 2 ODDS ZA — INTERESTING STATS MATCH CARD', f"{f['home']} vs {f['away']}",
                 f"{f['competition']} · {ko:%a %d %b %Y, %H:%M} SAST", '',
                 sample_line(f['home'],item['home']), sample_line(f['away'],item['away']), '',
                 sample_line(f"{f['home']} at home",item['hv']), sample_line(f"{f['away']} away",item['av'])]
        meetings = item['h2h']
        if len(meetings) >= 3:
            total = sum(m['hg']+m['ag'] for m in meetings)
            lines += ['', f"H2H context: {total} goals across {len(meetings)} recorded meetings ({meetings[-1]['date']}–{meetings[0]['date']}). Historical context, not a forecast."]
        angles = story(item)
        lines += ['', *angles, 'That recent scoring pattern makes this one worth watching; it does not predict the result.',
                  '', 'Which side’s recent pattern will carry into this match?', '', f'Source: {SOURCE}. Checked {now:%d %b %H:%M} SAST.']
        rows = [f"{f[s]}: {item[s]['form']} | GF {item[s]['scored']} / GA {item[s]['conceded']}" for s in ('home','away')]
        rows += [f"Home sample: {item['hv']['scored']} GF / {item['hv']['conceded']} GA",
                 f"Away sample: {item['av']['scored']} GF / {item['av']['conceded']} GA"]
        return candidate('card', f"card:{f['id']}", f"fixture:{f['id']}", '\n'.join(lines),
            graphic=dict(title='INTERESTING STATS MATCH CARD', subtitle=f"{f['home']} vs {f['away']}",
                         context=f"{f['competition']} | {ko:%d %b %H:%M} SAST", rows=rows,
                         notes=angles+[f"Form samples: 5 recorded competitive matches each. Newest first.",
                             f"Home {item['home']['start']}–{item['home']['end']} | Away {item['away']['start']}–{item['away']['end']}"]),
            fixture_ids=[f['id']], evidence=item)
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
            caption=(f"MR 2 ODDS ZA — THE HONEST REVIEW\n{yesterday}: {wins} won, {losses} lost; {pending} pending and {void} void. "
                f"{100*wins/(wins+losses):.1f}% across {wins+losses} settled selections, not matches.\n"
                "First-published Advisor selections; no backfill. We report losses too. Pending/void excluded from hit rate.\n"
                "Which part of a prediction review helps you most: the reasoning or the result?\n18+ · Past results do not guarantee future outcomes.")
            return candidate('community',f'community:{day}',f'review:{yesterday}',caption,mode=mode,source='frozen Advisor ledger')
        for item in items:
            f=item['fixture']; topic=f"{mode}:{f['id']}"
            if topic in topics or not story(item):
                continue
            ko=local(f['kickoff'])
            questions={
                'discussion':'Which side’s recent form gives you more confidence, and why?',
                'form':'When assessing form, would you put more weight on scoring regularly or conceding less?',
                'preview':'What would you watch first: pressing early or keeping the game compact?',
                'fact':'Does that scoring record change how you see this match?',
                'debate':'Would you favour a patient start or an aggressive opening here?',
                'development':'Which of these recent patterns is more likely to change next?'}
            caption='\n'.join([f"MR 2 ODDS ZA — {mode.upper()}",f"{f['home']} vs {f['away']} · {f['competition']}",
                f"{ko:%a %d %b, %H:%M} SAST",'',sample_line(f['home'],item['home']),sample_line(f['away'],item['away']),
                '',*story(item),'',questions[mode], '',f'Source: {SOURCE}. Observed results, not model estimates or guaranteed outcomes.'])
            return candidate('community',f'community:{day}',topic,caption,mode=mode,fixture_ids=[f['id']])
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
    lines=['MR 2 ODDS ZA — TEAMS TO WATCH THIS WEEK',f"Verified archive fixtures · next 7 days: {now:%d %b}–{now+timedelta(days=7):%d %b %Y}", '']
    sections=[]
    for team in chosen:
        s=team['stats']
        angle=f"Scored in {s['scored_in']}/5" if s['scored_in']>=4 else f"Conceded in {s['conceded_in']}/5"
        lines += [f"{team['name']} · {team['competition']}",sample_line(team['name'],s),
                  f"{angle}; that makes the upcoming schedule worth following, not a guaranteed prediction."]
        for fx in team['fixtures']:
            ko=local(fx['kickoff'])
            lines.append(f"{ko:%a %d %b %H:%M} SAST: {fx['home']} vs {fx['away']} · {fx['competition']}")
        lines.append('')
        first=team['fixtures'][0];ko=local(first['kickoff'])
        sections.append(f"{team['name']} | {s['form']} | {angle}\nNext: {ko:%d %b %H:%M} SAST · {first['home']} vs {first['away']}")
    lines += ['Which team will you be watching most closely this week?',f'Source: {SOURCE}. Dates/times may change; analysis, not guaranteed predictions.']
    return candidate('weekly',f'weekly:{week}',f'weekly:{week}','\n'.join(lines),
        graphic=dict(title='TEAMS TO WATCH THIS WEEK',subtitle=f"{now:%d %b} — {now+timedelta(days=7):%d %b %Y}",
                     context='Next seven days · kickoff times SAST',rows=sections,
                     notes=['Each form sample is 5 recorded competitive matches; dates and competitions in caption.']),teams=chosen,
        fixture_ids=sorted({f['id'] for t in chosen for f in t['fixtures']}))


def morning_results(root, now, config):
    """Yesterday's exact filmed selections, including losses/void/unsettled, once per day.

    Never substitute the current shortlist or a winning-only sample. The advisor ledger
    supplies verified settlement; the filmed history supplies the original market/price.
    """
    import advisor_tracking
    root = Path(root)
    source = load(root/'latest.json', {})
    try:
        generated = local(source['meta']['generated'])
        if not timedelta(minutes=-5) <= now-generated <= timedelta(hours=config['max_source_age_hours']):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    day = (now.date()-timedelta(days=1)).isoformat()
    history = (load(root/'telegram_state.json', {}) or {}).get('briefing_history', {}).get(day, [])
    unique = {}
    for p in history:
        if not isinstance(p, dict) or str(p.get('kickoff', ''))[:10] != day:
            continue
        if not all(isinstance(p.get(k), str) and p[k].strip() for k in ('home','away','sel')):
            continue
        key = (p['home'], p['away'], p['sel'], p['kickoff'])
        unique.setdefault(key, p)
    if not unique or len(unique)>24:
        return None
    filmed = list(unique.values())
    settled = advisor_tracking.video_results(load(root.parent/'advisor_ledger.json', []), filmed)
    resolved = {(p['home'],p['away'],p['sel'],p['kickoff']):p for p in settled}
    won = sum(p['result']=='hit' for p in settled)
    lost = sum(p['result']=='miss' for p in settled)
    void = sum(p['result']=='void' for p in settled)
    lines = ['MR 2 ODDS — YESTERDAY’S VIDEO RESULTS', day,
             f'Latest app publication: {generated:%d %b %H:%M} SAST',
             f'{won} won · {lost} lost · {void} void · {len(filmed)-len(settled)} not yet settled',
             f'All {len(filmed)} filmed selections across the day’s editions; no winning-only selection.', '']
    for key, p in unique.items():
        r = resolved.get(key)
        label = p.get('label') or p['sel']
        status = {'hit':'WON','miss':'LOST','void':'VOID'}.get((r or {}).get('result'), 'NOT YET SETTLED')
        score = ''
        if r and r.get('score') not in (None, '', '-'):
            value=str(r['score'])
            score=f" · FT goals {value}" if re.fullmatch(r"\d+\s*[-–:]\s*\d+",value) else f" · recorded {value}"
        price = ''
        try:
            odds = float(p['odds'])
            if 1 < odds < 1000:price=f' @ {odds:.2f}'
        except (KeyError, TypeError, ValueError):pass
        lines += [f"{p['home']} v {p['away']}", f'{label}{price} · {status}{score}', '']
    lines += ['Original filmed selections and prices; verified settlement from the app ledger.',
              'Unsettled picks are excluded from win/loss totals. Past results do not guarantee future outcomes.']
    return candidate('results', f'video-results:{day}', f'video-results:{day}', '\n'.join(lines),
                     result_date=day, fixture_ids=[])
