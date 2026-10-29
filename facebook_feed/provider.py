"""Free-plan API-FOOTBALL adapter. No fallback to the app's unofficial score endpoint."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import os
import re
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from urllib.error import HTTPError
from facebook_post import _NoRedirect
from .content import local, norm


class ProviderError(RuntimeError):
    pass


class APIFootball:
    BASE='https://v3.football.api-sports.io'
    def __init__(self, config, state, now, opener=None):
        self.config=config['provider'];self.settings=config;self.state=state;self.now=now
        self.opener=opener or build_opener(_NoRedirect())
        self.key=os.getenv('API_FOOTBALL_KEY','').strip()
        if not self.key:
            raise ProviderError('API_FOOTBALL_KEY is not configured; no live data fetched')
        utcday=now.astimezone(timezone.utc).date().isoformat()
        budget=state.setdefault('provider',{})
        if budget.get('utc_date')!=utcday:
            budget.update(utc_date=utcday,requests=0,remaining=None)
        self.budget=budget

    def get(self, endpoint, params=None):
        if endpoint!='status':self.ensure_free()
        if self.budget['requests']>=min(90,int(self.config['daily_request_budget'])) or self.budget.get('remaining')==0:
            raise ProviderError('Free request budget exhausted; skipping provider call')
        self.budget['requests']+=1
        req=Request(self.BASE+'/'+endpoint+('?' + urlencode(params) if params else ''),
                    headers={'x-apisports-key':self.key,'Accept':'application/json'},method='GET')
        try:
            with self.opener.open(req,timeout=25) as response:
                date=response.headers.get('Date')
                if not date or abs((self.now-parsedate_to_datetime(date)).total_seconds())>self.config['max_fetch_age_seconds']:
                    raise ProviderError('Provider HTTP timestamp is missing/stale; no score update')
                remaining=response.headers.get('x-ratelimit-requests-remaining')
                if remaining is not None:
                    self.budget['remaining']=int(remaining)
                if self.budget.get('remaining') is not None:
                    # The Free allocation is 100/day; respect usage by dry runs/other consumers too.
                    self.budget['requests']=max(self.budget['requests'],100-self.budget['remaining'])
                if response.headers.get('X-RateLimit-Remaining')=='0':
                    raise ProviderError('Provider per-minute limit reached; wait for the next scheduled poll')
                result=json.loads(response.read(8*1024*1024))
        except HTTPError as error:
            if error.code==429:
                self.budget['remaining']=0
            raise ProviderError(f'Provider HTTP {error.code}; no automatic retry') from None
        except ProviderError:
            raise
        except Exception:
            raise ProviderError('Provider network/response failure; raw details omitted') from None
        if not isinstance(result,dict):
            raise ProviderError('Invalid provider response wrapper')
        if result.get('errors'):
            raise ProviderError('Provider returned errors (possibly account/season coverage); no scores used')
        if (result.get('paging') or {}).get('total',1)>1:
            raise ProviderError('Provider response is paginated; refusing incomplete matchday')
        return result.get('response')

    def ensure_free(self):
        if self.budget.get('plan_checked')!=self.budget['utc_date']:
            account=self.get('status') or {}
            if not isinstance(account,dict) or str((account.get('subscription') or {}).get('plan','')).casefold()!='free':
                raise ProviderError('Only a verified Free account is authorized by this configuration')
            if (account.get('subscription') or {}).get('active') is not True:
                raise ProviderError('Provider subscription inactive')
            try:
                self.budget['requests']=max(self.budget['requests'],int((account.get('requests') or {}).get('current',0)))
            except (ValueError,TypeError):
                raise ProviderError('Cannot verify provider account usage') from None
            self.budget['plan_checked']=self.budget['utc_date']

    def fixtures(self):
        self.ensure_free()
        cache=self.budget.get('cache')
        if cache and timedelta(0)<=self.now-local(cache['at'])<timedelta(seconds=min(60*self.config['poll_interval_minutes'],self.config['max_fetch_age_seconds'])):
            return cache['matches'],cache['at']
        raw=self.get('fixtures',{'date':self.now.date().isoformat(),'timezone':'Africa/Johannesburg'})
        if not isinstance(raw,list):
            raise ProviderError('Provider fixture list unavailable')
        matches=[]
        for value in raw:
            match=normalize(value,self.now)
            if match and any(norm(match['country'])==norm(c['country']) and norm(match['competition']) in {norm(n) for n in c['names']}
                for c in self.settings['live']['competitions']):
                matches.append(match)
        # Keep only normalized, relevant public match data; never persist raw headers/credentials/provider wrappers.
        at=self.now.isoformat()
        self.budget['cache']={'at':at,'matches':matches}
        return matches,at

    def coverage(self):
        """Catalog is evidence of endpoint coverage, not proof this account can access current-season live scores."""
        self.ensure_free()
        cache=self.budget.get('coverage')
        if cache and self.now-local(cache['at'])<timedelta(days=self.config['coverage_check_days']):
            return cache
        values=self.get('leagues',{'current':'true'}) or []
        if not isinstance(values,list):raise ProviderError('Provider coverage catalog unavailable')
        entries=[]
        for comp in self.settings['live']['competitions']:
            found=[x for x in values if norm((x.get('country') or {}).get('name',''))==norm(comp['country']) and
                   norm((x.get('league') or {}).get('name','')) in {norm(n) for n in comp['names']}]
            entries.append({'competition':comp,'catalog_found':bool(found),'current_seasons':[
                {'year':s.get('year'),'coverage':s.get('coverage')} for x in found for s in x.get('seasons',[]) if s.get('current')]})
        cache={'at':self.now.isoformat(),'competitions':entries}
        self.budget['coverage']=cache
        return cache


def normalize(value,now):
    try:
        fixture=value['fixture'];teams=value['teams'];league=value['league'];goals=value['goals']
        status=fixture['status']['short'];elapsed=fixture['status'].get('elapsed')
        known={'NS','1H','HT','2H','ET','BT','P','FT','AET','PEN','PST','CANC','ABD','SUSP','INT'}
        if status not in known or not re.fullmatch(r'[1-9]\d*',str(fixture['id'])):
            return None
        kickoff=local(fixture['date'])
        age=(now-kickoff).total_seconds()/60
        if status in ('1H','HT','2H','ET','BT','P'):
            if not isinstance(elapsed,int) or isinstance(elapsed,bool) or not 0<=elapsed<=180 or elapsed>age+10:
                return None
            if age>{'1H':95,'HT':120,'2H':180,'ET':240,'BT':240,'P':270}[status]:
                return None
        if status in ('FT','AET','PEN') and age<75:
            return None
        if kickoff.date()!=now.date() or kickoff>now+timedelta(minutes=10) and status not in ('NS','PST','CANC'):
            return None
        numbers=[]
        for side in ('home','away'):
            number=goals.get(side)
            if number is not None and (isinstance(number,bool) or int(number)!=float(number) or int(number)<0):
                return None
            numbers.append(int(number) if number is not None else None)
        if status not in ('NS','PST','CANC') and any(x is None for x in numbers):
            return None
        if not teams['home']['name'] or not teams['away']['name']:
            return None
        penalties=(value.get('score') or {}).get('penalty') or {}
        p=[penalties.get('home'),penalties.get('away')]
        if not all(isinstance(n,int) and not isinstance(n,bool) and n>=0 for n in p):
            p=None
        return dict(id=str(fixture['id']),home=teams['home']['name'],away=teams['away']['name'],
                    kickoff=kickoff.isoformat(),status=status,elapsed=elapsed,home_goals=numbers[0],away_goals=numbers[1],
                    competition=league['name'],country=league['country'],round=league.get('round'),penalties=p)
    except (KeyError,TypeError,ValueError,OverflowError):
        return None
