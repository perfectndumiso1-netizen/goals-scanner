"""Direct Highlightly football transport, isolated from predictions and API-Sports.

Only documented matches routes are allowed. No redirects, raw provider messages,
video downloads, key rotation, fabricated scores, or cross-provider ID reuse.
"""
from datetime import timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import os
import re
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from facebook_post import _NoRedirect
from .content import local
from .provider import ProviderError
from .match_events import ACTIVE, normalise_observation, ledger, observe

STATES={'Not started':'NS','First half':'1H','Half time':'HT','Second half':'2H',
        'Extra time':'ET','Break time':'BT','Penalties':'P','Suspended':'SUSP',
        'Interrupted':'INT','Finished':'FT','Finished after extra time':'AET',
        'Finished after penalties':'PEN','Postponed':'PST','Cancelled':'CANC','Abandoned':'ABD'}


def pair(value):
    if value is None:return None
    if not isinstance(value,str) or not re.fullmatch(r'\d{1,2}\s*-\s*\d{1,2}',value):
        raise ProviderError('Highlightly score format unverified; no score inferred')
    return [int(v.strip()) for v in value.split('-')]


def observation(row,now):
    """Translate only documented factual fields; missing periods stay unknown."""
    try:
        mid=row['id'];home=row['homeTeam'];away=row['awayTeam'];phase=row['state']
        if type(mid) is not int or mid<=0:raise ValueError()
        if any(type(t['id']) is not int or t['id']<=0 for t in (home,away)) or home['id']==away['id']:raise ValueError()
        status=STATES.get(phase['description'])
        if not status:return None  # No guessing for Unknown, Awarded, In progress, TBD.
        current=pair(phase['score'].get('current'));pens=pair(phase['score'].get('penalties'))
        events=[]
        values=row.get('events',[])
        if not isinstance(values,list):raise ValueError()
        for event in values:
            if not isinstance(event,dict):continue
            kind=event.get('type')
            if kind not in ('Goal','Own Goal','Penalty','Red Card'):continue
            clock=event.get('time')
            if not isinstance(clock,str) or not re.fullmatch(r'\d{1,3}(\+\d{1,2})?',clock):continue
            minute,*extra=map(int,clock.split('+'))
            events.append({'type':'Card' if kind=='Red Card' else 'Goal',
                           'detail':'Normal Goal' if kind=='Goal' else kind,
                           'time':{'elapsed':minute,'extra':extra[0] if extra else None},
                           'team':event.get('team'),
                           'player':{'id':event.get('playerId'),'name':event.get('player')}})
        raw={'fixture':{'id':mid,'date':row['date'],'status':{'short':status,'elapsed':phase.get('clock')}},
             'teams':{'home':home,'away':away},'league':{'name':row['league']['name'],'country':row['country']['name'],'round':row.get('round')},
             'goals':dict(zip(('home','away'),current or [None,None])),
             'score':{'penalty':dict(zip(('home','away'),pens or [None,None]))},'events':events,
             '_source':'highlightly'}
        return normalise_observation(raw,now)
    except (KeyError,TypeError,ValueError,AttributeError):
        raise ProviderError('Highlightly match schema unverified; raw response omitted') from None


class Highlightly:
    BASE='https://soccer.highlightly.net'

    def __init__(self,cfg,state,now,opener=None):
        self.cfg=cfg['highlightly'];self.now=now;self.started=monotonic();self.at=None
        self.freshness=cfg['event_monitor']['max_source_age_seconds']
        self.key=os.getenv('HIGHLIGHTLY_API_KEY','').strip()
        self.opener=opener or build_opener(_NoRedirect())
        self.budget=state.setdefault('highlightly_api',{})
        day=now.astimezone(timezone.utc).date().isoformat()
        if self.budget.get('utc_date')!=day:
            # Only this provider's daily accounting rolls at UTC; no other history resets.
            after=self.budget.get('after')
            self.budget.clear();self.budget.update(utc_date=day,requests=0,remaining=None)
            if after:self.budget['after']=after
        self.reason='not_attempted';self.attempted=False

    def request(self,path,params=None):
        if path!='matches' and not re.fullmatch(r'matches/[1-9]\d*',path):raise ProviderError('Unsupported Highlightly route')
        if path!='matches' and not self.budget.get('plan_verified_at'):raise ProviderError('Highlightly Free plan must be checked before details')
        if not self.key:self.reason='not_configured';raise ProviderError('HIGHLIGHTLY_API_KEY is not configured')
        if self.budget.get('after') and self.now<local(self.budget['after']):
            self.reason='account_cooldown';raise ProviderError('Highlightly cooldown active; no retry')
        if self.budget['requests']>=self.cfg['daily_request_budget'] or self.budget.get('remaining')==0:
            self.reason='quota_unavailable';raise ProviderError('Highlightly daily budget unavailable; cached data retained')
        self.budget['requests']+=1;self.attempted=True;self.reason='invalid_provider_response'
        req=Request(self.BASE+'/'+path+('?' + urlencode(params) if params else ''),
                    headers={'x-rapidapi-key':self.key,'Accept':'application/json'})
        try:
            with self.opener.open(req,timeout=25) as response:
                # Count even a malformed/stale response, respecting usage elsewhere.
                limit=int(response.headers['x-ratelimit-requests-limit'])
                remaining=int(response.headers['x-ratelimit-requests-remaining'])
                if limit!=100 or not 0<=remaining<=limit:raise ProviderError('Unverified Highlightly Free allowance')
                self.budget.update(allocation=limit,remaining=remaining)
                self.budget['requests']=max(self.budget['requests'],limit-remaining)
                stamp=parsedate_to_datetime(response.headers.get('Date',''))
                if not -30<=(self.now+timedelta(seconds=monotonic()-self.started)-stamp).total_seconds()<=self.freshness:
                    self.reason='stale_timestamp';raise ProviderError('Highlightly response timestamp missing/stale')
                self.at=stamp.isoformat()
                raw=response.read(8*1024*1024+1)
                if len(raw)>8*1024*1024:raise ProviderError('Highlightly response exceeds size bound')
                data=json.loads(raw)
        except HTTPError as error:
            self.reason={401:'authentication_rejected',403:'access_restriction',429:'rate_or_quota_rejection'}.get(error.code,'http_rejection')
            try:
                retry=error.headers.get('Retry-After','600')
                seconds=int(retry) if str(retry).isdigit() else int((parsedate_to_datetime(retry)-self.now).total_seconds())
            except (TypeError,ValueError,AttributeError):seconds=600
            seconds=max(21600 if error.code in (401,403) else 600,min(seconds,86400))
            self.budget['after']=(self.now+timedelta(seconds=seconds)).isoformat()
            # A generic 429 is NOT proof of daily exhaustion.
            if error.code==429 and error.headers.get('x-ratelimit-requests-remaining')=='0':self.budget['remaining']=0
            raise ProviderError('Highlightly request rejected; details omitted, no provider/key switching') from None
        except ProviderError:raise
        except Exception:
            self.reason='transport_or_invalid_response'
            raise ProviderError('Highlightly network/response validation failed; details omitted') from None
        if isinstance(data,dict) and (data.get('errors') or data.get('error') or data.get('statusCode',200)!=200):
            self.reason='provider_rejection';raise ProviderError('Highlightly returned a provider error; raw message omitted')
        self.reason='response_received'
        return data

    def page(self,offset=0):
        result=self.request('matches',{'date':self.now.date().isoformat(),'timezone':'Africa/Johannesburg','limit':100,'offset':offset})
        try:
            rows=result['data'];p=result['pagination'];tier=result['plan']['tier']
            if tier not in ('BASIC','FREE'):raise ValueError()
            if not isinstance(rows,list) or len(rows)>100:raise ValueError()
            if any(type(p[k]) is not int for k in ('totalCount','offset','limit')):raise ValueError()
            if not 0<=p['totalCount']<=100000 or p['offset']!=offset or p['limit']!=100:raise ValueError()
            if len(rows)!=min(100,max(0,p['totalCount']-offset)):raise ValueError()
            self.budget['plan_verified_at']=self.at
            return rows,p['totalCount']
        except (KeyError,TypeError,ValueError):
            self.reason='invalid_page_or_plan';raise ProviderError('Highlightly page/Free plan unverified; no partial matchday used') from None

    def matches(self):
        rows=[];total=None;stamps=[]
        for page in range(self.cfg['max_pages_per_poll']):
            values,count=self.page(page*100);stamps.append(local(self.at))
            if total is not None and count!=total:raise ProviderError('Highlightly matchday changed during pagination; no partial observation')
            total=count;rows.extend(values)
            if len(rows)>=total:break
        else:raise ProviderError('Highlightly pagination safety bound reached; no partial observation')
        ids=[r.get('id') if isinstance(r,dict) else None for r in rows]
        if any(type(i) is not int or i<=0 for i in ids) or len(set(ids))!=len(ids):raise ProviderError('Highlightly duplicate/invalid match IDs')
        self.at=min(stamps).isoformat()
        return rows

    def detail(self,key):
        if not re.fullmatch(r'highlightly:[1-9]\d*',key):raise ProviderError('Cross-provider fixture ID refused')
        result=self.request('matches/'+key.split(':')[1])
        if not isinstance(result,list) or len(result)!=1 or not isinstance(result[0],dict) or result[0].get('id')!=int(key.split(':')[1]):
            raise ProviderError('Highlightly detail identity mismatch')
        if not isinstance(result[0].get('events'),list):raise ProviderError('Highlightly detail event schema unverified')
        return observation(result[0],self.now)


def diagnose(cfg,state,now,api=None):
    api=api or Highlightly(cfg,state,now)
    report={'mode':'read_only_highlightly_diagnostic','outcome':'blocked','reason':'not_attempted',
            'facebook_requests':0,'checked_at':now.isoformat(),'slot':'HIGHLIGHTLY_API_KEY',
            'configured':bool(api.key),'http_attempted':False}
    report.update(coverage='not_verified',match_detail_verified=False,ready_for_activation=False)
    phase='match_list'
    try:
        rows=api.matches();stamp=api.at
        phase='match_schema'
        parsed=[observation(row,now) for row in rows]
        usable=[m for m in parsed if m is not None]
        report.update(total_rows=len(rows),list_rows=len(rows),pages_read=max(1,(len(rows)+99)//100),
                      usable_observations=len(usable),coverage='complete_day')
        if usable:
            phase='match_detail'
            sample=next((m for m in usable if m['status'] in ACTIVE),usable[0])
            detailed=api.detail(sample['id'])
            if not detailed or any(detailed.get(k)!=sample.get(k) for k in ('id','source','home_team_id','away_team_id','home','away','kickoff')):
                raise ProviderError('Highlightly diagnostic detail identity/schema mismatch')
            oldest=min(local(stamp),local(api.at))
            if not -30<=(now-oldest).total_seconds()<=cfg['event_monitor']['max_source_age_seconds']:
                raise ProviderError('Highlightly diagnostic assembled observations expired')
            report.update(match_detail_verified=True,ready_for_activation=True)
        report.update(outcome='verified_read_only',reason='verified_full_match_list_and_detail' if usable else 'verified_list_no_usable_detail_sample')
    except ProviderError:
        report['reason']=api.reason if api.reason!='response_received' else phase+'_validation_failed'
    except Exception:report['reason']='unexpected_response_shape'
    report.update(http_attempted=api.attempted)
    for key in ('allocation','requests','remaining'):report[key]=api.budget.get(key)
    return report


def poll(cfg,state,now,api=None):
    from .live_window import in_window
    if not in_window(now,cfg):return False,'outside 08:00–24:00 SAST score coverage'
    if cfg['highlightly']['verification_only']:
        return False,'Highlightly integration staged: read-only verification required before live activation'
    cache=state.setdefault('highlightly_monitor_cache',{})
    if cache.get('next_poll') and now<local(cache['next_poll']):return False,'awaiting quota-aware Highlightly polling interval'
    cache['next_poll']=(now+timedelta(minutes=cfg['highlightly']['poll_interval_minutes'])).isoformat()
    api=api or Highlightly(cfg,state,now)
    rows=api.matches();stamp=api.at
    matches={}
    for row in rows:
        m=observation(row,now)
        if m:matches[m['id']]=m
    book=ledger(state)
    tracked={k:v for k,v in book['matches'].items() if k.startswith('highlightly:') and v['snapshot']['status'] in ACTIVE and now-local(v['observed_at'])<timedelta(hours=6)}
    # No old API-Sports IDs go to this provider. Terminal disappearance is never inferred.
    missing=sorted(set(tracked)-set(matches))
    active=sorted(k for k,m in matches.items() if m['status'] in ACTIVE)
    cursor=cache.get('detail_cursor',0)%max(1,len(active))
    targets=list(dict.fromkeys(missing+active[cursor:]+active[:cursor]))[:cfg['highlightly']['max_details_per_poll']]
    cache['detail_cursor']=cursor+len(targets)
    for key in targets:
        detailed=api.detail(key)
        if detailed:
            prior=matches.get(key) or tracked[key]['snapshot']
            if any(detailed.get(k)!=prior.get(k) for k in ('home_team_id','away_team_id','home','away','kickoff')):
                raise ProviderError('Highlightly detail team/kickoff identity mismatch')
            matches[key]=detailed;stamp=min(local(stamp),local(api.at)).isoformat()
    selected=[m for key,m in matches.items() if m['status'] in ACTIVE or key in tracked]
    if not -30<=(now-local(stamp)).total_seconds()<=cfg['event_monitor']['max_source_age_seconds']:
        raise ProviderError('Highlightly assembled observation expired; no event advanced')
    observe(state,selected,stamp,now)
    cache['last_live_success']=stamp
    return True,f'verified {len(selected)} Highlightly live/tracked observations; no absent fixture inferred finished'
