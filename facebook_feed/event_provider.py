"""Quota-aware API-SPORTS transport for the event monitor; secrets remain memory-only.

Slots sharing an account must share one quota group. Merely possessing multiple
free keys NEVER authorises pooling allowances. Separate groups require explicit
provider authorisation; quota/authentication failover are explicitly opt-in.
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


class AuthenticationRejected(ProviderError):pass


def authentication_rejection(errors):
    """Recognise credential errors, never IP restrictions/account suspension/plan errors.

    Provider text is inspected locally for classification only; it is never logged,
    stored, or included in the replacement error message.
    """
    if not isinstance(errors,dict) or not errors:return False
    kinds={str(k).casefold().replace('_','').replace('-','') for k in errors}
    if not kinds <= {'token','key','apikey','authentication','authorization','access'}:return False
    text=' '.join(str(v) for v in errors.values()).casefold()
    restricted=('suspend','banned','blocked','blacklist','whitelist','ip address','ip restriction','account disabled','account deactivated')
    return not any(term in text for term in restricted)


SAFE_ERROR_FIELDS={'token','key','apikey','authentication','authorization','access','ip','ipaddress',
                   'whitelist','allowlist','plan','subscription','season','coverage','requests',
                   'ratelimit','quota','limit','parameters','parameter','date','timezone','league','fixture'}


def safe_error_fields(errors):
    if not isinstance(errors,dict):return ['unstructured']
    names={str(k).casefold().replace('_','').replace('-','') for k in errors}
    return sorted({name if name in SAFE_ERROR_FIELDS else 'other' for name in names})


def rejection_category(errors):
    """Closed, non-secret categories only. Never return provider messages/unknown keys."""
    fields=set(safe_error_fields(errors))
    text=' '.join(str(v) for v in errors.values()).casefold() if isinstance(errors,dict) else ''
    if fields & {'ip','ipaddress','whitelist','allowlist'} or any(w in text for w in ('ip address','ip restriction','whitelist','blacklist')):return 'ip_access_restriction'
    if 'suspend' in text:return 'account_suspended'
    if any(w in text for w in ('banned','blocked','account disabled','account deactivated')):return 'account_access_restriction'
    if authentication_rejection(errors):return 'authentication_rejected'
    if fields & {'token','key','apikey','authentication','authorization','access'}:return 'mixed_authentication_rejection'
    if fields & {'plan','subscription','season','coverage'}:return 'plan_or_coverage_rejection'
    if fields & {'requests','ratelimit','quota','limit'}:return 'rate_or_quota_rejection'
    if fields & {'parameters','parameter','date','timezone','league','fixture'}:return 'parameter_rejection'
    return 'unclassified_provider_rejection'



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
        self.diagnostics=[]

    def note(self,slot,endpoint,category,**facts):
        # Call sites use fixed categories and slot constants; never provider values.
        row={'slot':slot if slot in SLOTS else 'unknown',
             'endpoint':endpoint if endpoint in ('status','fixtures') else 'provider','category':category}
        row.update(facts)
        self.diagnostics.append(row)
        self.diagnostics=self.diagnostics[-60:]

    def group(self,name):
        group=self.state['groups'].setdefault(name,{})
        if group.get('utc_date')!=self.day:
            group.clear();group.update(utc_date=self.day,requests=0,remaining=None)
        return group

    def get(self,endpoint,params=None):
        candidates=[s for s in SLOTS if self.keys[s] and self.cfg['key_slots'][s]['authorised']]
        if not candidates:raise ProviderError('No configured authorised API key slot; no request made')
        # Only configured provider-authorised allocations may follow a rejected key.
        # Network, IP restrictions, plan/parameter and server errors still stop here.
        first=candidates[0];first_group=self.cfg['key_slots'][first]['quota_group']
        auth_fallback=self.cfg.get('authentication_failover_permitted',False) and self.cfg['failover_permitted'] and bool(self.cfg['permission_reference'])
        auth_unavailable=False
        for index,slot in enumerate(candidates):
            group_name=self.cfg['key_slots'][slot]['quota_group']
            if index and (not self.cfg['failover_permitted'] or not self.cfg['permission_reference'] or group_name==first_group):continue
            budget=self.group(group_name)
            if budget.get('exhausted') or budget.get('remaining')==0 or (budget.get('allocation') is not None and budget.get('provider_used',0)>=budget['allocation']):
                self.note(slot,endpoint,'skipped_daily_quota')
                if index==0 and not self.cfg['failover_permitted']:raise QuotaExceeded('API account budget unavailable; cached data preserved, no key rotation')
                continue
            if budget['requests']>=self.cfg['daily_request_budget']:
                self.note(slot,endpoint,'local_request_ceiling');raise ProviderError('Safe local request ceiling reached; not a provider quota failover')
            slotstate=self.state['slots'].setdefault(slot,{})
            revision=self.cfg['credential_revision']
            if slotstate.get('revision')!=revision:slotstate.clear();slotstate['revision']=revision
            if slotstate.get('invalid_until') and self.now<local(slotstate['invalid_until']):
                self.note(slot,endpoint,'skipped_credential_cooldown',authentication_fallback_allowed=bool(auth_fallback and slotstate.get('failure_kind')=='authentication'))
                if auth_fallback and slotstate.get('failure_kind')=='authentication':
                    auth_unavailable=True;continue
                raise ProviderError('Primary credential unavailable; correct secret/revision before retrying')
            if budget.get('after') and self.now<local(budget['after']):
                self.note(slot,endpoint,'account_cooldown');raise ProviderError('API cooldown active; no key switching')
            try:
                if endpoint=='status':
                    cap=min(self.cfg['daily_request_budget'],max(0,budget.get('allocation',100)-self.cfg.get('daily_request_reserve',10)))
                    if budget['requests']>=cap:
                        self.note(slot,endpoint,'local_request_ceiling')
                        raise ProviderError('Safe account reserve reached; no quota rotation')
                if endpoint=='status' or budget.get('plan_checked')!=self.day or slotstate.get('plan_checked')!=self.day:
                    account=self._request(slot,budget,'status')
                    if not isinstance(account,dict):raise ProviderError('Invalid account status; raw response omitted')
                    subscription=account.get('subscription') or {};usage=account.get('requests') or {}
                    if str(subscription.get('plan','')).casefold()!='free' or subscription.get('active') is not True:
                        self.note(slot,'status','plan_not_authorised')
                        raise ProviderError('Only an active verified Free allocation is authorised')
                    for field in ('current','limit'):
                        if type(usage.get(field)) is not int or usage[field]<0:raise ProviderError('Account allowance could not be verified')
                    budget['requests']=max(budget['requests'],usage['current']);budget['allocation']=usage['limit']
                    budget['provider_used']=max(budget.get('provider_used',0),usage['current'])
                    budget['plan_checked']=self.day;slotstate['plan_checked']=self.day
                if endpoint=='status':
                    # The admitted request already succeeded and was validated. Even
                    # the final permitted status response is valid; make no more calls.
                    data=account
                else:
                    cap=min(self.cfg['daily_request_budget'],max(0,budget.get('allocation',100)-self.cfg.get('daily_request_reserve',10)))
                    if budget.get('allocation') is not None and budget.get('provider_used',0)>=budget['allocation']:raise QuotaExceeded('Verified account daily quota exhausted')
                    if budget['requests']>=cap:raise ProviderError('Safe account reserve reached; no quota rotation')
                    data=self._request(slot,budget,endpoint,params)
                self.active=slot
                self.state['last_successful_slot']=slot;self.state['last_successful_at']=self.at
                slotstate.pop('failure_kind',None);slotstate.pop('invalid_until',None)
                return data
            except AuthenticationRejected:
                slotstate['failure_kind']='authentication'
                slotstate['invalid_until']=(self.now+timedelta(hours=6)).isoformat()
                auth_unavailable=True
                self.note(slot,endpoint,'authentication_fallback' if auth_fallback else 'authentication_fallback_disabled')
                if not auth_fallback:raise
                continue
            except QuotaExceeded:
                budget['exhausted']=True;budget['remaining']=0;budget['exhausted_at']=self.now.isoformat()
                if budget.get('allocation') is not None:budget['requests']=max(budget['requests'],budget['allocation'])
                # Only a different provider-authorised quota allocation may follow.
                continue
        if auth_unavailable:raise AuthenticationRejected('Authorised API credentials unavailable; last successful data preserved; details omitted')
        raise QuotaExceeded('All permitted account allocations unavailable; last successful data preserved')

    def _request(self,slot,budget,endpoint,params=None):
        if budget['requests']>=self.cfg['daily_request_budget']:raise ProviderError('Safe local API request ceiling reached; no rotation')
        budget['requests']+=1
        self.note(slot,endpoint,'request_started')
        request=Request(self.BASE+'/'+endpoint+('?' + urlencode(params) if params else ''),
                        headers={'x-apisports-key':self.keys[slot],'Accept':'application/json'})
        try:
            with self.opener.open(request,timeout=25) as response:
                observed=self.now+timedelta(seconds=monotonic()-self.start)
                stamp=parsedate_to_datetime(response.headers.get('Date',''))
                if not -30<=(observed-stamp).total_seconds()<=self.cfg['max_source_age_seconds']:
                    self.note(slot,endpoint,'stale_timestamp')
                    raise ProviderError('Stale/missing API timestamp; no live observation used')
                self.at=stamp.isoformat()
                remaining=response.headers.get('x-ratelimit-requests-remaining')
                remaining_value=None
                if remaining is not None:
                    value=int(remaining)
                    if value<0:raise ProviderError('Invalid API quota header')
                    remaining_value=value
                raw=response.read(8*1024*1024+1)
                if len(raw)>8*1024*1024:raise ProviderError('API payload exceeds bounded response size')
                data=json.loads(raw)
        except HTTPError as error:
            self.note(slot,endpoint,'http_rejection',http_status=int(error.code))
            # An ordinary 429 is a minute/rate error, not proof of daily exhaustion.
            if error.code==429 and error.headers.get('x-ratelimit-requests-remaining')=='0':
                self.note(slot,endpoint,'daily_quota_rejected');budget['remaining']=0;raise QuotaExceeded('Documented daily quota exhausted') from None
            if error.code in (429,503):
                try:
                    retry=error.headers.get('Retry-After','300')
                    seconds=int(retry) if str(retry).isdigit() else int((parsedate_to_datetime(retry)-self.now).total_seconds())
                except (ValueError,TypeError,AttributeError):seconds=300
                budget['after']=(self.now+timedelta(seconds=max(300,min(seconds,86400)))).isoformat()
            if error.code==401:
                try:body=error.read(65536).decode('utf-8',errors='replace').casefold()
                except Exception:body=''
                if not any(term in body for term in ('suspend','banned','blocked','whitelist','ip address','ip restriction')):
                    self.note(slot,endpoint,'authentication_rejected')
                    raise AuthenticationRejected('API authentication rejected; credential details omitted') from None
            if error.code in (401,403):
                self.state['slots'][slot]['failure_kind']='access_restriction'
                self.state['slots'][slot]['invalid_until']=(self.now+timedelta(hours=6)).isoformat()
            raise ProviderError(f'API HTTP {error.code}; no ordinary-error key failover') from None
        except ProviderError:raise
        except Exception:
            self.note(slot,endpoint,'transport_or_invalid_response');raise ProviderError('API transport/response failure; no key switching; details omitted') from None
        if not isinstance(data,dict):raise ProviderError('Malformed API response wrapper')
        if data.get('errors'):
            self.note(slot,endpoint,rejection_category(data['errors']),error_fields=safe_error_fields(data['errors']),authentication_fallback_eligible=authentication_rejection(data['errors']))
            if daily_quota(data['errors'],remaining_value):
                budget['remaining']=0;raise QuotaExceeded('Documented daily quota exhausted')
            if authentication_rejection(data['errors']):raise AuthenticationRejected('API authentication rejected; credential details omitted')
            raise ProviderError(safe_error_reason(data['errors'],endpoint))
        if remaining is None and endpoint!='status':raise ProviderError('Missing account quota header; no unbudgeted data used')
        paging=data.get('paging') or {}
        if not isinstance(paging,dict) or paging.get('total',1)!=1:raise ProviderError('Incomplete/paginated API response rejected')
        if remaining_value is not None:
            budget['remaining']=remaining_value
            budget['provider_used']=max(budget.get('provider_used',0),budget.get('allocation',100)-remaining_value)
            budget['requests']=max(budget['requests'],budget['provider_used'])
        self.note(slot,endpoint,'response_received')
        return data.get('response')
