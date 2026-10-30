"""Quota-aware API-SPORTS transport for the event monitor; secrets remain memory-only.

Slots sharing an account must share one quota group. Merely possessing multiple
free keys NEVER authorises pooling allowances. Separate groups require explicit
provider authorisation; failover remains quota-only and opt-in.
"""
from datetime import timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import os
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from facebook_post import _NoRedirect
from .content import local
from .provider import ProviderError, safe_error_reason

SLOTS=('API_FOOTBALL_KEY','API_FOOTBALL_KEY_1','API_FOOTBALL_KEY_2')


def daily_quota(errors, remaining):
    if not isinstance(errors,dict) or set(errors)!={'requests'}:return False
    if remaining == 0:return True
    # Documented daily request rejection, NOT an arbitrary errors.requests value.
    text=str(errors.get('requests','')).casefold()
    if any(unit in text for unit in ('minute','second','per-min')):return False
    return ('day' in text and ('limit' in text or 'quota' in text) and
            any(word in text for word in ('reached','exceeded','exhausted')))


class QuotaExceeded(ProviderError):pass


class EventAPI:
    BASE='https://v3.football.api-sports.io'

    def __init__(self,cfg,state,now,opener=None):
        self.cfg=cfg['event_monitor'];self.now=now;self.start=monotonic()
        self.opener=opener or build_opener(_NoRedirect())
        self.state=state.setdefault('event_api',{'groups':{},'slots':{}})
        self.day=now.astimezone(timezone.utc).date().isoformat()
        self.keys={name:os.getenv(name,'').strip() for name in SLOTS}
        self.at=None
        self.active=None

    def group(self,name):
        group=self.state['groups'].setdefault(name,{})
        if group.get('utc_date')!=self.day:
            group.clear();group.update(utc_date=self.day,requests=0,remaining=None)
        return group

    def get(self,endpoint,params=None):
        candidates=[s for s in SLOTS if self.keys[s] and self.cfg['key_slots'][s]['authorised']]
        if not candidates:raise ProviderError('No configured authorised API key slot; no request made')
        # Keys are alternatives, not three daily allowances. A pinned primary is not
        # silently replaced following credentials/network/plan/server failures.
        first=candidates[0];first_group=self.cfg['key_slots'][first]['quota_group']
        for index,slot in enumerate(candidates):
            group_name=self.cfg['key_slots'][slot]['quota_group']
            if index and (not self.cfg['failover_permitted'] or not self.cfg['permission_reference'] or group_name==first_group):continue
            budget=self.group(group_name)
            if budget.get('exhausted') or budget.get('remaining')==0 or (budget.get('allocation') is not None and budget.get('provider_used',0)>=budget['allocation']):
                if index==0 and not self.cfg['failover_permitted']:raise QuotaExceeded('API account budget unavailable; cached data preserved, no key rotation')
                continue
            if budget['requests']>=self.cfg['daily_request_budget']:raise ProviderError('Safe local request ceiling reached; not a provider quota failover')
            slotstate=self.state['slots'].setdefault(slot,{})
            revision=self.cfg['credential_revision']
            if slotstate.get('revision')!=revision:slotstate.clear();slotstate['revision']=revision
            if slotstate.get('invalid_until') and self.now<local(slotstate['invalid_until']):
                raise ProviderError('Primary credential unavailable; correct secret/revision before retrying')
            if budget.get('after') and self.now<local(budget['after']):raise ProviderError('API cooldown active; no key switching')
            try:
                if budget.get('plan_checked')!=self.day or slotstate.get('plan_checked')!=self.day:
                    account=self._request(slot,budget,'status')
                    if not isinstance(account,dict):raise ProviderError('Invalid account status; raw response omitted')
                    subscription=account.get('subscription') or {};usage=account.get('requests') or {}
                    if str(subscription.get('plan','')).casefold()!='free' or subscription.get('active') is not True:
                        raise ProviderError('Only an active verified Free allocation is authorised')
                    for field in ('current','limit'):
                        if type(usage.get(field)) is not int or usage[field]<0:raise ProviderError('Account allowance could not be verified')
                    budget['requests']=max(budget['requests'],usage['current']);budget['allocation']=usage['limit']
                    budget['provider_used']=max(budget.get('provider_used',0),usage['current'])
                    budget['plan_checked']=self.day;slotstate['plan_checked']=self.day
                cap=min(self.cfg['daily_request_budget'],max(0,budget.get('allocation',100)-self.cfg.get('daily_request_reserve',10)))
                if budget.get('allocation') is not None and budget.get('provider_used',0)>=budget['allocation']:raise QuotaExceeded('Verified account daily quota exhausted')
                if budget['requests']>=cap:raise ProviderError('Safe account reserve reached; no quota rotation')
                data=self._request(slot,budget,endpoint,params)
                self.active=slot
                return data
            except QuotaExceeded:
                budget['exhausted']=True;budget['remaining']=0;budget['exhausted_at']=self.now.isoformat()
                if budget.get('allocation') is not None:budget['requests']=max(budget['requests'],budget['allocation'])
                # Only a different provider-authorised quota allocation may follow.
                continue
        raise QuotaExceeded('All permitted account allocations unavailable; last successful data preserved')

    def _request(self,slot,budget,endpoint,params=None):
        if budget['requests']>=self.cfg['daily_request_budget']:raise ProviderError('Safe local API request ceiling reached; no rotation')
        budget['requests']+=1
        request=Request(self.BASE+'/'+endpoint+('?' + urlencode(params) if params else ''),
                        headers={'x-apisports-key':self.keys[slot],'Accept':'application/json'})
        try:
            with self.opener.open(request,timeout=25) as response:
                observed=self.now+timedelta(seconds=monotonic()-self.start)
                stamp=parsedate_to_datetime(response.headers.get('Date',''))
                if not -30<=(observed-stamp).total_seconds()<=self.cfg['max_source_age_seconds']:
                    raise ProviderError('Stale/missing API timestamp; no live observation used')
                self.at=stamp.isoformat()
                remaining=response.headers.get('x-ratelimit-requests-remaining')
                remaining_value=None
                if remaining is not None:
                    value=int(remaining)
                    if value<0:raise ProviderError('Invalid API quota header')
                    remaining_value=value
                if remaining is None and endpoint!='status':raise ProviderError('Missing account quota header; no unbudgeted data used')
                raw=response.read(8*1024*1024+1)
                if len(raw)>8*1024*1024:raise ProviderError('API payload exceeds bounded response size')
                data=json.loads(raw)
        except HTTPError as error:
            # An ordinary 429 is a minute/rate error, not proof of daily exhaustion.
            if error.code==429 and error.headers.get('x-ratelimit-requests-remaining')=='0':
                budget['remaining']=0;raise QuotaExceeded('Documented daily quota exhausted') from None
            if error.code in (429,503):
                try:
                    retry=error.headers.get('Retry-After','300')
                    seconds=int(retry) if str(retry).isdigit() else int((parsedate_to_datetime(retry)-self.now).total_seconds())
                except (ValueError,TypeError,AttributeError):seconds=300
                budget['after']=(self.now+timedelta(seconds=max(300,min(seconds,86400)))).isoformat()
            if error.code in (401,403):self.state['slots'][slot]['invalid_until']=(self.now+timedelta(hours=6)).isoformat()
            raise ProviderError(f'API HTTP {error.code}; no ordinary-error key failover') from None
        except ProviderError:raise
        except Exception:raise ProviderError('API transport/response failure; no key switching; details omitted') from None
        if not isinstance(data,dict):raise ProviderError('Malformed API response wrapper')
        if data.get('errors'):
            if daily_quota(data['errors'],remaining_value):
                budget['remaining']=0;raise QuotaExceeded('Documented daily quota exhausted')
            if isinstance(data['errors'],dict) and 'token' in data['errors']:
                self.state['slots'][slot]['invalid_until']=(self.now+timedelta(hours=6)).isoformat()
            raise ProviderError(safe_error_reason(data['errors'],endpoint))
        paging=data.get('paging') or {}
        if not isinstance(paging,dict) or paging.get('total',1)!=1:raise ProviderError('Incomplete/paginated API response rejected')
        if remaining_value is not None:
            budget['remaining']=remaining_value
            budget['provider_used']=max(budget.get('provider_used',0),budget.get('allocation',100)-remaining_value)
            budget['requests']=max(budget['requests'],budget['provider_used'])
        return data.get('response')
