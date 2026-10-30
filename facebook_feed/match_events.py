"""Persistent meaningful-change detection. Minute ticks and baseline history never alert."""
from datetime import timedelta
import hashlib
import json
from .content import local, norm
from .provider import normalize

ACTIVE={'1H','HT','2H','ET','BT','P','INT','SUSP'}
TERMINAL={'FT','AET','PEN','PST','CANC','ABD'}
STATUS_LABELS={'HT':'Half-time','FT':'Full-time','AET':'Full-time after extra time','PEN':'Full-time after penalties',
               'PST':'Postponed','CANC':'Cancelled','ABD':'Abandoned','SUSP':'Suspended','INT':'Interrupted',
               '2H':'Second half started','ET':'Extra time','BT':'Extra-time break','P':'Penalty shoot-out'}


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def normalise_observation(raw,now):
    m=normalize(raw,now,allow_overnight=True)
    if not m:return None
    m['source']='api-football'
    m['events']=[]
    values=raw.get('events')
    if values is not None and not isinstance(values,list):return None
    seen=set()
    for event in values or []:
        if not isinstance(event,dict):continue
        kind=event.get('type');detail=event.get('detail');time=event.get('time') or {};team=event.get('team') or {};player=event.get('player') or {}
        if not all(isinstance(v,dict) for v in (time,team,player)):continue
        if not ((kind=='Goal' and detail in ('Normal Goal','Own Goal','Penalty')) or (kind=='Card' and isinstance(detail,str) and detail.casefold() in ('red card','second yellow card'))):continue
        minute=time.get('elapsed');extra=time.get('extra')
        if type(minute) is not int or not 0<=minute<=180 or (m.get('elapsed') is not None and minute>m['elapsed']):continue
        if extra is not None and (type(extra) is not int or not 0<=extra<=30):continue
        if type(team.get('id')) is not int or team['id'] not in (m.get('home_team_id'),m.get('away_team_id')):continue
        name=player.get('name');pid=player.get('id')
        if not isinstance(name,str) or not name.strip():name=None
        if type(pid) is not int or pid<=0:pid=None
        coarse=digest([m['id'],kind,'red_card' if kind=='Card' else detail,minute,extra,team['id']])
        eid=digest([m['id'],'red_card',team['id'],pid]) if kind=='Card' and pid is not None else digest([coarse,pid if pid is not None else norm(name) if name else None])
        if eid in seen:continue
        seen.add(eid)
        m['events'].append({'id':eid,'coarse':coarse,'kind':'goal' if kind=='Goal' else 'red_card',
                            'minute':minute,'extra':extra,'team_id':team['id'],'player_id':pid,'player':name,'detail':detail})
    return m


def ledger(state):return state.setdefault('live_event_ledger',{'version':1,'matches':{},'events':{},'last_successful_retrieval':None,'last_successful_publication':None})


def observe(state,matches,at,now):
    book=ledger(state)
    if not timedelta(seconds=-30)<=now-local(at)<=timedelta(seconds=180):raise ValueError('Stale event observation rejected')
    for m in matches:
        old=book['matches'].get(m['id'])
        # Reject out-of-order same-phase minutes/status regressions, not legitimate VAR score corrections.
        if old:
            if local(at)<local(old['observed_at']):continue
            prior=old['snapshot']
            if m['status']=='NS' and prior['status']!='NS':continue
            if (m['status']==prior['status'] and type(m.get('elapsed')) is int and type(prior.get('elapsed')) is int and m['elapsed']<prior['elapsed']):continue
            if prior['status'] in TERMINAL and m['status'] in ACTIVE:continue
            if prior['status'] in ('2H','ET','BT','P') and m['status'] in ('1H','HT'):continue
            if any(m.get(k)!=prior.get(k) for k in ('home','away')):continue
            if m['kickoff']!=prior['kickoff'] and m['status'] not in ('PST','CANC'):continue
        else:prior=None
        core=lambda row:[row.get(k) for k in ('status','elapsed','home_goals','away_goals')]
        changed_at=at if not prior or core(m)!=core(prior) else old.get('changed_at',old['observed_at'])
        if m['status'] in ('1H','HT','2H','ET','BT','P') and now-local(changed_at)>timedelta(minutes=35):continue
        known=(old or {}).get('seen_events',{})
        fresh=[]
        for e in m['events']:
            # Later scorer enrichment of an initially unnamed event isn't another card/goal.
            enrichment=any(v['coarse']==e['coarse'] and (not v.get('player_id') or not e.get('player_id')) for v in known.values())
            if e['id'] not in known and not enrichment:fresh.append(e)
            known[e['id']]=e
        sequence=(old or {}).get('sequence',0)
        changes=[]
        if prior:
            before=[prior.get('home_goals'),prior.get('away_goals')];after=[m.get('home_goals'),m.get('away_goals')]
            if all(type(n) is int for n in before+after) and before!=after:
                increased=sum(after)>sum(before) and all(a>=b for a,b in zip(after,before))
                goals=[e for e in fresh if e['kind']=='goal' and (type(prior.get('elapsed')) is not int or e['minute']>=prior['elapsed'])]
                if len(goals)>max(0,sum(after)-sum(before)):goals=[]
                changes.append({'kind':('goal' if goals else 'score_update') if increased else 'score_correction','minute':m.get('elapsed'),
                                'scorers':[e for e in goals] if increased else [],'source_event_ids':[e['id'] for e in goals]})
            pens=m.get('penalties');oldpens=prior.get('penalties')
            if isinstance(pens,list) and isinstance(oldpens,list) and pens!=oldpens and m['status'] in ('P','PEN'):
                changes.append({'kind':'shootout','minute':None,'source_event_ids':[]})
            if m['status']!=prior['status'] and m['status'] in STATUS_LABELS:
                changes.append({'kind':'status','status':m['status'],'minute':m.get('elapsed'),'source_event_ids':[]})
            for e in fresh:
                if e['kind']=='red_card' and (type(prior.get('elapsed')) is not int or e['minute']>=prior['elapsed']):changes.append({'kind':'red_card','minute':e['minute'],'extra':e.get('extra'),'player':e['player'],
                                                         'source_event_ids':[e['id']]})
        for change in changes:
            sequence+=1
            eid=digest([m['id'],sequence,change])
            book['events'][eid]={'id':eid,'fixture_id':m['id'],'change':change,'detected_at':at,'status':'pending'}
        book['matches'][m['id']]={'snapshot':m,'observed_at':at,'seen_events':known,'sequence':sequence,'changed_at':changed_at}
    book['last_successful_retrieval']=at
    # Keep pending/unresolved evidence. Completed old state and published dedupe records are bounded.
    for eid,e in list(book['events'].items()):
        if e['status']=='pending' and now-local(e['detected_at'])>timedelta(hours=6):e['status']='expired'
        if e['status'] in ('published','simulated','expired') and now-local(e['detected_at'])>timedelta(days=7):del book['events'][eid]
    referenced={e['fixture_id'] for e in book['events'].values() if e['status'] in ('pending','reserved','unknown')}
    for key,m in list(book['matches'].items()):
        if key not in referenced and now-local(m['observed_at'])>timedelta(days=2):del book['matches'][key]
    return book


def publication_state(state,post,status,now):
    if not post.get('event_ids'):return
    book=ledger(state)
    for eid in post.get('event_ids',[]):
        if eid in book['events']:
            book['events'][eid]['status']=status
            if status=='published':book['events'][eid]['post_id']=post.get('post_id')
    if status=='published':book['last_successful_publication']=now.isoformat()
