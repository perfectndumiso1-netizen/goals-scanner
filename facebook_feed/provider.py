"""Free-plan API-FOOTBALL adapter. No fallback to the app's unofficial score endpoint."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import os
import re
from time import monotonic
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from urllib.error import HTTPError
from facebook_post import _NoRedirect
from .content import local, norm


class ProviderError(RuntimeError):
    pass


def safe_error_reason(errors, endpoint):
    """Only static categories/known endpoints, never provider text, keys or account details.

    API-SPORTS can return HTTP 200 with errors. A green dry-run job must not be
    mistaken for successful authentication or current-season coverage.
    """
    keys={str(key).casefold().replace('_','').replace('-','') for key in errors} if isinstance(errors,dict) else set()
    if keys & {'token','key','apikey','authentication','authorization','access'}:
        reason='API credentials/account authorisation rejected; check the saved secret and provider dashboard'
    elif keys & {'ip','ipaddress','whitelist','allowlist'}:
        reason='source IP access restricted; check provider IP restrictions for GitHub Actions'
    elif keys & {'requests','ratelimit','quota','limit'}:
        reason='request allowance/rate limit rejected; check dashboard usage before retrying'
    elif keys & {'plan','subscription','season','coverage'}:
        reason='plan/season coverage restricted; verify this account can access the requested endpoint and season'
    elif keys & {'parameters','parameter','date','timezone','league','fixture'}:
        reason='request parameters rejected; endpoint/fixture validation is required'
    else:
        reason='unclassified provider rejection; inspect the provider dashboard (raw response deliberately omitted)'
    location=endpoint if endpoint in {'status','leagues','fixtures','fixtures/statistics'} else 'provider endpoint'
    return f'Provider returned errors at {location}: {reason}; no scores used'


class APIFootball:
    BASE='https://v3.football.api-sports.io'
    def __init__(self, config, state, now, opener=None):
        self.config=config['provider'];self.settings=config;self.state=state;self.now=now
        self.started=monotonic()
        self.opener=opener or build_opener(_NoRedirect())
        self.key=os.getenv('API_FOOTBALL_KEY','').strip()
        if not self.key:
            raise ProviderError('API_FOOTBALL_KEY is not configured; no live data fetched')
        utcday=now.astimezone(timezone.utc).date().isoformat()
        budget=state.setdefault('provider',{})
        if budget.get('utc_date')!=utcday:
            budget.update(utc_date=utcday,requests=0,remaining=None,statistics_requests=0)
            for field in ('cache','last_fixture_attempt','statistics_cache','retry_after'):
                budget.pop(field,None)
        self.budget=budget

    def get(self, endpoint, params=None):
        if self.budget.get('retry_after') and self.now<local(self.budget['retry_after']):
            raise ProviderError('Provider cooldown active; no automatic retry')
        if endpoint!='status':self.ensure_free()
        if self.budget['requests']>=min(90,int(self.config['daily_request_budget'])) or self.budget.get('remaining')==0:
            raise ProviderError('Free request budget exhausted; skipping provider call')
        self.budget['requests']+=1
        req=Request(self.BASE+'/'+endpoint+('?' + urlencode(params) if params else ''),
                    headers={'x-apisports-key':self.key,'Accept':'application/json'},method='GET')
        try:
            with self.opener.open(req,timeout=25) as response:
                observed=self.now+timedelta(seconds=monotonic()-self.started)
                date=response.headers.get('Date')
                if not date or not -30<=(observed-parsedate_to_datetime(date)).total_seconds()<=self.config['max_fetch_age_seconds']:
                    raise ProviderError('Provider HTTP timestamp is missing/stale; no score update')
                self.response_at=parsedate_to_datetime(date).astimezone(self.now.tzinfo).isoformat()
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
            if error.code in (429,503):
                try:
                    retry=error.headers.get('Retry-After','600')
                    seconds=int(retry) if str(retry).isdigit() else int((parsedate_to_datetime(retry)-self.now).total_seconds())
                except (ValueError,TypeError,AttributeError):seconds=600
                self.budget['retry_after']=(self.now+timedelta(seconds=max(600,min(seconds,86400)))).isoformat()
            raise ProviderError(f'Provider HTTP {error.code}; no automatic retry') from None
        except ProviderError:
            raise
        except Exception:
            raise ProviderError('Provider network/response failure; raw details omitted') from None
        if not isinstance(result,dict):
            raise ProviderError('Invalid provider response wrapper')
        if result.get('errors'):
            raise ProviderError(safe_error_reason(result['errors'],endpoint))
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

    def fixtures(self, coverage=None):
        self.ensure_free()
        cache=self.budget.get('cache')
        if cache and timedelta(0)<=self.now-local(cache['at'])<timedelta(seconds=min(60*self.config['poll_interval_minutes'],self.config['max_fetch_age_seconds'])):
            matches=cache['matches']
            if coverage is not None:
                from .live_window import match_app_coverage
                matches=match_app_coverage(matches,coverage)
            return matches,cache['at']
        last=self.budget.get('last_fixture_attempt')
        if last and self.now-local(last)<timedelta(minutes=self.config['poll_interval_minutes']):
            raise ProviderError('Awaiting next ten-minute poll; old scores are not fresh enough to post')
        self.budget['last_fixture_attempt']=self.now.isoformat()
        raw=self.get('fixtures',{'date':self.now.date().isoformat(),'timezone':'Africa/Johannesburg'})
        if not isinstance(raw,list):
            raise ProviderError('Provider fixture list unavailable')
        matches=[]
        for value in raw:
            match=normalize(value,self.now)
            if match and (self.settings['live'].get('app_coverage_only') or any(norm(match['country'])==norm(c['country']) and norm(match['competition']) in {norm(n) for n in c['names']}
                for c in self.settings['live']['competitions'])):
                matches.append(match)
        if coverage is not None:
            from .live_window import match_app_coverage
            matches=match_app_coverage(matches,coverage)
        # Keep only normalized, relevant public match data; never persist raw headers/credentials/provider wrappers.
        at=self.response_at
        self.budget['cache']={'at':at,'matches':matches}
        return matches,at

    def enrich_statistics(self, matches):
        """Optional per-fixture calls only for an otherwise eligible score post.

        No historical substitute, no null->zero coercion, no stats-only publications.
        Missing/unsupported statistics must never prevent publishing a verified score.
        """
        result=[]
        slots=min(2,self.config.get('statistics_max_matches_per_update',0))
        cache=self.budget.setdefault('statistics_cache',{})
        for match in matches:
            enriched={k:v for k,v in match.items() if k not in ('statistics','statistics_at')}
            if not self.config.get('statistics_enabled') or slots<=0 or match['status'] in ('NS','PST','CANC'):
                result.append(enriched);continue
            if any(type(match.get(side+'_team_id')) is not int or match[side+'_team_id']<=0 for side in ('home','away')):
                result.append(enriched);continue
            slots-=1
            saved=cache.get(match['id'])
            identity=[match['home_team_id'],match['away_team_id'],match['home'],match['away']]
            if saved and saved.get('identity')==identity and timedelta(0)<=self.now-local(saved['at'])<=timedelta(seconds=self.config['max_fetch_age_seconds']):
                enriched.update(statistics=saved['values'],statistics_at=saved['at'])
            elif (self.budget.get('statistics_requests',0)<min(6,self.config.get('statistics_daily_request_budget',0)) and
                  self.budget['requests']<min(90,self.config['daily_request_budget'])-2):
                self.budget['statistics_requests']=self.budget.get('statistics_requests',0)+1
                try:
                    raw=self.get('fixtures/statistics',{'fixture':match['id']})
                    values=normalize_statistics(raw,match)
                    if values:
                        saved={'at':self.response_at,'values':values,'identity':identity}
                        cache[match['id']]=saved
                        enriched.update(statistics=values,statistics_at=saved['at'])
                except ProviderError:
                    pass
            result.append(enriched)
        # Only small normalized values; never persist provider bodies, credentials or stale extras.
        self.budget['statistics_cache']={key:value for key,value in cache.items()
            if timedelta(0)<=self.now-local(value['at'])<=timedelta(seconds=self.config['max_fetch_age_seconds'])}
        return result

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
        if any(not isinstance(v,str) or not v.strip() for v in (teams['home']['name'],teams['away']['name'],league['name'],league['country'])):
            return None
        penalties=(value.get('score') or {}).get('penalty') or {}
        p=[penalties.get('home'),penalties.get('away')]
        if not all(isinstance(n,int) and not isinstance(n,bool) and n>=0 for n in p):
            p=None
        def period(name):
            value=(value_score.get(name) or {})
            if not isinstance(value,dict):return None
            values=[value.get('home'),value.get('away')]
            if not all(type(n) is int and n>=0 and g is not None and n<=g for n,g in zip(values,numbers)):return None
            return values
        value_score=value.get('score') or {}
        extra=fixture['status'].get('extra')
        extra=extra if type(extra) is int and 0<=extra<=30 else None
        return dict(id=str(fixture['id']),home_team_id=teams['home'].get('id'),away_team_id=teams['away'].get('id'),home=teams['home']['name'],away=teams['away']['name'],
                    kickoff=kickoff.isoformat(),status=status,elapsed=elapsed,home_goals=numbers[0],away_goals=numbers[1],
                    competition=league['name'],country=league['country'],round=league.get('round'),penalties=p,halftime=period('halftime'),fulltime=period('fulltime'),added_time=extra)
    except (KeyError,TypeError,ValueError,OverflowError,AttributeError):
        return None


STATISTICS = {
    'Corner Kicks': 'corners', 'Yellow Cards': 'yellow_cards', 'Red Cards': 'red_cards',
    'Ball Possession': 'possession', 'Shots on Goal': 'shots_on_target', 'Total Shots': 'total_shots',
    'Fouls': 'fouls', 'Offsides': 'offsides', 'Goalkeeper Saves': 'saves',
}


def normalize_statistics(raw, match):
    """Require both exact provider team IDs, unique rows and valid home/away values."""
    if not isinstance(raw,list) or len(raw)!=2:return {}
    sides=[]
    for side in ('home','away'):
        rows=[r for r in raw if isinstance(r,dict) and isinstance(r.get('team'),dict) and type(r['team'].get('id')) is int and
              r['team']['id']==match.get(side+'_team_id')]
        if len(rows)!=1 or norm(rows[0]['team'].get('name',''))!=norm(match[side]):return {}
        stats=rows[0].get('statistics')
        if not isinstance(stats,list):return {}
        pairs={};duplicates=set()
        for item in stats:
            if not isinstance(item,dict) or not isinstance(item.get('type'),str) or item['type'] not in STATISTICS:continue
            key=STATISTICS[item['type']]
            if key in pairs:duplicates.add(key)
            pairs[key]=item.get('value')
        sides.append({k:v for k,v in pairs.items() if k not in duplicates})
    output={}
    for key in STATISTICS.values():
        values=[]
        for side in sides:
            value=side.get(key)
            if type(value) not in (str,int,float):break
            text=str(value)
            if key=='possession':
                if not re.fullmatch(r'\d{1,3}(?:\.\d{1,2})?%',text):break
                value=float(text[:-1])
                if not 0<=value<=100:break
                values.append(int(value) if value.is_integer() else value)
            else:
                if not re.fullmatch(r'\d{1,3}',text) or int(text)>200:break
                values.append(int(text))
        if len(values)==2 and (key!='possession' or abs(sum(values)-100)<=1):output[key]=values
    return output
