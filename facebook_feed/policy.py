"""Shared anti-spam policy, deterministic reservations and score-centre planning."""
from datetime import timedelta
import hashlib
import json
from .content import candidate, local, norm


def history(state, now, days=28):
    cutoff=now-timedelta(days=days)
    posts=[p for p in state.get('posts',[]) if local(p['at'])>=cutoff or p.get('status') in ('reserved','unknown')]
    # Old score payloads aren't needed for dedupe; retain immutable reservation keys/hashes.
    for p in posts:
        if p.get('kind')=='live' and local(p['at']).date()<now.date() and p.get('status') in ('published','simulated'):p.pop('snapshot',None)
    return posts


def in_quiet_window(now, config):
    current=now.strftime('%H:%M')
    return any(start<=current<=end for start,end in config['reel_quiet_windows'])


def allowed(post, state, now, config):
    posts=history(state,now,config['topic_history_days'])
    counted=[p for p in posts if p.get('status') not in ('rejected','cancelled')]
    if any(p['key']==post['key'] for p in counted):
        return False,'duplicate or unresolved previous attempt'
    if any(p.get('topic')==post.get('topic') for p in counted):
        return False,'topic recently covered'
    if any(p.get('caption_hash')==post['caption_hash'] for p in counted):
        return False,'caption repeated'
    today=[p for p in counted if local(p['at']).date()==now.date() and p.get('operation')!='edit']
    live=post['kind'] in ('live','roundup')
    if post['kind']=='community' and any(p['kind']=='community' for p in today):
        return False,'daily community cap'
    if post['kind']=='weekly' and any(p['kind']=='weekly' and local(p['at']).isocalendar()[:2]==now.isocalendar()[:2] for p in counted):
        return False,'weekly feature cap'
    if post.get('operation')=='edit':
        if not config['live']['edit_existing']:
            return False,'editing has not been activated/verified'
        previous=[p for p in counted if p.get('post_id')==post['target_id'] or p.get('target_id')==post['target_id']]
        if previous and now-max(local(p['at']) for p in previous)<timedelta(minutes=config['edit_cooldown_minutes']):
            return False,'edit cooldown'
        return True,'eligible edit'
    limit=config['live']['max_posts_per_day'] if live else config['max_ordinary_posts_per_day']
    if sum((p['kind'] in ('live','roundup'))==live for p in today)>=limit:
        return False,'daily post cap'
    if not live and in_quiet_window(now,config):
        return False,'Reel quiet window'
    interval=config['live_post_cooldown_minutes'] if live else config['min_feed_interval_minutes']
    if counted and now-max(local(p['at']) for p in counted)<timedelta(minutes=interval):
        return False,'feed cooldown'
    if post['kind']=='card':
        iso=now.isocalendar()[:2]
        if sum(p['kind']=='card' and local(p['at']).isocalendar()[:2]==iso for p in counted)>=3:
            return False,'weekly card cap'
    return True,'eligible'


def reserve(post, state, now):
    entry={k:v for k,v in post.items() if k in ('kind','key','topic','mode','caption_hash','fixture_ids','operation','target_id','snapshot')}
    entry.update(at=now.isoformat(),status='reserved')
    state.setdefault('posts',[]).append(entry)
    return entry


def selected_matches(matches, config, stories=()):
    settings=config['live']
    if config.get('score_source')=='app' or settings.get('app_coverage_only'):
        # Reader already verifies exact app IDs, clubs, kickoff and HTTP freshness. No editorial
        # competition/rivalry filter may expand or silently narrow the app's coverage universe.
        active=[m for m in matches if m.get('fixture_id') and m['status'] not in ('NS',)]
        return sorted(active,key=lambda m:(m['status'] in ('FT','AET','PEN'),m['kickoff'],str(m['id'])))[:settings['max_matches']]
    manual={str(x) for x in settings['fixture_ids']}
    featured={norm(t) for t in settings['featured_teams']}
    story_pairs={frozenset((norm(f['home']),norm(f['away']))) for f in stories}
    rivalries=[frozenset(map(norm,pair)) for pair in settings['rivalries']]
    found=[]
    for m in matches:
        covered=any(norm(m['country'])==norm(c['country']) and norm(m['competition']) in {norm(n) for n in c['names']}
                    for c in settings['competitions'])
        if not covered:
            continue
        pair=frozenset((norm(m['home']),norm(m['away'])))
        score=(10 if str(m['id']) in manual else 0)+(4 if pair in rivalries else 0)
        score+=2*len(pair&featured)+(2 if pair in story_pairs else 0)
        if m.get('round') and any(x in m['round'].casefold() for x in ('final','quarter','semi','play-off')):
            score+=2
        if score>=settings['selection_min_score']:
            found.append((score,m))
    return [m for _,m in sorted(found,key=lambda x:(-x[0],x[1]['kickoff'],str(x[1]['id'])))[:settings['max_matches']]]


def score_text(m):
    status={'1H':'LIVE 1H','2H':'LIVE 2H','HT':'HT','ET':'LIVE ET','BT':'ET break','P':'Penalties',
            'FT':'FT','AET':'FT after extra time','PEN':'FT after penalties','PST':'Postponed',
            'CANC':'Cancelled','ABD':'Abandoned','SUSP':'Suspended','INT':'Interrupted','NS':'Scheduled'}.get(m['status'])
    if status is None:
        return None
    if m['status'] in ('NS','PST','CANC'):
        return f"📅 {m['home']} vs {m['away']} · {status} · {local(m['kickoff']):%H:%M} SAST"
    if m.get('home_goals') is None or m.get('away_goals') is None:
        return None
    icon='🏁' if m['status'] in ('FT','AET','PEN') else '⏸️' if m['status'] in ('HT','BT','SUSP','INT') else '🔴'
    text=f"{icon} {m['home']} {m['home_goals']}–{m['away_goals']} {m['away']} · {status}"
    penalties=m.get('penalties')
    if m['status']=='PEN' and penalties:
        text+=f" (penalties {penalties[0]}–{penalties[1]})"
    return text


def significant(old, new):
    if old is None:
        return new['status'] not in ('NS',)
    if new['status']!=old['status']:
        return True
    if new.get('penalties')!=old.get('penalties'):
        return True
    a,b=new.get('home_goals'),new.get('away_goals')
    c,d=old.get('home_goals'),old.get('away_goals')
    if any(v is None for v in (a,b,c,d)):
        return False
    return abs(a-c)+abs(b-d)>=2 or ((a-b)*(c-d)<0)


def score_post(matches,state,now,config,roundup=False):
    matches=[m for m in matches if score_text(m) and (local(m['kickoff']).date()==now.date() or config.get('score_source')=='app' and now-timedelta(hours=12)<=local(m['kickoff'])<=now)]
    centres=[p for p in state.get('posts',[]) if p['kind']=='live' and p.get('status')=='published'
             and local(p['at']).date()==now.date() and p.get('post_id')]
    centre=centres[-1] if centres else None
    previous={str(m['id']):m for m in (centre or {}).get('snapshot',[])
              if not config['live'].get('app_coverage_only') or m.get('source')==config.get('score_source')}
    # New combined updates also compare the last NEW live post when editing is disabled.
    if roundup:
        completed=[m for m in matches if m['status'] in ('FT','AET','PEN')]
        covered={str(m['id']) for p in state.get('posts',[]) if p.get('status')=='published'
                 for m in p.get('snapshot',[]) if m['status'] in ('FT','AET','PEN')}
        matches=[m for m in completed if str(m['id']) not in covered]
        if len(matches)<2:
            return None
    elif not any((significant(previous.get(str(m['id'])),m) or (config.get('score_source')=='app' or config['live'].get('app_coverage_only')) and previous.get(str(m['id'])) and any(previous[str(m['id'])].get(k)!=m.get(k) for k in ('status','home_goals','away_goals'))) for m in matches):
        return None
    if not matches:
        return None
    snapshot=[{k:m.get(k) for k in ('id','home','away','competition','country','kickoff','status','home_goals','away_goals','penalties','source','statistics','statistics_at')} for m in matches]
    for m in snapshot:
        if m['source'] is None:m['source']=config.get('score_source','api-football')
    fingerprint=hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest()[:20]
    lines=['⚽ MR 2 ODDS — '+('RESULTS ROUNDUP' if roundup else 'SELECTED LIVE SCORE CENTRE'),
           f"Latest reported scores · checked {now:%d %b %H:%M} SAST", 'Periodic updates, not a minute-by-minute service.', '']
    for m in matches:
        lines += [score_text(m),m['competition']]
        lines += statistics_lines(m)
        lines += ['']
    lines += ['Which result stands out to you?' if roundup else 'Which of these matches are you following?',
              '', 'Source: API-FOOTBALL / API-SPORTS. Statuses and scores may be corrected by the provider.']
    kind='roundup' if roundup else 'live'
    post=candidate(kind,f'{kind}:{now.date()}:{fingerprint}',f'{kind}:{now.date()}:{fingerprint}','\n'.join(lines),snapshot=snapshot)
    if centre and not roundup and config['live']['edit_existing']:
        post.update(operation='edit',target_id=centre['post_id'])
    return post


# Fixed labels: no unsupported metric can leak from the provider into a caption.
STAT_LABELS = {
    'corners': '🚩 Corners', 'yellow_cards': '🟨 Yellow cards', 'red_cards': '🟥 Red cards',
    'possession': '📊 Possession', 'shots_on_target': '🎯 Shots on target',
    'total_shots': '🥅 Total shots', 'fouls': '⚠️ Fouls', 'offsides': '🚫 Offsides',
}


def statistics_lines(match):
    stats=match.get('statistics') or {}
    if not stats or not match.get('statistics_at'):return []
    lines=[f"📈 Match stats · home–away · {local(match['statistics_at']):%H:%M} SAST"]
    for key,label in STAT_LABELS.items():
        values=stats.get(key)
        if not isinstance(values,list) or len(values)!=2:continue
        if any(type(n) not in (int,float) or not 0<=n<=(100 if key=='possession' else 200) for n in values):continue
        if key=='possession' and abs(sum(values)-100)>1:continue
        if key!='possession' and any(int(n)!=n for n in values):continue
        suffix='%' if key=='possession' else ''
        lines.append(f'{label}: {values[0]:g}{suffix}–{values[1]:g}{suffix}')
    return lines if len(lines)>1 else []
