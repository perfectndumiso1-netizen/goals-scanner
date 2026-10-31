"""24-hour monitoring, batched terminal refresh, pending consolidated newsroom posts."""
from datetime import timedelta
from .content import candidate, local
from .event_provider import EventAPI
from .match_events import ACTIVE, TERMINAL, STATUS_LABELS, digest, ledger, normalise_observation, observe
from .provider import ProviderError


def poll(cfg,state,now,api=None):
    from .live_window import in_window
    if not in_window(now,cfg):return False,'outside 08:00–24:00 SAST score coverage'
    if cfg.get('score_source')=='highlightly':
        from .highlightly import poll as highlightly_poll
        return highlightly_poll(cfg,state,now,api)
    settings=cfg['event_monitor'];book=ledger(state)
    cache=state.setdefault('event_monitor_cache',{})
    if cache.get('next_poll') and now<local(cache['next_poll']):return False,'awaiting next polling/discovery interval'
    api=api or EventAPI(cfg,state,now)
    cache['next_poll']=(now+timedelta(minutes=5)).isoformat()  # Also rate-limit failed attempts.
    active=[key for key,m in book['matches'].items() if m['snapshot']['status'] in ACTIVE and now-local(m['observed_at'])<timedelta(hours=6)]
    # A bounded calendar cache prevents wasting live requests in known empty periods.
    calendar_due=not cache.get('calendar_at') or now-local(cache['calendar_at'])>=timedelta(hours=6) or cache.get('calendar_day')!=now.date().isoformat()
    if not active and calendar_due and (not cache.get('calendar_retry_after') or now>=local(cache['calendar_retry_after'])):
        try:
            calendar=api.get('fixtures',{'date':now.date().isoformat(),'timezone':'Africa/Johannesburg'})
            if not isinstance(calendar,list):raise ProviderError('Fixture calendar unavailable; preserving last data')
            upcoming=[]
            for raw in calendar:
                try:
                    f=raw['fixture'];ko=local(f['date'])
                    if f['status']['short'] in ('NS','TBD') and now-timedelta(minutes=15)<=ko<=now+timedelta(days=1):
                        upcoming.append({'id':str(f['id']),'kickoff':ko.isoformat()})
                    elif f['status']['short'] in ACTIVE:active.append(str(f['id']))
                except (KeyError,ValueError,TypeError):continue
            cache.update(calendar_at=api.at,calendar_day=now.date().isoformat(),upcoming=upcoming)
            cache.pop('calendar_retry_after',None)
        except ProviderError:
            cache['calendar_retry_after']=(now+timedelta(hours=6)).isoformat()
            cache['calendar_problem']='Optional calendar unavailable; trying global discovery on the same authorised allocation'
    due=[f for f in cache.get('upcoming',[]) if now-timedelta(minutes=15)<=local(f['kickoff'])<=now+timedelta(minutes=5)]
    need_retry={e['fixture_id'] for e in book['events'].values() if e['status']=='pending'}
    if not active and not due and not need_retry and cache.get('last_live_success') and now-local(cache['last_live_success'])<timedelta(minutes=60):
        future=[local(f['kickoff']) for f in cache.get('upcoming',[]) if local(f['kickoff'])>now]
        cache['next_poll']=min([now+timedelta(minutes=60)]+future).isoformat()
        return False,'no scheduled/live matches; quota-saving discovery backoff (up to 60 minutes)'
    raw=api.get('fixtures',{'live':'all','timezone':'Africa/Johannesburg'})
    if not isinstance(raw,list):raise ProviderError('Live fixture response unavailable')
    matches=[];ids=set();duplicates=set()
    for value in raw:
        match=normalise_observation(value,now)
        if not match:continue
        if match['id'] in ids:duplicates.add(match['id'])
        ids.add(match['id']);matches.append(match)
    matches=[m for m in matches if m['id'] not in duplicates]
    # Missing from live=all is NOT a full-time/cancellation event. Refresh only known
    # tracked or pending fixtures, at most one documented batch of <=20 IDs per poll.
    checks=cache.setdefault('terminal_checks',{})
    for key in list(checks):
        if key not in book['matches'] and key not in active:del checks[key]
    missing=[]
    for key in dict.fromkeys(active+sorted(need_retry)):
        if key in ids or key in duplicates:continue
        prior=checks.get(key)
        if not prior or now>=local(prior['after']):missing.append(key)
    stamp=api.at
    if missing:
        targets=missing[:20]
        for key in targets:checks[key]={'after':(now+timedelta(minutes=15)).isoformat()}
        try:
            extra=api.get('fixtures',{'ids':'-'.join(targets),'timezone':'Africa/Johannesburg'})
            if not isinstance(extra,list):raise ProviderError('Terminal fixture response malformed')
            # Observations from both requests retain their actual source freshness.
            details=[normalise_observation(value,now) for value in extra]
            counts={}
            for m in details:
                if m:counts[m['id']]=counts.get(m['id'],0)+1
            for m in details:
                if m and counts[m['id']]==1 and m['id'] in targets and m['id'] not in ids:matches.append(m);ids.add(m['id'])
            stamp=min((local(stamp),local(api.at))).isoformat()
        except ProviderError:
            cache['terminal_problem']='Some missing fixtures could not be refreshed; no terminal status inferred'
    observe(state,matches,stamp,now)
    cache['last_live_success']=stamp
    cache['last_live_ids']=[m['id'] for m in matches if m['status'] in ACTIVE]
    unresolved_live=any(m['snapshot']['status'] in ACTIVE and now-local(m['observed_at'])<timedelta(hours=6) for m in book['matches'].values())
    if not unresolved_live and not cache['last_live_ids'] and not any(e['status']=='pending' for e in book['events'].values()):
        future=[local(f['kickoff']) for f in cache.get('upcoming',[]) if local(f['kickoff'])>now]
        cache['next_poll']=min([now+timedelta(minutes=60)]+future).isoformat()
    return True,f'verified {len(matches)} live/tracked fixture observations; missing scores never inferred'


def caption(matches,events,at):
    lines=['PLAYREPORT ZA | LIVE SCORES','','LIVE MATCH UPDATES',f'{local(at):%d %b %Y, %H:%M} SAST','']
    previous=None
    for m in sorted(matches,key=lambda m:(m['competition'],m['id'])):
        if m['competition']!=previous:lines += [m['competition']];previous=m['competition']
        if type(m.get('home_goals')) is int and type(m.get('away_goals')) is int:
            lines.append(f"{m['home']} {m['home_goals']}–{m['away_goals']} {m['away']}")
        else:lines.append(f"{m['home']} v {m['away']}")
        for event in events:
            if event['fixture_id']!=m['id']:continue
            change=event['change'];minute=change.get('minute')
            clock=(str(minute)+(f"+{change['extra']}" if change.get('extra') else '')+"'") if type(minute) is int else ''
            prefix=clock+' | ' if clock else ''
            if change['kind']=='goal':
                scorers=change.get('scorers',[])
                if scorers:
                    for scorer in scorers:
                        when=str(scorer['minute'])+(f"+{scorer['extra']}" if scorer.get('extra') else '')+"'"
                        label='Own goal' if scorer['detail']=='Own Goal' else 'Goal'
                        lines.append(f"{when} | {label}"+(f" — {scorer['player']}" if scorer.get('player') else ''))
                else:lines.append('Goal — score updated')
            elif change['kind']=='score_update':lines.append('Score updated')
            elif change['kind']=='score_correction':lines.append('Score corrected')
            elif change['kind']=='shootout':lines.append('Penalty shoot-out updated')
            elif change['kind']=='red_card':lines.append(prefix+'Red card'+(f" — {change['player']}" if change.get('player') else ''))
            else:lines.append(prefix+STATUS_LABELS[change['status']])
        phase={'1H':'First half','2H':'Second half','ET':'Extra time','BT':'Extra-time break','P':'Penalty shoot-out'}.get(m['status'],STATUS_LABELS.get(m['status'],m['status']))
        elapsed=m.get('elapsed')
        display_minute=str(elapsed)+(f"+{m['added_time']}" if m.get('added_time') else '')+"'" if type(elapsed) is int else ''
        lines.append(f"Status: {phase}"+(f' | {display_minute}' if display_minute else ''))
        if m['status'] in ('P','PEN') and isinstance(m.get('penalties'),list):lines.append(f"Penalties: {m['penalties'][0]}–{m['penalties'][1]}")
        lines.append('')
    lines += ['Scores are updated when meaningful match events occur.','','#PlayReportZA #LiveScores']
    return '\n'.join(lines)


def build(cfg,state,now,api=None):
    fresh,reason=poll(cfg,state,now,api)
    book=ledger(state)
    if not fresh:return None,reason
    available=[]
    for e in book['events'].values():
        if e['status']!='pending':continue
        if cfg.get('score_source')=='highlightly' and cfg['highlightly'].get('monitor_mode','all')=='selected':
            target=state.get('highlightly_watchlist',{}).get('selected',{}).get(e['fixture_id'])
            if not target or not target.get('baseline_at') or local(e['detected_at'])<=local(target['baseline_at']):continue
        m=book['matches'].get(e['fixture_id'])
        if m and m['snapshot'].get('source')!=cfg.get('score_source','api-football'):continue
        if not m or not timedelta(seconds=-30)<=now-local(m['observed_at'])<=timedelta(seconds=cfg['event_monitor']['max_source_age_seconds']):continue
        if e.get('retry_after') and now<local(e['retry_after']):continue
        available.append(e)
    available.sort(key=lambda e:(e['detected_at'],e['id']))
    selected=available
    ids=list(dict.fromkeys(e['fixture_id'] for e in selected))
    if not selected:return None,'baseline/unchanged observations; no pending meaningful event'
    matches=[book['matches'][key]['snapshot'] for key in ids]
    at=min(local(book['matches'][m['id']]['observed_at']) for m in matches).isoformat()
    event_ids=[e['id'] for e in selected]
    key='live-events:'+digest(sorted(event_ids))
    text=caption(matches,selected,at)
    if cfg.get('score_source')=='highlightly' and cfg['highlightly'].get('monitor_mode','all')=='selected':
        text=text.replace('LIVE MATCH UPDATES','SELECTED MATCH UPDATES',1)
    if len(text)>60000:raise ProviderError('Consolidated event text exceeds safe size; inspect pending batch')
    post=candidate('live',key,key,text,event_ids=event_ids,snapshot=matches,
                   expires_at=(local(at)+timedelta(seconds=cfg['event_monitor']['max_source_age_seconds'])).isoformat())
    if cfg['live']['image_required']:
        feature=next((m for m in matches if type(m.get('home_goals')) is int and type(m.get('away_goals')) is int),matches[0])
        post['graphic']={'kind':'live-score','match':dict(feature),'checked_at':at,'status_only':True,'header':'PLAYREPORT ZA | LIVE SCORES','style':cfg['live'].get('graphic_style','classic')}
    return post,reason
